"""Bounded native automation, confined to the F05 driver."""
import os
import signal
import subprocess
import sys
import time

from check_linux_host import Session as OriginalSession, command


def reap_group(process, timeout=5):
    """Reap the child and require its whole process group to disappear."""
    deadline = time.monotonic() + timeout
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=max(.001, deadline - time.monotonic()))
    while True:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("clipboard process group remains")
        time.sleep(.02)


def paste(host, value):
    # -quiet keeps xclip in the foreground, in the group we own and reap.
    process = subprocess.Popen(["xclip", "-quiet", "-selection", "clipboard"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)
    primary = None
    try:
        process.stdin.write(value.encode())
        process.stdin.close()
        deadline = time.monotonic() + 5
        while True:
            if process.poll() is not None:
                raise RuntimeError("clipboard owner exited before paste")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("clipboard ownership deadline")
            result = subprocess.run(["xclip", "-o", "-selection", "clipboard"],
                capture_output=True, timeout=remaining)
            if result.returncode == 0 and result.stdout == value.encode():
                break
            time.sleep(.02)
        host.key("ctrl+v")
    except BaseException:
        primary = sys.exc_info()[1]
        raise
    finally:
        try:
            reap_group(process)
        except BaseException as error:
            if primary is None:
                raise
            primary.f05_cleanup_errors = [repr(error)]


class Session(OriginalSession):
    def paste(self, value):
        paste(self, value)

    def close(self):
        deadline = time.monotonic() + 20
        def run(*args):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("native close exceeded 20 seconds")
            return subprocess.run(list(map(str, args)), capture_output=True,
                text=True, timeout=remaining)
        try:
            if self.process and self.process.poll() is None:
                while True:
                    modal = run("xdotool", "search", "--onlyvisible", "--all",
                        "--pid", self.process.pid, "--name", "^Account and Sync$")
                    if modal.returncode == 1:
                        break
                    modal.check_returncode()
                    target = modal.stdout.splitlines()[-1]
                    run("xdotool", "windowactivate", "--sync", target).check_returncode()
                    run("xdotool", "key", "--clearmodifiers", "alt+F4").check_returncode()
                    time.sleep(.1)
                run("xdotool", "windowactivate", "--sync", self.window).check_returncode()
                run("xdotool", "key", "--clearmodifiers", "alt+F4").check_returncode()
                self.process.wait(timeout=max(.001, deadline - time.monotonic()))
            if self.process and self.process.returncode != 0:
                raise RuntimeError("Host close failed")
        finally:
            if self.log:
                self.log.close()
