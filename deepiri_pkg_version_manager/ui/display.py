from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QListWidget,
    QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QSplitter
)
from PySide6.QtCore import Qt
from rich import print as rprint
from packaging.version import Version


from deepiri_pkg_version_manager.tags.tag_manager import TagManager
from deepiri_pkg_version_manager.deps.dependency_registry import DependencyRegistry
from deepiri_pkg_version_manager.cli.main import run_git_command


class PackageManagerUI(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Deepiri Package Version Manager")
        self.setGeometry(100, 100, 1000, 600)

        self.tag_manager = TagManager()
        self.dependency_registry = DependencyRegistry()

        main_widget = QWidget()
        main_layout = QVBoxLayout()

        button_layout = QHBoxLayout()
        self.add_tag_btn = QPushButton("Add Tag")
        self.push_tag_btn = QPushButton("Push Tag")
        self.remove_tag_btn = QPushButton("Remove Tag")

        button_layout.addWidget(self.add_tag_btn)
        button_layout.addWidget(self.push_tag_btn)
        button_layout.addWidget(self.remove_tag_btn)

        splitter = QSplitter(Qt.Horizontal)

        self.dep_list = QListWidget()
        self.dep_list.addItems([dep.name for dep in self.dependency_registry.get_all()])
        splitter.addWidget(self.dep_list)

        right_panel = QWidget()
        right_layout = QVBoxLayout()

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            "Name", "Remote Version", "Local Version", "Status"
        ])

        self.tag_label = QLabel("Tags:")
        self.tag_list = QListWidget()

        right_layout.addWidget(self.table)
        right_layout.addWidget(self.tag_label)
        right_layout.addWidget(self.tag_list)

        right_panel.setLayout(right_layout)
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(1, 3)

        main_layout.addLayout(button_layout)
        main_layout.addWidget(splitter)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        self.dep_list.currentItemChanged.connect(self.on_dependency_selected)
        self.add_tag_btn.clicked.connect(self.on_add_tag)
        self.push_tag_btn.clicked.connect(self.on_push_tag)
        self.remove_tag_btn.clicked.connect(self.on_remove_tag)

    def on_dependency_selected(self, current, previous):
        if current:
            dep_name = current.text()
            print(f"Selected dependency: {dep_name}")
            self.load_dependency_data(dep_name)

    def on_add_tag(self):
        print("Add tag clicked")

    def on_push_tag(self):
        print("Push tag clicked")

    def on_remove_tag(self):
        print("Remove tag clicked")

    def load_dependency_data(self, dep_name):
        dep = self.dependency_registry.get(dep_name)
        remote_tags = self.get_remote_tags(dep_name, dep.repo_path)
        if remote_tags is None:
            remote_tag = "None"
        else:
            remote_tag = remote_tags[0]

        local_tags = self.get_local_tags(dep_name, dep.repo_path)
        if local_tags is None:
            local_tag = "None"
        else:
            local_tag = local_tags[0]

        # Ensure row 0 exists before setting table cells.
        self.table.setRowCount(1)
        self.table.setItem(0, 0, QTableWidgetItem(dep_name))
        self.table.setItem(0, 1, QTableWidgetItem(remote_tag))
        self.table.setItem(0, 2, QTableWidgetItem(local_tag))
        self.table.setItem(0, 3, QTableWidgetItem(self.get_status(remote_tags[0], local_tags[0])))

    def get_status(self, remote_tag, local_tag) -> str:
        if (remote_tag is None and local_tag is None) or (Version(remote_tag) == Version(local_tag)):
            return "Up to date"
        elif remote_tag is None and local_tag is not None:
            return "Ahead"
        elif remote_tag is not None and local_tag is None:
            return "Behind"
        elif Version(remote_tag) > Version(local_tag):
            return "Ahead"
        elif Version(remote_tag) < Version(local_tag):
            return "Behind"

    def get_local_tags(self, dep_name, repo_path):
        output = run_git_command(['git', 'tag', '--sort=-v:refname'], repo_path)
        if output is None:
            rprint(f"[red]Error:[/red] Failed to get local tags for '{dep_name}'")
            return None
        elif output.strip() == "":
            print(f"No local tags found for '{dep_name}'")
            return None
        else:
            rprint('[green]Local tags fetched successfully[/green]')
            return [tag for tag in output.strip().split('\n')]

    def get_remote_tags(self, dep_name, repo_path):
        output = run_git_command(['git', 'ls-remote', '--tags', '--sort=-v:refname', 'origin'], repo_path)
        if output is None:
            rprint(f"[red]Error:[/red] Failed to get remote tags for '{dep_name}'")
            return None
        elif output.strip() == "":
            print(f"No remote tags found for '{dep_name}'")
            return None
        else:
            rprint('[green]Remote tags fetched successfully[/green]')
            return [tag.split('refs/tags/')[1] for tag in output.strip().split('\n')]
