"""Actions-only recovery of original frozen input bytes, never old SDK results."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from check_parallel_integration import fetch, pages, require

SOURCE = 'fa540271ea8ad2d9af4cd31467699db2e50c640a'
RUN = 39902467216
ARTIFACT = 12479327987
DIGEST = 'sha256:60ba3753cd54a5e932a3446a462ad66a486f23a521f888ee7a5a568b3cacd005'
BYTES = 41084748
MANIFEST = Path('tools/reading_corpus/real-v1.json')


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    root = Path(sys.argv[1]);root.mkdir(parents=True, exist_ok=False)
    raw_manifest = MANIFEST.read_bytes();manifest = json.loads(raw_manifest)
    manifest_sha = hashlib.sha256(raw_manifest).hexdigest()
    require(manifest_sha == 'f71f8a24faff664a03b7e15a7f424ec354f83c53fbd14f602d4b050f3fd19de1', 'frozen manifest changed')
    run = fetch('actions/runs/%d' % RUN)
    require(run['head_sha'] == SOURCE and run['run_attempt'] == 1 and run['status'] == 'completed'
            and run['conclusion'] == 'success' and run['path'] == '.github/workflows/reading-required.yml', 'wrong original run')
    jobs = pages('actions/runs/%d/attempts/1/jobs' % RUN, 'jobs')
    producer, = [j for j in jobs if j['name'] == 'corpus / R2 real document acceptance']
    require(producer['head_sha'] == SOURCE and producer['run_attempt'] == 1
            and producer['status'] == 'completed' and producer['conclusion'] == 'success', 'original input producer not complete')
    artifact = fetch('actions/artifacts/%d' % ARTIFACT)
    require(artifact['name'] == 'r2-real-corpus-%d-1' % RUN and artifact['size_in_bytes'] == BYTES
            and artifact['digest'] == DIGEST and artifact['workflow_run']['head_sha'] == SOURCE
            and artifact['workflow_run']['id'] == RUN and not artifact['expired']
            and datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc), 'foreign or expired input cache')
    data = subprocess.check_output(['gh', 'api', 'repos/' + os.environ['GITHUB_REPOSITORY']
                                    + '/actions/artifacts/%d/zip' % ARTIFACT], timeout=120)
    require(len(data) == BYTES and 'sha256:' + hashlib.sha256(data).hexdigest() == DIGEST, 'original ZIP changed')
    restored = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist();names = [i.filename for i in infos]
        require(len(infos) <= 10000 and len(names) == len(set(names))
                and sum(i.file_size for i in infos) <= 256*1024*1024, 'unbounded or duplicate ZIP')
        require(all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n
                    for n in names), 'unsafe ZIP path')
        def raw(tail, bound):
            name, = [n for n in names if n == tail or n.endswith('/' + tail)]
            require(0 < archive.getinfo(name).file_size <= bound, 'oversized original member')
            return archive.read(name)
        original = json.loads(raw('inputs/manifest.json', 1024*1024))
        require(original['complete'] is True and original['engine_executed'] is False
                and original['original_manifest_sha256'] == manifest_sha
                and len(original['files']) == len(manifest['files']) == 8, 'incomplete original input collection')
        for entry in manifest['files']:
            relative = PurePosixPath(entry['path'])
            require(not relative.is_absolute() and '..' not in relative.parts and '\\' not in entry['path'], 'unsafe input path')
            previous, = [r for r in original['files'] if r['id'] == entry['id']]
            require(all(previous[k] == entry[k] for k in ('id', 'path', 'sha256', 'size', 'source_url', 'license_url')),
                    'original publisher identity differs')
            value = raw('inputs/assets/' + entry['path'], entry['limits']['download_bytes'])
            require(len(value) == entry['size'] and hashlib.sha256(value).hexdigest() == entry['sha256'], 'original bytes differ')
            path = root/entry['path'];path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(value)
            restored.append({k: entry[k] for k in ('id', 'path', 'sha256', 'size', 'source_url')})
    result = dict(validator_source=os.environ['GITHUB_SHA'], validation_run=os.environ['GITHUB_RUN_ID'],
                  source_input_run=RUN, source_input_sha=SOURCE, source_input_job=producer['id'],
                  source_artifact=artifact, corpus_manifest_sha256=manifest_sha, files=restored,
                  purpose='original frozen input bytes only; no old SDK output/results reused', sdk_accepted=False)
    (root/'provenance.json').write_text(json.dumps(result, indent=2)+'\n');print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
