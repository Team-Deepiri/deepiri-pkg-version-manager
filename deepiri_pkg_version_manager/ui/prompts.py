from PySide6.QtWidgets import (
    QDialog, QLineEdit, QTextEdit, QFormLayout, QDialogButtonBox,
    QLabel, QVBoxLayout, QMessageBox,
)

from deepiri_pkg_version_manager.deps.dependency_registry import DependencyRegistry
from deepiri_pkg_version_manager.cli.main import dependency_tree_check, check_valid_tag

def prompt_tag_name_and_description(parent, dependency_mgr: DependencyRegistry, dep: str = None) -> (
    tuple[str, str, str | None] | tuple[str, str | None] | None
):
    dlg = QDialog(parent)
    dlg.setWindowTitle("Add tag")
    name_edit = QLineEdit()
    name_edit.setPlaceholderText("e.g. v0.0.0")
    desc_edit = QTextEdit()
    desc_edit.setPlaceholderText("Optional")
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

    desc_raw = desc_edit.toPlainText().strip()
    description = desc_raw if desc_raw else None

    if dep is None:
        return dependency, name, description
    else:
        return name, description