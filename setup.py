import subprocess
import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.editable_wheel import editable_wheel
from setuptools.command.install import install

SCRIPT = Path(__file__).resolve().parent / "scripts" / "install_system_deps.py"


def _run_system_deps_install() -> None:
    """Best-effort install of non-pip Qt system deps; never abort the install."""
    if not SCRIPT.exists():
        return
    try:
        subprocess.run([sys.executable, str(SCRIPT)], check=False)
    except OSError:
        pass


class PostInstallCommand(install):
    def run(self) -> None:
        install.run(self)
        _run_system_deps_install()


class PostEditableWheel(editable_wheel):
    def run(self) -> None:
        editable_wheel.run(self)
        _run_system_deps_install()


setup(
    cmdclass={
        "install": PostInstallCommand,
        "editable_wheel": PostEditableWheel,
    },
)
