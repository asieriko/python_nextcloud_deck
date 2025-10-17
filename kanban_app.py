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
    QMessageBox, QFrame, QSplitter
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
    QLabel#stackTitle {
        font-size: 12pt; font-weight: bold; padding: 8px; color: #88c0d0;
        background-color: #434c5e; border-top-left-radius: 8px; border-top-right-radius: 8px;
    }
    QListWidget#cardList {
        background-color: transparent; border: none;
    }
    /* This is important for custom widgets to be sized correctly */
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
    QLabel#cardDueDate.overdue {
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

        self._duedate_label = None
        duedate_str = card_data.get('duedate')
        if duedate_str:
            self._duedate_label = self.format_duedate(duedate_str)
            if self._duedate_label:
                self._main_layout.addWidget(self._duedate_label)

    def format_duedate(self, duedate_str):
        try:
            dt_obj = datetime.fromisoformat(duedate_str.replace('Z', '+00:00'))
            is_overdue = dt_obj < datetime.now(timezone.utc)
            meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
            formatted_date = f"Vence: {dt_obj.day} {meses[dt_obj.month - 1]} {dt_obj.year}"
            label = QLabel(formatted_date)
            label.setObjectName("cardDueDate")
            if is_overdue:
                label.setProperty("class", "overdue")
            return label
        except (ValueError, TypeError):
            return None


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

    def get_values(self): return [widget.text() for widget in self.inputs]


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
        self.board_list_widget = QListWidget();
        self.board_list_widget.itemClicked.connect(self.handle_board_selection)
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
        title_label = QLabel(stack['title']);
        title_label.setObjectName("stackTitle")
        add_card_btn = QPushButton("+ Añadir Tarjeta");
        add_card_btn.setObjectName("addButton")
        card_list_widget = QListWidget();
        card_list_widget.setObjectName("cardList")
        card_list_widget.itemDoubleClicked.connect(self.edit_card)
        add_card_btn.clicked.connect(partial(self.add_new_card, stack['id'], card_list_widget))
        layout.addWidget(title_label);
        layout.addWidget(add_card_btn);
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
        if not cards:
            return

        for card_data in cards:
            card_widget = CardWidget(card_data)
            list_item = QListWidgetItem()
            list_item.setData(Qt.UserRole, card_data)
            list_item.setSizeHint(card_widget.sizeHint())
            list_widget.addItem(list_item)
            list_widget.setItemWidget(list_item, card_widget)

    def add_new_board(self):
        dialog = GenericCreateDialog("Crear Nuevo Tablero", ["Título:", "Color (hex):"], self)
        if dialog.exec() == QDialog.Accepted:
            title, color = dialog.get_values()
            # --- CAMBIO ---
            # Se añade validación para el título y el color
            title = title.strip()
            color = color.strip()
            if not all([title, color]):
                self.show_error("El título y el color no pueden estar vacíos.");
                return

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
            # --- CAMBIO ---
            # Se añade validación para el título
            title = dialog.get_values()[0].strip()
            if not title:
                self.show_error("El título no puede estar vacío.");
                return

            self.status_label.setText("Creando lista...")
            self.run_worker(lambda: self.data_manager.create_stack(self.current_board_id, title),
                            lambda s: self.load_board(self.current_board_id), "Error al crear lista")

    def add_new_card(self, stack_id, card_list_widget):
        dialog = GenericCreateDialog("Crear Nueva Tarjeta", ["Título:"], self)
        if dialog.exec() == QDialog.Accepted:
            # --- CAMBIO ---
            # Se añade validación para el título
            title = dialog.get_values()[0].strip()
            if not title:
                self.show_error("El título no puede estar vacío.");
                return

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

