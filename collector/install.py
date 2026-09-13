"""One-command, cross-platform installer for a local cc-statusboard checkout.

It owns the setup that should not leak into user instructions: editable
installation and a persistent user PATH entry for the generated console script.
Windows uses the user Environment registry key; POSIX systems receive an
idempotent entry in the default shell's startup configuration.
"""

from __future__ import annotations

import ctypes
import os
import shlex
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MARKER = "# Added by cc-statusboard installer"


def _user_scripts_dir() -> Path:
    scheme = "nt_user" if sys.platform == "win32" else "posix_user"
    path = sysconfig.get_path("scripts", scheme=scheme)
    if not path:
        raise RuntimeError("Python could not determine the user Scripts directory")
    return Path(path)


def _install_editable(project_root: Path) -> None:
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "--user", "--upgrade",
        "--editable", str(project_root),
    ])


def _add_windows_user_path(scripts_dir: Path) -> bool:
    """Add ``scripts_dir`` to the Windows user PATH once."""
    import winreg

    target = os.path.normcase(os.path.normpath(str(scripts_dir)))
    access = winreg.KEY_READ | winreg.KEY_SET_VALUE
    # A 32-bit Python on 64-bit Windows otherwise writes the redirected HKCU
    # view, while new 64-bit terminals read the native Environment key.
    access |= getattr(winreg, "KEY_WOW64_64KEY", 0)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, "Environment", 0, access) as key:
        try:
            current, value_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current, value_type = "", winreg.REG_EXPAND_SZ
        entries = [entry for entry in str(current).split(";") if entry]
        known = {
            os.path.normcase(os.path.normpath(os.path.expandvars(entry)))
            for entry in entries
        }
        if target in known:
            return False
        winreg.SetValueEx(key, "Path", 0, value_type,
                          ";".join([*entries, str(scripts_dir)]))

    # Notify Explorer without failing a remote/headless installation.
    try:
        result = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000,
            ctypes.byref(result),
        )
    except OSError:
        pass
    return True


def _posix_config_files(home: Path) -> List[tuple[Path, bool]]:
    """Return profile files for the default shell, plus the portable profile."""
    shell = Path(os.environ.get("SHELL", "")).name
    files: List[tuple[Path, bool]] = [(home / ".profile", False)]
    if shell == "bash":
        files.extend([(home / ".bashrc", False), (home / ".bash_profile", False)])
    elif shell == "zsh":
        files.extend([(home / ".zshrc", False), (home / ".zprofile", False)])
    elif shell == "fish":
        files.append((home / ".config" / "fish" / "config.fish", True))
    return files


def _add_posix_user_path(scripts_dir: Path) -> List[Path]:
    """Persist PATH setup for the user's default POSIX shell, idempotently."""
    changed: List[Path] = []
    quoted = shlex.quote(str(scripts_dir))
    for config, is_fish in _posix_config_files(Path.home()):
        line = (f"set -gx PATH {quoted} $PATH" if is_fish
                else f"export PATH={quoted}:$PATH")
        try:
            text = config.read_text(encoding="utf-8")
        except FileNotFoundError:
            text = ""
        if _MARKER in text and str(scripts_dir) in text:
            continue
        config.parent.mkdir(parents=True, exist_ok=True)
        with config.open("a", encoding="utf-8", newline="\n") as f:
            if text and not text.endswith("\n"):
                f.write("\n")
            f.write(f"{_MARKER}\n{line}\n")
        changed.append(config)
    return changed


def main() -> int:
    _install_editable(PROJECT_ROOT)
    scripts_dir = _user_scripts_dir()
    if sys.platform == "win32":
        changed = _add_windows_user_path(scripts_dir)
        path_status = "Added to" if changed else "Already present in"
        print(f"\n{path_status} your user PATH: {scripts_dir}")
    else:
        changed_files = _add_posix_user_path(scripts_dir)
        if changed_files:
            print("\nConfigured PATH in: " + ", ".join(map(str, changed_files)))
        else:
            print(f"\nAlready present in your shell PATH setup: {scripts_dir}")
    print("cc-statusboard installed in editable mode.")
    print("Open a new terminal, then run: cc-statusboard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
