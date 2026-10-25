"""Actions-only supported physical display mode selection for unchanged old UI tests."""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import time


class DISPLAY(C.Structure):
    _fields_ = [('position', W.POINT), ('orientation', W.DWORD), ('fixed_output', W.DWORD)]


class MODE_UNION(C.Union):
    _fields_ = [('display', DISPLAY), ('printer_bytes', C.c_byte * 16)]


class MODE(C.Structure):
    _fields_ = [('device', W.WCHAR * 32), ('spec_version', W.WORD), ('driver_version', W.WORD),
                ('size', W.WORD), ('driver_extra', W.WORD), ('fields', W.DWORD), ('variant', MODE_UNION),
                ('color', C.c_short), ('duplex', C.c_short), ('y_resolution', C.c_short),
                ('tt_option', C.c_short), ('collate', C.c_short), ('form', W.WCHAR * 32),
                ('log_pixels', W.WORD), ('bits', W.DWORD), ('width', W.DWORD), ('height', W.DWORD),
                ('display_flags', W.DWORD), ('frequency', W.DWORD), ('icm_method', W.DWORD),
                ('icm_intent', W.DWORD), ('media_type', W.DWORD), ('dither_type', W.DWORD),
                ('reserved1', W.DWORD), ('reserved2', W.DWORD), ('panning_width', W.DWORD),
                ('panning_height', W.DWORD)]


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and os.name == 'nt'
    assert C.sizeof(MODE) == 220
    user = C.WinDLL('user32', use_last_error=True)
    user.EnumDisplaySettingsW.argtypes = [W.LPCWSTR, W.DWORD, C.POINTER(MODE)]
    user.EnumDisplaySettingsW.restype = W.BOOL
    user.ChangeDisplaySettingsExW.argtypes = [W.LPCWSTR, C.POINTER(MODE), W.HWND, W.DWORD, C.c_void_p]
    user.ChangeDisplaySettingsExW.restype = W.LONG
    user.SystemParametersInfoW.argtypes = [W.UINT, W.UINT, C.c_void_p, W.UINT]
    user.SystemParametersInfoW.restype = W.BOOL

    def current():
        mode = MODE()
        mode.size = C.sizeof(mode)
        assert user.EnumDisplaySettingsW(None, 0xFFFFFFFF, C.byref(mode))
        return mode

    def fields(mode):
        return dict(width=mode.width, height=mode.height, bits=mode.bits, frequency=mode.frequency)

    before = current()
    supported = []
    for index in range(1024):
        mode = MODE()
        mode.size = C.sizeof(mode)
        if not user.EnumDisplaySettingsW(None, index, C.byref(mode)):
            break
        supported.append(mode)
    assert supported, 'no actual supported display mode enumerated'
    candidates = sorted((m for m in supported if m.width >= 1280 and m.height >= 900 and m.bits >= 24),
                        key=lambda m: (m.width * m.height, -m.bits, m.frequency))
    report = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], before=fields(before),
                  supported_modes=[fields(m) for m in supported], attempts=[], accepted=False)
    try:
        if before.width < 1280 or before.height < 900:
            for mode in candidates:
                mode.fields = 0x40000 | 0x80000 | 0x100000
                test = user.ChangeDisplaySettingsExW(None, C.byref(mode), None, 2, None)
                result = user.ChangeDisplaySettingsExW(None, C.byref(mode), None, 0, None) if test == 0 else None
                report['attempts'].append(dict(mode=fields(mode), native_test_return=test,
                                               native_apply_return=result, actual_readback=fields(current())))
                actual = current()
                if result == 0 and actual.width >= 1280 and actual.height >= 900:
                    break
        actual = current()
        area = W.RECT()
        deadline = time.monotonic() + 10
        while True:
            actual = current()
            assert user.SystemParametersInfoW(0x30, 0, C.byref(area), 0)
            if area.right - area.left >= 1060 and area.bottom - area.top >= 660 or time.monotonic() >= deadline:
                break
            time.sleep(.1)
        report['actual_mode'] = fields(actual)
        report['actual_work_area'] = [area.left, area.top, area.right, area.bottom]
        assert actual.width >= 1280 and actual.height >= 900 and area.right - area.left >= 1060 and area.bottom - area.top >= 660, 'runner cannot provide a real supported display for the unchanged original compact22 minimum assertions'
        report['accepted'] = True
    finally:
        folder = Path('build/native-owner-preflight')
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'display.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
