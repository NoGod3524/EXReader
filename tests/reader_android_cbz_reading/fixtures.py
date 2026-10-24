"""Actions-only predeclared CBZ identities over the accepted deterministic writer."""
import json
import os
from pathlib import Path
import subprocess
import sys

assert os.environ.get('GITHUB_ACTIONS') == 'true'
folder = Path(sys.argv[1])
root = Path(__file__).resolve().parents[2]
subprocess.check_call([sys.executable, str(root / 'tests/reader_android_reading/fixtures.py'), str(folder)])
path = folder / 'manifest.json'
manifest = json.loads(path.read_text(encoding='utf-8'))
manifest['cbz_expected'] = {'page_ids': ['001.png', '002.png', '003.png'], 'rgb': [[40, 80, 215], [110, 80, 145], [180, 80, 75]],
                            'text_bytes': 0, 'text_regions': 0, 'plan_precedes_sdk_read': True,
                            'writer': 'tests/reader_reading_state/make_fixtures.py::cbz'}
path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
