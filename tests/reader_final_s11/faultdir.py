#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real operating-system fault injection for the S11 import regression.

Two fault classes are produced with the operating system itself and never by
patching the modules under test:

  * a genuinely read-only directory (POSIX mode bits, Windows ACL deny), and
  * a genuinely bounded volume (a Linux tmpfs mounted at a fixed size).

Every helper returns {"supported": bool, "detail": str}. When the platform cannot
provide the fault the helper says so and the judge records the row as pending
with that exact reason instead of a pass. Nothing here fakes a failure: each
fault is proven by trying to write through it before it is used.
"""
import os
import subprocess
import sys
from pathlib import Path

PROBE_NAME = "s11-fault-probe.bin"


def _run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def _current_user():
    return os.environ.get("USERNAME") or os.environ.get("USER") or "runner"


def write_denied(path):
    """True when creating a file in path is refused right now."""
    probe = Path(path) / PROBE_NAME
    try:
        with open(probe, "wb") as handle:
            handle.write(b"x")
    except OSError:
        return True
    finally:
        try:
            probe.unlink()
        except OSError:
            pass
    return False


def make_readonly(path):
    """Make an existing directory refuse new files; prove it."""
    path = Path(path)
    if not path.is_dir():
        return {"supported": False, "detail": "not a directory: " + str(path)}
    if os.name == "nt":
        user = _current_user()
        ok, detail = _run(["icacls", str(path), "/deny", user + ":(WD,AD)"])
        if not ok:
            return {"supported": False, "detail": "icacls deny failed: " + detail}
        if not write_denied(path):
            _run(["icacls", str(path), "/remove:d", user])
            return {"supported": False, "detail": "write still allowed after ACL deny"}
        return {"supported": True, "detail": "icacls deny " + user + ":(WD,AD)"}
    mode = path.stat().st_mode & 0o7777
    path.chmod(mode & 0o555)
    if not write_denied(path):
        path.chmod(mode)
        return {"supported": False, "detail": "write still allowed after chmod " + oct(mode & 0o555)}
    return {"supported": True, "detail": "chmod " + oct(mode & 0o555), "mode": mode}


def restore_writable(path, record):
    """Undo make_readonly using the record it returned."""
    path = Path(path)
    if os.name == "nt":
        _run(["icacls", str(path), "/remove:d", _current_user()])
    else:
        mode = record.get("mode", 0o700)
        path.chmod(mode)
    if write_denied(path):
        return {"restored": False, "detail": "directory still refuses writes"}
    return {"restored": True, "detail": "writable again"}


def mount_tmpfs(path, kib=256):
    """Mount a bounded tmpfs and prove the bound with a real ENOSPC."""
    path = Path(path)
    if sys.platform != "linux":
        return {"supported": False,
                "detail": "a fixed-size volume needs root mount; available on Linux only"}
    path.mkdir(parents=True, exist_ok=True)
    ok, detail = _run(["sudo", "-n", "mount", "-t", "tmpfs", "-o",
                       "size=" + str(kib) + "k,mode=0700", "tmpfs", str(path)])
    if not ok:
        return {"supported": False, "detail": "tmpfs mount failed: " + detail}
    probe = path / "s11-capacity-probe.bin"
    try:
        with open(probe, "wb") as handle:
            handle.write(b"x" * ((kib + 64) * 1024))
    except OSError as exc:
        try:
            probe.unlink()
        except OSError:
            pass
        return {"supported": True, "kib": kib,
                "detail": str(kib) + " KiB tmpfs, ENOSPC proven: " + str(exc)}
    try:
        probe.unlink()
    except OSError:
        pass
    _run(["sudo", "-n", "umount", str(path)])
    return {"supported": False, "detail": "bounded tmpfs accepted more than its size"}


def remount_tmpfs(path, kib):
    ok, detail = _run(["sudo", "-n", "mount", "-o", "remount,size=" + str(kib) + "k", str(path)])
    return {"ok": ok, "detail": detail or str(kib) + " KiB"}


def unmount_tmpfs(path):
    return _run(["sudo", "-n", "umount", "-l", str(path)])
