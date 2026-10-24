"""Reuse the original strict verifiers with this explicit caller identity."""
import importlib.util
import os
from pathlib import Path
import sys

WORKFLOW = '.github/workflows/reader-hosts-integration.yml'
ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mode = sys.argv.pop(1)
if mode == 'windows':
    original = load('host_windows_navigation_verifier', ROOT / 'reader_windows_navigation/verify.py')
    if sys.argv[1:] == ['--protocol-selftest']:
        assert os.environ.get('GITHUB_ACTIONS') == 'true'
        print(original.self_test())
    else:
        original.main(workflow_path=WORKFLOW)
elif mode == 'composition':
    original = load('host_composition_verifier', ROOT / 'reader_g1_integration/aggregate.py')
    original.original.WORKFLOW = WORKFLOW
    raise SystemExit(original.main())
else:
    raise ValueError('unknown integration verifier: ' + mode)
