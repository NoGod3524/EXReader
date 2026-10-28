"""Independent same-run upload authentication and native replay, without launching."""
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

import contract as C
sys.path.insert(0, str(C.ROOT / 'tools'))
from check_parallel_integration import download_artifact_zip


def get(path):
    request = urllib.request.Request('https://api.github.com/repos/' + C.REPO + '/' + path,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main():
    C.actions_only()
    out = C.ROOT / 'build/linux-f07-authentication'; out.mkdir(parents=True, exist_ok=True)
    report = dict(C.identity(), capture_authenticated=False, f07_accepted=False,
        acceptance_gap='Final Linux SDK/SQLite provider and cross-package private-entry audit remains separate.')
    try:
        C.guard()
        C.require(os.environ['PRODUCER_RESULT'] == 'success' and os.environ['PROTOCOL_RESULT'] == 'success', 'producer/protocol job did not succeed')
        run, attempt = os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT']
        workflow = json.loads(get('actions/runs/' + run + '/attempts/' + attempt))
        C.require(workflow['head_sha'] == os.environ['GITHUB_SHA'] and str(workflow['run_attempt']) == attempt,
                  'remote run SHA/attempt mismatch')
        C.require(workflow['path'] == C.WORKFLOW and workflow['head_branch'] == C.BRANCH, 'remote workflow/branch mismatch')
        jobs = json.loads(get('actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100'))
        C.require(jobs['total_count'] == len(jobs['jobs']), 'job pagination not supported')
        producer = [j for j in jobs['jobs'] if j['name'] == 'produce']
        C.require(len(producer) == 1 and producer[0]['conclusion'] == 'success' and producer[0]['status'] == 'completed'
                  and producer[0]['head_sha'] == os.environ['GITHUB_SHA'], 'exact producer job not successful')
        protocol = [j for j in jobs['jobs'] if j['name'] == 'protocol']
        C.require(len(protocol) == 1 and protocol[0]['conclusion'] == 'success' and protocol[0]['status'] == 'completed'
                  and protocol[0]['head_sha'] == os.environ['GITHUB_SHA'], 'exact protocol job not successful')
        artifacts = json.loads(get('actions/runs/' + run + '/artifacts?per_page=100'))
        C.require(artifacts['total_count'] == len(artifacts['artifacts']), 'artifact pagination not supported')
        name = 'linux-f07-capture-' + run + '-' + attempt
        found = [a for a in artifacts['artifacts'] if a['name'] == name]
        C.require(len(found) == 1, 'missing/duplicate same-attempt capture upload')
        artifact = found[0]
        C.require(artifact['id'] == int(os.environ['CAPTURE_ARTIFACT_ID']) and artifact['expired'] is False and artifact['workflow_run']['id'] == int(run)
                  and artifact['workflow_run']['head_sha'] == os.environ['GITHUB_SHA'], 'upload run/source/expiry')
        raw_path = out / 'original-github-upload.zip'
        with raw_path.open('w+b') as stream:
            download_artifact_zip(artifact['id'], output=stream)
        raw = raw_path.read_bytes()
        C.require(len(raw) == artifact['size_in_bytes'] and artifact['digest'] == 'sha256:' + C.sha(raw)
                  and os.environ['CAPTURE_ARTIFACT_DIGEST'].removeprefix('sha256:') == C.sha(raw), 'original GitHub upload size/digest')
        upload = C.extract(raw, out / 'original-upload')
        C.require({p.relative_to(upload).as_posix() for p in upload.rglob('*') if p.is_file()}
                  == {'capture.json', 'source.json', 'evidence.zip'}, 'unexpected upload inventory')
        capture = json.loads((upload / 'capture.json').read_text())
        source = json.loads((upload / 'source.json').read_text())
        for item in (capture, source):
            for key, value in C.identity().items():
                C.require(item[key] == value, 'uploaded metadata identity drift: ' + key)
        C.require(capture['capture_complete'] is True and capture['f07_accepted'] is False, 'capture result absent/inflated')
        envelope = capture['evidence']
        C.require(envelope['name'] == 'evidence.zip', 'unknown nested archive')
        evidence = (upload / 'evidence.zip').read_bytes()
        C.require(len(evidence) == envelope['bytes'] and C.sha(evidence) == envelope['sha256'], 'nested evidence bytes')
        folder = C.extract(evidence, out / 'evidence')
        C.require(C.digest(folder / 'inventory.json') == capture['inventory_sha256'], 'inventory digest mismatch')
        inventory = json.loads((folder / 'inventory.json').read_text())
        for key, value in C.identity().items():
            C.require(inventory[key] == value, 'inventory identity drift: ' + key)
        C.require(inventory['source'] == source and inventory['f07_accepted'] is False, 'source proof/F07 scope mismatch')
        C.verify_files(folder, inventory)
        package = C.verify_package(folder)
        C.require(package == capture['package_identity'] == inventory['package_identity'], 'recomputed package binding differs')
        loads = C.project_loads((folder / C.MAP).read_text(), inventory['producer_workspace'])
        C.require(loads == inventory['final_map_inputs'], 'actual final map input inventory differs')
        C.require(all(p in inventory['files'] for p in loads['project']), 'actual map inputs missing from retained closure')
        native = sorted(name for name in inventory['files'] if name.endswith('.a') or '.so' in Path(name).name)
        C.require(native and native == inventory['native_inputs'], 'native inventory mismatch')
        command_graph = (folder / 'commands/final-ninja-commands.txt').read_text()
        final = [line for line in command_graph.splitlines() if '-o gtk-host/exreader-linux ' in line]
        C.require(len(final) == 1 and final[0] == inventory['final_link_command'] and 'gtk-account-host.map' in final[0], 'actual final link command mismatch')
        recorded = {row['label']: row for row in inventory['commands']}
        C.require(len(recorded) == len(inventory['commands']), 'duplicate native command labels')
        producer_stage = inventory['producer_workspace'] + '/build/linux-f07-capture/evidence'
        replay = []
        def inspect(label, argv):
            done = subprocess.run(list(map(str, argv)), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            path = out / 'native-replay' / (label + '.txt'); path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(done.stdout); path.with_suffix('.stderr.txt').write_bytes(done.stderr)
            replay.append(dict(label=label, argv=list(map(str, argv)), exit_code=done.returncode,
                               stdout_sha256=C.sha(done.stdout), stderr_sha256=C.sha(done.stderr)))
            C.require(done.returncode == 0 and done.stdout.strip(), 'native replay failed/empty: ' + label)
            original = recorded[label]
            C.require(original['exit_code'] == 0 and original['cwd'] == inventory['producer_workspace'],
                      'producer native inspection did not succeed: ' + label)
            rewritten = [arg.replace(producer_stage + '/', str(folder) + '/') for arg in original['argv']]
            C.require(rewritten == list(map(str, argv)), 'producer native invocation mismatch: ' + label)
            for key, actual in (('stdout', done.stdout), ('stderr', done.stderr)):
                original_bytes = (folder / original[key]).read_bytes()
                normalized_original = original_bytes.replace(producer_stage.encode(), b'<CAPTURE>')
                normalized_actual = actual.replace(str(folder).encode(), b'<CAPTURE>')
                C.require(normalized_original == normalized_actual, 'native replay output mismatch: ' + label + '/' + key)
        inspect('final-readelf-header', ['readelf', '-h', folder / C.PROGRAM])
        inspect('final-readelf-dynamic', ['readelf', '-d', folder / C.PROGRAM])
        inspect('final-readelf-symbols', ['readelf', '-Ws', folder / C.PROGRAM])
        inspect('final-nm', ['nm', '-A', '-g', folder / C.PROGRAM])
        for index, name in enumerate(native):
            inspect('archive-' + str(index) + '-nm', ['nm', '-A', '-g', folder / name])
            if name.endswith('.a'):
                inspect('archive-' + str(index) + '-members', ['ar', 't', folder / name])
            else:
                inspect('image-' + str(index) + '-dynamic', ['readelf', '-d', folder / name])
        C.require(set(recorded) == {r['label'] for r in replay} | {'final-ninja-commands', 'final-ninja-query'}, 'unexpected/missing producer inspection')
        report.update(capture_authenticated=True, artifact=artifact, original_upload_sha256=C.sha(raw),
            package_identity=package, evidence_sha256=envelope['sha256'], inventory_sha256=capture['inventory_sha256'],
            files=len(inventory['files']), native_inputs=len(native), final_map_inputs=loads, replay=replay,
            producer_job_id=producer[0]['id'], source=source)
    except Exception as error:
        report['failure'] = str(error)
        raise
    finally:
        C.save(out / 'authentication.json', report)


if __name__ == '__main__':
    main()
