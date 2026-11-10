"""Check document drift, missing/renamed exports and explicit additions policy."""
import json
from pathlib import Path
import tempfile

from check_abi import check, load_baseline
from test_check_exports import macho


def main():
    assert load_baseline()
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        doc, contract, binary = (directory / name for name in ('ABI.md', 'contract.json', 'sdk.dylib'))
        doc.write_text('| `exr_one` | `void exr_one(void);` |\n', encoding='utf-8')
        contract.write_text(json.dumps({'symbols': ['exr_one']}), encoding='utf-8')
        options = {'abi_doc': doc, 'contract': contract}
        binary.write_bytes(macho([('exr_one', 0xf)]))
        assert check(binary, **options)['passed']
        binary.write_bytes(macho([('exr_renamed', 0xf)]))
        report = check(binary, added_reason='intentional additions', **options)
        assert not report['passed'] and report['slices'][0]['missing'] == ['exr_one']
        binary.write_bytes(macho([('exr_one', 0xf), ('exr_two', 0xf)]))
        assert not check(binary, **options)['passed']
        report = check(binary, added_reason='exr_two is an intentional additive API', **options)
        assert report['passed'] and report['slices'][0]['added_count'] == 1
        contract.write_text(json.dumps({'symbols': ['exr_one', 'exr_two']}), encoding='utf-8')
        report = check(binary, added_reason='documented addition', **options)
        assert report['contract_additions'] == ['exr_two'] and report['baseline_count'] == 1
        contract.write_text(json.dumps({'symbols': ['exr_two']}), encoding='utf-8')
        try:
            load_baseline(doc, contract)
        except ValueError as error:
            assert 'missing' in str(error)
        else:
            raise AssertionError('stale baseline accepted')
        binary.write_bytes(b'not a binary')
        contract.write_text(json.dumps({'symbols': ['exr_one']}), encoding='utf-8')
        try:
            check(binary, **options)
        except ValueError:
            pass
        else:
            raise AssertionError('malformed binary accepted')
    print('PASS consumer ABI: baseline drift, renamed/missing, added policy, malformed binary')


if __name__ == '__main__':
    main()
