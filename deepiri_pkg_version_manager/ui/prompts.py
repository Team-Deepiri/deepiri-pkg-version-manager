from PySide6.QtWidgets import (
    QDialog, QLineEdit, QTextEdit, QFormLayout, QDialogButtonBox,
    QLabel, QVBoxLayout, QMessageBox,
)

from deepiri_pkg_version_manager.deps.dependency_registry import DependencyRegistry
from deepiri_pkg_version_manager.cli.main import dependency_tree_check, check_valid_tag, push_sanitization, check_valid_format, run_command

import logging
logger = logging.getLogger(__name__)


def prompt_add(parent, dependency_mgr: DependencyRegistry, dep: str = None) -> (
    tuple[str, str, str] | tuple[str, str] | None
):
    dlg = QDialog(parent)
    dlg.setWindowTitle("Add tag")
    name_edit = QLineEdit()
    name_edit.setPlaceholderText("e.g. v0.0.0")
    desc_edit = QTextEdit()
    desc_edit.setPlaceholderText("Required")
    desc_edit.setFixedHeight(80)
    form = QFormLayout()
    if dep is None:
        dep_edit = QLineEdit()
        dep_edit.setPlaceholderText("e.g. deepiri-pkg-version-manager")
        form.addRow(QLabel("Dependency"), dep_edit)
    form.addRow(QLabel("Tag name"), name_edit)
    form.addRow(QLabel("Description"), desc_edit)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )

    def try_accept() -> None:
        if dep is None and not dep_edit.text().strip():
            QMessageBox.warning(
                parent,
                "Missing dependency",
                "Please enter a dependency name.",
            )
            return
        if dep is None and not dependency_tree_check(dep_edit.text().strip(), dependency_mgr):
            QMessageBox.warning(
                parent,
                "Dependency Error",
                "Invalid dependency, ensure the dependency name is valid and the working tree is clean.",
            )
            return
        if not name_edit.text().strip():
            QMessageBox.warning(
                parent,
                "Missing tag name",
                "Please enter a tag name.",
            )
            return
        if not check_valid_tag(name_edit.text().strip(), 
                                dep if dep is not None else dep_edit.text().strip(),
                                dependency_mgr.get(dep if dep is not None else dep_edit.text().strip()).repo_path
        ):
            QMessageBox.warning(
                parent,
                "Invalid tag name",
                "Please enter a valid tag name.",
            )
            return
        if not desc_edit.toPlainText().strip():
            QMessageBox.warning(
                parent,
                "Missing description",
                "Please enter a tag description.",
            )
            return
        dlg.accept()

    buttons.accepted.connect(try_accept)
    buttons.rejected.connect(dlg.reject)
    layout = QVBoxLayout(dlg)
    layout.addLayout(form)
    layout.addWidget(buttons)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None

    if dep is None:
        dependency = dep_edit.text().strip()
    name = name_edit.text().strip()

    description = desc_edit.toPlainText().strip()

    if dep is None:
        return dependency, name, description
    else:
        return name, description


def prompt_push(parent, dependency_mgr: DependencyRegistry, dep: str = None):
    dlg = QDialog(parent)
    dlg.setWindowTitle("Push a tag")
    name_edit = QLineEdit()
    name_edit.setPlaceholderText("e.g. v0.0.0")
    form = QFormLayout()
    if dep is None:
        dep_edit = QLineEdit()
        dep_edit.setPlaceholderText("e.g. deepiri-pkg-version-manager")
        form.addRow(QLabel("Dependency"), dep_edit)
    form.addRow(QLabel("Tag name"), name_edit)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )

    def try_accept() -> None:
        if dep is None and not dep_edit.text().strip():
            QMessageBox.warning(
                parent,
                "Missing dependency",
                "Please enter a dependency name.",
            )
            return
        if dep is None and not dependency_tree_check(dep_edit.text().strip(), dependency_mgr):
            QMessageBox.warning(
                parent,
                "Dependency Error",
                "Invalid dependency, ensure the dependency name is valid and the working tree is clean.",
            )
            return
        if not name_edit.text().strip():
            QMessageBox.warning(
                parent,
                "Missing tag name",
                "Please enter a tag name.",
            )
            return
        if not check_valid_format(name_edit.text().strip()):
            QMessageBox.warning(
                parent,
                "Invalid tag name",
                "Please enter a valid tag name.",
            )
            return
        if not push_sanitization(dep if dep is not None else dep_edit.text().strip(),
                                name_edit.text().strip(),
                                dependency_mgr.get(dep if dep is not None else dep_edit.text().strip()).repo_path):
            QMessageBox.warning(
                parent,
                "Push sanitization failed",
                "Please ensure the tag you are pushing is greater than the latest tag in the remote repository.",
            )
            return
        dlg.accept()

    buttons.accepted.connect(try_accept)
    buttons.rejected.connect(dlg.reject)
    layout = QVBoxLayout(dlg)
    layout.addLayout(form)
    layout.addWidget(buttons)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return

    if dep is None:
        dependency = dep_edit.text().strip()
    name = name_edit.text().strip()

    if dep is None:
        return dependency, name_edit
    else:
        return name


def prompt_remove(parent, dependency_mgr: DependencyRegistry, dep: str = None):
    dlg = QDialog(parent)
    dlg.setWindowTitle("Remove tag")
    name_edit = QLineEdit()
    name_edit.setPlaceholderText("e.g. v0.0.0")
    form = QFormLayout()
    if dep is None:
        dep_edit = QLineEdit()
        dep_edit.setPlaceholderText("e.g. deepiri-pkg-version-manager")
        form.addRow(QLabel("Dependency"), dep_edit)
    form.addRow(QLabel("Tag name"), name_edit)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )

    def try_accept() -> None:
        if dep is None and not dep_edit.text().strip():
            QMessageBox.warning(
                parent,
                "Missing dependency",
                "Please enter a dependency name.",
            )
            return
        if dep is None and not dependency_tree_check(dep_edit.text().strip(), dependency_mgr):
            QMessageBox.warning(
                parent,
                "Dependency Error",
                "Invalid dependency, ensure the dependency name is valid and the working tree is clean.",
            )
            return
        if not name_edit.text().strip():
            QMessageBox.warning(
                parent,
                "Missing tag name",
                "Please enter a tag name.",
            )
            return
        if not check_valid_format(name_edit.text().strip()):
            QMessageBox.warning(
                parent,
                "Invalid tag name",
                "Please enter a valid tag name.",
            )
            return
        dlg.accept()

    buttons.accepted.connect(try_accept)
    buttons.rejected.connect(dlg.reject)
    layout = QVBoxLayout(dlg)
    layout.addLayout(form)
    layout.addWidget(buttons)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None

    if dep is None:
        dependency = dep_edit.text().strip()
    name = name_edit.text().strip()

    if dep is None:
        return dependency, name
    else:
        return name


def prompt_update(parent, dependency_mgr: DependencyRegistry, type: str, dep: str = None):
    dlg = QDialog(parent)
    dlg.setWindowTitle(f"{type.capitalize()} tag")
    desc_edit = QTextEdit()
    desc_edit.setPlaceholderText("Required")
    desc_edit.setFixedHeight(80)
    form = QFormLayout()
    if dep is None:
        dep_edit = QLineEdit()
        dep_edit.setPlaceholderText("e.g. deepiri-pkg-version-manager")
        form.addRow(QLabel("Dependency"), dep_edit)
    form.addRow(QLabel("Description"), desc_edit)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )

    def try_accept() -> None:
        if dep is None and not dep_edit.text().strip():
            QMessageBox.warning(
                parent,
                "Missing dependency",
                "Please enter a dependency name.",
            )
            return
        if dep is None and not dependency_tree_check(dep_edit.text().strip(), dependency_mgr):
            QMessageBox.warning(
                parent,
                "Dependency Error",
                "Invalid dependency, ensure the dependency name is valid and the working tree is clean.",
            )
            return
        if not check_tags_exist_locally(dependency_mgr.get(dep if dep is not None else dep_edit.text().strip()).repo_path):
            QMessageBox.warning(
                parent,
                "Tag not found",
                "Please add a tag to the dependency or select a dependency with tags.",
            )
            return
        if not desc_edit.toPlainText().strip():
            QMessageBox.warning(
                parent,
                "Missing description",
                "Please enter a tag description.",
            )
            return
        dlg.accept()

    buttons.accepted.connect(try_accept)
    buttons.rejected.connect(dlg.reject)
    layout = QVBoxLayout(dlg)
    layout.addLayout(form)
    layout.addWidget(buttons)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None

    if dep is None:
        dependency = dep_edit.text().strip()

    description = desc_edit.toPlainText().strip()

    if dep is None:
        return dependency,description
    else:
        return description


def check_tags_exist_locally(dep_path: str) -> bool:
    tags = run_command(['git', 'tag', '--sort=-v:refname'], dep_path)
    if tags is None:
        logging.error(f"Failed to get tags for '{dep_path}'")
        return False
    elif tags.strip() == "":
        logging.info(f"No tags found in '{dep_path}'")
        return False
    else:
        return True