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
        self.current_username = None

    def attempt_login(self, url, username, password):
        """Intenta crear un cliente de API y conectar."""
        try:
            self.api = DeckAPIClient(url, username, password)
            self.db.save_credentials(url, username, password)
            self.current_username = username
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
            payload = json.loads(change['payload']) if change['payload'] else None
            print(f"Sincronizando: {change['method']} {change['endpoint']}")

            # Ensure card payloads include required fields (defensive: double-check here)
            try:
                if isinstance(payload, dict):
                    parts = change['endpoint'].split('/') if change['endpoint'] else []
                    if len(parts) >= 5 and parts[0] == 'boards' and parts[2] == 'stacks' and parts[4].startswith('cards'):
                        card_id = None
                        try:
                            card_id = int(parts[5]) if len(parts) > 5 else None
                        except Exception:
                            card_id = None

                        existing_card = self.db.get_card_by_id(card_id) if card_id is not None else None

                        # For POST/PUT ensure 'type' and 'owner' exist
                        if change['method'].upper() in ('POST', 'PUT'):
                            if not payload.get('title') and existing_card and existing_card.get('title'):
                                payload['title'] = existing_card['title']
                            if not payload.get('type'):
                                payload['type'] = 'plain'
                            if not payload.get('owner'):
                                if existing_card and existing_card.get('owner'):
                                    payload['owner'] = existing_card['owner']
                                elif self.current_username:
                                    payload['owner'] = self.current_username
            except Exception:
                pass

            # show payload after normalization for debugging
            try:
                print("Payload to send:", json.dumps(payload, ensure_ascii=False) if payload is not None else 'None')
            except Exception:
                print("Payload to send (repr):", repr(payload))

            # Use _execute_or_queue so any additional normalization or queuing logic is applied
            res = self._execute_or_queue(change['method'], change['endpoint'], payload)
            if res is not None:
                # Successfully sent to API, remove from queue
                self.db.delete_offline_change(change['id'])
                synced_count += 1
            else:
                # If it failed and was re-queued by _execute_or_queue, stop to retry later
                print(f"Error al sincronizar cambio {change['id']}: quedó en cola o falló.")
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

    # --- Métodos de Creación/Actualización/Eliminación ---
    def _execute_or_queue(self, method, endpoint, payload):
        # Normalize payload for card endpoints: Deck requires 'type' and 'owner' present for card POST/PUT
        try:
            if isinstance(payload, dict) and endpoint and ('/boards/' in endpoint or endpoint.startswith('boards')):
                # endpoints for cards look like 'boards/{board_id}/stacks/{stack_id}/cards' or 'boards/{board_id}/stacks/{stack_id}/cards/{card_id}'
                parts = endpoint.split('/')
                if len(parts) >= 5 and parts[0] == 'boards' and parts[2] == 'stacks' and parts[4].startswith('cards'):
                    if method.upper() in ('POST', 'PUT'):
                        payload = dict(payload)
                        # ensure 'type' exists and is non-empty
                        if not payload.get('type'):
                            payload['type'] = 'plain'
                        # ensure 'owner' exists and is non-empty
                        if not payload.get('owner') and self.current_username:
                            payload['owner'] = self.current_username
        except Exception:
            # be conservative: don't fail here
            pass

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
        stacks = self.db.get_stacks(board_id)
        if stacks:
            max_order = max(s.get('order', 0) for s in stacks if s.get('order') is not None) if any(
                s.get('order') is not None for s in stacks) else 0
            new_order = max_order + 1
        else:
            new_order = 1

        payload = {'title': title, 'order': new_order}
        return self._execute_or_queue('POST', f'boards/{board_id}/stacks', payload)

    def create_card(self, board_id, stack_id, title, **kwargs):
        cards = self.db.get_cards(stack_id)
        if cards:
            max_order = max(c.get('order', 0) for c in cards if c.get('order') is not None) if any(
                c.get('order') is not None for c in cards) else 0
            new_order = max_order + 1
        else:
            new_order = 1

        payload = {'title': title, 'order': new_order}
        # include additional optional fields such as description, duedate, type
        if kwargs:
            payload.update(kwargs)
        # Ensure owner is set for new cards
        if not payload.get('owner') and self.current_username:
            payload['owner'] = self.current_username
        return self._execute_or_queue('POST', f'boards/{board_id}/stacks/{stack_id}/cards', payload)

    def update_card(self, board_id, stack_id, card_id, new_stack_id=None, **kwargs):
        """Update card. new_stack_id can be provided to move the card to another stack.
        Keeps backward compatibility with callers that pass arbitrary kwargs for card fields.
        Preserves existing fields from DB if not provided.
        """
        # Fetch existing card to preserve required fields and get owner
        try:
            existing_card = self.db.get_card_by_id(card_id)
            if not existing_card:
                cards = self.db.get_cards(stack_id)
                existing_card = next((c for c in cards if c['id'] == card_id), None)
            if existing_card:
                # Start with existing fields, then override with kwargs
                payload = {
                    'title': existing_card.get('title'),
                    'description': existing_card.get('description', ''),
                    'duedate': existing_card.get('duedate'),
                    'owner': existing_card.get('owner'),
                }
                # Override with provided kwargs
                payload.update(kwargs)
            else:
                # Fallback: just use kwargs, but ensure title (caller should provide it)
                payload = dict(kwargs)
                if not payload.get('owner') and self.current_username:
                    payload['owner'] = self.current_username
        except Exception:
            # Fallback: just use kwargs
            payload = dict(kwargs)
            if not payload.get('owner') and self.current_username:
                payload['owner'] = self.current_username

        if not payload.get('title'):
            try:
                existing_card = self.db.get_card_by_id(card_id)
                if existing_card and existing_card.get('title'):
                    payload['title'] = existing_card['title']
            except Exception:
                pass

        if new_stack_id is not None:
            # map to payload 'stack_id' expected by the API without conflicting with positional arg
            payload['stack_id'] = new_stack_id
        
        return self._execute_or_queue('PUT', f'boards/{board_id}/stacks/{stack_id}/cards/{card_id}', payload)

    def delete_stack(self, board_id, stack_id):
        """Orquesta la eliminación de una pila."""
        return self._execute_or_queue('DELETE', f'boards/{board_id}/stacks/{stack_id}', payload=None)
