#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check Android ownership sources and fail closed on complete cloud evidence."""
import argparse
import json
import os
from pathlib import Path
import re

from android_host_evidence import (ROOT, WALKTHROUGH_IDS, check_evidence, check_identity,
    cloud_identity, load, require, sha256)

APP = ROOT/'examples/android/app/src/main'
TEST = ROOT/'examples/android/uitest/src/androidTest/java/org/exreader/host/uitest/HostWalkthroughTest.java'
REVIEW = TEST.with_name('HostReviewTest.java')
WORKFLOW = ROOT/'.github/workflows/wp13-android.yml'
DOC = ROOT/'docs/WP13-ANDROID.md'


# Narrow source-contract migration; this is not a Java runtime correctness proof.
IMPORT_CONTRACT_PATHS = {
    "activity": "examples/android/app/src/main/java/org/exreader/host/MainActivity.java",
    "controller": "examples/android/app/src/main/java/org/exreader/host/ImportController.java",
    "entry": "extras/android-import-entry/android/importentry/src/main/java/org/exreader/importentry/ImportEntry.java",
    "gradle": "examples/android/app/build.gradle",
    "settings": "examples/android/settings.gradle",
}

def _import_lex(text):
    token = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
    def blank(value):
        return ''.join('\n' if char == '\n' else ' ' for char in value)
    clean = token.sub(lambda match: blank(match.group()) if match.group().startswith(('/',)) else match.group(), text)
    code = token.sub(lambda match: blank(match.group()), text)
    return clean, code

def _import_body(text, name, arguments, literals=False, raw=False):
    clean, code = _import_lex(text)
    signature = r'\b' + re.escape(name) + r'\s*\(\s*' + arguments + r'\s*\)\s*(?:throws\s+[^;{]+)?\{'
    matches = list(re.finditer(signature, code))
    if len(matches) != 1:
        return ''
    start = matches[0].end(); depth = 1
    for end in range(start, len(code)):
        depth += (code[end] == '{') - (code[end] == '}')
        if depth == 0:
            body = (clean if literals else code)[start:end]
            return body if raw else re.sub(r'\s+', '', body)
    return ''

def _import_live_literal(text, pattern):
    clean, code = _import_lex(text)
    return any(code[match.start():match.start()+1].strip() for match in re.finditer(pattern, clean))

def import_contract_sources(sources):
    a = sources.get('activity', '')
    result = _import_body(a, 'onActivityResult', r'int\s+requestCode\s*,\s*int\s+resultCode\s*,\s*Intent\s+data')
    # Legacy direct implementation remains supported only by a real scoped call, not a comment/string token.
    if re.search(r'\.takePersistableUriPermission\([^)]', result):
        return []
    c = sources.get('controller', ''); e = sources.get('entry', '')
    start = _import_body(a, 'onCreate', r'Bundle\s+savedInstanceState')
    constructor = _import_body(c, 'ImportController', r'Context\s+context')
    submit = _import_body(c, 'submit', r'Intent\s+intent')
    pump = _import_body(c, 'pump', '')
    intent = _import_body(e, 'submit', r'Intent\s+intent')
    uri = _import_body(e, 'submit', r'Uri\s+uri\s*,\s*String\s+mimeHint')
    run = _import_body(e, 'run', r'ImportTicket\s+ticket\s*,\s*String\s+mimeHint')
    copy = _import_body(e, 'copy', r'ImportTicket\s+ticket\s*,\s*String\s+mimeHint')
    opened = _import_body(e, 'open', r'Uri\s+uri')
    entry_init = _import_body(e, 'ImportEntry', r'ContentResolver\s+resolver\s*,\s*File\s+root\s*,\s*Executor\s+executor\s*,\s*ImportOwner\s+owner\s*,\s*long\s+stallTimeoutMillis\s*,\s*boolean\s+retainDisplayFilename')
    recovery = _import_body(e, 'cleanStaging', '')
    host = _import_body(a, 'importReady', r'ReadyRequest\s+ready')
    creator = _import_body(e, 'createWithDisplayFilename', r'Context\s+context\s*,\s*File\s+stagingParent\s*,\s*Executor\s+ownerExecutor\s*,\s*ImportOwner\s+owner')
    factory = _import_body(e, 'create', r'Context\s+context\s*,\s*File\s+stagingParent\s*,\s*Executor\s+ownerExecutor\s*,\s*ImportOwner\s+owner\s*,\s*long\s+stallTimeoutMillis\s*,\s*boolean\s+retainDisplayFilename')
    finish = _import_body(e, 'finish', r'ImportTicket\s+ticket\s*,\s*ReadyRequest\s+request\s*,\s*ImportError\s+error')
    deliver = _import_body(e, 'deliver', r'ImportTicket\s+ticket\s*,\s*ReadyRequest\s+request\s*,\s*ImportError\s+error')
    on_ready = _import_body(c, 'onReady', r'ImportTicket\s+ticket\s*,\s*ReadyRequest\s+request')
    checks = {
        'activity controller ownership': 'imports=ImportController.get(this);' in start and 'imports.attach(this);' in start,
        'activity result delegation': 'imports.submit(data);' in result,
        'private staging creation': 'ImportEntry.createWithDisplayFilename(context,newFile(context.getFilesDir(),' in constructor,
        'ready recovery handoff': 'opened.pendingReady()' in constructor and 'entry=opened;' in constructor and 'pending.addAll(recovered)' in constructor,
        'private factory chain': 'returncreate(context,stagingParent,ownerExecutor,owner,DEFAULT_STALL_TIMEOUT_MILLIS,true);' in creator and 'returnnewImportEntry(context.getApplicationContext().getContentResolver(),newFile(stagingParent,' in factory,
        'ready callback chain': 'finish(ticket,copied,null);' in run and 'deliver(ticket,request,error);' in finish and 'owner.onReady(ticket,request)' in deliver and 'pending.add(request)' in on_ready and 'pump();' in on_ready,
        'controller submit delegation': 'entry.submit(intent)' in submit,
        'controller native handoff': 'owner.importReady(next)' in pump,
        'compiled module dependency': _import_live_literal(sources.get('gradle', ''), r'\bimplementation\s+project\(\s*[\'\"]:importentry[\'\"]\s*\)'),
        'compiled module location': _import_live_literal(sources.get('settings', ''), r'\binclude\s+[\'\"]:importentry[\'\"]') and _import_live_literal(sources.get('settings', ''), r'\bproject\(\s*[\'\"]:importentry[\'\"]\s*\)\.projectDir\s*=\s*file\(\s*[\'\"]\.\./\.\./extras/android-import-entry/android/importentry[\'\"]\s*\)'),
        'intent URI dispatch': 'submit(uri,intent.getType())' in intent,
        'URI worker dispatch': 'worker.execute(()->run(ticket,mimeHint))' in uri,
        'worker copy dispatch': 'copied=copy(ticket,mimeHint);' in run,
        'copy descriptor dispatch': 'afd=open(uri);' in copy,
        'provider descriptor read': _import_live_literal(_import_body(e, 'open', r'Uri\s+uri', literals=True, raw=True), r'\bresolver\s*\.\s*openAssetFileDescriptor\s*\(\s*uri\s*,\s*"r"\s*\)'),
        'permission denial retained': copy.count('catch(SecurityExceptione){thrownewFailure(ImportError.Code.PERMISSION,') == 2,
        'private publication': 'Filetarget=newFile(readyDir,id);' in copy and 'Files.move(part.toPath(),target.toPath(),StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING)' in copy and 'newReadyRequest(id,target,format,total,title,false)' in copy,
        'constructor recovery': 'cleanStaging();' in entry_init,
        'private ready reconstruction': 'readyDir.listFiles()' in recovery and 'newReadyRequest(name,f,format,f.length(),readSidecar(f),false)' in recovery and 'ready.put(name,recovered)' in recovery,
        'host uses private ready bytes': 'copyUri(Uri.fromFile(ready.file()),ready.id(),task)' in host,
    }
    return ['Android import contract lacks ' + name for name, passed in checks.items() if not passed]

def import_contract_checks(root):
    sources = {}
    for name, path in IMPORT_CONTRACT_PATHS.items():
        try:
            sources[name] = (root/path).read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            sources[name] = ''
    return import_contract_sources(sources)


def static_checks():
    problems = []
    required = [APP/'AndroidManifest.xml', APP/'res/layout/activity_main.xml', APP/'res/values/ids.xml',
        *[APP/('java/org/exreader/host/' + name + '.java') for name in
          ('MainActivity', 'ReaderView', 'NativeLibrary', 'ReflowSession', 'FixedSession')],
        APP/'java/org/exreader/EXReader.java', APP/'java/org/exreader/EXReaderException.java',
        APP/'cpp/exreader_host_jni.c', APP/'cpp/CMakeLists.txt', ROOT/'examples/android/app/build.gradle',
        ROOT/'examples/android/uitest/build.gradle', ROOT/'examples/android/ci/emulator.sh',
        TEST, REVIEW, WORKFLOW, DOC, ROOT/'tools/build_android_host.py', ROOT/'tools/run_android_host_evidence.py']
    for path in required:
        if not path.is_file():
            problems.append('missing file: ' + str(path.relative_to(ROOT)))
    if problems:
        return problems, {}
    activity = (APP/'java/org/exreader/host/MainActivity.java').read_text()
    view = (APP/'java/org/exreader/host/ReaderView.java').read_text()
    native = (APP/'java/org/exreader/host/NativeLibrary.java').read_text()
    bridge = (APP/'cpp/exreader_host_jni.c').read_text()
    bounded_bridge = (APP/'cpp/bounded_epub_jni.inc').read_text()
    app_gradle = (ROOT/'examples/android/app/build.gradle').read_text()
    test, workflow, doc = TEST.read_text(), WORKFLOW.read_text(), DOC.read_text()
    layout = (APP/'res/layout/activity_main.xml').read_text()
    for needle in ('newSingleThreadExecutor', 'onSaveInstanceState',
                   'MAX_INPUT_BYTES', 'saveProgress', 'setPosition', 'onStop'):
        if needle not in activity:
            problems.append('MainActivity lacks ' + needle)
    problems.extend(import_contract_checks(ROOT))
    for needle in ('onTouchEvent', 'AccessibilityNodeProvider', 'getAccessibilityNodeProvider',
                   'AccessibilityNodeInfo.obtain(ReaderView.this'):
        if needle not in view:
            problems.append('ReaderView lacks ' + needle)
    if 'System.loadLibrary("exreader_host")' not in native:
        problems.append('NativeLibrary does not load exreader_host')
    for symbol in ('exr_library_import_file_unique', 'exr_library_note', 'exr_library_fixed_note',
                   'exr_library_progress', 'exr_anchor_create', 'exr_library_notes'):
        if symbol not in bridge:
            problems.append('JNI bridge lacks ' + symbol)
    for symbol in ('exr_library_source', 'exr_publication_open_source', 'exr_publication_pager_create',
                   'exr_pager_read_text', 'exr_pager_anchor_resolve', 'exr_library_epub_progress',
                   'exr_library_epub_note', 'exr_library_epub_notes'):
        if symbol not in bounded_bridge:
            problems.append('bounded JNI bridge lacks ' + symbol)
    if any(symbol in bounded_bridge for symbol in ('exr_library_document', 'exr_publication_load', 'exr_document_open')):
        problems.append('bounded JNI bridge must not use document snapshots')
    if 'androidx' in app_gradle or "abiFilters 'x86_64'" not in app_gradle or 'ndkVersion' not in app_gradle:
        problems.append('app dependency, ABI or NDK contract changed')
    for control in ('import_button', 'book_list', 'reader_view', 'page_label', 'select_button',
                    'copy_button', 'annotate_button', 'notes_button', 'note_list', 'status_text',
                    'cancel_button', 'rebuild_view'):
        if '@+id/' + control not in layout or control not in activity:
            problems.append('layout/activity lacks ' + control)
    ids = re.findall(r'step\("([a-z0-9_]+)"', test)
    if ids != WALKTHROUGH_IDS:
        problems.append('the original 45 named walkthrough cases must remain complete and ordered')
    for needle in ('force-stop', 'setOrientationLeft', 'takeScreenshot', 'validation.json', 'physical_device_execution'):
        if needle not in test:
            problems.append('walkthrough lacks ' + needle)
    for needle in ('android-emulator-runner', 'api-level: 34', 'arch: x86_64', 'upload-artifact',
                   'workflow_dispatch', 'examples/android/ci/emulator.sh'):
        if needle not in workflow:
            problems.append('workflow lacks ' + needle)
    emulator = (ROOT/'examples/android/ci/emulator.sh').read_text()
    if 'adb install' not in emulator or '/sdcard/Download' not in emulator or 'run_android_host_evidence.py' not in emulator:
        problems.append('emulator execution/collection entry point missing')
    if 'physical_device_execution' not in doc or 'x86_64' not in doc:
        problems.append('documentation must state device scope and ABI')
    return problems, {'cases_declared': len(ids), 'unique_cases': len(set(ids))}


def check_gate_review(path, expected, script_name='check_evidence_gate.py'):
    from importlib.util import module_from_spec, spec_from_file_location
    script = ROOT/'tests/android_host'/script_name
    spec = spec_from_file_location('android_gate_review', script)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    result = load(path)
    check_identity(result, expected)
    require(result.get('accepted') is True and result.get('script_sha256') == sha256(script),
            'gate regression identity missing')
    checks = result.get('checks', [])
    require([item.get('name') for item in checks] == module.expected_names() and
            all(item.get('passed') is True for item in checks), 'gate regression checks incomplete')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--stage', type=Path, default=ROOT/'stage/android-x86_64')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--api', type=int, default=34)
    parser.add_argument('--target', default='default')
    parser.add_argument('--image', default='system-images;android-34;default;x86_64')
    parser.add_argument('--run-id', default=os.environ.get('GITHUB_RUN_ID', ''))
    parser.add_argument('--attempt', default=os.environ.get('GITHUB_RUN_ATTEMPT', ''))
    parser.add_argument('--source-sha', default=os.environ.get('GITHUB_SHA', ''))
    parser.add_argument('--run-url', default='')
    parser.add_argument('--workflow', default='wp13-android')
    parser.add_argument('--upstream', default=os.environ.get('ANDROID_HOST_UPSTREAM', '{}'))
    parser.add_argument('--gate-review', type=Path)
    parser.add_argument('--bounded-gate-review', type=Path)
    args = parser.parse_args()
    summary, problems = {}, []
    try:
        require(args.repo.resolve() == ROOT, 'checker must use the tested checkout')
        problems, summary = static_checks()
        if args.evidence:
            require(args.build is not None, 'build evidence is required')
            require(args.api == 34 and args.target == 'default' and
                    args.image == 'system-images;android-34;default;x86_64', 'emulator contract mismatch')
            expected = {**cloud_identity(), 'source_sha': args.source_sha, 'run_id': args.run_id, 'attempt': args.attempt}
            run_url = os.environ.get('GITHUB_SERVER_URL', 'https://github.com') + '/' + os.environ['GITHUB_REPOSITORY'] + '/actions/runs/' + expected['run_id']
            require(not args.run_url or args.run_url == run_url, 'run URL differs from the active cloud execution')
            summary = check_evidence(args.evidence, args.build, args.stage, json.loads(args.upstream), expected)
            summary['run']['url'] = run_url
            if args.gate_review:
                require(os.environ.get('ANDROID_GATE_OUTCOME') == 'success', 'gate regression step did not succeed')
                check_gate_review(args.gate_review, expected)
                summary['gate_review_sha256'] = sha256(args.gate_review)
                require(args.bounded_gate_review is not None and os.environ.get('ANDROID_BOUNDED_GATE_OUTCOME')=='success',
                        'bounded gate regression step did not succeed')
                check_gate_review(args.bounded_gate_review,expected,'check_bounded_evidence_gate.py')
                summary['bounded_gate_review_sha256']=sha256(args.bounded_gate_review)
    except Exception as error:
        problems.append(type(error).__name__ + ': ' + str(error)[:1200])
    candidate_only=bool(os.environ.get('ANDROID_CANDIDATE_SDK_BASE'))
    report = {'schema': 2, 'accepted': not problems and not candidate_only, 'ok': not problems,
              'candidate_only': candidate_only, 'candidate_validated': candidate_only and not problems,
              'problems': problems, 'summary': summary}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'accepted': report['accepted'], 'problems': problems,
                      'candidate_only':candidate_only,'candidate_validated':report['candidate_validated'],
                      'walkthrough': summary.get('summary'), 'review': summary.get('review', {}).get('summary')}))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
