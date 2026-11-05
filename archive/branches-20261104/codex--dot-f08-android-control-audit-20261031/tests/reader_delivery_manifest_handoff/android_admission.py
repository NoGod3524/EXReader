"""Actions-only C3 identity admission and installed-OPDSHash staging for the Android 3.42 licence run.

The original frozen guard in tests/android_sdk342_package/run.py is not edited and not
weakened; it admits only the integration branch's fixed path list, which cannot contain this
package's files. This admission instead allows exactly the C3-declared changes and proves
that every original recipe/builder/identity file is byte-identical to the common base.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/c3-android'
BASE = 'bd28d4946f17a184dd3cd47a584cf49fce34e973'
ANCHOR = "    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'): shutil.copyfile(ROOT / name, payload / name)\n"
PATCH_LINES = (
    "    # F12 handoff patch (docs/reader-delivery-handoff/PACKAGING-PATCH.md): ship the SDK's installed licence texts.\n",
    "    shutil.copytree(ROOT / 'build/wave3/sdk-stage/share/exreader/licenses', payload / 'licenses')\n",
    "    product_share = ROOT / 'build/wave3/stage/share'\n",
    "    for item in sorted(product_share.rglob('*')):\n",
    "        if item.is_file() and any(k in item.name.lower() for k in ('licen', 'copying', 'notice', 'public-domain')):\n",
    "            destination = payload / 'product-licenses' / item.relative_to(product_share)\n",
    "            destination.parent.mkdir(parents=True, exist_ok=True)\n",
    "            shutil.copyfile(item, destination)\n",
)
PATCHED = 'tests/android_sdk342_package/run.py'
ALLOWED_PREFIXES = ('docs/reader-delivery-handoff/', 'tests/reader_delivery_manifest_handoff/')
ALLOWED_FILES = {PATCHED, '.github/workflows/reader-delivery-manifest-handoff.yml',
                 '.github/workflows/reader-delivery-android-sdk342-licenses.yml'}
# Original builders, identity tools, recipe and every product/SDK input: byte-identical to the base.
FROZEN = ('src', 'include', 'cmake', 'CMakeLists.txt', 'CMakePresets.json', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
          'licenses', 'apps', 'examples', 'bindings', 'tools', 'extras',
          'tests/reader_f06_packages', 'tests/reader_wave3_c11', 'tests/reader_wave3_c09',
          '.github/workflows/android-composition-candidate.yml', '.github/workflows/android-sdk342-package.yml',
          '.github/workflows/sdk342-aggregate.yml')


def git(*args):
    return subprocess.check_output(['git', *map(str, args)], cwd=ROOT, text=True)


def sh(args):
    print('$', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def guard():
    head = git('rev-parse', 'HEAD').strip()
    assert head == os.environ['GITHUB_SHA'], (head, os.environ['GITHUB_SHA'])
    git('merge-base', '--is-ancestor', BASE, 'HEAD')
    changed = git('diff', '--name-only', BASE, 'HEAD').splitlines()
    outside = [p for p in changed if p not in ALLOWED_FILES and not p.startswith(ALLOWED_PREFIXES)]
    assert not outside, outside
    git('diff', '--exit-code', BASE, 'HEAD', '--', *FROZEN)
    old = git('show', BASE + ':' + PATCHED)
    new = (ROOT / PATCHED).read_text(encoding='utf-8')
    assert old.count(ANCHOR) == 1, 'anchor line missing from base'
    assert new == old.replace(ANCHOR, ANCHOR + ''.join(PATCH_LINES), 1), 'run.py differs from base by more than the declared patch'
    assert os.environ.get('GITHUB_EVENT_NAME') in ('push', 'workflow_dispatch')
    frozen = {p: git('rev-parse', 'HEAD:' + p).strip() for p in (
        'tests/reader_f06_packages/build.py', 'tests/reader_f06_packages/identity.py',
        '.github/workflows/android-composition-candidate.yml', '.github/workflows/android-sdk342-package.yml')}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'admission.json').write_text(json.dumps(dict(
        source_sha=head, base=BASE, run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
        changed=changed, patched_file=PATCHED, patch_sha256=sha(''.join(PATCH_LINES).encode('utf-8')),
        frozen_blobs=frozen, original_guard_edited=False, passed=True), indent=2, sort_keys=True) + '\n')


def hash_stage():
    """Same explicit installed canonical OPDSHash prefix the public-boundary and C1 lanes give Sync/product.

    There is no private fallback: the product and sync CMake require EXREADER_ORIGINAL_HASH_PREFIX and their
    own provider checks stay untouched.
    """
    ndk = Path(os.environ['ANDROID_HOME']) / 'ndk' / os.environ['C11_NDK']
    stage, build = OUT / 'hash-stage', OUT / 'hash-build'
    assert not stage.exists() and not build.exists()
    sh(['cmake', '-S', ROOT / 'extras/opds', '-B', build, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
        '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DCMAKE_POSITION_INDEPENDENT_CODE=ON',
        '-DCMAKE_TOOLCHAIN_FILE=' + str(ndk / 'build/cmake/android.toolchain.cmake'),
        '-DANDROID_ABI=x86_64', '-DANDROID_PLATFORM=android-26', '-DANDROID_STL=c++_static',
        '-DEXREADER_OPDS_HASH_ONLY=ON', '-DCMAKE_INSTALL_PREFIX=' + stage.as_posix()])
    sh(['cmake', '--build', build, '--parallel', '4'])
    sh(['cmake', '--install', build])
    assert stage.resolve() == stage and (stage / 'lib/cmake/EXReaderOPDSHash').is_dir()
    with Path(os.environ['GITHUB_ENV']).open('a') as handle:
        handle.write('EXREADER_ORIGINAL_HASH_PREFIX=' + stage.as_posix() + '\n')


if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    {'guard': guard, 'hash-stage': hash_stage}[sys.argv[1]]()
