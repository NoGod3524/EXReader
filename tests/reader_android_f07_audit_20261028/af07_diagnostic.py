"""Actions-only diagnosis of the preserved first audit; no native inspection."""
import json
import re
import sys
import zipfile

import af07_contract as C
sys.path.insert(0, str(C.ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip

PRIOR_SHA = '9ee16b298f89e2a1aff613df7b7076bcbd28250f'
PRIOR_RUN, PRIOR_ATTEMPT, ARTIFACT = 40780887828, 1, 12856916312
SIZE = 207019263
DIGEST = 'e78cc22ad3f6b810c038fb22877e880090deb5ca128d37c20b140303f3628325'


def selected_failure(summary, commands, stdout, stderr):
    C.require(summary['audit_sha'] == PRIOR_SHA and str(summary['audit_run']) == str(PRIOR_RUN) and
              str(summary['audit_attempt']) == '1' and summary['original_capture_replayed'] is True and
              summary['android_static_closure_accepted'] is False and summary['full_six_platform_f07_accepted'] is False,
              'prior audit summary identity/acceptance differs')
    rows = [row for row in commands if row['label'] == 'system-008']
    C.require(len(rows) == 1, 'failed inspector record absent/duplicate')
    row = rows[0]; argv = row['argv']
    C.require(type(row['exit']) is int and row['exit'] != 0 and len(argv) == 5 and
              argv[1:4] == ['-D', '-g', '--defined-only'] and
              re.fullmatch(r'/[^\n]+/ndk/27\.0\.12077973/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-nm', argv[0]) and
              re.fullmatch(r'/[^\n]+/ndk/27\.0\.12077973/toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/x86_64-linux-android/26/[A-Za-z0-9_.+-]+\.so', argv[4]),
              'not the exact failed pinned-system inspection shape')
    C.require(len(stdout) <= 8192 and len(stderr) <= 8192 and C.sha(stdout) == row['stdout_sha256'] and
              C.sha(stderr) == row['stderr_sha256'], 'prior failed native output hash/budget differs')
    return dict(command=row, stdout=stdout.decode('utf-8'), stderr=stderr.decode('utf-8'),
                prior_audit_sha=PRIOR_SHA, prior_audit_run=PRIOR_RUN, prior_audit_attempt=1,
                prior_original_capture_replayed=True, diagnostic_only=True, android_static_closure_accepted=False,
                full_six_platform_f07_accepted=False, no_payload_or_native_tool_execution=True,
                include_dependency_coverage_complete=False,
                include_dependency_gap='Original capture omitted compiler depfiles, .ninja_deps and ninja -t deps; source scans are not complete preprocessed include evidence.')


def main():
    C.guard()
    attempt = f'actions/runs/{PRIOR_RUN}/attempts/1'
    run = fetch(attempt)
    C.require(run['head_sha'] == PRIOR_SHA and run['run_attempt'] == 1 and run['path'] == C.WORKFLOW and
              run['head_branch'] == C.BRANCH and run['status'] == 'completed' and run['conclusion'] == 'failure',
              'prior failed audit run differs')
    item = fetch('actions/artifacts/' + str(ARTIFACT))
    C.require(item['id'] == ARTIFACT and item['name'] == f'android-f07-audit-{PRIOR_RUN}-1' and
              item['size_in_bytes'] == SIZE and item['digest'] == 'sha256:' + DIGEST and item['expired'] is False and
              item['workflow_run']['id'] == PRIOR_RUN and item['workflow_run']['head_sha'] == PRIOR_SHA,
              'prior audit upload metadata differs')
    folder = C.OUT / 'diagnostic-input'; folder.mkdir(parents=True, exist_ok=False)
    path = folder / 'original.zip'
    with path.open('w+b') as output: download_artifact_zip(ARTIFACT, output=output)
    C.require(path.stat().st_size == SIZE and C.digest(path) == DIGEST, 'prior audit ZIP bytes differ')
    with zipfile.ZipFile(path) as bundle:
        infos = {item.filename: item for item in C.members(bundle)}
        def read(name):
            C.require(name in infos and not infos[name].is_dir() and infos[name].file_size <= 1024**2,
                      'required bounded diagnostic member absent/oversized')
            return bundle.read(name)
        report = selected_failure(json.loads(read('summary.json')), json.loads(read('native/commands.json')),
                                  read('native/system-008.stdout'), read('native/system-008.stderr'))
    report.update(C.identity(), original_artifact=ARTIFACT, original_bytes=SIZE, original_sha256=DIGEST)
    C.save(C.OUT / 'prior-native-diagnostic.json', report)
    print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == '__main__': main()
