"""Actions-only format and injected-persistence rejection regression."""
import copy
import shlex

import common
from static_apks import manifest_booleans
from summary import application_persisted
from emulator import Driver, PACKAGE


def main():
    common.require_actions()
    for raw, expected in [('false', False), ('true', True),
                          ('(type 0x12)0x0', False), ('(type 0x12)0xffffffff', True)]:
        for prefix in ('android:', 'http://schemas.android.com/apk/res/android:'):
            line = '    A: ' + prefix + 'allowBackup(0x01010280)=' + raw
            assert manifest_booleans(line, 'allowBackup', '0x01010280') == [expected]
    for raw in ('', '1', '0', 'TRUE', 'null', '(type 0x10)0xffffffff',
                '(type 0x12)0x1', 'true trailing'):
        line = 'A: android:allowBackup(0x01010280)=' + raw
        assert manifest_booleans(line, 'allowBackup', '0x01010280') == [None]
    assert manifest_booleans('', 'allowBackup', '0x01010280') == []
    assert manifest_booleans('A: android:allowBackup(0x01010010)=false',
                             'allowBackup', '0x01010280') == []
    duplicate = 'A: android:exported(0x01010010)=true\n' * 2
    assert manifest_booleans(duplicate, 'exported', '0x01010010') != [True]
    valid = {'observed': {'restore_input': 'app', 'open_path': 'ui_tap',
                          'preferences_injected': False},
             'checks': [{'name': 'app_persisted_reader_selection', 'pass': True, 'mandatory': True}]}
    assert application_persisted(valid)
    for key, value in [('restore_input', 'injected'), ('restore_input', None),
                       ('open_path', 'prefs_restore'), ('preferences_injected', True),
                       ('preferences_injected', None)]:
        bad = copy.deepcopy(valid)
        bad['observed'][key] = value
        assert not application_persisted(bad)
    for field in ('pass', 'mandatory'):
        bad = copy.deepcopy(valid)
        bad['checks'][0][field] = False
        assert not application_persisted(bad)
    bad = copy.deepcopy(valid)
    bad['checks'] = []
    assert not application_persisted(bad)
    driver = Driver.__new__(Driver)
    calls = []
    driver.adb = lambda *args, **kwargs: calls.append((args, kwargs))
    script = 'printf %s "s04 original" > files/book.title'
    driver.shell('run-as', PACKAGE, 'sh', '-c', script)
    assert calls[-1][0][0] == 'shell'
    assert shlex.split(calls[-1][0][1]) == ['run-as', PACKAGE, 'sh', '-c', script]
    driver.run_as('sh', '-c', 'ls files/books 2>/dev/null')
    assert calls[-1][0][0] == 'exec-out' and calls[-1][1]['binary'] is True
    assert shlex.split(calls[-1][0][1]) == ['run-as', PACKAGE, 'sh', '-c', 'ls files/books 2>/dev/null']
    print('S04 strict boolean formats and injected-persistence negatives passed', flush=True)


if __name__ == '__main__':
    main()
