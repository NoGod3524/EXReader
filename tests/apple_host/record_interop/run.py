"""Actions-only actual Apple sender/receiver; Android peer remains pending."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    for name in ('sdk', 'resources', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--incoming', type=Path)
    args = parser.parse_args()
    sdk, out = args.sdk.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    resources = out / 'resources'
    shutil.copytree(args.resources, resources)
    # This existing source PDF has actual public selectable text. Its original
    # bytes are exported through the real SDK lease, never regenerated.
    shutil.copyfile(ROOT / 'tests/fixtures/pdf-public-text.pdf', resources / 'Sample.pdf')
    program = out / 'record-interop'
    commands = []

    def run(command, label):
        with (out / (label + '.log')).open('wb') as stream:
            process = subprocess.Popen([str(value) for value in command], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
            try:
                status = process.wait(timeout=1800)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(); raise
        print((out / (label + '.log')).read_text(errors='replace'), flush=True)
        commands.append(dict(label=label, pid=process.pid, status=status))
        assert status == 0, (label, status)

    run([sys.executable, 'tools/apple_swift.py', '--sdk', sdk, '--', '-swift-version', '5', '-parse-as-library', '-O',
         '-D', 'EXR_APPLE_HOST_REVIEW', '-I', sdk / 'include', '-L', sdk / 'lib', '-lexreader',
         '-Xlinker', '-rpath', '-Xlinker', sdk / 'lib', 'examples/apple/HostSDK.swift',
         'examples/apple/HostModel.swift', 'examples/apple/HostCatalog.swift', 'examples/apple/SelectableText.swift',
         'tests/apple_host/record_interop/RecordInterop.swift', '-o', program], 'compile')
    bundle = out / 'sender-bundle'
    if args.incoming:
        # Directional receive is explicit; the default real Apple NUL sender
        # failure remains visible and is never substituted with an easier book.
        shutil.copytree(args.incoming, out / 'peer')
        bundle = out / 'peer/bundle'
    phases = []
    plan = [('send', 'send', out / 'sender-profile'),
                                  ('loopback-receive', 'receive', out / 'receiver-profile'),
                                  ('loopback-reopen', 'receive', out / 'receiver-profile')]
    if args.incoming:
        plan = [('android-receive', 'receive', out / 'receiver-profile'),
                ('android-reopen', 'receive', out / 'receiver-profile')]
    for label, mode, profile in plan:
        report = out / (label + '.json')
        run([program, mode, resources, profile, bundle, report], label)
        value = json.loads(report.read_text())
        assert value['accepted'] is True and value['mode'] == mode and len(value['checks']) == 12
        assert value['source_sha'] == os.environ['GITHUB_SHA'] and str(value['run_id']) == os.environ['GITHUB_RUN_ID'] and str(value['attempt']) == os.environ['GITHUB_RUN_ATTEMPT']
        phases.append(value)
    assert len({value['pid'] for value in phases}) == len(plan)
    manifest = json.loads((bundle / 'manifest.json').read_text())
    if not args.incoming:
        assert manifest['sender']['program_sha256'] == sha(program)
        assert manifest['sender']['sdk_dso_sha256'] == sha(bundle / 'proofs/sdk.dylib')
    original = ROOT / 'build/apple-record-compatibility/evidence'
    shutil.copytree(original, out / 'original-compatibility')
    result = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], accepted=True, commands=commands,
                  phases=phases, program_sha256=sha(program), manifest_sha256=sha(bundle / 'manifest.json'),
                  actual_android_host_interop_accepted=False, actual_android_peer='pending',
                  host_ui_accepted=False, physical_device_accepted=False)
    if args.incoming:
        result.update(direction='android-to-apple', android_to_apple_accepted=True,
                      apple_to_android_accepted=False, bidirectional_interoperability_accepted=False,
                      actual_apple_sender_accepted=False, actual_android_peer='authenticated-sender-only',
                      peer_receipt=json.loads((out / 'peer/receipt.json').read_text()))
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('ACTUAL_APPLE_SENDER_AND_LOOPBACK ' + json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
