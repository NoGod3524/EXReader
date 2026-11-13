"""Offline regression checks; never download or execute a product binary."""
import importlib.util
from pathlib import Path
import tempfile
import hashlib
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('f07', Path(__file__).resolve().parents[1] /
    'tools/f07_authoritative_symbols_20261103.py')
f07 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f07)


def main():
    blob = b'fixed artifact bytes'
    metadata = {'id': 123, 'expired': False, 'size_in_bytes': len(blob),
        'digest': 'sha256:' + hashlib.sha256(blob).hexdigest(),
        'workflow_run': {'id': int(f07.RUN_ID), 'head_sha': f07.SOURCE_SHA,
            'repository_id': f07.REPOSITORY_ID, 'head_repository_id': f07.REPOSITORY_ID}}
    assert f07.validate_artifact(metadata, 123, blob) == metadata['digest']
    for bad, data in ((dict(metadata, id=124), blob),
                      (dict(metadata, digest=None), blob), (metadata, blob + b'x'),
                      (dict(metadata, workflow_run=dict(metadata['workflow_run'], head_sha='bad')), blob)):
        try:
            f07.validate_artifact(bad, 123, data)
        except ValueError:
            pass
        else:
            raise AssertionError('unbound input accepted')
    c = f07.classify_nm('sqlite3_a T 10 4\n00000020 T _sqlite3_b\n'
                        '         U _sqlite3_c\nsqlite3_d w 0 0\n'
                        'sqlite3_e W 20 4\nsqlite3_f u 30 4\nsqlite3_g C 40 4\n')
    assert c['defined'] == ['sqlite3_a', 'sqlite3_b', 'sqlite3_e', 'sqlite3_f', 'sqlite3_g']
    assert c['undefined'] == ['sqlite3_c', 'sqlite3_d']
    assert c['weak_defined'] == ['sqlite3_e']
    assert c['weak_undefined'] == ['sqlite3_d']
    c = f07.classify_readobj('''Symbols [
  Symbol {
    Name: _sqlite3_a (1)
    Section: __text (0x1)
    RefType: UndefinedNonLazy (0x0)
    Flags [
      WeakDef (0x80)
    ]
  }
  Symbol {
    Name: _sqlite3_b (2)
    Section: Undefined (0x0)
    Binding: Weak (0x2)
  }
]
Section {
 Name: sqlite3_not_a_symbol
 Undefined Weak
}
''')
    assert c['defined'] == c['weak_defined'] == ['sqlite3_a']
    assert c['undefined'] == c['weak_undefined'] == ['sqlite3_b']
    with tempfile.NamedTemporaryFile() as payload:
        def success(cmd):
            return {'cmd': ' '.join(cmd), 'rc': 0, 'out': 'Sections [\n]', 'stderr': ''}
        with patch.object(f07, 'run', side_effect=success):
            e = f07.analyse_payload('gtk', 'elf', payload.name)
            assert e['operations_complete'] and e['version_assessed']
            assert e['version_info_present'] is False
            e = f07.analyse_payload('macos', 'macho', payload.name)
            assert e['version_info_present'] is None
            assert not any('-m' in op['cmd'].split() for op in e['operations'])
            assert any('--symbols' in op['cmd'] for op in e['operations'])
        def versioned(cmd):
            return {'cmd': ' '.join(cmd), 'rc': 0,
                    'out': 'Name: .gnu.version_r (12)\n', 'stderr': ''}
        with patch.object(f07, 'run', side_effect=versioned):
            assert f07.analyse_payload('gtk', 'elf', payload.name)['version_info_present'] is True
        for result in ({'rc': 1, 'out': 'sqlite3_false T 0 0'},
                       {'rc': None, 'timeout': True}):
            with patch.object(f07, 'run', return_value=result):
                e = f07.analyse_payload('macos', 'macho', payload.name)
                assert not e['operations_complete'] and not e['weak_assessed']
                assert e['sqlite_counts']['defined'] == 0
    print('F07 offline regression checks passed')


if __name__ == '__main__':
    main()
