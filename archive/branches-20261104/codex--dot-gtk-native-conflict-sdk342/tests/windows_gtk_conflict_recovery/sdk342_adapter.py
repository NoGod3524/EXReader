"""Run original C09 semantics with authenticated, explicit SDK 3.42 identity.

No original file is edited. Only exact SDK CMake arguments, one owner source
path and one owner_report expected-version condition are adapted. Runtime
SDK values, fixtures, assertions, owner implementation and budgets are real.
"""
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys

from sdk342_identity import (ROOT, PACKAGE, ORIGINALS, OWNER_FUNCTION_SHA256,
                            ADAPTED_FUNCTION_SHA256, authenticate, digest, identity, write)


def main():
    originals = authenticate()
    assert sys.platform == 'win32'
    source = ROOT / 'tests/reader_wave3_c09/build.py'
    spec = importlib.util.spec_from_file_location('original_c09_builder', source)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    helper = original.H
    function = inspect.getsource(helper.owner_run)
    assert digest(function.encode()) == OWNER_FUNCTION_SHA256
    old = "report.get('sdk_version')!='3.41.0'"
    new = "report.get('sdk_version')!='3.42.0'"
    assert function.count(old) == 1
    adapted = function.replace(old, new)
    assert digest(adapted.encode()) == ADAPTED_FUNCTION_SHA256
    original_function = helper.owner_run
    exec(compile(adapted, str(PACKAGE / 'sdk342_adapter.py') + ':authenticated-owner_run', 'exec'), helper.__dict__)
    report = dict(identity(), accepted=False, originals=originals,
                  owner_function_sha256=OWNER_FUNCTION_SHA256,
                  adapted_function_sha256=ADAPTED_FUNCTION_SHA256,
                  sdk_argument_changes=0, owner_source_redirects=0,
                  expected_sdk_argument_changes=len(helper.MODULES) + len(original.NEW_MODULES) + 1,
                  changes=[], disclosure=__doc__)
    prior_run = helper.run
    old_owner = ROOT / 'tests/reader_windows_raw3/owner-probe'
    new_owner = PACKAGE / 'sdk342_owner_probe'

    def run(argv, name, timeout=1800):
        args = list(argv)
        for index, value in enumerate(args):
            if str(value) == '-DEXR_SDK_VERSION=3.41.0':
                args[index] = '-DEXR_SDK_VERSION=3.42.0'
                report['sdk_argument_changes'] += 1
                report['changes'].append(dict(step=name, index=index, before=str(value), after=args[index]))
            elif str(value) == str(old_owner):
                assert index > 0 and str(args[index - 1]) == '-S'
                args[index] = new_owner
                report['owner_source_redirects'] += 1
                report['changes'].append(dict(step=name, index=index, before=str(value), after=str(new_owner)))
        return prior_run(args, name, timeout)

    helper.run = run
    try:
        original.main()
        assert report['sdk_argument_changes'] == report['expected_sdk_argument_changes']
        assert report['owner_source_redirects'] == 1
        assert authenticate() == ORIGINALS
        report['accepted'] = True
    finally:
        helper.run = prior_run
        helper.owner_run = original_function
        write(ROOT / 'build/sdk342-evidence/windows/c09-adapter.json', report)
        print('SDK342_C09_ADAPTER ' + json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
