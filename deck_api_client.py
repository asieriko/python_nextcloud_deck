import requests
from requests.auth import HTTPBasicAuth
import json


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
        # Debug: print outgoing request
        try:
            print("\n--- PETICIÓN SALIENTE ---")
            print(f"Petición: {method} {url}")
            print(f"Headers: {self.session.headers}")
            if data is not None:
                try:
                    print("Payload:", json.dumps(data, ensure_ascii=False))
                except Exception:
                    print("Payload (repr):", repr(data))
            else:
                print("Payload: None")
        except Exception:
            pass

        response = self.session.request(method, url, json=data)

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print("\n--- DETALLES DEL ERROR HTTP ---")
            print(f"Petición: {method} {url}")
            print(f"Código de Estado: {response.status_code}")
            print(f"Respuesta del Servidor: {response.text}")
            print("-----------------------------\n")
            raise e

        return response.json() if response.status_code != 204 else None

    # --- Métodos de la API ---
    def get_boards(self):
        return self._api_request('GET', 'boards')

    def get_stacks_with_cards(self, board_id):
        return self._api_request('GET', f'boards/{board_id}/stacks')

    def create_board(self, title, color):
        # sanitize color: Deck expects hex without leading '#' and max 6 chars
        if color is not None:
            clean_color = color.lstrip('#')[:6].lower()
            payload = {'title': title, 'color': clean_color}
        else:
            payload = {'title': title}
        return self._api_request('POST', 'boards', data=payload)

    def create_stack(self, board_id, title, order):
        return self._api_request('POST', f'boards/{board_id}/stacks', data={'title': title, 'order': order})

    def create_card(self, board_id, stack_id, title, order):
        return self._api_request('POST', f'boards/{board_id}/stacks/{stack_id}/cards',
                                 data={'title': title, 'order': order})

    def update_card(self, board_id, stack_id, card_id, **kwargs):
        # Ensure 'type' is present; fetch existing card if necessary
        if not kwargs.get('type'):
            try:
                existing = self._api_request('GET', f'boards/{board_id}/stacks/{stack_id}/cards/{card_id}')
                if existing and isinstance(existing, dict) and 'type' in existing:
                    kwargs['type'] = existing['type']
                else:
                    kwargs['type'] = 'plain'  # API expects string 'plain'
            except requests.exceptions.RequestException:
                # couldn't fetch existing, ensure non-empty type to avoid API error
                kwargs['type'] = 'plain'
        return self._api_request('PUT', f'boards/{board_id}/stacks/{stack_id}/cards/{card_id}', data=kwargs)

    def delete_stack(self, board_id, stack_id):
        """Envía una petición DELETE para eliminar una pila."""
        return self._api_request('DELETE', f'boards/{board_id}/stacks/{stack_id}')

