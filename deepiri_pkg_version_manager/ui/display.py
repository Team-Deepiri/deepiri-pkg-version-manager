import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QListWidget,
    QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QSplitter
)
from PySide6.QtCore import Qt


class PackageManagerUI(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Package Manager")
        self.setGeometry(100, 100, 1000, 600)

        # Main container
        main_widget = QWidget()
        main_layout = QVBoxLayout()

        # --- Top Buttons ---
        button_layout = QHBoxLayout()

        self.add_tag_btn = QPushButton("Add Tag")
        self.push_tag_btn = QPushButton("Push Tag")
        self.sync_btn = QPushButton("Sync")
        self.delete_tag_btn = QPushButton("Delete Tag")

        button_layout.addWidget(self.add_tag_btn)
        button_layout.addWidget(self.push_tag_btn)
        button_layout.addWidget(self.sync_btn)
        button_layout.addWidget(self.delete_tag_btn)

        # --- Split Layout ---
        splitter = QSplitter(Qt.Horizontal)

        # Left: Dependency List
        self.dep_list = QListWidget()
        self.dep_list.addItems(["dependency-A", "dependency-B", "dependency-C"])
        splitter.addWidget(self.dep_list)

        # Right: Main Panel
        right_panel = QWidget()
        right_layout = QVBoxLayout()

        # Table for versions
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            "Name", "Current Version", "Local Version", "Status"
        ])

        # Tag view
        self.tag_label = QLabel("Tags:")
        self.tag_list = QListWidget()

        right_layout.addWidget(self.table)
        right_layout.addWidget(self.tag_label)
        right_layout.addWidget(self.tag_list)

        right_panel.setLayout(right_layout)
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(1, 3)

        # Assemble layout
        main_layout.addLayout(button_layout)
        main_layout.addWidget(splitter)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # --- Signals ---
        self.dep_list.currentItemChanged.connect(self.on_dependency_selected)
        self.add_tag_btn.clicked.connect(self.on_add_tag)
        self.push_tag_btn.clicked.connect(self.on_push_tag)

    # --- Event Handlers ---
    def on_dependency_selected(self, current, previous):
        if current:
            dep_name = current.text()
            print(f"Selected dependency: {dep_name}")

            # Placeholder: update table + tags
            self.load_dependency_data(dep_name)

    def on_add_tag(self):
        print("Add tag clicked")

    def on_push_tag(self):
        print("Push tag clicked")

    # --- Data Loading ---
    def load_dependency_data(self, dep_name):
        # Dummy data (replace with your backend)
        self.table.setRowCount(1)
        self.table.setItem(0, 0, QTableWidgetItem(dep_name))
        self.table.setItem(0, 1, QTableWidgetItem("v1.0.0"))
        self.table.setItem(0, 2, QTableWidgetItem("v1.1.0"))
        self.table.setItem(0, 3, QTableWidgetItem("Ahead"))

        self.tag_list.clear()
        self.tag_list.addItems(["v1.0.0", "v1.1.0", "v2.0.0"])


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PackageManagerUI()
    window.show()
    sys.exit(app.exec())