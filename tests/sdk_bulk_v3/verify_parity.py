"""Keep every original acceptance scenario and budget in the v3 suite."""
import os
from pathlib import Path

assert os.environ.get('GITHUB_ACTIONS') == 'true'
root = Path(__file__).resolve().parents[2]
original = (root / 'tests/reader_bulk_organization/check_bulk.py').read_bytes()
candidate = (root / 'tests/sdk_bulk_v3/check_bulk_v3.py').read_bytes()
v1 = b"assert sql('PRAGMA user_version')[0][0] == 1 and sql('PRAGMA application_id')[0][0] == 1163416144"
v3 = v1.replace(b'== 1 and', b'== 3 and')
assert original.count(v1) == 1 and candidate.count(v3) == 1
assert original.replace(v1, v3) == candidate
print('All original checks and budgets retained; only expected schema version differs.')
