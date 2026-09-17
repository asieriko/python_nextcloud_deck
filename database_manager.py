import sqlite3
import json
import base64


class DatabaseManager:
    """
    Gestiona todas las operaciones de la base de datos local (SQLite).
    Es seguro para usar en múltiples hilos.
    """

    def __init__(self, db_path='kanban_data.db'):
        self.db_path = db_path
        self._create_tables()

    def _execute(self, query, params=(), commit=False, fetchone=False, fetchall=False):
        """
        Ejecuta consultas SQL, creando una conexión nueva en cada llamada
        para ser seguro en entornos multihilo.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            result = None
            if fetchone:
                # Corregido: Llamar a fetchone solo una vez
                row = cursor.fetchone()
                result = dict(row) if row else None
            if fetchall:
                result = [dict(row) for row in cursor.fetchall()]
            if commit:
                conn.commit()
            return result
        finally:
            conn.close()

    def _create_tables(self):
        self._execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)", commit=True)
        self._execute("CREATE TABLE IF NOT EXISTS boards (id INTEGER PRIMARY KEY, title TEXT NOT NULL, color TEXT)",
                      commit=True)
        # --- CAMBIO --- Se añade la columna "order" a la tabla de stacks
        self._execute(
            "CREATE TABLE IF NOT EXISTS stacks (id INTEGER PRIMARY KEY, board_id INTEGER NOT NULL, title TEXT NOT NULL, \"order\" INTEGER, FOREIGN KEY (board_id) REFERENCES boards (id) ON DELETE CASCADE)",
            commit=True)
        self._execute(
            "CREATE TABLE IF NOT EXISTS cards (id INTEGER PRIMARY KEY, stack_id INTEGER NOT NULL, board_id INTEGER NOT NULL, title TEXT NOT NULL, description TEXT, duedate TEXT, labels_json TEXT, owner TEXT)",
            commit=True)
        # Ensure owner column exists (for existing DBs)
        try:
            self._execute("ALTER TABLE cards ADD COLUMN owner TEXT", commit=True)
        except Exception:
            pass  # Column already exists
        self._execute(
            "CREATE TABLE IF NOT EXISTS offline_changes (id INTEGER PRIMARY KEY AUTOINCREMENT, method TEXT NOT NULL, endpoint TEXT NOT NULL, payload TEXT)",
            commit=True)

    # --- Credenciales ---
    def save_credentials(self, url, username, password):
        encoded_pass = base64.b64encode(password.encode()).decode()
        self._execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?), (?, ?), (?, ?)",
                      ('deck_url', url, 'username', username, 'password', encoded_pass), commit=True)

    def load_credentials(self):
        creds = {}
        for key in ['deck_url', 'username', 'password']:
            row = self._execute("SELECT value FROM settings WHERE key = ?", (key,), fetchone=True)
            creds[key] = row['value'] if row else None

        if not all(creds.values()):
            return None

        return {
            'url': creds['deck_url'],
            'username': creds['username'],
            'password': base64.b64decode(creds['password']).decode()
        }

    # --- Operaciones de Datos ---
    def save_boards(self, boards):
        self._execute("DELETE FROM boards", commit=True)
        if boards:
            for board in boards:
                self._execute("INSERT OR REPLACE INTO boards (id, title, color) VALUES (?, ?, ?)",
                              (board['id'], board['title'], board.get('color')), commit=True)

    def get_boards(self):
        return self._execute("SELECT * FROM boards", fetchall=True)

    def save_stacks_and_cards(self, board_id, stacks):
        self._execute("DELETE FROM stacks WHERE board_id = ?", (board_id,), commit=True)
        self._execute("DELETE FROM cards WHERE board_id = ?", (board_id,), commit=True)
        if stacks:
            for stack in stacks:
                # --- CAMBIO --- Se guarda el valor de "order"
                self._execute("INSERT OR REPLACE INTO stacks (id, board_id, title, \"order\") VALUES (?, ?, ?, ?)",
                              (stack['id'], board_id, stack['title'], stack.get('order')), commit=True)
                cards_from_stack = stack.get('cards', [])
                if cards_from_stack:
                    for card in cards_from_stack:
                        # Extract owner: API may return it as dict {uid:...} or string
                        owner = card.get('owner')
                        if isinstance(owner, dict):
                            owner = owner.get('uid') or owner.get('username')
                        
                        self._execute(
                            "INSERT OR REPLACE INTO cards (id, stack_id, board_id, title, description, duedate, labels_json, owner) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (card['id'], stack['id'], board_id, card['title'], card.get('description'),
                             card.get('duedate'), json.dumps(card.get('labels', [])), owner),
                            commit=True
                        )

    def get_stacks(self, board_id):
        return self._execute("SELECT * FROM stacks WHERE board_id = ?", (board_id,), fetchall=True)

    def get_cards(self, stack_id):
        return self._execute("SELECT * FROM cards WHERE stack_id = ?", (stack_id,), fetchall=True)

    def get_card_by_id(self, card_id):
        return self._execute("SELECT * FROM cards WHERE id = ?", (card_id,), fetchone=True)

    def save_card(self, card):
        owner = card.get('owner')
        if isinstance(owner, dict):
            owner = owner.get('uid') or owner.get('username')

        labels_json = card.get('labels_json')
        if labels_json is None and card.get('labels') is not None:
            labels_json = json.dumps(card.get('labels', []))

        self._execute(
            "INSERT OR REPLACE INTO cards (id, stack_id, board_id, title, description, duedate, labels_json, owner) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                card['id'],
                card['stack_id'],
                card['board_id'],
                card['title'],
                card.get('description'),
                card.get('duedate'),
                labels_json,
                owner,
            ),
            commit=True,
        )

    def rename_card_id(self, old_id, new_id):
        self._execute("UPDATE cards SET id = ? WHERE id = ?", (new_id, old_id), commit=True)

    # --- Cambios Offline ---
    def queue_offline_change(self, method, endpoint, payload):
        # Sanitize payload before queuing to avoid API validation errors (e.g., color with leading '#')
        if isinstance(payload, dict) and 'color' in payload and payload.get('color') is not None:
            color = str(payload.get('color'))
            clean_color = color.lstrip('#')[:6].lower()
            payload = dict(payload)
            payload['color'] = clean_color

        # store payload as JSON (or NULL if no payload)
        payload_json = json.dumps(payload) if payload is not None else None
        self._execute("INSERT INTO offline_changes (method, endpoint, payload) VALUES (?, ?, ?)",
                      (method.upper(), endpoint, payload_json), commit=True)

    def get_offline_changes(self):
        return self._execute("SELECT * FROM offline_changes ORDER BY id", fetchall=True)

    def delete_offline_change(self, change_id):
        self._execute("DELETE FROM offline_changes WHERE id = ?", (change_id,), commit=True)
