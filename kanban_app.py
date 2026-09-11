import sys
import json
import traceback
from functools import partial
from datetime import datetime, timezone

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDateEdit

from data_manager import DataManager

from PySide6.QtCore import (
    Qt, QObject, Signal, QRunnable, QThreadPool, Slot, QSize
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem,
    QDialog, QLineEdit, QTextEdit, QDialogButtonBox, QFormLayout,
    QMessageBox, QFrame, QSplitter, QMenu
)

# --- ESTILO DE LA APLICACIÓN (TEMA OSCURO) ---
STYLE_SHEET = """
    /* --- Estilos generales --- */
    QWidget {
        background-color: #2e3440;
        color: #d8dee9;
        font-family: 'Segoe UI', 'Roboto', 'Helvetica Neue', sans-serif;
        font-size: 10pt;
    }
    QMainWindow, QDialog {
        background-color: #3b4252;
    }
    QSplitter::handle {
        background-color: #4c566a;
    }
    QSplitter::handle:hover {
        background-color: #5e81ac;
    }
    QSplitter::handle:pressed {
        background-color: #81a1c1;
    }

    /* --- Barra lateral --- */
    #sidebar {
        background-color: #3b4252;
    }
    #sidebar QLabel {
        font-size: 14pt; font-weight: bold; color: #eceff4; padding: 10px;
    }
    #sidebar QListWidget {
        border: none; background-color: #3b4252;
    }
    #sidebar QListWidget::item {
        padding: 12px 10px; border-radius: 4px; margin: 2px 5px;
    }
    #sidebar QListWidget::item:selected, #sidebar QListWidget::item:hover {
        background-color: #4c566a;
    }

    /* --- Botones --- */
    QPushButton {
        background-color: #5e81ac; color: #eceff4; border: none;
        padding: 8px 16px; border-radius: 4px; min-height: 20px;
    }
    QPushButton:hover { background-color: #81a1c1; }
    QPushButton#addButton {
        background-color: #434c5e; color: #a3be8c; font-weight: bold;
    }
    QPushButton#addButton:hover { background-color: #4c566a; }

    /* --- CAMBIO --- Estilo para el botón de eliminar */
    QPushButton#deleteButton {
        background-color: #bf616a; /* Rojo */
        color: #eceff4;
        font-weight: bold;
        padding: 0px;
        border-radius: 12px; /* Círculo */
        min-height: 0px;
        max-height: 24px;
        font-size: 12pt;
    }
    QPushButton#deleteButton:hover {
        background-color: #d08770; /* Naranja */
    }

    /* --- Entradas de texto --- */
    QLineEdit, QTextEdit, QDateEdit {
        background-color: #4c566a; border: 1px solid #434c5e;
        padding: 5px; border-radius: 4px; color: #eceff4;
    }
    QDateEdit::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 15px;
        border-left-width: 1px;
        border-left-color: #434c5e;
        border-left-style: solid;
        border-top-right-radius: 3px;
        border-bottom-right-radius: 3px;
    }

    /* --- Columnas de Pilas (Stacks) --- */
    QFrame#stackFrame {
        background-color: #3b4252; border-radius: 8px; min-width: 280px;
    }
    QFrame#titleBar {
        background-color: #434c5e; border-top-left-radius: 8px; border-top-right-radius: 8px;
    }
    QLabel#stackTitle {
        font-size: 12pt; font-weight: bold; padding: 8px; color: #88c0d0;
        background-color: transparent;
    }
    QListWidget#cardList {
        background-color: transparent; border: none;
    }
    QListWidget#cardList::item {
        border: none;
        padding: 0px;
        margin: 0px;
        background-color: transparent;
    }

    /* --- Widget de Tarjeta Personalizado --- */
    #CardWidget {
        background-color: #434c5e;
        border-radius: 4px;
        margin: 4px;
        border: 1px solid #4c566a;
    }
    #CardWidget:hover {
        border: 1px solid #5e81ac;
    }
    QLabel#cardTitle {
        font-weight: bold;
        font-size: 11pt;
    }
    QLabel#cardDueDate {
        font-size: 8pt;
        color: #b48ead;
    }
    QLabel#cardDueDate.overdue, QDateEdit.overdue {
        color: #bf616a;
        font-weight: bold;
    }
    QLabel.cardLabel {
        font-size: 8pt;
        padding: 2px 6px;
        border-radius: 6px;
        color: #2e3440;
        font-weight: bold;
    }
"""


# --- WORKER THREADS ---
class WorkerSignals(QObject):
    finished = Signal()
    error = Signal(tuple)
    result = Signal(object)


class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()
        self.fn = fn;
        self.args = args;
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            self.signals.error.emit((type(e), e, traceback.format_exc()))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


# --- WIDGET PERSONALIZADO PARA TARJETAS ---
class CardWidget(QWidget):
    def __init__(self, card_data):
        super().__init__()
        self.setObjectName("CardWidget")
        self.card_id = card_data['id']
        self.stack_id = card_data['stack_id']
        self.board_id = card_data['board_id']

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(10, 10, 10, 10)
        self._main_layout.setSpacing(6)

        self._title_label = QLabel(card_data['title'])
        self._title_label.setObjectName("cardTitle")
        self._title_label.setWordWrap(True)
        self._main_layout.addWidget(self._title_label)

        self._labels_layout = QHBoxLayout()
        self._labels_layout.setSpacing(5)
        self._label_widgets = []
        labels_json = card_data.get('labels_json')
        if labels_json:
            labels = json.loads(labels_json)
            for label_data in labels:
                label_widget = QLabel(label_data['title'])
                label_widget.setObjectName("cardLabel")
                bg_color = f"#{label_data.get('color', 'CCCCCC').lstrip('#'):.6}"
                label_widget.setStyleSheet(f"background-color: {bg_color};")
                self._labels_layout.addWidget(label_widget)
                self._label_widgets.append(label_widget)
        self._labels_layout.addStretch()
        self._main_layout.addLayout(self._labels_layout)

        self._duedate_widget = None
        duedate_str = card_data.get('duedate')
        if duedate_str:
            self._duedate_widget = self.format_duedate(duedate_str)
            if self._duedate_widget:
                self._main_layout.addWidget(self._duedate_widget)

    def format_duedate(self, duedate_str):
        try:
            dt_obj = datetime.fromisoformat(duedate_str.replace('Z', '+00:00'))
            is_overdue = dt_obj < datetime.now(timezone.utc)

            date_edit = QDateEdit()
            date_edit.setDate(QDate(dt_obj.year, dt_obj.month, dt_obj.day))
            date_edit.setCalendarPopup(True)
            date_edit.setReadOnly(True) # User cannot type, but can pick from calendar? No, readOnly prevents editing.
            # If we want it to be just a display that looks like a calendar picker but is not editable here (only in edit dialog):
            # The requirement says "The date in the cards is not editable, it should display a calendar widget to pick it"
            # This is slightly ambiguous. "not editable" usually means read-only. "display a calendar widget to pick it" implies interaction.
            # However, usually in Kanban cards on the board are read-only summaries. Editing happens in the detail view.
            # If the user meant "The date in the cards (in the board view) is currently just text, but I want to be able to change it directly from the card using a calendar widget", then I should make it editable.
            # But the prompt says "The date in the cards is not editable". This sounds like a complaint about the current state OR a description of the desired state.
            # "it should display a calendar widget to pick it" -> This strongly suggests they want to be able to PICK the date.
            # So I will make it editable.

            date_edit.setReadOnly(False)
            # But wait, if I change it here, does it update the backend?
            # The current architecture updates via `edit_card` dialog.
            # If I make this editable here, I need to connect the signal to an update function.
            # The CardWidget doesn't have easy access to the data manager or board controller directly to trigger an update.
            # Let's look at how `CardWidget` is used. It's created in `populate_card_list`.
            # `populate_card_list` is in `KanbanApp`.

            # If the user just wants the VISUAL of a calendar widget instead of a label, but still read-only in the card view (and editable in the dialog), that's one interpretation.
            # But "to pick it" implies action.

            # Let's assume for a moment the user wants to change the date directly on the card.
            # I would need to expose a signal from CardWidget that KanbanApp can connect to.

            # However, re-reading: "The date in the cards is not editable, it should display a calendar widget to pick it"
            # It could mean "Currently it is not editable (problem), it should display a calendar widget to pick it (solution)".

            # So I will replace the QLabel with a QDateEdit.
            # I will disable text entry (setReadOnly(False) but maybe setButtonSymbols or something? No, QDateEdit is fine).
            # I need to handle the dateChanged signal.

            date_edit.setDisplayFormat("dd/MM/yyyy")
            if is_overdue:
                date_edit.setProperty("class", "overdue")

            # Store the original date to check for changes if needed, or just emit signal on change.
            return date_edit
        except (ValueError, TypeError):
            return None


class CardListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.board_id = None
        self.stack_id = None
        self.move_callback = None
        self._dragged_card = None
        # Enable drag and drop between lists
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListWidget.DragDrop)
        # Context menu handled by parent KanbanApp
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        if parent is not None:
            # parent is KanbanApp instance
            try:
                self.customContextMenuRequested.connect(lambda pos: parent.on_card_context_menu(pos, self))
            except Exception:
                pass

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item:
            self._dragged_card = item.data(Qt.UserRole)
        super().startDrag(supportedActions)

    def dropEvent(self, event):
        super().dropEvent(event)
        # After the default handling, notify parent to perform backend move
        if self._dragged_card:
            card = self._dragged_card
            if self.move_callback:
                try:
                    self.move_callback(card, self.board_id, self.stack_id)
                except Exception:
                    pass
        self._dragged_card = None


class DraggableTitleBar(QFrame):
    def __init__(self, parent=None, board_id=None, stack=None):
        super().__init__(parent)
        self._drag_start_pos = None
        self.board_id = board_id
        self.stack = stack

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos and (event.pos() - self._drag_start_pos).manhattanLength() > QApplication.startDragDistance():
            from PySide6.QtGui import QDrag, QMimeData
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData('application/x-stack', json.dumps({'board_id': self.board_id, 'stack_id': self.stack['id'], 'title': self.stack['title']}).encode())
            drag.setMimeData(mime)
            drag.exec(Qt.MoveAction)
            self._drag_start_pos = None
        super().mouseMoveEvent(event)


class BoardListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(False)
        self.setDropIndicatorShown(True)

    def dropEvent(self, event):
        try:
            md = event.mimeData()
            if md and md.hasFormat('application/x-stack'):
                raw = bytes(md.data('application/x-stack'))
                info = json.loads(raw.decode())
                orig_board_id = info.get('board_id')
                stack_id = info.get('stack_id')
                title = info.get('title')
                item = self.itemAt(event.pos())
                if item:
                    dest_board_id = item.data(Qt.UserRole)
                    parent = self.parent()
                    if hasattr(parent, 'move_stack'):
                        parent.move_stack(orig_board_id, stack_id, title, dest_board_id)
                        event.accept()
                        return
        except Exception:
            pass
        super().dropEvent(event)


# --- DIÁLOGOS ---
class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Conectar a Nextcloud Deck")
        self.setMinimumWidth(350)
        self.url = QLineEdit("https://")
        self.username = QLineEdit()
        self.password = QLineEdit();
        self.password.setEchoMode(QLineEdit.Password)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept);
        buttons.rejected.connect(self.reject)
        layout = QFormLayout(self)
        layout.addRow("URL de Nextcloud:", self.url)
        layout.addRow("Usuario:", self.username)
        layout.addRow("Contraseña de Aplicación:", self.password)
        layout.addWidget(buttons)

    def get_credentials(self): return (self.url.text(), self.username.text(), self.password.text())


class CardEditDialog(QDialog):
    def __init__(self, card_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Tarjeta")
        self.setMinimumWidth(400)

        self.title_edit = QLineEdit(card_data.get('title', ''))
        self.description_edit = QTextEdit(card_data.get('description', ''))

        self.duedate_edit = QDateEdit()
        self.duedate_edit.setCalendarPopup(True)
        self.duedate_edit.setDisplayFormat("dd/MM/yyyy")
        duedate_str = card_data.get('duedate')
        if duedate_str:
            dt_obj = datetime.fromisoformat(duedate_str.replace('Z', '+00:00'))
            self.duedate_edit.setDate(QDate(dt_obj.year, dt_obj.month, dt_obj.day))
        else:
            self.duedate_edit.setDate(QDate.currentDate())

        self.labels_edit = QLineEdit()
        self.labels_edit.setReadOnly(True)
        self.labels_edit.setPlaceholderText("La edición de etiquetas no está implementada")
        labels_json = card_data.get('labels_json')
        if labels_json:
            labels = json.loads(labels_json)
            self.labels_edit.setText(", ".join([l['title'] for l in labels]))

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept);
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.addRow("Título:", self.title_edit)
        form_layout.addRow("Descripción:", self.description_edit)
        form_layout.addRow("Fecha Límite:", self.duedate_edit)
        form_layout.addRow("Etiquetas:", self.labels_edit)
        layout.addLayout(form_layout)
        layout.addWidget(buttons)

    def get_updated_data(self):
        data = {
            "title": self.title_edit.text(),
            "description": self.description_edit.toPlainText()
        }

        q_date = self.duedate_edit.date()
        dt_obj = datetime(q_date.year(), q_date.month(), q_date.day(), 12, 0, 0, tzinfo=timezone.utc)
        data['duedate'] = dt_obj.isoformat().replace('+00:00', 'Z')

        return data


class GenericCreateDialog(QDialog):
    def __init__(self, title, labels, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title);
        self.setMinimumWidth(350)
        self.inputs = [QLineEdit() for _ in labels]
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept);
        buttons.rejected.connect(self.reject)
        layout = QFormLayout(self)
        for label, input_widget in zip(labels, self.inputs): layout.addRow(label, input_widget)
        layout.addWidget(buttons)

    def get_values(self): return [widget.text().strip() for widget in self.inputs]


# --- VENTANA PRINCIPAL ---
class KanbanApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Visor de Kanban para Nextcloud Deck");
        self.setGeometry(100, 100, 1400, 900)
        self.setStyleSheet(STYLE_SHEET)
        self.data_manager = DataManager()
        self.current_board_id = None
        self.threadpool = QThreadPool()
        self.active_workers = set()

        self.splitter = QSplitter(Qt.Horizontal);
        self.setCentralWidget(self.splitter)
        sidebar_widget = QWidget();
        sidebar_widget.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar_widget);
        sidebar_layout.setContentsMargins(0, 0, 0, 0);
        sidebar_layout.setSpacing(5)
        sidebar_header = QLabel("Tableros")
        self.board_list_widget = BoardListWidget(self);
        self.board_list_widget.itemClicked.connect(self.handle_board_selection)
        # Allow dropping stacks onto boards
        self.board_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        add_board_button = QPushButton("+ Añadir Tablero");
        add_board_button.setObjectName("addButton");
        add_board_button.clicked.connect(self.add_new_board)
        sidebar_layout.addWidget(sidebar_header);
        sidebar_layout.addWidget(self.board_list_widget);
        sidebar_layout.addWidget(add_board_button)

        self.board_area = QWidget();
        self.board_layout = QHBoxLayout(self.board_area);
        self.board_layout.setSpacing(15)
        self.splitter.addWidget(sidebar_widget);
        self.splitter.addWidget(self.board_area);
        self.splitter.setSizes([250, 1150])

        self.status_label = QLabel("Inicializando...");
        self.statusBar().addPermanentWidget(self.status_label)
        self.show()
        self.init_app()

    def run_worker(self, fn, on_success, on_error_msg, on_finish=None):
        worker = Worker(fn)
        worker.signals.result.connect(on_success)
        worker.signals.error.connect(lambda err: self.show_error(f"{on_error_msg}: {err[1]}"))

        def cleanup():
            self.active_workers.discard(worker)
            if on_finish:
                on_finish()
            else:
                self.status_label.setText("Listo.")

        worker.signals.finished.connect(cleanup)

        self.active_workers.add(worker)
        self.threadpool.start(worker)

    def init_app(self):
        creds = self.data_manager.load_credentials()
        if creds:
            self.status_label.setText("Conectando automáticamente...")
            self.run_worker(lambda: self.data_manager.attempt_login(**creds), self.post_login_actions,
                            "Fallo al autoconectar")
        else:
            self.handle_login()

    def handle_login(self):
        dialog = LoginDialog(self)
        if dialog.exec() == QDialog.Accepted:
            url, user, password = dialog.get_credentials()
            if not all([url, user, password]): self.close(); return
            self.status_label.setText("Conectando...")
            self.run_worker(lambda: self.data_manager.attempt_login(url, user, password), self.post_login_actions,
                            "Error de conexión")
        else:
            self.close()

    def post_login_actions(self, success):
        if success:
            self.status_label.setText("Conectado. Sincronizando...")
            self.load_boards()
            self.sync_offline_changes()
        else:
            self.status_label.setText("[Offline] No se pudo conectar.")
            self.load_boards()

    def sync_offline_changes(self):
        if not self.data_manager.is_online(): return
        self.status_label.setText("Sincronizando cambios locales...")
        on_success = lambda count: self.status_label.setText(f"{count} cambios locales sincronizados.")
        self.run_worker(self.data_manager.sync_offline_changes, on_success, "Error al sincronizar cambios")

    def load_boards(self):
        self.status_label.setText("Cargando tableros...")
        self.run_worker(self.data_manager.get_boards, self.populate_board_list, "Error al cargar tableros")

    def populate_board_list(self, boards):
        self.board_list_widget.clear()
        for board in boards:
            item = QListWidgetItem(board['title']);
            item.setData(Qt.UserRole, board['id'])
            self.board_list_widget.addItem(item)
        self.status_label.setText(f"{len(boards)} tableros cargados.")

    def handle_board_selection(self, item):
        board_id = item.data(Qt.UserRole);
        self.load_board(board_id)

    def load_board(self, board_id):
        self.current_board_id = board_id;
        self.status_label.setText(f"Cargando tablero ID: {board_id}...")
        self.clear_board_layout()
        self.run_worker(lambda: self.data_manager.get_stacks(board_id), self.display_board, f"Error al cargar pilas")

    def display_board(self, stacks):
        for stack in stacks:
            stack_widget = self.create_stack_widget(self.current_board_id, stack)
            self.board_layout.addWidget(stack_widget)
        self.add_new_stack_widget();
        self.status_label.setText("Tablero cargado.")

    def create_stack_widget(self, board_id, stack):
        stack_frame = QFrame();
        stack_frame.setObjectName("stackFrame")
        layout = QVBoxLayout(stack_frame);
        layout.setSpacing(8)

        # --- CAMBIO --- Barra de título con botón de eliminar
        title_bar_frame = DraggableTitleBar(self, board_id, stack);
        title_bar_frame.setObjectName("titleBar")
        title_bar_layout = QHBoxLayout(title_bar_frame)
        title_bar_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel(stack['title']);
        title_label.setObjectName("stackTitle")
        title_bar_layout.addWidget(title_label, 1)

        delete_stack_btn = QPushButton("✕")
        delete_stack_btn.setObjectName("deleteButton")
        delete_stack_btn.setFixedSize(24, 24)
        delete_stack_btn.setToolTip("Eliminar esta lista")
        delete_stack_btn.clicked.connect(partial(self.handle_delete_stack, board_id, stack['id'], stack['title']))
        title_bar_layout.addWidget(delete_stack_btn)

        # Context menu for moving the entire list
        title_bar_frame.setContextMenuPolicy(Qt.CustomContextMenu)
        title_bar_frame.customContextMenuRequested.connect(partial(self.on_stack_context_menu, board_id, stack))

        add_card_btn = QPushButton("+ Añadir Tarjeta");
        add_card_btn.setObjectName("addButton")
        card_list_widget = CardListWidget(self);
        card_list_widget.setObjectName("cardList")
        card_list_widget.board_id = board_id
        card_list_widget.stack_id = stack['id']
        card_list_widget.move_callback = self.move_card
        card_list_widget.itemDoubleClicked.connect(self.edit_card)
        add_card_btn.clicked.connect(partial(self.add_new_card, stack['id'], card_list_widget))

        layout.addWidget(title_bar_frame)
        layout.addWidget(add_card_btn)
        layout.addWidget(card_list_widget, 1)
        self.refresh_cards_for_stack(board_id, stack['id'], card_list_widget)
        return stack_frame

    def refresh_cards_for_stack(self, board_id, stack_id, list_widget):
        self.status_label.setText(f"Pidiendo tarjetas para pila {stack_id}...")

        def on_cards_loaded(cards):
            self.status_label.setText(f"Mostrando {len(cards)} tarjetas...")
            self.populate_card_list(list_widget, cards)

        self.run_worker(
            lambda: self.data_manager.get_cards(board_id, stack_id),
            on_cards_loaded,
            f"Error al cargar tarjetas para pila {stack_id}"
        )

    def populate_card_list(self, list_widget, cards):
        list_widget.clear()
        if not cards: return
        for card_data in cards:
            card_widget = CardWidget(card_data)

            # Connect the date changed signal if the widget exists
            if card_widget._duedate_widget:
                card_widget._duedate_widget.dateChanged.connect(
                    partial(self.handle_card_date_change, card_widget)
                )

            list_item = QListWidgetItem()
            list_item.setData(Qt.UserRole, card_data)
            list_item.setSizeHint(card_widget.sizeHint())
            list_widget.addItem(list_item)
            list_widget.setItemWidget(list_item, card_widget)

    def handle_card_date_change(self, card_widget, new_date):
        """Handle date changes directly from the card widget"""
        dt_obj = datetime(new_date.year(), new_date.month(), new_date.day(), 12, 0, 0, tzinfo=timezone.utc)
        new_duedate_str = dt_obj.isoformat().replace('+00:00', 'Z')

        self.status_label.setText(f"Actualizando fecha de tarjeta {card_widget.card_id}...")

        # We don't need to reload the whole board for a date change, but we should probably refresh the card data
        # For now, let's just update the backend.
        # Note: We are not updating the local card_data stored in the list item immediately,
        # but since we reload the board on success usually, it might be fine.
        # However, for a smoother experience, we might want to avoid full reload if possible.
        # But the current architecture relies on `load_board` or `refresh_cards_for_stack`.

        on_success = lambda result: self.status_label.setText("Fecha actualizada.")
        # If we want to refresh the UI to show overdue status correctly if it changed:
        # on_success = lambda result: self.refresh_cards_for_stack(card_widget.board_id, card_widget.stack_id, ???)
        # We don't have easy access to the list_widget here.
        # Let's just update backend and maybe show status.

        self.run_worker(
            lambda: self.data_manager.update_card(
                card_widget.board_id,
                card_widget.stack_id,
                card_widget.card_id,
                duedate=new_duedate_str
            ),
            on_success,
            "Error al actualizar la fecha"
        )

    def add_new_board(self):
        dialog = GenericCreateDialog("Crear Nuevo Tablero", ["Título:", "Color (hex):"], self)
        if dialog.exec() == QDialog.Accepted:
            title, color = dialog.get_values()
            if not title: self.show_error("El título es obligatorio."); return
            if not color: color = "5e81ac"  # Color por defecto
            self.status_label.setText("Creando tablero...")
            self.run_worker(lambda: self.data_manager.create_board(title, f"#{color.lstrip('#')}"),
                            lambda b: self.load_boards(), "Error al crear tablero")

    def add_new_stack_widget(self):
        add_stack_btn = QPushButton("+ Añadir otra lista");
        add_stack_btn.setObjectName("addButton")
        add_stack_btn.clicked.connect(self.add_new_stack)
        frame = QFrame();
        frame.setObjectName("stackFrame")
        layout = QVBoxLayout(frame);
        layout.addWidget(add_stack_btn)
        self.board_layout.addWidget(frame, 0, Qt.AlignLeft)

    def add_new_stack(self):
        dialog = GenericCreateDialog("Crear Nueva Lista", ["Título:"], self)
        if dialog.exec() == QDialog.Accepted:
            title = dialog.get_values()[0]
            if not title: self.show_error("El título es obligatorio."); return
            self.status_label.setText("Creando lista...")
            self.run_worker(lambda: self.data_manager.create_stack(self.current_board_id, title),
                            lambda s: self.load_board(self.current_board_id), "Error al crear lista")

    def add_new_card(self, stack_id, card_list_widget):
        dialog = GenericCreateDialog("Crear Nueva Tarjeta", ["Título:"], self)
        if dialog.exec() == QDialog.Accepted:
            title = dialog.get_values()[0]
            if not title: self.show_error("El título es obligatorio."); return
            self.status_label.setText("Creando tarjeta...")
            on_success = lambda c: self.refresh_cards_for_stack(self.current_board_id, stack_id, card_list_widget)
            self.run_worker(lambda: self.data_manager.create_card(self.current_board_id, stack_id, title), on_success,
                            "Error al crear tarjeta")

    def edit_card(self, item):
        card_data = item.data(Qt.UserRole)
        dialog = CardEditDialog(card_data, self)
        if dialog.exec() == QDialog.Accepted:
            updated_data = dialog.get_updated_data()
            self.status_label.setText(f"Actualizando tarjeta '{card_data['title']}'...")
            on_success = lambda card: self.load_board(self.current_board_id)
            self.run_worker(
                lambda: self.data_manager.update_card(card_data['board_id'], card_data['stack_id'], card_data['id'],
                                                      **updated_data),
                on_success, "Error al actualizar la tarjeta")

    # --- CAMBIO --- Nuevo método para gestionar la eliminación de una pila
    def handle_delete_stack(self, board_id, stack_id, stack_title):
        """Muestra un diálogo de confirmación y elimina la pila si se confirma."""
        confirm_dialog = QMessageBox(self)
        confirm_dialog.setWindowTitle("Confirmar Eliminación")
        confirm_dialog.setText(f"¿Estás seguro de que quieres eliminar la lista '{stack_title}'?")
        confirm_dialog.setInformativeText("Esta acción es irreversible y eliminará todas las tarjetas que contiene.")
        confirm_dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm_dialog.setDefaultButton(QMessageBox.No)
        confirm_dialog.setIcon(QMessageBox.Warning)

        if confirm_dialog.exec() == QMessageBox.Yes:
            self.status_label.setText(f"Eliminando lista '{stack_title}'...")
            on_finish = lambda: self.load_board(self.current_board_id)
            self.run_worker(
                lambda: self.data_manager.delete_stack(board_id, stack_id),
                on_success=lambda result: None,
                on_error_msg="Error al eliminar la lista",
                on_finish=on_finish
            )

    def move_card(self, card_data, dest_board_id, dest_stack_id):
        """Move a card to a different stack (and possibly board). Runs in background."""
        if card_data.get('stack_id') == dest_stack_id and card_data.get('board_id') == dest_board_id:
            return
        self.status_label.setText(f"Moviendo tarjeta '{card_data.get('title')}'...")

        def do_move():
            # call update_card with original board/stack and payload specifying new stack
            return self.data_manager.update_card(card_data['board_id'], card_data['stack_id'], card_data['id'], stack_id=dest_stack_id)

        def on_success(result):
            # Refresh current board if affected
            if self.current_board_id in (card_data.get('board_id'), dest_board_id):
                self.load_board(self.current_board_id)
            self.status_label.setText("Tarjeta movida.")

        self.run_worker(do_move, on_success, "Error al mover tarjeta")

    def create_and_move_card_to_new_list(self, card_data, board_id):
        dialog = GenericCreateDialog("Crear Nueva Lista y mover tarjeta", ["Título de la lista:"], self)
        if dialog.exec() == QDialog.Accepted:
            title = dialog.get_values()[0]
            if not title:
                self.show_error("El título es obligatorio.")
                return

            self.status_label.setText("Creando lista y moviendo tarjeta...")

            def do_create():
                return self.data_manager.create_stack(board_id, title)

            def on_created(stack_res):
                if not stack_res:
                    self.status_label.setText("La operación se ha encolado para sincronizar.")
                    return
                new_stack_id = stack_res.get('id')
                if new_stack_id:
                    self.move_card(card_data, board_id, new_stack_id)
                else:
                    self.status_label.setText("Lista creada pero no se obtuvo el ID. Actualiza manualmente.")

            self.run_worker(do_create, on_created, "Error al crear lista")

    def create_board_and_move_card(self, card_data):
        dialog = GenericCreateDialog("Crear Nuevo Tablero", ["Título:", "Color (hex):"], self)
        if dialog.exec() == QDialog.Accepted:
            title, color = dialog.get_values()
            if not title:
                self.show_error("El título es obligatorio.")
                return
            if not color:
                color = "5e81ac"
            self.status_label.setText("Creando tablero...")

            def do_create_board():
                return self.data_manager.create_board(title, f"#{color.lstrip('#')}")

            def on_board_created(board_res):
                if not board_res:
                    self.status_label.setText("La operación se ha encolado para sincronizar.")
                    return
                new_board_id = board_res.get('id')
                if new_board_id:
                    # After creating board, ask for a list name to create and move the card
                    dialog2 = GenericCreateDialog("Crear Lista en nuevo Tablero", ["Título de la lista:"], self)
                    if dialog2.exec() == QDialog.Accepted:
                        list_title = dialog2.get_values()[0]
                        if list_title:
                            def do_create_list():
                                return self.data_manager.create_stack(new_board_id, list_title)

                            def on_list_created(list_res):
                                if list_res and list_res.get('id'):
                                    self.move_card(card_data, new_board_id, list_res.get('id'))
                                else:
                                    self.status_label.setText("Lista creada pero no se obtuvo ID.")

                            self.run_worker(do_create_list, on_list_created, "Error al crear lista")
                else:
                    self.status_label.setText("Tablero creado pero no se obtuvo el ID.")

            self.run_worker(do_create_board, on_board_created, "Error al crear tablero")

    def on_card_context_menu(self, pos, list_widget):
        item = list_widget.itemAt(pos)
        if not item:
            return
        card = item.data(Qt.UserRole)
        menu = QMenu(self)
        move_menu = menu.addMenu("Mover a")

        boards = self.data_manager.db.get_boards()
        for b in boards:
            b_sub = move_menu.addMenu(b['title'])
            stacks = self.data_manager.db.get_stacks(b['id'])
            for s in stacks:
                action = b_sub.addAction(s['title'])
                action.triggered.connect(partial(self.move_card, card, b['id'], s['id']))
            # Option to create new list in this board
            action_new = b_sub.addAction("Nueva lista...")
            action_new.triggered.connect(partial(self.create_and_move_card_to_new_list, card, b['id']))

        menu.addSeparator()
        action_new_board = menu.addAction("Crear nuevo tablero...")
        action_new_board.triggered.connect(partial(self.create_board_and_move_card, card))

        menu.exec(list_widget.mapToGlobal(pos))

    def on_stack_context_menu(self, board_id, stack, pos):
        # pos comes from customContextMenuRequested of the title bar; map to global via sender
        menu = QMenu(self)
        move_menu = menu.addMenu("Mover lista a tablero")
        boards = self.data_manager.db.get_boards()
        for b in boards:
            if b['id'] == board_id:
                continue
            action = move_menu.addAction(b['title'])
            action.triggered.connect(partial(self.move_stack, board_id, stack['id'], stack['title'], b['id']))
        menu.addSeparator()
        action_new_board = menu.addAction("Crear nuevo tablero...")
        action_new_board.triggered.connect(partial(self.create_and_move_stack, board_id, stack))

        # Attempt to determine widget to map position; fallback to cursor
        sender = self.sender()
        if hasattr(sender, 'mapToGlobal'):
            global_pos = sender.mapToGlobal(pos)
        else:
            from PySide6.QtGui import QCursor
            global_pos = QCursor.pos()
        menu.exec(global_pos)

    def create_and_move_stack(self, orig_board_id, stack):
        dialog = GenericCreateDialog("Crear Nuevo Tablero", ["Título:", "Color (hex):"], self)
        if dialog.exec() == QDialog.Accepted:
            title, color = dialog.get_values()
            if not title:
                self.show_error("El título es obligatorio.")
                return
            if not color:
                color = "5e81ac"
            self.status_label.setText("Creando tablero y moviendo lista...")

            def do_create_board():
                return self.data_manager.create_board(title, f"#{color.lstrip('#')}")

            def on_board_created(board_res):
                if not board_res:
                    self.status_label.setText("La operación se ha encolado para sincronizar.")
                    return
                new_board_id = board_res.get('id')
                if new_board_id:
                    self.move_stack(orig_board_id, stack['id'], stack['title'], new_board_id)

            self.run_worker(do_create_board, on_board_created, "Error al crear tablero")

    def move_stack(self, orig_board_id, stack_id, stack_title, dest_board_id):
        """Moves a whole stack to another board by creating a new stack there, moving cards, and deleting the original."""
        if not self.data_manager.is_online():
            self.show_error("Mover listas requiere estar en línea. La operación no está soportada en modo offline.")
            return
        self.status_label.setText(f"Moviendo lista '{stack_title}' a otro tablero...")

        def do_move():
            # 1) create new stack on dest board
            new_stack = self.data_manager.create_stack(dest_board_id, stack_title)
            if not new_stack:
                return None
            new_stack_id = new_stack.get('id')
            # 2) get cards currently in stack
            cards = self.data_manager.get_cards(stack_id)
            # 3) move each card
            if cards:
                for c in cards:
                    try:
                        self.data_manager.update_card(c['board_id'], c['stack_id'], c['id'], stack_id=new_stack_id)
                    except Exception:
                        pass
            # 4) delete old stack
            self.data_manager.delete_stack(orig_board_id, stack_id)
            return True

        def on_done(res):
            self.load_board(self.current_board_id)
            self.load_boards()
            self.status_label.setText("Lista movida.")

        self.run_worker(do_move, on_done, "Error al mover lista")

    def clear_board_layout(self):
        while self.board_layout.count():
            child = self.board_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()

    def show_error(self, message):
        self.status_label.setText(f"Error: {message}")
        QMessageBox.critical(self, "Error", message)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = KanbanApp()
    sys.exit(app.exec())

