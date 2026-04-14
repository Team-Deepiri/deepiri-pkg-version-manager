from PySide6.QtWidgets import (
    QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QListWidget,
    QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QSplitter, QHeaderView,
    QMessageBox
)
from PySide6.QtCore import Qt, QEvent
from rich import print as rprint
from rich.console import Console
from packaging.version import Version

from deepiri_pkg_version_manager.ui.prompts import prompt_add, prompt_push, prompt_remove, prompt_update

from deepiri_pkg_version_manager.tags.tag_manager import TagManager
from deepiri_pkg_version_manager.deps.dependency_registry import DependencyRegistry
from deepiri_pkg_version_manager.cli.main import run_command, dependency_tree_check, create_tag, push_tag, remove_tag, update_helper

import logging
logger = logging.getLogger(__name__)

console = Console()


class PackageManagerUI(QMainWindow):
    def __init__(self):
        super().__init__()

        with console.status("[green]Launching UI...[/green]"):
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
            self.dependencies = self.dependency_registry.get_all()
            self.dep_list.addItems([dep.name for dep in self.dependencies])
            self.row_for_dependencies = {dep.name: index for index, dep in enumerate(self.dependencies)}
            self.dep_list.viewport().installEventFilter(self)
            splitter.addWidget(self.dep_list)

            self.remote_tags = {}
            self.local_tags = {}

            right_panel = QWidget()
            right_layout = QVBoxLayout()

            self.table = QTableWidget(0, 4)
            self.table.setHorizontalHeaderLabels([
                "Name", "Remote Version", "Local Version", "Status"
            ])
            table_header = self.table.horizontalHeader()
            table_header.setSectionsMovable(False)
            for col in range(4):
                table_header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._apply_table_column_widths()
            self.load_dependency_data()
            self.table.viewport().installEventFilter(self)

            tags_row = QWidget()
            tags_row_layout = QHBoxLayout(tags_row)
            tags_row_layout.setContentsMargins(0, 0, 0, 0)

            local_col = QVBoxLayout()
            local_label = QLabel("Local tags")
            self.local_tag_list = QListWidget()
            self.local_tag_list.viewport().installEventFilter(self)
            local_col.addWidget(local_label)
            local_col.addWidget(self.local_tag_list)

            remote_col = QVBoxLayout()
            remote_label = QLabel("Remote tags")
            self.remote_tag_list = QListWidget()
            self.remote_tag_list.viewport().installEventFilter(self)
            remote_col.addWidget(remote_label)
            remote_col.addWidget(self.remote_tag_list)

            tags_row_layout.addLayout(local_col, 1)
            tags_row_layout.addLayout(remote_col, 1)

            bump_row = QHBoxLayout()
            bump_row.setContentsMargins(0, 0, 0, 0)
            self.patch_btn = QPushButton("Patch")
            self.minor_btn = QPushButton("Minor")
            self.major_btn = QPushButton("Major")
            bump_row.addWidget(self.patch_btn)
            bump_row.addWidget(self.minor_btn)
            bump_row.addWidget(self.major_btn)

            right_layout.addWidget(self.table)
            right_layout.addWidget(tags_row)
            right_layout.addLayout(bump_row)

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
            self.patch_btn.clicked.connect(self.on_patch)
            self.minor_btn.clicked.connect(self.on_minor)
            self.major_btn.clicked.connect(self.on_major)
            
        rprint("[green]UI launched successfully[/green]")

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_table_column_widths()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_table_column_widths()

    def _apply_table_column_widths(self) -> None:
        """Fill table width: Name = 50%, other columns split the rest equally; no manual resize."""
        w = self.table.viewport().width()
        if w <= 0:
            return
        name_w = int(w * 0.5)
        rem = w - name_w
        third = rem // 3
        rest = rem - 2 * third
        self.table.setColumnWidth(0, name_w)
        self.table.setColumnWidth(1, third)
        self.table.setColumnWidth(2, third)
        self.table.setColumnWidth(3, rest)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if obj == self.dep_list.viewport() and not self.dep_list.indexAt(event.pos()).isValid():
                self.dep_list.clearSelection()
                self.dep_list.setCurrentItem(None)
                return True
            if obj == self.local_tag_list.viewport() and not self.local_tag_list.indexAt(event.pos()).isValid():
                self.local_tag_list.clearSelection()
                self.local_tag_list.setCurrentItem(None)
                return True
            if obj == self.remote_tag_list.viewport() and not self.remote_tag_list.indexAt(event.pos()).isValid():
                self.remote_tag_list.clearSelection()
                self.remote_tag_list.setCurrentItem(None)
                return True
            if obj == self.table.viewport() and not self.table.indexAt(event.pos()).isValid():
                self.table.clearSelection()
                self.table.setCurrentCell(-1, -1)
                return True
        return super().eventFilter(obj, event)

    def on_dependency_selected(self, current, previous):
        self.local_tag_list.clear()
        self.remote_tag_list.clear()
        if not current:
            return
        dep_name = current.text()
        for tag in self.local_tags.get(dep_name, []):
            self.local_tag_list.addItem(f" - {tag}")
        for tag in self.remote_tags.get(dep_name, []):
            self.remote_tag_list.addItem(f" - {tag}")

    def on_add_tag(self):
        item = self.dep_list.currentItem()
        if not item:
            result = prompt_add(self, self.dependency_registry)
            if result is None:
                self.error_message("Failed to launch prompt")
                return
            dep_name, tag_name, description = result
        else:
            dep_name = item.text()
            if not dependency_tree_check(dep_name, self.dependency_registry):
                self.error_message("Dependency tree check failed")
                return
            result = prompt_add(self, self.dependency_registry, dep=dep_name)
            if result is None:
                self.error_message("Failed to launch prompt")
                return
            tag_name, description = result

        if not create_tag(dep_name, self.tag_manager, self.dependency_registry, tag_name, description):
            self.error_message("Failed to create tag")
            return
        else:
            self.local_tags[dep_name].insert(0, tag_name)
            self.table.setItem(self.row_for_dependencies[dep_name], 2, QTableWidgetItem(tag_name))
            remote_tag = self.table.item(self.row_for_dependencies[dep_name], 1).text()
            self.table.setItem(self.row_for_dependencies[dep_name], 3, QTableWidgetItem(self.get_status(remote_tag, tag_name)))
            if item:
                self.local_tag_list.insertItem(0, f" - {tag_name}")

        self.success_message(f"Tag '{tag_name}' added to '{dep_name}'")

    def on_push_tag(self):
        item = self.dep_list.currentItem()
        if not item:
            result = prompt_push(self, self.dependency_registry)
            if result is None:
                self.error_message("Failed to launch prompt")
                return
            dep_name, tag_name = result
        else:
            dep_name = item.text()
            if not dependency_tree_check(dep_name, self.dependency_registry):
                self.error_message("Dependency tree check failed")
                return
            local_tag_item = self.local_tag_list.currentItem()
            remote_tag_item = self.remote_tag_list.currentItem()
            if local_tag_item is None and remote_tag_item is not None:
                self.error_message("Cannot push remote tags, please select a local tag to push.")
                return
            if local_tag_item is None:
                result = prompt_push(self, self.dependency_registry, dep=dep_name)
                if result is None:
                    self.error_message("Failed to launch prompt")
                    return
                tag_name = result
            else:
                tag_name = local_tag_item.text().split(' - ')[1]

        dep = self.dependency_registry.get(dep_name)
        if not push_tag(dep_name, self.dependency_registry.get(dep_name).repo_path, self.tag_manager, tag_name):
            self.error_message("Failed to push tag")
            return
        else:
            self.remote_tags[dep_name].insert(0, tag_name)
            self.table.setItem(self.row_for_dependencies[dep_name], 1, QTableWidgetItem(tag_name))
            local_tag = self.table.item(self.row_for_dependencies[dep_name], 2).text()
            self.table.setItem(self.row_for_dependencies[dep_name], 3, QTableWidgetItem(self.get_status(tag_name, local_tag)))
            if item:
                self.remote_tag_list.insertItem(0, f" - {tag_name}")

        self.success_message(f"Tag '{tag_name}' pushed to '{dep_name}'")

    def on_remove_tag(self):
        item = self.dep_list.currentItem()
        if item is None:
            result = prompt_remove(self, self.dependency_registry)
            if result is None:
                self.error_message("Failed to launch prompt")
                return
            dep_name, tag_name = result
        else:
            dep_name = item.text()
            local_tag_item = self.local_tag_list.currentItem()
            remote_tag_item = self.remote_tag_list.currentItem()
            if local_tag_item is None and remote_tag_item is None:
                result = prompt_remove(self, self.dependency_registry, dep=dep_name)
                if result is None:
                    self.error_message("Failed to launch prompt")
                    return
                tag_name = result
            elif local_tag_item is not None and remote_tag_item is None:
                tag_name = local_tag_item.text().split(' - ')[1]
            elif local_tag_item is None and remote_tag_item is not None:
                tag_name = remote_tag_item.text().split(' - ')[1]
            else:
                if local_tag_item.text().split(' - ')[1] == remote_tag_item.text().split(' - ')[1]:
                    tag_name = local_tag_item.text().split(' - ')[1]
                else:
                    self.error_message("Cannot remove tags, please select the same tag from both local and remote.")
                    return

        success = remove_tag(dep_name, tag_name, self.tag_manager, self.dependency_registry)
        if not success:
            self.error_message("Failed to remove tag")
            return
        else:
            if tag_name in self.remote_tags[dep_name]:
                self.remote_tags[dep_name].remove(tag_name)
                self.remote_tag_list.takeItem(self.remote_tag_list.row(self.remote_tag_list.findItems(f" - {tag_name}", Qt.MatchFlag.MatchExactly)[0]))
                self.table.setItem(self.row_for_dependencies[dep_name], 1, QTableWidgetItem(self.remote_tags[dep_name][0] if self.remote_tags[dep_name] else "None"))
            if tag_name in self.local_tags[dep_name]:
                self.local_tags[dep_name].remove(tag_name)
                self.local_tag_list.takeItem(self.local_tag_list.row(self.local_tag_list.findItems(f" - {tag_name}", Qt.MatchFlag.MatchExactly)[0]))
                self.table.setItem(self.row_for_dependencies[dep_name], 2, QTableWidgetItem(self.local_tags[dep_name][0] if self.local_tags[dep_name] else "None"))
            self.table.setItem(self.row_for_dependencies[dep_name], 3, QTableWidgetItem(self.get_status(self.table.item(self.row_for_dependencies[dep_name], 1).text(), self.table.item(self.row_for_dependencies[dep_name], 2).text())))

        self.success_message(f"Tag '{tag_name}' removed from '{dep_name}'")

    def on_patch(self):
        self.update("patch")

    def on_minor(self):
        self.update("minor")

    def on_major(self):
        self.update("major")

    def load_dependency_data(self):
        self.table.setRowCount(len(self.dependencies))
        for index, dep in enumerate(self.dependencies):
            remote_tags = self.get_remote_tags(dep.name, dep.repo_path)
            if remote_tags is None:
                remote_tag = "None"
                self.remote_tags[dep.name] = []
            else:
                remote_tags = [tag for tag in remote_tags if "^{}" not in tag]
                remote_tag = remote_tags[0]
                self.remote_tags[dep.name] = remote_tags

            local_tags = self.get_local_tags(dep.name, dep.repo_path)
            if local_tags is None:
                local_tag = "None"
                self.local_tags[dep.name] = []
            else:
                local_tags = [tag for tag in local_tags if "^{}" not in tag]
                local_tag = local_tags[0]
                self.local_tags[dep.name] = local_tags

            self.table.setItem(index, 0, QTableWidgetItem(dep.name))
            self.table.setItem(index, 1, QTableWidgetItem(remote_tag))
            self.table.setItem(index, 2, QTableWidgetItem(local_tag))
            self.table.setItem(index, 3, QTableWidgetItem(self.get_status(remote_tag, local_tag)))

    def get_status(self, remote_tag, local_tag) -> str:
        if remote_tag == "None" and local_tag == "None":
            return "Up to date"
        elif remote_tag == "None" and local_tag != "None":
            return "Ahead"
        elif remote_tag != "None" and local_tag == "None":
            return "Behind"
        elif Version(remote_tag) > Version(local_tag):
            return "Behind"
        elif Version(remote_tag) < Version(local_tag):
            return "Ahead"
        else:
            return "Up to date"

    def get_local_tags(self, dep_name, repo_path):
        output = run_command(['git', 'tag', '--sort=-v:refname'], repo_path)
        if output is None:
            logger.error(f"[red]Error:[/red] Failed to get local tags for '{dep_name}'")
            return None
        elif output.strip() == "":
            logger.info(f"No local tags found for '{dep_name}'")
            return None
        else:
            logger.info(f'[green]Local tags in {dep_name} fetched successfully[/green]')
            return [tag for tag in output.strip().split('\n')]

    def get_remote_tags(self, dep_name, repo_path):
        output = run_command(['git', 'ls-remote', '--tags', '--sort=-v:refname', 'origin'], repo_path)
        if output is None:
            logger.error(f"[red]Error:[/red] Failed to get remote tags for '{dep_name}'")
            return None
        elif output.strip() == "":
            logger.info(f"No remote tags found for '{dep_name}'")
            return None
        else:
            logger.info(f'[green]Remote tags in {dep_name} fetched successfully[/green]')
            return [tag.split('refs/tags/')[1] for tag in output.strip().split('\n')]

    def update(self, type: str):
        item = self.dep_list.currentItem()
        if not item:
            result = prompt_update(self, self.dependency_registry, type)
            if result is None:
                self.error_message("Failed to launch prompt")
                return
            dep_name, description = result
        else:
            dep_name = item.text()
            if self.local_tags[dep_name] is None:
                self.error_message("No local tags found for this dependency")
                return
            result = prompt_update(self, self.dependency_registry, type, dep=dep_name)
            if result is None:
                self.error_message("Failed to launch prompt")
                return
            description = result

        tag_name = update_helper(dep_name, self.tag_manager, self.dependency_registry.get(dep_name).repo_path, type, description)
        if tag_name is None:
            self.error_message(f"Failed to patch {dep_name}")
            return
        else:
            self.local_tags[dep_name].insert(0, tag_name)
            self.table.setItem(self.row_for_dependencies[dep_name], 2, QTableWidgetItem(tag_name))
            remote_tag = self.table.item(self.row_for_dependencies[dep_name], 1).text()
            self.table.setItem(self.row_for_dependencies[dep_name], 3, QTableWidgetItem(self.get_status(remote_tag, tag_name)))
            if item:
                self.local_tag_list.insertItem(0, f" - {tag_name}")
        
        self.success_message(f"'{dep_name}' successfully updated")

    def success_message(self, message: str) -> None:
        QMessageBox.information(
            self,
            "Operation Successful",
            message,
        )

    def error_message(self, message: str) -> None:
        QMessageBox.warning(
            self,
            "Error",
            f"{message}\nCheck logs for more information",
        )
