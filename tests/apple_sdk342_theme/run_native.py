#!/usr/bin/env python3
"""Actions-only, version-bound copy of the unchanged native theme assertions."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    source = ROOT / 'tests/apple_host/page_theme/run_native.py'
    original = source.read_text()
    replacements = [("report['sdk'] == '3.41.0'", "report['sdk'] == '3.42.0'"),
                    ("'sdk_version': '3.41.0'", "'sdk_version': '3.42.0'"),
                    ("'sdk_source': 'edddc463c06ed5731195cdb8f06b2df6dff7699e'", "'sdk_source': os.environ['GITHUB_SHA']")]
    derived = original
    for before, after in replacements:
        assert derived.count(before) == 1, before
        derived = derived.replace(before, after, 1)
    candidate = source.with_name('run_native_sdk342_candidate.py')
    assert not candidate.exists()
    candidate.write_text(derived)
    out = ROOT / 'build/apple-sdk342-theme'; out.mkdir(parents=True, exist_ok=True)
    (out / 'original-run-native.py').write_text(original)
    (out / 'derived-run-native.py').write_text(derived)
    sdk = ROOT / 'build/apple-sdk342/macos/sdk'
    subprocess.run([sys.executable, 'tools/build_apple_product.py', '--sdk', str(sdk), '--sdk-version', '3.42.0',
                    '--target', 'macos', '--build', str(out / 'legacy-products')], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(candidate), '--sdk', str(sdk), '--resources', str(out / 'resources'),
                    '--output', str(out / 'native')], cwd=ROOT, check=True)
    value = json.loads((out / 'native/native.json').read_text())
    assert value['accepted'] and value['sdk_version'] == '3.42.0' and value['sdk_source'] == os.environ['GITHUB_SHA']
    assert value['source_sha'] == os.environ['GITHUB_SHA'] and value['run_id'] == os.environ['GITHUB_RUN_ID'] and value['attempt'] == os.environ['GITHUB_RUN_ATTEMPT']
    assert value['original_on_off_exact'] and len(value['reports']['off']['checks']) == 10 and len(value['reports']['on']['checks']) == 37
    provenance = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                  'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'original_sha256': hashlib.sha256(original.encode()).hexdigest(),
                  'derived_sha256': hashlib.sha256(derived.encode()).hexdigest(), 'only_replacements': replacements,
                  'sdk_content_candidate': '8357eafa28423a7ab93ba08b823af80f01ad1505',
                  'old_checks': 10, 'new_checks': 37, 'page_theme_ui_accepted': False, 'physical_device': False}
    (out / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print(json.dumps(provenance), flush=True)

if __name__ == '__main__': main()
