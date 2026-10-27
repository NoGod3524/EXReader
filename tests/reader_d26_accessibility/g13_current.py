"""Run the retained G13 assertions unchanged with honest current SDK metadata.

Only the report's three source/version metadata constants are rebound. No check,
threshold, observation, fixture, event, name lookup or result is replaced.
Historical files and failure reports remain untouched.
"""
import os
from pathlib import Path
import runpy
import sys

assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
root = Path(__file__).resolve().parents[2]
original = root / 'tests/reader_a11y_gtk'
sys.path.insert(0, str(original))
import expectations

expectations.START_SHA = '2f215f5793a7344d22db350276ba9f8a07abe86f'
expectations.SDK_SHA = os.environ['GITHUB_SHA']
expectations.SDK_VERSION = '3.41.0'
kind = sys.argv.pop(1)
assert kind in ('audit', 'gate')
script = original / ('audit_gtk_a11y.py' if kind == 'audit' else 'check_a11y_report.py')
sys.argv[0] = str(script)
runpy.run_path(str(script), run_name='__main__')
