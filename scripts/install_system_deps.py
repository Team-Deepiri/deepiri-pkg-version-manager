#!/usr/bin/env python3
"""Install system packages required by deepiri-pkg-version-manager.

PySide6's Qt xcb platform plugin needs a set of X11/xcb shared libraries that
are not pip-installable. On Debian/Ubuntu (including WSL) they are shipped as
apt packages. This script detects which are missing and installs them so that
``dtm graph`` and ``dtm display`` work out of the box.

Best-effort: failures never abort the pip install that invoked this script,
but a clear message is printed with the manual command to run.

Run directly:  python scripts/install_system_deps.py
"""

import shutil
import subprocess
import sys

APT_PACKAGES = [
    "libxcb-cursor0",
    "libxcb-icccm4",
    "libxcb-keysyms1",
    "libxcb-image0",
    "libxcb-render-util0",
    "libxcb-xinerama0",
    "libxcb-xkb1",
    "libxkbcommon-x11-0",
]


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _is_debian_like() -> bool:
    return shutil.which("apt-get") is not None


def _installed(lib: str) -> bool:
    dpkg = shutil.which("dpkg")
    if not dpkg:
        return False
    try:
        result = subprocess.run(
            [dpkg, "-s", lib],
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return result.returncode == 0 and "Status: install ok installed" in result.stdout


def _missing_packages() -> list[str]:
    return [pkg for pkg in APT_PACKAGES if not _installed(pkg)]


def _sudo_prefix() -> list[str]:
    if shutil.which("sudo") is not None and not _is_root():
        return ["sudo"]
    return []


def _is_root() -> bool:
    try:
        import os

        return os.geteuid() == 0
    except (AttributeError, OSError):
        return False


def _install_packages(packages: list[str]) -> bool:
    cmd = _sudo_prefix() + [
        "apt-get",
        "install",
        "-y",
        "--no-install-recommends",
        *packages,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        print(f"[dtm] apt-get failed to start: {exc}")
        return False

    if result.returncode == 0:
        return True

    print(f"[dtm] apt-get exited with code {result.returncode}:")
    if result.stderr.strip():
        print(result.stderr.strip()[:2000])
    return False


def main() -> int:
    if not _is_linux():
        print("[dtm] Non-Linux platform, skipping Qt system dependency install")
        return 0

    if not _is_debian_like():
        print(
            "[dtm] No apt-get found; install the equivalent of these packages for "
            "PySide6 xcb support: " + ", ".join(APT_PACKAGES)
        )
        return 0

    missing = _missing_packages()
    if not missing:
        print("[dtm] All Qt system dependencies already installed")
        return 0

    print("[dtm] Installing missing Qt system dependencies: " + ", ".join(missing))
    if _install_packages(missing):
        still_missing = _missing_packages()
        if still_missing:
            print("[dtm] Some packages still missing: " + ", ".join(still_missing))
            return 1
        print("[dtm] Qt system dependencies installed")
        return 0

    manual = " ".join(_sudo_prefix() + ["apt-get", "install", "-y", *missing])
    print(
        "\n[dtm] Could not install Qt system dependencies automatically.\n"
        f"[dtm] Run manually:  {manual}\n"
        "[dtm] Until installed, dtm graph/display fall back to a headless "
        "platform when QT_QPA_PLATFORM is set to offscreen or minimal."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
