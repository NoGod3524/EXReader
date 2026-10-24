# SPDX-License-Identifier: MIT
"""Run every original shelf assertion against one coherent native list snapshot.

The old helper reads LB_GETCOUNT then sends one message per row. A real shelf
refresh can replace that list between messages. Only retry observations whose
native mutation serial changed; a stable bad title remains a real failure.
"""
import ctypes as C
from ctypes import wintypes as W
import importlib.util
from pathlib import Path
import time


def main():
    source = Path(__file__).resolve().parents[1] / "windows_host" / "check_shelf_ui.py"
    spec = importlib.util.spec_from_file_location("retained_windows_shelf", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.U.GetPropW.argtypes = [W.HWND, W.LPCWSTR]
    module.U.GetPropW.restype = W.HANDLE

    def titles(self):
        box = self.control("books")
        before = int(module.U.GetPropW(box, "EXReaderShelfSnapshot") or 0)
        if not before or before & 1:
            raise TimeoutError("native shelf replacement is in progress")
        count = module.send(box, 0x18B)
        assert 0 <= count <= 150, count
        result, failed_row = [], None
        for index in range(count):
            value = C.create_unicode_buffer(1024)
            written = module.send(box, 0x189, index, C.addressof(value))
            if written == C.c_size_t(-1).value:
                failed_row = index
            result.append(value.value)
        after = int(module.U.GetPropW(box, "EXReaderShelfSnapshot") or 0)
        if after != before or after & 1:
            raise TimeoutError("native shelf changed during row observation")
        assert failed_row is None, ("stable native LB_GETTEXT failure", failed_row, before)
        return result

    def scroll(self, direction, wanted):
        box = self.control("books")
        # Exactly the original 320 iterations, eight wheel messages and delay.
        # A changing observation consumes an iteration; it never earns a pass.
        for _ in range(320):
            for _ in range(8):
                module.send(box, 0x20A, ((-120 if direction > 0 else 120) & 0xffff) << 16)
            time.sleep(.08)
            try:
                values = self.numbers()
                if values and wanted(values):
                    self.wait_idle()
                    return
            except TimeoutError:
                continue
        raise AssertionError("Native wheel traversal incomplete: " + repr(self.numbers()))

    module.Product.titles = titles
    module.Product.scroll = scroll
    module.main()  # All thirteen original named checks and report stay unchanged.


if __name__ == "__main__":
    main()
