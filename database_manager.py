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
                # --- CORRECCIÓN ---
                # Se llama a fetchone() una sola vez y se guarda el resultado
                row = cursor.fetchone()
                if row:
                    result = dict(row)
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
        self._execute(
            "CREATE TABLE IF NOT EXISTS stacks (id INTEGER PRIMARY KEY, board_id INTEGER NOT NULL, title TEXT NOT NULL, FOREIGN KEY (board_id) REFERENCES boards (id) ON DELETE CASCADE)",
            commit=True)
        self._execute(
            "CREATE TABLE IF NOT EXISTS cards (id INTEGER PRIMARY KEY, stack_id INTEGER NOT NULL, board_id INTEGER NOT NULL, title TEXT NOT NULL, description TEXT, duedate TEXT, labels_json TEXT)",
            commit=True)
        self._execute(
            "CREATE TABLE IF NOT EXISTS offline_changes (id INTEGER PRIMARY KEY AUTOINCREMENT, method TEXT NOT NULL, endpoint TEXT NOT NULL, payload TEXT)",
            commit=True)

    # --- Credenciales ---
    def save_credentials(self, url, username, password):
        encoded_pass = base64.b64encode(password.encode()).decode()
        # Usar múltiples sentencias para claridad y compatibilidad
        self._execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('deck_url', url), commit=True)
        self._execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('username', username), commit=True)
        self._execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('password', encoded_pass),
                      commit=True)

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
                self._execute("INSERT OR REPLACE INTO stacks (id, board_id, title) VALUES (?, ?, ?)",
                              (stack['id'], board_id, stack['title']), commit=True)
                cards_from_stack = stack.get('cards', [])
                if cards_from_stack:
                    for card in cards_from_stack:
                        self._execute(
                            "INSERT OR REPLACE INTO cards (id, stack_id, board_id, title, description, duedate, labels_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (card['id'], stack['id'], board_id, card['title'], card.get('description'),
                             card.get('duedate'), json.dumps(card.get('labels', []))),
                            commit=True
                        )

    def get_stacks(self, board_id):
        return self._execute("SELECT * FROM stacks WHERE board_id = ?", (board_id,), fetchall=True)

    def get_cards(self, stack_id):
        return self._execute("SELECT * FROM cards WHERE stack_id = ?", (stack_id,), fetchall=True)

    # --- Cambios Offline ---
    def queue_offline_change(self, method, endpoint, payload):
        self._execute("INSERT INTO offline_changes (method, endpoint, payload) VALUES (?, ?, ?)",
                      (method.upper(), endpoint, json.dumps(payload)), commit=True)

    def get_offline_changes(self):
        return self._execute("SELECT * FROM offline_changes ORDER BY id", fetchall=True)

    def delete_offline_change(self, change_id):
        self._execute("DELETE FROM offline_changes WHERE id = ?", (change_id,), commit=True)

