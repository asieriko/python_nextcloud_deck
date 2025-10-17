import requests
import json
from deck_api_client import DeckAPIClient
from database_manager import DatabaseManager


class DataManager:
    """
    Actúa como un orquestador entre el cliente de la API y el gestor de la base de datos.
    Contiene la lógica de negocio para la sincronización y el modo offline.
    """

    def __init__(self, db_path='kanban_data.db'):
        self.db = DatabaseManager(db_path)
        self.api = None

    def attempt_login(self, url, username, password):
        """Intenta crear un cliente de API y conectar."""
        try:
            self.api = DeckAPIClient(url, username, password)
            self.db.save_credentials(url, username, password)
            return True
        except (requests.exceptions.RequestException, requests.exceptions.HTTPError):
            self.api = None
            return False

    def load_credentials(self):
        return self.db.load_credentials()

    def is_online(self):
        return self.api is not None

    def sync_offline_changes(self):
        if not self.is_online():
            return 0

        changes = self.db.get_offline_changes()
        synced_count = 0
        for change in changes:
            try:
                print(f"Sincronizando: {change['method']} {change['endpoint']}")
                self.api._api_request(
                    change['method'],
                    change['endpoint'],
                    json.loads(change['payload']) if change['payload'] else None
                )
                self.db.delete_offline_change(change['id'])
                synced_count += 1
            except requests.exceptions.RequestException as e:
                print(f"Error al sincronizar cambio {change['id']}: {e}")
                break
        return synced_count

    # --- Métodos de Datos con Lógica de Sincronización ---
    def get_boards(self):
        if self.is_online():
            try:
                boards_from_api = self.api.get_boards()
                self.db.save_boards(boards_from_api)
            except requests.exceptions.RequestException as e:
                print(f"No se pudo sincronizar tableros: {e}")
        return self.db.get_boards()

    def get_stacks(self, board_id):
        if self.is_online():
            try:
                stacks_from_api = self.api.get_stacks_with_cards(board_id)
                self.db.save_stacks_and_cards(board_id, stacks_from_api)
            except requests.exceptions.RequestException as e:
                print(f"No se pudo sincronizar pilas/tarjetas: {e}")
        return self.db.get_stacks(board_id)

    def get_cards(self, board_id, stack_id):
        return self.db.get_cards(stack_id)

    # --- Métodos de Creación/Actualización ---
    def _execute_or_queue(self, method, endpoint, payload):
        if self.is_online():
            try:
                return self.api._api_request(method, endpoint, payload)
            except requests.exceptions.RequestException as e:
                print(
                    f"La acción API falló. Revisa los 'DETALLES DEL ERROR HTTP' impresos arriba. El cambio se encolará para reintentar más tarde. Error: {e}")
                self.db.queue_offline_change(method, endpoint, payload)
                return None
        else:
            self.db.queue_offline_change(method, endpoint, payload)
            return None

    def create_board(self, title, color):
        return self._execute_or_queue('POST', 'boards', {'title': title, 'color': color})

    def create_stack(self, board_id, title):
        # --- CAMBIO ---
        # Calcular el nuevo 'order' para la pila
        stacks = self.db.get_stacks(board_id)
        if stacks:
            # Encuentra el 'order' máximo y le suma 1. Usa 0 como default si una pila no tuviera 'order'.
            max_order = max(s.get('order', 0) for s in stacks if s.get('order') is not None) if any(
                s.get('order') is not None for s in stacks) else 0
            new_order = max_order + 1
        else:
            new_order = 1

        payload = {'title': title, 'order': new_order}
        return self._execute_or_queue('POST', f'boards/{board_id}/stacks', payload)

    def create_card(self, board_id, stack_id, title):
        # Calcular el nuevo 'order' para la tarjeta
        cards = self.db.get_cards(stack_id)
        if cards:
            max_order = max(c.get('order', 0) for c in cards if c.get('order') is not None) if any(
                c.get('order') is not None for c in cards) else 0
            new_order = max_order + 1
        else:
            new_order = 1

        payload = {'title': title, 'order': new_order}
        return self._execute_or_queue('POST', f'boards/{board_id}/stacks/{stack_id}/cards', payload)

    def update_card(self, board_id, stack_id, card_id, **kwargs):
        return self._execute_or_queue('PUT', f'boards/{board_id}/stacks/{stack_id}/cards/{card_id}', kwargs)

