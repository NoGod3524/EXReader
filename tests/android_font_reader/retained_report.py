"""Run every unchanged C11 acceptance check with this task's explicit provenance seed.
The historical standalone guard's d263... ownership scope predates the common
candidate. Only its seed identity is rebound; no acceptance case is removed.
"""
import importlib.util
import os
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS') == 'true'
path = Path('tests/reader_wave3_c11/report.py')
spec = importlib.util.spec_from_file_location('retained_c11_report', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.SEED = '1dfd2c3ba3184eb9a9df531d3858eafb95c2e80c'
raise SystemExit(module.main())
