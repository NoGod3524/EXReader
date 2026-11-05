"""D16 exact seed/new-file guard and executable immutable-driver projection proof."""
import hashlib, json, os, subprocess
from pathlib import Path
from projection import project
assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
BASE = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
D10 = '7e4fcac25120199dd4818a86039e2257f28132a1'
ROOT = Path('tests/reader_wave3_d16')
def git(*args): return subprocess.check_output(['git', *args], text=True).strip()
def upstream(path): return subprocess.check_output(['git', 'show', D10 + ':' + path])
def allowed(status, path):
    return status == 'A' and (path.startswith(('tests/reader_wave3_d16/', 'docs/reader-wave3-d16/')) or path in ('.github/workflows/reader-wave3-d16.yml', 'HANDOFF-RESULT-D16.md'))
assert git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA']
subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], check=True)
changed = [line.split('\t') for line in git('diff', '--name-status', BASE, 'HEAD').splitlines()]
for status, path in changed: assert allowed(status, path), (status, path)
for path in ('src', 'include', 'cmake', 'CMakeLists.txt', 'bindings'):
    assert git('rev-parse', 'HEAD:' + path) == git('rev-parse', SDK + ':' + path), path
original = upstream('tests/reader_dot_wave2/d10/accessibility/DefaultUITests.swift')
assert (ROOT/'upstream/DefaultUITests.swift').read_bytes() == original
assert (ROOT/'accessibility/DefaultUITests.swift').read_text() == project(original.decode())
assert (ROOT/'accessibility/A11yAuditSupport.swift').read_bytes() == upstream('tests/reader_dot_wave2/d10/accessibility/A11yAuditSupport.swift')
assert (ROOT/'contract.py').read_bytes() == upstream('tests/reader_dot_wave2/d10/contract.py')
# The original full regression copied by run.sh remains byte-identical in this seed.
for path in ('tests/apple_host/accessibility/ui/ReaderAccessUITests.swift', 'tests/apple_host/make_xcodeproj.rb'):
    assert Path(path).read_bytes() == upstream(path), path
negatives=[]
for status,path in [('M','examples/apple/HostViews.swift'),('A','tests/reader_wave3_d15/extra.py'),('M','tests/apple_host/accessibility/ui/ReaderAccessUITests.swift'),('M','CMakeLists.txt'),('A','include/extra.h')]:
    assert not allowed(status,path); negatives.append(path)
mutant=project(original.decode()).replace('        XCTAssertTrue(node(id).isHittable, id)\n','')
assert mutant != project(original.decode()); negatives.append('removed-original-hittable-assertion')
report=dict(seed=BASE,source=os.environ['GITHUB_SHA'],sdk=SDK,d10_source=D10,changed_paths=changed,
    original_driver_sha256=hashlib.sha256(original).hexdigest(),semantic_assertions_preserved=True,
    exact_projection=True,original_guard_bytes_unchanged=True,negative_rejections=negatives,
    seed_is_accepted_production_base=False)
Path('build').mkdir(exist_ok=True)
Path('build/d16-guard.json').write_text(json.dumps(report,indent=2)+'\n')
print('D16_SOURCE_GUARD '+json.dumps(report))
