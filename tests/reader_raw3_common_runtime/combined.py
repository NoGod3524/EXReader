"""Reuse authenticated preflight judges with explicit updated composition identities."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = '1a6d98ed613c61ffea4267f01f83e2c49b1c02f6'
HELPERS = '49383afab9a78d33a604d83bc3e76b4997496e94'
GTK = '69c60ace09f7f995e92c55494b1bdf80e6474621'
WORKFLOW = '.github/workflows/reader-raw3-common-final-preflight.yml'
EXTENSIONS = {
    '.github/workflows/reader-raw3-common.yml',
    '.github/workflows/reader-raw3-common-windows.yml',
    WORKFLOW,
    'docs/READER-RAW3-COMMON-PREFLIGHT.md',
    'docs/validation/reader-raw3-common-preflight.json',
    'docs/reader-raw3-common-runtime/README.md',
    'tests/reader_raw3_common/guard.py',
    'tests/reader_raw3_common/composition.json',
    'tests/reader_raw3_common/selftest.py',
    'tests/reader_raw3_common/strict.py',
    'tests/reader_raw3_common_runtime/guard.py',
    'tests/reader_raw3_common_runtime/test_guard.py',
    'tests/reader_raw3_common_runtime/windows_verify.py',
    'tests/reader_raw3_common_runtime/combined.py',
    'tests/reader_raw3_common_runtime/combined-composition.json',
    '.github/workflows/reader-raw3-common-android.yml',
    'docs/READER-RAW3-COMMON-ANDROID.md',
    'docs/validation/reader-raw3-common-android.json',
    'tests/reader_raw3_common_android/guard.py',
    'tests/reader_raw3_common_android/projection.py',
    'tests/reader_raw3_common_android/selftest.py',
    'tests/reader_raw3_common_android/strict.py',
    '.github/workflows/reader-raw3-common-gtk.yml',
    'tests/reader_raw3_common_gtk/README.md',
    'tests/reader_raw3_common_gtk/collect.py',
    'tests/reader_raw3_common_gtk/guard.py',
    'tests/reader_raw3_common_gtk/retained.py',
    'tests/reader_raw3_common_gtk/test_guard.py',
    '.github/workflows/reader-raw3-common-apple-records.yml',
    '.github/workflows/reader-raw3-common-apple-macos.yml',
    '.github/workflows/reader-raw3-common-apple-ios.yml',
    'tests/reader_raw3_common_apple/guard.py',
    'tests/reader_raw3_common_apple/verify.py',
    'tests/reader_raw3_common_apple/test_guard.py',
    'tests/reader_raw3_common_apple/README.md',
}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def configure():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    # The historical judges are executed without changing their source bytes.
    subprocess.run(['git', 'diff', '--exit-code', HELPERS, 'HEAD', '--',
                    'tests/reader_raw3_common', '.github/workflows/reader-raw3-common.yml'],
                   cwd=ROOT, check=True)
    sys.path.insert(0, str(ROOT / 'tests/reader_raw3_common'))
    spec = importlib.util.spec_from_file_location('guard', ROOT / 'tests/reader_raw3_common/guard.py')
    original = importlib.util.module_from_spec(spec)
    sys.modules['guard'] = original
    spec.loader.exec_module(original)
    original.BASE = BASE
    original.WORKFLOW = WORKFLOW
    original.MANIFEST = 'tests/reader_raw3_common_runtime/combined-composition.json'
    original.REFS = dict(original.REFS, gtk=GTK)
    original.owned = lambda path: path in EXTENSIONS

    inspect = original.inspect_tree

    def inspect_tree(source):
        result = inspect(source)
        additions = set(original.snapshot(source)) - set(original.snapshot(BASE))
        if additions != EXTENSIONS:
            result['errors'].append('extensions.exact_set')
        result['guard_kind'] = 'common-composition-updated-v1'
        result['historical_helper_source'] = HELPERS
        result['independent_platform_guards_executed'] = False
        return result

    original.inspect_tree = inspect_tree
    return original


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('inspect', 'selftest', 'strict'):
        raise SystemExit('use inspect, selftest or strict')
    original = configure()
    mode = sys.argv[1]
    if mode == 'inspect':
        original.main()
    elif mode == 'selftest':
        import selftest
        # Previously forbidden entry points are now explicitly reviewed files.
        # Keep both refusal controls, targeting distinct still-unapproved paths.
        selftest.CASES['future_runtime_unapproved'] = (
            'tests/reader_raw3_common_runtime/unapproved.py', '100644', b'pass\n', 'scope.unowned:')
        selftest.CASES['future_leaf_workflow_unapproved'] = (
            '.github/workflows/reader-raw3-common-unapproved.yml', '100644', b'name: new\n', 'scope.unowned:')
        target = 'tests/reader_raw3_common_runtime/windows_verify.py'
        selftest.CASES['owned_symlink'] = (target, '120000', b'../../src/library.c', 'scope.mode:')
        selftest.CASES['owned_executable'] = (target, '100755', b'pass\n', 'scope.mode:')
        selftest.CASES['owned_gitlink'] = (target, '160000', None, 'scope.mode:')
        selftest.main()
    else:
        import strict
        strict.main()


if __name__ == '__main__':
    main()
