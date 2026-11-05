"""Actions-only observations of the original failing test; no acceptance."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE = '25bc0c67971f81491f50e0a3caaaf7e509bb7e35'
TEST = 'tests/apple_host/reading/ui/ReadingUITests.swift'


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    mode, = sys.argv[1:]
    changed = subprocess.check_output(['git', 'diff', '--name-only', SOURCE, 'HEAD'], cwd=ROOT, text=True).splitlines()
    if not all(p.startswith('tests/reader_apple_reading_inspect/') or p in {
        '.github/workflows/reader-apple-reading-inspect.yml',
        '.github/workflows/reader-apple-import-observe.yml'} for p in changed):
        raise RuntimeError('Original production or judges changed')
    original = subprocess.check_output(['git', 'show', SOURCE + ':' + TEST], cwd=ROOT).decode()
    path = ROOT / TEST
    if path.read_text() != original:
        raise RuntimeError('Original test differs')
    if mode == 'verify':
        print('Original production, fixture, generator, tests and 90s waits unchanged')
        return
    if mode != 'observe':
        raise RuntimeError('Unknown mode')
    helper = '''
    private func observeImport(_ phase: String) {
        let title = element("library.title")
        let value = title.exists ? String(describing: title.value) : "title absent"
        let body = "IMPORT-OBSERVATION " + phase + " trace=" + value + "\\n" + app.debugDescription
        print(body)
        let attachment = XCTAttachment(string: body)
        attachment.name = "import-observation-" + phase + ".txt"
        attachment.lifetime = .keepAlways
        add(attachment)
    }
'''
    edits = [
        ('    private func element(', helper + '    private func element('),
        ('    override func tearDownWithError() throws {\n', '    override func tearDownWithError() throws {\n        observeImport("teardown")\n'),
        ('        element(id).tap()\n', '        element(id).tap()\n        if id.hasPrefix("library.import.") { observeImport("after-tap") }\n'),
    ]
    observed = original
    for before, after in edits:
        if observed.count(before) != 1:
            raise RuntimeError('Observation insertion is ambiguous')
        observed = observed.replace(before, after)
    restored = observed
    for before, after in reversed(edits):
        restored = restored.replace(after, before)
    if restored != original:
        raise RuntimeError('Original assertions not preserved')
    path.write_text(observed)
    print('Diagnostic only: original assertion sequence and timeouts preserved; post-tap and teardown AX observations added')


if __name__ == '__main__':
    main()
