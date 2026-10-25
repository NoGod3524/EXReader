"""Actions-only original Apple owner processes across the two installed SDKs."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

BASE = 'eea3087c2ef27b9d45e00333ef0a16e586a0ac6e'
SDKS = {'old': ('3.40.0', '9854061be331fe603a1822d9b2b36ee357154927'),
        'new': ('3.41.0', 'edddc463c06ed5731195cdb8f06b2df6dff7699e')}
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    out = ROOT / 'build/apple-record-compatibility'
    out.mkdir(parents=True, exist_ok=False)
    evidence = out / 'evidence'
    evidence.mkdir()
    commands, phases, programs = [], [], {}

    def run(arguments, name, *, expected=0, timeout=1800, cwd=ROOT):
        log = evidence / (name + '.log')
        with log.open('wb') as stream:
            process = subprocess.Popen([str(x) for x in arguments], cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
            try:
                status = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
                raise
        print(log.read_text(errors='replace'), flush=True)
        commands.append(dict(name=name, pid=process.pid, exit=status, expected_exit=expected,
                             log=log.name, arguments=[str(x) for x in arguments]))
        assert status == expected, (name, status, expected)

    old_owner = evidence / 'original-owner/HostReadingRecords.swift'
    old_owner.parent.mkdir()
    old_owner.write_bytes(subprocess.check_output(['git', 'show', BASE + ':examples/apple/HostReadingRecords.swift'], cwd=ROOT))
    java_classes = evidence / 'java-policy-classes'
    run(['javac', '-d', java_classes,
         ROOT / 'examples/android/app/src/main/java/org/exreader/host/ReadingParserPolicy.java',
         HERE / 'ParserPolicyCheck.java'], 'java-policy-compile')
    run(['java', '-cp', java_classes, 'org.exreader.host.ParserPolicyCheck'], 'java-policy-check')
    java_cases = [line.removeprefix('CASE ') for line in (evidence / 'java-policy-check.log').read_text().splitlines() if line.startswith('CASE ')]
    assert len(java_cases) == len(set(java_cases)) == 20
    for label, (version, source) in SDKS.items():
        source_dir, prefix = out / ('source-' + label), out / ('sdk-' + label)
        source_dir.mkdir()
        # Archive/extract only inside this Actions job.
        archive = out / (label + '.tar')
        with archive.open('wb') as stream:
            subprocess.run(['git', 'archive', source], cwd=ROOT, stdout=stream, check=True)
        run(['tar', '-xf', archive, '-C', source_dir], label + '-archive')
        build = out / ('build-' + label)
        run(['cmake', '-S', source_dir, '-B', build, '-DCMAKE_BUILD_TYPE=Release',
             '-DEXR_BUILD_TESTS=OFF', '-DEXR_BUILD_TOOLS=OFF', '-DEXR_ENABLE_AAC=OFF'], label + '-configure')
        run(['cmake', '--build', build, '--parallel', '4'], label + '-build')
        run(['cmake', '--install', build, '--prefix', prefix], label + '-install')
        run([sys.executable, 'tools/build_apple_product.py', '--sdk', prefix, '--sdk-version', version,
             '--target', 'macos', '--build', out / ('products-' + label)], label + '-products')
        # Keep the complete original 19-case owner/recovery suite unchanged.
        run([sys.executable, 'tests/apple_host/reading/run_native.py', '--sdk', prefix,
             '--resources', out / ('resources-' + label), '--output', evidence / ('original-' + label)], label + '-original19')
        for owner in (['original'] if label == 'old' else ['original', 'compatible']):
            name = label + '-' + owner
            program = evidence / name
            sources = ['examples/apple/HostSDK.swift', 'examples/apple/HostModel.swift',
                       'examples/apple/HostCatalog.swift', 'examples/apple/SelectableText.swift', str(HERE / 'RecordCompatibility.swift')]
            if owner == 'original':
                sources.append(str(old_owner))
            run([sys.executable, 'tools/apple_swift.py', '--sdk', prefix, '--', '-swift-version', '5',
                 '-parse-as-library', '-O', '-D', 'EXR_APPLE_HOST_REVIEW', '-I', prefix / 'include',
                 '-L', prefix / 'lib', '-lexreader', '-Xlinker', '-rpath', '-Xlinker', prefix / 'lib',
                 *sources, '-o', program], name + '-compile')
            programs[name] = dict(path=program.name, sha256=digest(program), sdk=version,
                                  owner_sha256=digest(old_owner if owner == 'original' else ROOT / 'examples/apple/HostReadingRecords.swift'))
        for library in prefix.glob('lib/*'):
            if library.suffix in ('.a', '.dylib') and library.is_file():
                destination = evidence / ('libraries-' + label) / library.name
                destination.parent.mkdir(exist_ok=True)
                shutil.copyfile(library.resolve(), destination)

    resources = out / 'resources-old'
    for name in ('Records.txt', 'Bounded.epub', 'Sample.pdf', 'NavigationPages.cbz', 'Reader.otf', 'reader-catalog-v1.sql'):
        destination = evidence / 'inputs' / name
        destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(resources / name, destination)
    profiles = evidence / 'profiles'
    profiles.mkdir()

    def phase(program, mode, profile, tag, name, expected=0):
        report = evidence / (name + '.json')
        run([evidence / program, mode, resources, profile, report, tag], name, expected=expected)
        record = dict(name=name, program=program, mode=mode, producer_parser=tag,
                      pid=commands[-1]['pid'], exit=expected, report=report.name if expected == 0 else None)
        if expected == 0:
            raw = json.loads(report.read_text())
            assert raw['accepted'] is True and raw['mode'] == mode and raw['sdk'] == programs[program]['sdk']
            assert raw['pid'] == record['pid'] and raw['producer_parser'] == tag
        phases.append(record)

    old = profiles / 'old-produced'
    phase('old-original', 'produce', old, '3.40.0', 'old-produce')
    for program, mode, name in [('old-original', 'consume', 'old-control'),
                                ('new-original', 'refuse', 'new-original-rejection'),
                                ('new-compatible', 'consume', 'new-upgrade')]:
        profile = profiles / name
        shutil.copytree(old, profile)
        phase(program, mode, profile, '3.40.0', name)
    new = profiles / 'new-produced'
    phase('new-compatible', 'produce', new, '3.41.0', 'new-produce')
    for program, mode, name in [('new-compatible', 'consume', 'new-control'),
                                ('old-original', 'refuse', 'old-downgrade-rejection')]:
        profile = profiles / name
        shutil.copytree(new, profile)
        phase(program, mode, profile, '3.41.0', name)
    for boundary, code in [('before', 73), ('after', 74)]:
        profile = profiles / ('pending-' + boundary)
        phase('old-original', 'kill-' + boundary, profile, '3.40.0', 'kill-' + boundary, expected=code)
        original = profile / 'original-request.json'
        prior = digest(original)
        phase('new-compatible', 'replay-' + boundary, profile, '3.40.0', 'replay-' + boundary)
        assert digest(original) == prior

    for label, tag in [('old', 'exreader-sdk-3.40.0'), ('new', 'exreader-sdk-3.41.0')]:
        produced = profiles / (label + '-prefixed-produced')
        program = 'old-original' if label == 'old' else 'new-compatible'
        phase(program, 'produce-prefixed', produced, tag, label + '-prefixed-produce')
        controls = [('new-compatible', 'consume', label + '-prefixed-accept'),
                    ('new-original', 'refuse', label + '-prefixed-original-reject')]
        if label == 'old':
            controls.append(('old-original', 'refuse', 'old-prefixed-original340-reject'))
        for consumer, mode, name in controls:
            target = profiles / name
            shutil.copytree(produced, target)
            phase(consumer, mode, target, tag, name)

    result = dict(accepted=True, source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], sdks=SDKS, programs=programs,
                  commands=commands, phases=phases, host_ui_accepted=False, physical_device_accepted=False,
                  downgrade_accepted=False, original_suite_cases_per_sdk=19,
                  java_policy_cases=java_cases, actual_android_host_interop_accepted=False)
    result['inputs'] = {p.name: dict(bytes=p.stat().st_size, sha256=digest(p)) for p in (evidence / 'inputs').iterdir() if p.is_file()}
    result['files'] = {p.relative_to(evidence).as_posix(): dict(bytes=p.stat().st_size, sha256=digest(p))
                       for p in evidence.rglob('*') if p.is_file()}
    (evidence / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('APPLE_RECORD_UPGRADE_ACCEPTED ' + json.dumps({k: v for k, v in result.items() if k not in ('files', 'inputs', 'commands')}))


if __name__ == '__main__':
    main()
