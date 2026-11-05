"""Authenticate original successful capture before inspecting any native bytes."""
import json
import sys
import lf07_contract as C

sys.path.insert(0, str(C.ROOT / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch


def authenticate():
    C.actions_only()
    C.OUT.mkdir(parents=True, exist_ok=True)
    attempt = 'actions/runs/%d/attempts/%d' % (C.PACKAGE_RUN, C.PACKAGE_ATTEMPT)
    run = fetch(attempt)
    C.require(run['head_sha'] == C.PACKAGE_SHA and run['run_attempt'] == C.PACKAGE_ATTEMPT and
        run['path'] == C.PACKAGE_WORKFLOW and run['head_branch'] == C.PACKAGE_BRANCH and
        run['status'] == 'completed' and run['conclusion'] == 'success', 'pinned capture run not exact successful source/attempt')
    jobs = fetch(attempt + '/jobs?per_page=100')
    C.require(jobs['total_count'] == len(jobs['jobs']), 'job pagination unsupported')
    for name in ('protocol', 'produce', 'authenticate'):
        matches = [j for j in jobs['jobs'] if j['name'] == name]
        C.require(len(matches) == 1 and matches[0]['head_sha'] == C.PACKAGE_SHA and
            matches[0]['status'] == 'completed' and matches[0]['conclusion'] == 'success', 'original job failed/missing: ' + name)
    artifact = fetch('actions/artifacts/' + str(C.CAPTURE['id']))
    C.require(all(artifact[k] == v for k, v in C.CAPTURE.items()) and not artifact['expired'] and
        artifact['workflow_run']['id'] == C.PACKAGE_RUN and artifact['workflow_run']['head_sha'] == C.PACKAGE_SHA,
        'original upload ID/name/size/digest/source/run differs')
    raw_path = C.OUT / 'original-upload.zip'
    with raw_path.open('w+b') as stream: download_artifact_zip(C.CAPTURE['id'], output=stream)
    C.require(raw_path.stat().st_size == C.CAPTURE['size_in_bytes'] and
        'sha256:' + C.digest(raw_path) == C.CAPTURE['digest'], 'download does not match pinned upload bytes')
    frozen = C.frozen_capture()
    upload = frozen.extract(raw_path.read_bytes(), C.OUT / 'original-upload')
    C.require({p.relative_to(upload).as_posix() for p in upload.rglob('*') if p.is_file()} ==
        {'capture.json', 'source.json', 'evidence.zip'}, 'unexpected upload files')
    capture = json.loads((upload / 'capture.json').read_text())
    source = json.loads((upload / 'source.json').read_text())
    for record in (capture, source):
        C.require(all(record[k] == v for k, v in C.package_identity().items()), 'original metadata identity mismatch')
    C.require(capture['capture_complete'] is True and capture['f07_accepted'] is False and
        source['source_scope_passed'] is True, 'original capture incomplete or inflated')
    envelope = capture['evidence']; path = upload / 'evidence.zip'
    C.require(envelope['name'] == path.name and envelope['bytes'] == path.stat().st_size and
        envelope['sha256'] == C.digest(path), 'nested evidence does not match capture')
    folder = frozen.extract(path.read_bytes(), C.OUT / 'evidence')
    C.require(C.digest(folder / 'inventory.json') == capture['inventory_sha256'], 'inventory hash differs')
    inventory = json.loads((folder / 'inventory.json').read_text())
    C.require(all(inventory[k] == v for k, v in C.package_identity().items()) and
        inventory['source'] == source and inventory['f07_accepted'] is False, 'inventory source identity differs')
    frozen.verify_files(folder, inventory)
    package = frozen.verify_package(folder)
    C.require(package == capture['package_identity'] == inventory['package_identity'], 'recomputed raw/F06/unpack/entry differs')
    loads = frozen.project_loads((folder / frozen.MAP).read_text(), inventory['producer_workspace'])
    C.require(loads == inventory['final_map_inputs'] and all(p in inventory['files'] for p in loads['project']), 'map closure differs')
    graph = (folder / 'commands/final-ninja-commands.txt').read_text()
    final = [line for line in graph.splitlines() if '-o gtk-host/exreader-linux ' in line]
    C.require(final == [inventory['final_link_command']] and 'gtk-account-host.map' in final[0], 'actual final link command differs')
    record = dict(C.identity(), capture_authenticated=True, artifact=artifact, original_run=run,
        original_jobs=jobs, package_identity=package, inventory_sha256=capture['inventory_sha256'],
        final_link_command=final[0], final_map_inputs=loads, f07_accepted=False)
    C.save(C.OUT / 'evidence-authentication.json', record)
    return folder, inventory, frozen
