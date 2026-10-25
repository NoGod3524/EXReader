"""Execute all original Windows judges under the common-source workflow identity."""
import importlib.util
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = '.github/workflows/reader-raw3-common-windows.yml'


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    sys.path.insert(0, str(ROOT / 'tests/reader_windows_compact'))
    spec = importlib.util.spec_from_file_location('common_windows_original_judge',
        ROOT / 'tests/reader_windows_compact/verify.py')
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    original.WORKFLOW = WORKFLOW
    original.main()


if __name__ == '__main__':
    main()
