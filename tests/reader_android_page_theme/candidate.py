"""Actions-only versioned expectations; the original accepted test trees stay untouched."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil

assert os.environ.get('GITHUB_ACTIONS') == 'true'
root = Path('tests/reader_android_page_theme')
out = Path('build/android-page-theme/candidate')
out.mkdir(parents=True, exist_ok=True)
changes = []
def write_copy(source, destination, text):
    original = source.read_text()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text)
    changes.append({'source': str(source), 'copy': str(destination), 'original_sha256': hashlib.sha256(original.encode()).hexdigest(), 'candidate_sha256': hashlib.sha256(text.encode()).hexdigest(), 'diff': ''.join(difflib.unified_diff(original.splitlines(True), text.splitlines(True)))})

host = Path('tests/reader_host_session_android/java')
shutil.copytree(host, out/'host-session/java', dirs_exist_ok=True)
source = host/'org/exreader/host/HostSyncTest.java'
original = source.read_text()
assert original.count('identity[0].equals("3.40.0")') == 1
write_copy(source, out/'host-session/java/org/exreader/host/HostSyncTest.java', original.replace('identity[0].equals("3.40.0")', 'identity[0].equals("3.41.0")'))

source = Path('tests/reader_android_preferences/java/org/exreader/host/PreferencesUiTest.java')
original = source.read_text()
lines = original.splitlines(True)
for index, line in enumerate(lines):
    if 'check("dark_page_gap_is_recorded_and_not_saved_as_success"' in line:
        lines[index] = '                check("sdk341_dark_page_actual_palette_saved",()->{settingsPanel();choose("翻页操作","点击");choose("翻页方向","从左向右");choose("主题","深色");themeOriginal(false);apply();colorFailure=actualThemeFrame("f3-dark",true);need(new JSONObject(new String(saved(),StandardCharsets.UTF_8)).getString("theme").equals("dark"),"real F3 dark persisted");capture("dark-applied");});\n'
    elif 'check(phase.equals("reopen")?' in line:
        assert 'actual_system_dark_resolves_but_does_not_fake_page_palette' in line
        lines[index] = line.replace('actual_system_dark_resolves_but_does_not_fake_page_palette','sdk341_actual_system_dark_frame_palette').replace('until(node->id(node,"reader_status")&&text(node).contains("配色暂不支持"),null,"truthful system-dark refusal",30000);colorFailure=owner(store->themeGap());', 'colorFailure=actualThemeFrame("f3-system-dark",true);')
candidate = ''.join(lines)
assert candidate.count('sdk341_dark_page_actual_palette_saved') == 1 and candidate.count('sdk341_actual_system_dark_frame_palette') == 1
helper = (root/'theme_observation.java.inc').read_text()
candidate = candidate.replace('    private JSONObject colorFailure;', helper+'\n    private JSONObject colorFailure;')
candidate = candidate.replace('.put("page_colors_accepted",false)', '.put("page_colors_accepted",true).put("theme_frames",themeFrames)')
candidate = candidate.replace('report.put("retained_color_failure",colorFailure)', 'report.put("actual_theme_frame",colorFailure)')
write_copy(source, out/'preferences/java/org/exreader/host/PreferencesUiTest.java', candidate)

prelude = original[:original.index('    private JSONObject colorFailure;')]
prelude = prelude.replace('public final class PreferencesUiTest', 'public final class PageThemeUiTest')
theme = prelude + helper + '\n' + (root/'theme_cases.java.inc').read_text() + '\n}\n'
(out/'preferences/java/org/exreader/host/PageThemeUiTest.java').write_text(theme)

source = Path('tests/reader_android_preferences/run_ui.py')
runner = source.read_text().replace('dark_page_gap_is_recorded_and_not_saved_as_success','sdk341_dark_page_actual_palette_saved').replace('actual_system_dark_resolves_but_does_not_fake_page_palette','sdk341_actual_system_dark_frame_palette').replace("report['page_colors_accepted'] is False", "report['page_colors_accepted'] is True")
start = runner.index("        if phase in ('first', 'night'):")
end = runner.index('        reports.append(report)', start)
runner = runner[:start] + '''        for image in report['theme_frames']:
            for extension in ('rgba','png'):
                data = private('page-theme-captures/' + image['name'] + '.' + extension)
                assert hashlib.sha256(data).hexdigest() == image[extension + '_sha256']
                save('theme-frames/' + image['name'] + '.' + extension, data)
        if phase in ('first', 'night'):
            assert report['actual_theme_frame']['accepted'] is True
''' + runner[end:]
runner = runner.replace("'page_colors_accepted': False", "'page_colors_accepted': True")
write_copy(source, out/'preferences_run_ui.py', runner)
(out/'expectation-diff.json').write_text(json.dumps({'sdk':'3.41.0','original_f3_checks':17,'replacement_checks':['sdk341_dark_page_actual_palette_saved','sdk341_actual_system_dark_frame_palette'],'changes':changes},indent=2)+'\n')
