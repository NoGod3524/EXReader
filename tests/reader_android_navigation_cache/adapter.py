"""Actions-only fixed-source navigation query projection and additional provenance judge."""
import ast
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/android-navigation/cache'
JAVA = 'tests/reader_android_navigation/java/org/exreader/host/NavigationUiTest.java'
RUNNER = 'tests/reader_android_navigation/run_ui.py'
ID = 'reader-nav-cache-query-v1-fd64dad4'
PINS = {JAVA: 'fd64dad4ec09e808f1aafaf3ff7711fcb4bc16b0', RUNNER: 'a5053beed5b83699eb6e41cdeffbbd62ccb28659',
        'examples/android/app/src/main/java/org/exreader/host/MainActivity.java': '002cd4e7d0f9b733fa2aa2b37836d02a0277e445',
        'examples/android/app/src/main/java/org/exreader/host/NavigationPanel.java': '16ff166fd787870230c1d0517901fd4ee9835a27'}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity():
    return {key: os.environ[value] for key, value in
            [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')]}


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def fixed_source():
    need(subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == os.environ['GITHUB_SHA'], 'checkout identity differs')
    for path, blob in PINS.items():
        actual = subprocess.check_output(['git', 'rev-parse', 'HEAD:' + path], text=True).strip()
        need(actual == blob, 'fixed original Git bytes differ: ' + path)
    subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--', *PINS], check=True)
    return subprocess.check_output(['git', 'cat-file', 'blob', PINS[JAVA]]).decode('utf-8')


def project(original):
    helper = ('    private int navigationCacheQueries,navigationCacheClears;\n'
              '    private void navigationFreshCache(){navigationCacheQueries++;if(getUiAutomation().clearCache())navigationCacheClears++;}\n')
    marker = '    private Bundle arguments;'
    report = '.put("native_live",NativeNavigationProbe.live());'
    new_report = ('.put("navigation_cache_projection",new JSONObject().put("id","' + ID + '")'
                  '.put("cache_queries",navigationCacheQueries).put("cache_clears",navigationCacheClears))' + report)
    edits = [(marker, helper + marker, 1),
             ('AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow()',
              'navigationFreshCache();AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow()', 2),
             ('java.util.List<AccessibilityWindowInfo> windows=getUiAutomation().getWindows()',
              'navigationFreshCache();java.util.List<AccessibilityWindowInfo> windows=getUiAutomation().getWindows()', 1),
             ('AccessibilityNodeInfo root=window.getRoot()', 'navigationFreshCache();AccessibilityNodeInfo root=window.getRoot()', 1),
             (report, new_report, 1)]
    generated = original
    for old, new, count in edits:
        need(generated.count(old) == count, 'original projection fragment count differs')
        generated = generated.replace(old, new)
    restored = generated
    for old, new, count in reversed(edits):
        need(restored.count(new) == count, 'reverse projection fragment count differs')
        restored = restored.replace(new, old)
    need(restored == original, 'original assertions, actions or waits changed')
    return generated, [{'old': old, 'new': new, 'count': count} for old, new, count in edits]


def proof():
    original = fixed_source(); generated, edits = project(original)
    return {'id': ID, **identity(), 'original_git_blobs': PINS,
            'original_java_sha256': digest(original.encode()), 'generated_java_sha256': digest(generated.encode()),
            'generator_sha256': digest(Path(__file__).read_bytes()),
            'gradle_init_sha256': digest((Path(__file__).parent / 'init.gradle').read_bytes()),
            'reverse_projection_exact': True, 'original_checks': 18, 'query_wait_ms': 30000,
            'phase_timeout_seconds': 900, 'edits': edits}, original, generated


def prepare():
    record, original, generated = proof()
    target = OUT / 'generated/org/exreader/host/NavigationUiTest.java'
    target.parent.mkdir(parents=True, exist_ok=True); target.write_text(generated, encoding='utf-8')
    (OUT / 'original-NavigationUiTest.java').write_text(original, encoding='utf-8')
    write(OUT / 'projection.json', record)
    print(json.dumps(record, ensure_ascii=False), flush=True)


def apk_record(path):
    signer = Path(os.environ['ANDROID_HOME']) / 'build-tools/35.0.0/apksigner'
    text = subprocess.check_output([str(signer), 'verify', '--print-certs', str(path)], text=True)
    certs = [line.split(': ', 1)[1] for line in text.splitlines() if 'certificate SHA-256 digest: ' in line]
    need(certs, 'APK signer digest absent')
    return {'bytes': path.stat().st_size, 'sha256': digest(path.read_bytes()), 'certificate_sha256': certs,
            'certificate_output': text}


def validate_compile(inputs, expected):
    need(all(inputs.get(key) == value for key, value in identity().items()), 'actual Java compilation identity differs')
    source = 'build/android-navigation/cache/generated/org/exreader/host/NavigationUiTest.java'
    matches = [row for row in inputs['sources'] if row['path'].endswith('/NavigationUiTest.java')]
    need(matches == [{'path': source, 'sha256': expected['generated_java_sha256']}], 'compiled navigation source is not the exact generated file')


def build():
    expected, _, _ = proof()
    need(json.loads((OUT / 'projection.json').read_text()) == expected, 'prepared source changed')
    inputs = json.loads((OUT / 'compile-input.json').read_text()); validate_compile(inputs, expected)
    test = ROOT / 'build/android-navigation/test-apks/navigation-ui.apk'
    host = ROOT / 'examples/android/app/build/outputs/apk/debug/app-debug.apk'
    with zipfile.ZipFile(test) as apk:
        need(any(ID.encode() in apk.read(name) for name in apk.namelist() if name.endswith('.dex')), 'generated projection marker absent from actual test APK')
    record = {**identity(), 'projection': expected, 'compile_input': inputs, 'test_apk': apk_record(test), 'host_apk': apk_record(host)}
    need(record['test_apk']['certificate_sha256'] == record['host_apk']['certificate_sha256'], 'test and host signers differ')
    write(OUT / 'build.json', record)


def validate_runtime(result):
    need(all(result.get(key) == value for key, value in identity().items()) and result['accepted'] is True
         and result['checks'] == 18 and len(result['phases']) == 2, 'original complete navigation runner did not pass')
    expected = next(ast.literal_eval(node.value) for node in ast.parse((ROOT / RUNNER).read_text()).body
                    if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'expected' for target in node.targets))
    need([row['phase'] for row in result['phases']] == list(expected), 'original navigation phase order differs')
    for row in result['phases']:
        need(all(row.get(key) == value for key, value in identity().items())
             and row['passed'] is True and row['native_live'] == 0 and row['count'] == len(expected[row['phase']])
             and [check['name'] for check in row['checks']] == expected[row['phase']]
             and all(check['pass'] is True for check in row['checks']), 'original navigation assertions incomplete')
        actual = row.get('navigation_cache_projection', {})
        need(actual.get('id') == ID and actual.get('cache_queries', 0) > 0
             and actual.get('cache_clears') == actual.get('cache_queries'), 'executed instrumentation did not attest successful query-cache refreshes')


def runtime():
    record = json.loads((OUT / 'build.json').read_text())
    result = json.loads((ROOT / 'build/android-navigation/ui/result.json').read_text()); validate_runtime(result)
    paths = subprocess.check_output(['adb', 'shell', 'pm', 'path', 'org.exreader.host.test'], text=True).strip().splitlines()
    need(len(paths) == 1 and paths[0].startswith('package:/data/app/'), 'actual installed instrumentation path differs')
    data = subprocess.check_output(['adb', 'exec-out', 'cat', paths[0][8:]], timeout=90)
    need(digest(data) == record['test_apk']['sha256'] and len(data) == record['test_apk']['bytes'], 'executed installed test APK differs from generated build')
    write(OUT / 'runtime.json', {**identity(), 'projection_id': ID, 'installed_test_apk_sha256': digest(data),
                               'original_complete_checks': 18, 'phases': result['phases']})


def strict():
    def api(path, binary=False):
        body = subprocess.check_output(['gh', 'api', 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/' + path], timeout=240)
        return body if binary else json.loads(body)
    ident = identity(); run, attempt = ident['run_id'], ident['attempt']
    old = json.loads((ROOT / 'build/reader-raw3-common-android/strict/report.json').read_text())
    need(old['accepted'] and old['original_judges_executed_unchanged'] and all(old.get(key) == value for key, value in ident.items()), 'unchanged old strict must complete first')
    actual = api('actions/runs/' + run + '/attempts/' + attempt)
    need(actual['head_sha'] == ident['source_sha'] and str(actual['run_attempt']) == attempt
         and actual['path'].split('@')[0] == '.github/workflows/reader-raw3-common-android.yml', 'common producer identity differs')
    jobs = api('actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
    job, = [row for row in jobs if row['name'] == 'android']
    need(job['conclusion'] == 'success' and job['head_sha'] == ident['source_sha'] and str(job['run_attempt']) == attempt, 'actual Android producer did not pass')
    artifacts = api('actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
    item, = [row for row in artifacts if row['name'] == 'reader-android-page-theme-' + run + '-' + attempt]
    need(not item['expired'] and item['workflow_run']['head_sha'] == ident['source_sha']
         and item['workflow_run']['id'] == int(run) and 0 < item['size_in_bytes'] <= 512 * 1024**2
         and datetime.fromisoformat(item['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc), 'adapter artifact metadata differs')
    body = api('actions/artifacts/' + str(item['id']) + '/zip', True)
    need(len(body) == item['size_in_bytes'] and 'sha256:' + digest(body) == item['digest'], 'adapter original ZIP bytes differ')
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist(); need(len(names) == len(set(names)), 'duplicate adapter ZIP members')
        for name in names:
            path = PurePosixPath(name)
            need(not path.is_absolute() and '..' not in path.parts and '\\' not in name, 'unsafe adapter ZIP path')
        def read(suffix):
            matches = [name for name in names if name == suffix or name.endswith('/' + suffix)]
            need(len(matches) == 1 and archive.getinfo(matches[0]).file_size <= 32 * 1024**2, 'adapter member absent, duplicate or oversized')
            return archive.read(matches[0])
        prefix = 'build/android-navigation/cache/'
        expected, original, generated = proof()
        need(json.loads(read(prefix + 'projection.json')) == expected and read(prefix + 'original-NavigationUiTest.java') == original.encode()
             and read(prefix + 'generated/org/exreader/host/NavigationUiTest.java') == generated.encode(), 'authenticated generated projection differs')
        built = json.loads(read(prefix + 'build.json')); observed = json.loads(read(prefix + 'runtime.json'))
        need(built['projection'] == expected and all(built.get(key) == observed.get(key) == value for key, value in ident.items()), 'adapter build/runtime source differs')
        compiled = json.loads(read(prefix + 'compile-input.json')); validate_compile(compiled, expected)
        need(compiled == built['compile_input'], 'authenticated actual javac input differs')
        test = read('build/android-navigation/test-apks/navigation-ui.apk')
        host = read('examples/android/app/build/outputs/apk/debug/app-debug.apk')
        need(digest(test) == built['test_apk']['sha256'] == observed['installed_test_apk_sha256']
             and len(test) == built['test_apk']['bytes'] and digest(host) == built['host_apk']['sha256']
             and built['test_apk']['certificate_sha256'] == built['host_apk']['certificate_sha256'], 'actual compiled installed APK or signer differs')
        with zipfile.ZipFile(io.BytesIO(test)) as apk:
            need(any(ID.encode() in apk.read(name) for name in apk.namelist() if name.endswith('.dex')), 'authenticated actual APK lacks projection marker')
        result = json.loads(read('build/android-navigation/ui/result.json')); validate_runtime(result)
        need(observed['phases'] == result['phases'] and observed['projection_id'] == ID, 'installed probe reports differ')
    write(ROOT / 'build/reader-raw3-common-android/strict/navigation-cache.json',
          {**ident, 'accepted': True, 'complete_product': False, 'scope': 'generated navigation probe provenance only',
           'old_strict_unchanged': True, 'original_complete_checks': 18, 'projection': expected,
           'artifact': {key: item[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
           'test_apk': built['test_apk'], 'host_apk': built['host_apk']})


if __name__ == '__main__':
    need(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    {'prepare': prepare, 'build': build, 'runtime': runtime, 'strict': strict}[sys.argv[1]]()
