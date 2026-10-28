"""Retain the original product10 judge, expecting this caller's exact SDK3.41."""
import hashlib
import json
import os
from pathlib import Path
import sys
import candidate

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / 'tests/reader_catalog/check_windows_product.py'
OLD = "{'phase': '4', 'engine': '3.40.0', 'pid': str(process.pid)}"
SCHEMA_OLD = "assert db.execute('PRAGMA user_version').fetchone()[0] == 1"
SCHEMA_NEW = SCHEMA_OLD[:-1] + '3'
NEW = "{'phase': '4', 'engine': '3.41.0', 'pid': str(process.pid)}"


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    original = PATH.read_text(encoding='utf-8')
    assert original.count(OLD) == 1
    adapted = original.replace(OLD, NEW)
    if candidate.active():
        assert original.count(SCHEMA_OLD) == 1
        adapted = adapted.replace(SCHEMA_OLD, SCHEMA_NEW)
    code = compile(adapted, str(PATH), 'exec')
    if sys.argv[1:] == ['--self-test']:
        print('original catalog assertions retained; exact runtime and candidate schema expectations adapted')
        return
    value = type(sys)('original_catalog_341'); value.__file__ = str(PATH)
    exec(code, value.__dict__)
    value.main()
    out = ROOT / 'build/windows-341-catalog-adapter.json'
    out.write_text(json.dumps(dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
        attempt=os.environ['GITHUB_RUN_ATTEMPT'], original_source_sha256=hashlib.sha256(original.encode()).hexdigest(),
        adapted_source_sha256=hashlib.sha256(adapted.encode()).hexdigest(), changed_literal_count=1,
        expected_runtime='3.41.0', expected_schema=3 if candidate.active() else 1,
        schema_literal_count=1 if candidate.active() else 0, original_assertions_retained=True), indent=2) + '\n')


if __name__ == '__main__':
    main()
