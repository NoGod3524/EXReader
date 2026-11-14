# SPDX-License-Identifier: MIT
"""Current-source model evidence; never grants iPad UI or physical-device acceptance."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('c06_checks', ROOT / 'tests/reader_next_c06/run.py')
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    # Reuse the independent JSON/wire/database judges, not the historical runner's
    # source-freeze guards or its unrelated old-source/platform acceptance.
    result = {'scope': 'current-source shared raw3 annotation model', 'passed': False,
              'source': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'actions': os.environ.get('GITHUB_ACTIONS') == 'true',
              'host_ui_verified': False, 'physical_device_verified': False}
    try:
        checks.OUT = Path(tempfile.mkdtemp(prefix='exchange-', dir=args.output))
        result['artifacts'] = str(checks.OUT.resolve())
        checks.legacy_phase('off', args.probe.resolve(), checks.OUT / 'legacy-off')
        pdf = ROOT / 'tests/fixtures/pdf-public-text.pdf'
        checks.expect(checks.sha(pdf) == checks.PDF_SHA, 'fixed PDF fixture SHA-256')
        hashes, _ = checks.raw_phase(args.probe.resolve(), args.probe.resolve(), pdf, checks.OUT / 'raw')
        result.update(passed=True, exported_sha256=hashes)
    finally:
        result.update(checks=checks.CHECKS, failed=checks.FAILED, count=len(checks.CHECKS))
        (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(f"DFINAL-C annotation model: {len(checks.CHECKS)} checks, passed={result['passed']}")


if __name__ == '__main__':
    main()
