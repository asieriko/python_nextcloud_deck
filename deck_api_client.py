import requests
from requests.auth import HTTPBasicAuth

class DeckAPIClient:
    """
    Un cliente de Python para interactuar con la API de Nextcloud Deck.
    Se encarga exclusivamente de las peticiones HTTP.
    """
    def __init__(self, url, username, password):
        self.base_url = f"{url.rstrip('/')}/index.php/apps/deck/api/v1.0"
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(username, password)
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'OCS-APIRequest': 'true',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        # Lanza una petición inicial para verificar la conexión y las credenciales
        self.get_boards()

    def _api_request(self, method, endpoint, data=None):
        """Método auxiliar para realizar peticiones a la API."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.request(method, url, json=data)
        response.raise_for_status()  # Lanza una excepción para errores HTTP (4xx o 5xx)
        return response.json() if response.status_code != 204 else None

    # --- Métodos de la API ---
    def get_boards(self):
        return self._api_request('GET', 'boards')

    def get_stacks_with_cards(self, board_id):
        return self._api_request('GET', f'boards/{board_id}/stacks')

    def create_board(self, title, color):
        return self._api_request('POST', 'boards', data={'title': title, 'color': color})

    def create_stack(self, board_id, title):
        return self._api_request('POST', f'boards/{board_id}/stacks', data={'title': title})

    def create_card(self, board_id, stack_id, title):
        return self._api_request('POST', f'boards/{board_id}/stacks/{stack_id}/cards', data={'title': title})

    def update_card(self, board_id, stack_id, card_id, **kwargs):
        return self._api_request('PUT', f'boards/{board_id}/stacks/{stack_id}/cards/{card_id}', data=kwargs)

