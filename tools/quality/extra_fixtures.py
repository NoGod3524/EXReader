"""Exercise typed fixtures which are not ordinary document/image/font extensions."""
import ctypes as c
import json
import os
from pathlib import Path
import shutil
import subprocess

from measure import ROOT, regression, progress, write_json

OUT = ROOT / 'evidence/quality-20261108'
BUILD = OUT / 'local/coverage-build'


def main():
    os.environ['GCOV_PREFIX'] = str(OUT / 'local/runtime-coverage/x')
    os.environ['GCOV_PREFIX_STRIP'] = str(len(BUILD.parts))
    sdk = regression.SDK(BUILD / 'libexreader.dll')
    local = OUT / 'local/extra-fixtures'
    local.mkdir(parents=True, exist_ok=True)
    rows = []

    def bind(name, restype, *argtypes):
        function = getattr(sdk.dll, 'exr_' + name)
        function.restype, function.argtypes = restype, argtypes
        return function

    for relative in ('sample.txt', 'utf16.txt', 'font-cff-regression.bin', 'font-image-regression.bin',
                     'fuzz-cbz-truncated.bin', 'foreign.sqlite', 'future.sqlite',
                     'audio/pcm.wav', 'audio/metadata.m4b', 'font_manager/fonts.conf'):
        path = ROOT / 'tests/fixtures' / relative
        row = dict(file=path.relative_to(ROOT).as_posix(), sha256=regression.file_hash(path))
        pointer, error = c.c_void_p(), regression.Error()
        err, outptr = c.POINTER(regression.Error), c.POINTER(c.c_void_p)
        if relative.endswith('.txt') or relative.startswith('fuzz-cbz'):
            probe_path = path
            if relative.endswith('.bin'):
                probe_path = local / 'fuzz-cbz-truncated.cbz'
                shutil.copyfile(path, probe_path)
            command = [str(BUILD / 'exreader-check-document.exe'), str(probe_path),
                       str(ROOT / 'tests/fixtures/fonts/primary.ttf')]
            result = subprocess.run(command, capture_output=True, timeout=60, encoding='utf-8', errors='replace')
            probe = json.loads(result.stdout)
            row.update(kind='document', exit_code=result.returncode, probe=probe, stderr=result.stderr,
                       outcome='complete' if probe['complete'] else 'sdk_rejected')
        elif relative.startswith('font-'):
            code = sdk.font_open(str(path).encode(), c.byref(pointer), c.byref(error))
            sdk.font_free(pointer)
            row.update(kind='font', status=code, outcome='opened' if code == 0 else 'sdk_rejected')
        else:
            if relative.endswith('.sqlite'):
                copied = local / path.name
                shutil.copyfile(path, copied)
                open_fn = bind('library_open', c.c_int, c.c_char_p, outptr, err)
                code = open_fn(str(copied).encode(), c.byref(pointer), c.byref(error))
                bind('library_close', None, c.c_void_p)(pointer)
                kind = 'library'
            elif relative.endswith('.conf'):
                copied = local / 'tests/fixtures/font_manager'
                shutil.copytree(path.parent, copied, dirs_exist_ok=True)
                (local / 'build').mkdir(exist_ok=True)
                open_fn = bind('font_manager_open', c.c_int, c.c_char_p, outptr, err)
                code = open_fn(str(copied / path.name).encode(), c.byref(pointer), c.byref(error))
                bind('font_manager_free', None, c.c_void_p)(pointer)
                kind = 'font_configuration'
            elif relative.endswith('.m4b'):
                open_fn = bind('m4b_inspect', c.c_int, c.c_char_p, c.c_void_p, outptr, err)
                code = open_fn(str(path).encode(), None, c.byref(pointer), c.byref(error))
                bind('m4b_inspection_free', None, c.c_void_p)(pointer)
                kind = 'audio_metadata'
            else:
                class PCMInfo(c.Structure):
                    _fields_ = [('sample_rate', c.c_uint32), ('channels', c.c_uint32),
                                ('channel_mask', c.c_uint32), ('frames', c.c_uint64)]
                open_fn = bind('pcm_open', c.c_int, c.c_char_p, c.c_void_p, outptr, err)
                code = open_fn(str(path).encode(), None, c.byref(pointer), c.byref(error))
                total = 0
                if code == 0:
                    info = bind('pcm_format', c.POINTER(PCMInfo), c.c_void_p)(pointer).contents
                    samples = (c.c_float * (4096 * info.channels))()
                    read_fn = bind('pcm_read', c.c_int, c.c_void_p, c.c_uint64, c.c_size_t,
                                   c.POINTER(c.c_float), c.POINTER(c.c_size_t), c.c_void_p, err)
                    while total < info.frames:
                        count = c.c_size_t()
                        code = read_fn(pointer, total, min(4096, info.frames - total), samples,
                                       c.byref(count), None, c.byref(error))
                        if code or not count.value:
                            break
                        total += count.value
                    assert code or total == info.frames
                bind('pcm_free', None, c.c_void_p)(pointer)
                row['decoded_frames'] = total
                kind = 'audio'
            row.update(kind=kind, status=code, outcome='processed' if code == 0 else 'sdk_rejected')
        assert regression.file_hash(path) == row['sha256']
        rows.append(row)
        write_json(OUT / 'fixtures-extra.json', rows)
        progress(OUT, f'Extra fixture: {row["file"]}: {row["outcome"]}')


if __name__ == '__main__':
    main()
