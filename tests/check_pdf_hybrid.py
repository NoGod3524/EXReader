"""Validate manifest integrity and public rendering, rejecting unexpected diagnostics."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def check(executable, directory, name):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    entry = next(e for e in manifest if e['file'] == name)
    data = (directory / name).read_bytes()
    assert len(data) == entry['bytes']
    assert hashlib.sha256(data).hexdigest() == entry['sha256']
    print(f"file={name} bytes={len(data)} sha256={entry['sha256']}", flush=True)
    result = subprocess.run([executable, str(directory / name), str(entry['pages']),
                             str(entry.get('encrypt_conflicts', 0)), entry.get('security', 'plain')],
                            capture_output=True, text=True)
    print(result.stdout, end='')
    print(result.stderr, end='', file=sys.stderr)
    assert result.returncode == 0, f'renderer exit={result.returncode}'
    conflicts = entry.get('encrypt_conflicts', 0)
    allowed_conflict = 'PDF warning: hybrid /Encrypt conflict; using classic trailer /Encrypt'
    lines = result.stderr.splitlines()
    assert lines.count(allowed_conflict) == conflicts * 2  # parser probe and public open
    for line in lines:
        assert line == allowed_conflict or re.fullmatch(r'.*(?:font fallback|missing glyph).*', line, re.I), line
    if entry['pages'] > 0:
        evidence = re.search(r'parser discovered /XRefStm offset=(\d+) sections=(\d+)', result.stdout)
        assert evidence
        offset = int(evidence[1])
        assert re.match(rb'\d+ 0 obj\s*<<\s*/(?:Length\s+\d+\s+/)?Type\s*/XRef', data[offset:])
        if 'xrefstm' in entry:
            assert offset == entry['xrefstm'] and entry['hybrid'] and entry['has_xrefstm']
        pages = re.findall(r'^page=(\d+) status=0 .*nonwhite_pixels=(\d+)$', result.stdout, re.M)
        assert [int(p) for p, _ in pages] == list(range(1, entry['pages'] + 1))
        assert all(int(ink) > 0 for _, ink in pages)
        if name == 'incremental.pdf':
            assert 'width=120 height=120' in result.stdout  # latest revision, not old 200x200 page
        if name == 'encrypted-conflict.pdf':
            # Same dictionary identity must decrypt successfully without a warning.
            consistent = data.replace(b'/Encrypt 8 0 R', b'/Encrypt 7 0 R')
            assert consistent != data and len(consistent) == len(data)
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / 'consistent.pdf'
                path.write_bytes(consistent)
                same = subprocess.run([executable, str(path), '1', '0', 'encrypted'],
                                      capture_output=True, text=True)
                assert same.returncode == 0 and not same.stderr, same.stdout + same.stderr
                assert 'rendered=1 failures=0' in same.stdout
            print('same /Encrypt identity: status=0 warnings=0 rendered=1')


if __name__ == '__main__':
    check(*sys.argv[1:])
