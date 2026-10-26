"""Actions-only copies of frozen UI drivers with explicit ImportEntry title expectations."""
import hashlib
import json
import os
from pathlib import Path
import shutil

assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
root = Path(__file__).resolve().parents[2]
source = root / 'examples/android/uitest/src/androidTest/java'
output = root / 'build/wave3/candidate/java'
assert not output.exists(), 'never reuse candidate driver bytes'
shutil.copytree(source, output)
files = ('Sample.epub', 'Sample.txt', 'Sample.pdf', 'BigChapter.epub', 'Ambiguous.epub',
         'Broken.epub', 'Second.epub', 'TooLarge.epub', 'Large.epub', 'NewReview.txt',
         'Cross.epub', 'DuplicateSpine.epub', 'DamagedNext.epub', 'BudgetNext.epub', 'EmptyNext.epub')
expected = {name: {'title': Path(name).stem, 'format': Path(name).suffix[1:].upper()} for name in files}
helper = '''
    // Independent exact fixture expectations: never infer titles from observed UI.
    private static androidx.test.uiautomator.BySelector expectedRow(String file) {
        String title, format;
        switch(file) {
''' + ''.join('            case ' + json.dumps(name) + ': title=' + json.dumps(item['title']) + '; format=' + json.dumps(item['format']) + '; break;\n' for name, item in expected.items()) + '''
            default: throw new AssertionError("Unspecified fixture title: " + file);
        }
        return By.text(java.util.regex.Pattern.compile("^" + java.util.regex.Pattern.quote(title)
            + "\\\\n(?:[^\\\\n]* · )?" + format + " · [^\\\\n]+$"));
    }
'''
provenance = []
for name in ('HostWalkthroughTest.java', 'HostReviewTest.java'):
    relative = Path('org/exreader/host/uitest') / name
    original = (source / relative).read_text(encoding='utf-8')
    candidate = original
    if name == 'HostWalkthroughTest.java':
        old = 'By.textContains(title)'
        assert candidate.count(old) == 2
        candidate = candidate.replace(old, 'expectedRow(title)')
        # The frozen picker statement is left exactly as written: the candidate only
        # projects the public title stem and format, it never turns a tolerant wait
        # into a new hard gate.
        assert candidate.count('device.wait(Until.hasObject(By.pkg(APP)), 10000);') == 1
        old = 'if (device.hasObject(By.textContains(needle))) return true;'
        assert candidate.count(old) == 1
        candidate = candidate.replace(old, 'if (device.hasObject(needle.startsWith("Imported ") || needle.startsWith("Already in shelf: ") ? By.text(needle) : By.textContains(needle))) return true;')
    else:
        old = 'By.textStartsWith(name + "\\n")'
        assert candidate.count(old) == 2
        candidate = candidate.replace(old, 'expectedRow(name)')
        old = 'By.textStartsWith("Sample.epub\\n")'
        assert candidate.count(old) == 2
        candidate = candidate.replace(old, 'expectedRow("Sample.epub")')
        old = 'device.wait(Until.hasObject(By.textContains(value)), 20000)'
        assert candidate.count(old) == 1
        candidate = candidate.replace(old, 'device.wait(Until.hasObject(value.startsWith("Imported ") || value.startsWith("Already in shelf: ") ? By.text(value) : By.textContains(value)), 20000)')
    for file, item in expected.items():
        for prefix in ('Imported ', 'Already in shelf: ', 'Opened ', 'Opening ', 'Could not open '):
            candidate = candidate.replace('"' + prefix + file, '"' + prefix + item['title'])
        candidate = candidate.replace('text("book_title").contains("' + file + '")',
                                      'text("book_title").equals("' + item['title'] + '")')
        candidate = candidate.replace('review_open_title ' + file + '"', 'review_open_title ' + item['title'] + '"')
        candidate = candidate.replace('contains("Opened ' + item['title'] + '")', 'equals("Opened ' + item['title'] + '")')
        candidate = candidate.replace('"Could not open ' + item['title'] + '"', '"Could not open ' + item['title'] + ':"')
        candidate = candidate.replace('startsWith("Opening ' + item['title'] + '")', 'equals("Opening ' + item['title'] + '...")')
    position = candidate.rfind('}')
    assert position > 0
    candidate = candidate[:position] + helper + candidate[position:]
    (output / relative).write_text(candidate, encoding='utf-8')
    provenance.append({'file': str(relative).replace('\\', '/'),
                       'original_sha256': hashlib.sha256((source / relative).read_bytes()).hexdigest(),
                       'candidate_sha256': hashlib.sha256((output / relative).read_bytes()).hexdigest()})
(output.parent / 'provenance.json').write_text(json.dumps({'expected_titles': expected, 'drivers': provenance}, indent=2) + '\n', encoding='utf-8')
