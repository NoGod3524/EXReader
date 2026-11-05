"""Read actual failed legacy fixture without mutating it; Actions only."""
import json
import os
from pathlib import Path
import sqlite3

assert os.environ.get('GITHUB_ACTIONS') == 'true'
root = Path(__file__).resolve().parents[2]
db = root / 'build/wio-bulk-module/product.sqlite'
report = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
              old_judge='tests/reader_bulk_organization/check_bulk.py:135', old_expected_user_version=1, accepted=False)
try:
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as connection:
        report['actual_user_version'] = connection.execute('PRAGMA user_version').fetchone()[0]
        report['actual_application_id'] = connection.execute('PRAGMA application_id').fetchone()[0]
        report['books'] = connection.execute('SELECT count(*) FROM reader_books').fetchone()[0]
        report['schema_tables'] = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
except Exception as error:
    report['read_error'] = repr(error)
output = root / 'build/windows-341-guard/bulk-schema-diagnostic.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print('LEGACY_BULK_SCHEMA_DIAGNOSTIC '+json.dumps(report), flush=True)
