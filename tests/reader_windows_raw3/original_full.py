"""Run the unchanged compact/full341 judges under this wrapper's workflow ID."""
import importlib.util
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = '.github/workflows/reader-windows-raw3-original-full.yml'


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    sys.path.insert(0, str(ROOT / 'tests/reader_windows_compact'))
    spec = importlib.util.spec_from_file_location('raw3_original_compact_verify',
        ROOT / 'tests/reader_windows_compact/verify.py')
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    original.WORKFLOW = WORKFLOW
    original.main()  # The original compact verifier itself invokes full341/F3/atomic13.


if __name__ == '__main__':
    main()
