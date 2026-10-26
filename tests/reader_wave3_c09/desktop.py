"""Actions-only: configure a supported desktop mode for the unchanged compact UI geometry."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path


class Display(C.Structure):
    _fields_ = [('position', W.POINT), ('orientation', W.DWORD), ('fixed_output', W.DWORD)]


class Settings(C.Structure):
    _fields_ = [('device', W.WCHAR * 32), ('spec', W.WORD), ('driver', W.WORD),
                ('size', W.WORD), ('extra', W.WORD), ('fields', W.DWORD), ('display', Display),
                ('color', C.c_short), ('duplex', C.c_short), ('y_resolution', C.c_short),
                ('tt_option', C.c_short), ('collate', C.c_short), ('form', W.WCHAR * 32),
                ('log_pixels', W.WORD), ('bits', W.DWORD), ('width', W.DWORD), ('height', W.DWORD),
                ('flags', W.DWORD), ('frequency', W.DWORD), ('icm_method', W.DWORD),
                ('icm_intent', W.DWORD), ('media', W.DWORD), ('dither', W.DWORD),
                ('reserved1', W.DWORD), ('reserved2', W.DWORD),
                ('panning_width', W.DWORD), ('panning_height', W.DWORD)]


def main():
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    user = C.WinDLL('user32', use_last_error=True)
    user.EnumDisplaySettingsW.argtypes = [W.LPCWSTR, W.DWORD, C.POINTER(Settings)]
    user.EnumDisplaySettingsW.restype = W.BOOL
    user.ChangeDisplaySettingsExW.argtypes = [W.LPCWSTR, C.POINTER(Settings), W.HWND, W.DWORD, W.LPVOID]
    user.ChangeDisplaySettingsExW.restype = W.LONG
    current = Settings(size=C.sizeof(Settings))
    assert user.EnumDisplaySettingsW(None, 0xffffffff, C.byref(current))
    report = dict(before=[current.width, current.height], attempts=[], accepted=False)
    try:
        if current.width < 1280 or current.height < 800:
            candidates = []
            index = 0
            while True:
                mode = Settings(size=C.sizeof(Settings))
                if not user.EnumDisplaySettingsW(None, index, C.byref(mode)):
                    break
                if mode.width >= 1280 and mode.height >= 800 and mode.bits >= 24:
                    candidates.append(mode)
                index += 1
            # The remote display driver can accept an explicit mode even when
            # its enumerated list exposes only the initial hosted-runner size.
            requested = Settings.from_buffer_copy(current)
            requested.width, requested.height = 1280, 800
            requested.fields = 0x00080000 | 0x00100000
            candidates.sort(key=lambda m: (m.width * m.height, -m.bits))
            candidates.append(requested)
            for mode in candidates:
                tested = user.ChangeDisplaySettingsExW(None, C.byref(mode), None, 2, None)
                changed = user.ChangeDisplaySettingsExW(None, C.byref(mode), None, 0, None) if tested == 0 else None
                report['attempts'].append(dict(width=mode.width, height=mode.height, test=tested, change=changed))
                if changed == 0:
                    break
        after = Settings(size=C.sizeof(Settings))
        assert user.EnumDisplaySettingsW(None, 0xffffffff, C.byref(after))
        report['after'] = [after.width, after.height]
        report['accepted'] = after.width >= 1280 and after.height >= 800
        assert report['accepted'], report
    finally:
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
