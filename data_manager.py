import sqlite3
import json
import requests
import base64
from requests.auth import HTTPBasicAuth


class DataManager:
    """
    Gestiona todos los datos de la aplicación.
    CORREGIDO: Ahora es seguro para usar en múltiples hilos, ya que cada
    operación de base de datos crea su propia conexión.
    """

    def __init__(self, db_path='kanban_data.db'):
        self.db_path = db_path
        self._create_tables()
        self.session = None  # requests.Session, se inicializa al hacer login
        self.base_url = ""

    def _execute(self, query, params=(), commit=False, fetchone=False, fetchall=False):
        """
        Método auxiliar para ejecutar consultas SQL.
        Crea una conexión nueva y la cierra en cada llamada para ser thread-safe.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)

            result = None
            if fetchone:
                result = cursor.fetchone()
                if result:
                    result = dict(result)
            if fetchall:
                result = [dict(row) for row in cursor.fetchall()]

            if commit:
                conn.commit()

            return result
        finally:
            conn.close()

    def _create_tables(self):
        """Crea las tablas de la base de datos si no existen."""
        self._execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """, commit=True)
        self._execute("""
        CREATE TABLE IF NOT EXISTS boards (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            color TEXT
        )
        """, commit=True)
        self._execute("""
        CREATE TABLE IF NOT EXISTS stacks (
            id INTEGER PRIMARY KEY,
            board_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            FOREIGN KEY (board_id) REFERENCES boards (id) ON DELETE CASCADE
        )
        """, commit=True)
        self._execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY,
            stack_id INTEGER NOT NULL,
            board_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            duedate TEXT,
            labels_json TEXT
        )
        """, commit=True)
        self._execute("""
        CREATE TABLE IF NOT EXISTS offline_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            method TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            payload TEXT 
        )
        """, commit=True)

    # --- Gestión de Credenciales ---
    def save_credentials(self, url, username, password):
        """Guarda las credenciales de forma segura (ofuscada)."""
        self._execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('deck_url', url), commit=True)
        self._execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('username', username), commit=True)
        encoded_pass = base64.b64encode(password.encode()).decode()
        self._execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('password', encoded_pass),
                      commit=True)

    def load_credentials(self):
        """Carga las credenciales guardadas."""
        url_row = self._execute("SELECT value FROM settings WHERE key = ?", ('deck_url',), fetchone=True)
        username_row = self._execute("SELECT value FROM settings WHERE key = ?", ('username',), fetchone=True)
        encoded_pass_row = self._execute("SELECT value FROM settings WHERE key = ?", ('password',), fetchone=True)

        if not all([url_row, username_row, encoded_pass_row]):
            return None

        password = base64.b64decode(encoded_pass_row['value']).decode()
        return {'url': url_row['value'], 'username': username_row['value'], 'password': password}

    def attempt_login(self, url, username, password):
        """Intenta conectar con la API usando las credenciales."""
        self.base_url = f"{url.rstrip('/')}/index.php/apps/deck/api/v1.0"
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(username, password)
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'OCS-APIRequest': 'true',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        try:
            self._api_request('GET', 'boards')
            self.save_credentials(url, username, password)
            return True
        except (requests.exceptions.RequestException, requests.exceptions.HTTPError):
            self.session = None
            return False

    def is_online(self):
        return self.session is not None

    # --- API y Sincronización ---
    def _api_request(self, method, endpoint, data=None):
        if not self.is_online():
            self._queue_offline_change(method, endpoint, data)
            return None

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.request(method, url, json=data)
        response.raise_for_status()
        return response.json() if response.status_code != 204 else None

    def _queue_offline_change(self, method, endpoint, payload):
        if method.upper() in ['POST', 'PUT', 'DELETE']:
            self._execute(
                "INSERT INTO offline_changes (method, endpoint, payload) VALUES (?, ?, ?)",
                (method.upper(), endpoint, json.dumps(payload)),
                commit=True
            )

    def sync_offline_changes(self):
        if not self.is_online(): return 0
        changes = self._execute("SELECT * FROM offline_changes ORDER BY id", fetchall=True)
        synced_count = 0
        for change in changes:
            try:
                self._api_request(
                    change['method'],
                    change['endpoint'],
                    json.loads(change['payload']) if change['payload'] else None
                )
                self._execute("DELETE FROM offline_changes WHERE id = ?", (change['id'],), commit=True)
                synced_count += 1
            except requests.exceptions.RequestException as e:
                print(f"Error al sincronizar cambio {change['id']}: {e}")
                break
        return synced_count

    # --- Métodos de Datos ---
    def get_boards(self):
        if self.is_online():
            try:
                boards_from_api = self._api_request('GET', 'boards')
                self._execute("DELETE FROM boards", commit=True)
                if boards_from_api:
                    for board in boards_from_api:
                        self._execute("INSERT OR REPLACE INTO boards (id, title, color) VALUES (?, ?, ?)",
                                      (board['id'], board['title'], board.get('color')), commit=True)
            except requests.exceptions.RequestException as e:
                print(f"No se pudo sincronizar tableros: {e}")
        return self._execute("SELECT * FROM boards", fetchall=True)

    def get_stacks(self, board_id):
        if self.is_online():
            try:
                stacks_from_api = self._api_request('GET', f'boards/{board_id}/stacks')
                self._execute("DELETE FROM stacks WHERE board_id = ?", (board_id,), commit=True)
                self._execute("DELETE FROM cards WHERE board_id = ?", (board_id,), commit=True)
                if stacks_from_api:
                    for stack in stacks_from_api:
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
            except requests.exceptions.RequestException as e:
                print(f"No se pudo sincronizar pilas/tarjetas: {e}")
        return self._execute("SELECT * FROM stacks WHERE board_id = ?", (board_id,), fetchall=True)

    def get_cards(self, board_id, stack_id):
        # --- INICIO DE LA MODIFICACIÓN ---
        print(f"[DATA_MANAGER] Buscando tarjetas en la BD para stack_id: {stack_id}")
        cards = self._execute("SELECT * FROM cards WHERE stack_id = ?", (stack_id,), fetchall=True)
        print(f"[DATA_MANAGER] Encontradas {len(cards) if cards else 0} tarjetas para stack_id: {stack_id}")
        return cards
        # --- FIN DE LA MODIFICACIÓN ---

    def create_board(self, title, color):
        self._api_request('POST', 'boards', data={'title': title, 'color': color})

    def create_stack(self, board_id, title):
        self._api_request('POST', f'boards/{board_id}/stacks', data={'title': title})

    def create_card(self, board_id, stack_id, title):
        self._api_request('POST', f'boards/{board_id}/stacks/{stack_id}/cards', data={'title': title})

    def update_card(self, board_id, stack_id, card_id, **kwargs):
        self._api_request('PUT', f'boards/{board_id}/stacks/{stack_id}/cards/{card_id}', data=kwargs)

