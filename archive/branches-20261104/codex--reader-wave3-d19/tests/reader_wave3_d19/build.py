"""Reuse D14's real compact builder at this exact candidate; add public readback."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from reuse import ROOT, source, SEED, D14
from contract import digest, write

assert os.environ.get('GITHUB_ACTIONS') == 'true'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT / 'target', text=True).strip() == os.environ['GITHUB_SHA']
sys.argv = [__file__, 'gtk']
exec(compile(source('build.py'), 'immutable-D14/build.py', 'exec'), dict(globals(), __name__='__main__'))
out = ROOT / 'evidence'
# Preserve D14's exact Processing.txt plus all original four-format fixtures.
# Add the existing GTK search suite's bounded-source cancellation workload.
fixtures = out / 'fixtures/search'
subprocess.run([sys.executable, ROOT / 'target/tests/reader_search/make_search_fixtures.py', fixtures], check=True)
subprocess.run([sys.executable, ROOT / 'target/tests/reader_gtk_search/make_inputs.py', fixtures], check=True)
sdk = ROOT / 'target/build/reading-library/stage'
prefix = ROOT / 'target/build/d14-stage'
build = ROOT / 'target/build/d19-catalog'
subprocess.run(['cmake', '-S', ROOT / 'target/tests/reader_wave3_d19', '-B', build, '-G', 'Ninja',
                '-DCMAKE_BUILD_TYPE=Release', '-DEXR_SDK=' + str(sdk),
                '-DCMAKE_PREFIX_PATH=' + str(prefix) + ';' + str(sdk)], check=True)
subprocess.run(['cmake', '--build', build, '--parallel', '4', '--verbose'], check=True)
shutil.copy2(build / 'd19-catalog', out / 'd19-catalog')
identity = json.loads((out / 'build-identity.json').read_text())
identity.update(seed=SEED, historical_judge=D14, catalog_program='d19-catalog', catalog_program_sha256=digest(out / 'd19-catalog'),
                source_identity_projection='Only D14 gtk TARGETS is bound to actual GITHUB_SHA; no report source spoofing',
                phase_fixture='Original Processing.txt imported and retained; additional unchanged GTK search cancel.epub used for real phase-2 close')
write(out / 'build-identity.json', identity)
