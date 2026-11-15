# SPDX-License-Identifier: MIT
"""A green job or a green report cannot conceal missing or skipped CTest cases."""
import io
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from check_dfinal_c_artifacts import check_ctest, unique_member

REPORT = ('<testsuite tests="2" failures="0" skipped="0">'
          '<testcase name="one" status="run"/><testcase name="two" status="run"/>'
          '</testsuite>')


def main():
    assert check_ctest(REPORT, ['one', 'two'])['passed'] == 2
    cases = [
        (REPORT.replace('tests="2"', 'tests="3"'), ['one', 'two']),
        (REPORT.replace('failures="0"', 'failures="1"'), ['one', 'two']),
        (REPORT.replace('skipped="0"', 'skipped="1"'), ['one', 'two']),
        (REPORT.replace('status="run"', 'status="notrun"', 1), ['one', 'two']),
        (REPORT.replace('name="two"', 'name="one"'), ['one', 'two']),
        (REPORT.replace('status="run"/>', 'status="run"><failure/></testcase>', 1), ['one', 'two']),
        (REPORT.replace('status="run"/>', 'status="run"><skipped/></testcase>', 1), ['one', 'two']),
        (REPORT, ['one']), (REPORT, ['one', 'two', 'missing']),
        (REPORT, ['one', 'two', 'two']),
        (REPORT.replace('name="two"', 'name="sdk-release"'), ['one', 'sdk-release']),
        ('<testsuite tests="0"/>', []),
    ]
    for report, expected in cases:
        try:
            check_ctest(report, expected)
        except AssertionError:
            continue
        raise AssertionError(('accepted altered CTest evidence', report, expected))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('a/ctest-full.xml', REPORT)
        archive.writestr('b/ctest-full.xml', REPORT)
    with zipfile.ZipFile(buffer) as archive:
        for suffix in ('/ctest-full.xml', '/missing.xml'):
            try:
                unique_member(archive, suffix)
            except AssertionError:
                continue
            raise AssertionError(('accepted missing or ambiguous archive member', suffix))
    print('DFINAL-C evidence checker: 1 positive, 14 negative checks passed')


if __name__ == '__main__':
    main()
