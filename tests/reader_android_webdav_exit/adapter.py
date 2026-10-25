"""Actions-only WebDAV test wait projection; original owner and runner stay immutable."""
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import io
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / 'tests/reader_android_navigation_cache/adapter.py'
spec = importlib.util.spec_from_file_location('navigation_provenance_helpers', SHARED)
nav = importlib.util.module_from_spec(spec); spec.loader.exec_module(nav)
need, digest, identity, write, apk_record = nav.need, nav.digest, nav.identity, nav.write, nav.apk_record
OUT = ROOT / 'build/webdav-android/backend/exit-projection'
JAVA = 'tests/webdav_android/android/backend/src/androidTest/java/org/exreader/webdav/probe/BackendProbe.java'
RUNNER = 'tests/webdav_android/run_backend.py'
ID = 'webdav-exit-joint-wait-v1-82b9a2bb'
PINS = {JAVA: '82b9a2bbb5a76c8e7c9f729c473f7de01a4b1498', RUNNER: '5c7e7371639bfb4c5b373b487b2f560dba670794',
        'tests/webdav_android/android/backend/src/debug/java/org/exreader/webdav/probe/ExitActivity.java': '98a946954164dd2c9f18c926f28d1ec937939972'}


def proof():
    need(subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == os.environ['GITHUB_SHA'], 'actual checkout differs')
    for path, blob in PINS.items():
        need(subprocess.check_output(['git', 'rev-parse', 'HEAD:' + path], text=True).strip() == blob, 'original source changed: ' + path)
    subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--', *PINS], check=True)
    original = subprocess.check_output(['git', 'cat-file', 'blob', PINS[JAVA]]).decode()
    helper = '''    private final JSONArray exitStates=new JSONArray();
    private void observeExit(File files,String phase,long started)throws Exception {
        JSONObject value=new JSONObject().put("source_sha",args.getString("source_sha")).put("run_id",args.getString("run_id"))
            .put("attempt",args.getString("attempt")).put("projection_id","''' + ID + '''").put("phase",phase)
            .put("done",ExitActivity.done).put("destroyed",ExitActivity.destroyed)
            .put("worker_failure_class",ExitActivity.failure==null?JSONObject.NULL:ExitActivity.failure.getClass().getName())
            .put("elapsed_ms",SystemClock.elapsedRealtime()-started).put("pid",android.os.Process.myPid());
        exitStates.put(value);
        Files.write(new File(files,"activity-exit-state.json").toPath(),new JSONObject().put("projection_id","''' + ID + '''")
            .put("events",exitStates).toString().getBytes(StandardCharsets.UTF_8));
    }
'''
    old_wait = 'long deadline=SystemClock.elapsedRealtime()+10000;while(!ExitActivity.done&&SystemClock.elapsedRealtime()<deadline)SystemClock.sleep(20);'
    new_wait = ('long exitStarted=SystemClock.elapsedRealtime();long deadline=exitStarted+10000;observeExit(files,"before-wait",exitStarted);'
                'while((!ExitActivity.done||!ExitActivity.destroyed)&&SystemClock.elapsedRealtime()<deadline)SystemClock.sleep(20);'
                'observeExit(files,"after-wait",exitStarted);')
    edits = [('    private Bundle args;', helper + '    private Bundle args;'), (old_wait, new_wait),
             ('.put("accepted",true);', '.put("accepted",true).put("backend_exit_projection","' + ID + '").put("activity_exit_states",exitStates);')]
    generated = original
    for old, new in edits:
        need(generated.count(old) == 1, 'projection source fragment differs')
        generated = generated.replace(old, new, 1)
    restored = generated
    for old, new in reversed(edits):
        need(restored.count(new) == 1, 'inverse projection fragment differs')
        restored = restored.replace(new, old, 1)
    need(restored == original, 'an original assertion or behavior changed outside the joint wait')
    record = {**identity(), 'id': ID, 'original_git_blobs': PINS, 'original_java_sha256': digest(original.encode()),
              'generated_java_sha256': digest(generated.encode()), 'generator_sha256': digest(Path(__file__).read_bytes()),
              'shared_provenance_sha256': digest(SHARED.read_bytes()), 'init_sha256': digest((Path(__file__).parent / 'init.gradle').read_bytes()),
              'reverse_projection_exact': True, 'activity_wait_ms': 10000, 'poll_ms': 20,
              'all_original_assertions_unchanged': True, 'edits': [{'old': old, 'new': new} for old, new in edits]}
    return record, original, generated


def prepare():
    record, original, generated = proof()
    target = OUT / 'generated/org/exreader/webdav/probe/BackendProbe.java'
    target.parent.mkdir(parents=True, exist_ok=True); target.write_text(generated, encoding='utf-8')
    (OUT / 'original-BackendProbe.java').write_text(original, encoding='utf-8'); write(OUT / 'projection.json', record)


def validate_compile(actual, expected):
    need(all(actual.get(key) == value for key, value in identity().items()), 'actual javac identity differs')
    matches = [row for row in actual['sources'] if row['path'].endswith('/BackendProbe.java')]
    need(matches == [{'path': 'build/webdav-android/backend/exit-projection/generated/org/exreader/webdav/probe/BackendProbe.java',
                      'sha256': expected['generated_java_sha256']}], 'actual javac source is not the generated BackendProbe')


def build():
    expected, _, _ = proof(); need(json.loads((OUT / 'projection.json').read_text()) == expected, 'prepared projection changed')
    compiled = json.loads((OUT / 'compile-input.json').read_text()); validate_compile(compiled, expected)
    apks = ROOT / 'tests/webdav_android/android/backend/build/outputs/apk'
    paths = {'owner': apks / 'debug/backend-debug.apk', 'test': apks / 'androidTest/debug/backend-debug-androidTest.apk'}
    records = {}
    for key, path in paths.items():
        records[key] = apk_record(path); target = OUT / 'apks' / (key + '.apk')
        target.parent.mkdir(exist_ok=True); shutil.copyfile(path, target)
    need(records['owner']['certificate_sha256'] == records['test']['certificate_sha256'], 'owner/test APK signer differs')
    with zipfile.ZipFile(paths['test']) as apk:
        need(any(ID.encode() in apk.read(name) for name in apk.namelist() if name.endswith('.dex')), 'projection marker absent from actual APK')
    write(OUT / 'build.json', {**identity(), 'projection': expected, 'compile_input': compiled, 'apks': records})


def validate_reports(read):
    result, first, second = [json.loads(read(name)) for name in ('result.json', 'backend-device.json', 'process-restart-device.json')]
    for record in (result, first, second):
        need(all(record.get(key) == value for key, value in identity().items()) and record['accepted'] is True,
             'unchanged complete WebDAV runner did not pass at this source')
    need(first['count'] == len(first['cases']) == result['backend_cases'] and second['count'] == result['restart_cases'] == 4,
         'original WebDAV complete case counts differ')
    need([row for row in first['cases'] if row.get('name') == 'activity_exit_worker_cleanup']
         == [{'name': 'activity_exit_worker_cleanup', 'status': 0}], 'original Activity final assertion was not passed')
    need(first['backend_exit_projection'] == second['backend_exit_projection'] == ID
         and second['activity_exit_states'] == [], 'actual executed instrumentation projection differs')
    events = first['activity_exit_states']
    need(len(events) == 2 and [row['phase'] for row in events] == ['before-wait', 'after-wait'], 'joint-wait observations missing')
    for event in events:
        need(set(event) == {'source_sha', 'run_id', 'attempt', 'projection_id', 'phase', 'done', 'destroyed',
                            'worker_failure_class', 'elapsed_ms', 'pid'} and event['projection_id'] == ID
             and all(event.get(key) == value for key, value in identity().items()), 'unsafe or foreign Activity state evidence')
    need(events[-1]['done'] is True and events[-1]['destroyed'] is True and events[-1]['worker_failure_class'] is None
         and events[0]['pid'] == events[-1]['pid'] and events[-1]['elapsed_ms'] >= events[0]['elapsed_ms'], 'joint completion not observed')
    return events


def run():
    # The complete original runner is executed first, with its exact CLI. A
    # read-only collector retains safe flags even when that runner fails.
    code = subprocess.run([sys.executable, str(ROOT / RUNNER), *sys.argv[2:]], cwd=ROOT).returncode
    state, collector_error = None, None
    try:
        collected = subprocess.run(['adb', 'exec-out', 'run-as', 'org.exreader.webdav.probe', 'cat', 'files/activity-exit-state.json'],
                                   capture_output=True, timeout=90)
        (OUT / 'state-read-stdout.txt').write_bytes(collected.stdout); (OUT / 'state-read-stderr.txt').write_bytes(collected.stderr)
        (OUT / 'state-read-exit.txt').write_text(str(collected.returncode) + '\n')
        # adb exit0 is not evidence that the requested file exists or is JSON.
        need(collected.returncode == 0, 'safe Activity state read failed')
        state = json.loads(collected.stdout)
        need(isinstance(state, dict) and set(state) == {'projection_id', 'events'} and state['projection_id'] == ID,
             'safe Activity state object unavailable')
        print(json.dumps({'original_runner_exit': code, 'activity_exit_state': state}), flush=True)
    except Exception as error:
        collector_error = type(error).__name__
        print(json.dumps({'original_runner_exit': code, 'state_collector_error_class': collector_error}), flush=True)
        try:
            write(OUT / 'collector-error.json', {'original_runner_exit': code, 'error_class': collector_error})
        except Exception:
            pass
    if code:
        raise SystemExit(code)
    need(collector_error is None, 'additional safe-state provenance could not be collected')
    write(OUT / 'observed-state.json', state)
    events = validate_reports(lambda name: (OUT.parent / name).read_bytes())
    need(state == {'projection_id': ID, 'events': events}, 'actual private Activity evidence differs from the original report')
    built = json.loads((OUT / 'build.json').read_text())
    paths = subprocess.check_output(['adb', 'shell', 'pm', 'path', 'org.exreader.webdav.probe.test'], text=True).strip().splitlines()
    need(len(paths) == 1 and paths[0].startswith('package:/data/app/'), 'installed instrumentation path differs')
    actual = subprocess.check_output(['adb', 'exec-out', 'cat', paths[0][8:]], timeout=90)
    need(digest(actual) == built['apks']['test']['sha256'] and len(actual) == built['apks']['test']['bytes'], 'executed installed APK differs')
    write(OUT / 'runtime.json', {**identity(), 'id': ID, 'installed_test_sha256': digest(actual), 'states': events})


def strict():
    # Reuse the already-authenticated navigation ZIP identity; its strict entry
    # runs after both unchanged original judges, before this additional gate.
    earlier = json.loads((ROOT / 'build/reader-raw3-common-android/strict/navigation-cache.json').read_text())
    need(earlier['accepted'] is True and earlier['old_strict_unchanged'] is True
         and all(earlier.get(key) == value for key, value in identity().items()), 'old judges and navigation provenance must pass first')
    item = earlier['artifact']
    body = subprocess.check_output(['gh', 'api', 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/actions/artifacts/' + str(item['id']) + '/zip'], timeout=240)
    need(len(body) == item['size_in_bytes'] and 'sha256:' + digest(body) == item['digest'], 'same authenticated ZIP bytes differ')
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist(); need(len(names) == len(set(names)), 'duplicate ZIP members')
        for name in names:
            path = PurePosixPath(name); need(not path.is_absolute() and '..' not in path.parts and '\\' not in name, 'unsafe ZIP member')
        def read(suffix):
            matches = [name for name in names if name == suffix or name.endswith('/' + suffix)]
            need(len(matches) == 1 and archive.getinfo(matches[0]).file_size <= 32 * 1024**2, 'missing/duplicate/oversized provenance member')
            return archive.read(matches[0])
        prefix = 'build/webdav-android/backend/exit-projection/'
        expected, original, generated = proof()
        need(json.loads(read(prefix + 'projection.json')) == expected and read(prefix + 'original-BackendProbe.java') == original.encode()
             and read(prefix + 'generated/org/exreader/webdav/probe/BackendProbe.java') == generated.encode(), 'authenticated projection differs')
        built = json.loads(read(prefix + 'build.json')); runtime = json.loads(read(prefix + 'runtime.json'))
        compiled = json.loads(read(prefix + 'compile-input.json')); validate_compile(compiled, expected)
        need(built['projection'] == expected and built['compile_input'] == compiled
             and all(built.get(key) == runtime.get(key) == value for key, value in identity().items()), 'build/runtime source differs')
        for role in ('owner', 'test'):
            data = read(prefix + 'apks/' + role + '.apk')
            need(digest(data) == built['apks'][role]['sha256'] and len(data) == built['apks'][role]['bytes'], 'actual APK bytes differ')
        with zipfile.ZipFile(io.BytesIO(read(prefix + 'apks/test.apk'))) as apk:
            need(any(ID.encode() in apk.read(name) for name in apk.namelist() if name.endswith('.dex')), 'authenticated actual APK lacks projection marker')
        need(runtime['installed_test_sha256'] == built['apks']['test']['sha256'] and runtime['id'] == ID
             and built['apks']['owner']['certificate_sha256'] == built['apks']['test']['certificate_sha256'], 'installed test APK or certificate differs')
        events = validate_reports(lambda name: read('build/webdav-android/backend/' + name))
        need(runtime['states'] == events and json.loads(read(prefix + 'observed-state.json')) == {'projection_id': ID, 'events': events}, 'raw private/report/runtime states differ')
    write(ROOT / 'build/reader-raw3-common-android/strict/webdav-exit.json',
          {**identity(), 'accepted': True, 'complete_product': False, 'old_full_runner_unchanged': True,
           'scope': 'generated WebDAV instrumentation provenance only', 'projection': expected, 'states': events,
           'artifact': item, 'apks': built['apks']})


if __name__ == '__main__':
    need(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    {'prepare': prepare, 'build': build, 'run': run, 'strict': strict}[sys.argv[1]]()
