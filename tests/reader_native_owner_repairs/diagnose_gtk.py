"""Actions-only read-only authentication of round two's failed chooser evidence."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/reader_hosts_integration'))
from final import Bundle, fetch, require


def observations(tree):
    selected = []
    def visit(node):
        if node.get('states', {}).get('focused') or node.get('states', {}).get('selected') or node.get('name') == 'Import':
            selected.append({k: node.get(k) for k in ('path', 'name', 'role', 'states')})
        for child in node.get('children', []):
            visit(child)
    visit(tree)
    return selected


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    meta = fetch('actions/artifacts/12618471568')
    require(meta['workflow_run']['head_sha'] == 'b11b0dd3b1354134dc1c82525e7e8578f3633758'
            and meta['workflow_run']['id'] == 40243909026 and meta['size_in_bytes'] == 128105447
            and meta['digest'] == 'sha256:3234dcf05413fcadb55f9ea84b02394caeb3aa7af0a8ee353c74c60d7309681d', 'original failed GTK ZIP identity differs')
    job = fetch('actions/jobs/121321358219')
    require(job['status'] == 'completed' and job['conclusion'] == 'failure' and job['head_sha'] == meta['workflow_run']['head_sha'], 'original failed GTK job differs')
    bundle = Bundle(meta)
    try:
        base = 'native-owner-gtk-focus-legacy/'
        report = bundle.report(base + 'report.json')
        require(report['accepted'] is False and report['observations'] == []
                and 'native keyboard Tab cannot reach enabled Import button' in report['failure'], 'original failure was replaced')
        result = dict(diagnostic_only=True, acceptance_granted=False, source_sha=os.environ['GITHUB_SHA'],
                      original_artifact={k: meta[k] for k in ('id', 'size_in_bytes', 'digest', 'expires_at')},
                      original_failure=report['failure'],
                      before=observations(bundle.report(base + 'import-chooser-tree.json')),
                      after=observations(bundle.report(base + 'failure-tree.json')),
                      keys=bundle.bytes(base + 'keys.log', 1024**2).decode())
        path = ROOT / 'build/native-owner-preflight/round-two-gtk-diagnostic.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result), flush=True)
    finally:
        bundle.close()


if __name__ == '__main__':
    main()
