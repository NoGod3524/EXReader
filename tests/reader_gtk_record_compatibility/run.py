"""Actions-only true old/new GTK owner processes and durable-boundary kills."""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

OLD_HOST = 'eaa6852c8e965720c4ad07cfd223c30c282803f8'
OLD_SDK = '9854061be331fe603a1822d9b2b36ee357154927'
NEW_SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
BASE = '7290245f5ce0c85e76ea31bcf9d2de6b12723b5c'
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/gtk-record-compatibility'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(label, args, cwd=ROOT, timeout=1800):
    print('RUN ' + label, flush=True)
    done = subprocess.run(list(map(str, args)), cwd=cwd, capture_output=True,
                          text=True, encoding='utf-8', errors='replace', timeout=timeout)
    (OUT / (label + '.log')).write_text(done.stdout + '\n' + done.stderr)
    print(done.stdout[-12000:], flush=True)
    if done.returncode:
        print(done.stderr[-12000:], flush=True)
        raise RuntimeError(label + ' exited ' + str(done.returncode))


def cmake(label, source, binary, *, prefix=None, sdk=None, version=None, owner=None, install=False):
    args = ['cmake', '-S', source, '-B', binary, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release']
    if prefix:
        search = str(prefix) + (';' + str(sdk) if sdk else '')
        args += ['-DCMAKE_PREFIX_PATH=' + search, '-DREADER_PRODUCT_PREFIX=' + str(prefix),
                 '-DCMAKE_INSTALL_PREFIX=' + str(prefix)]
    if sdk:
        args += ['-DEXR_SDK=' + str(sdk)]
    if version:
        args += ['-DEXR_SDK_VERSION=' + version]
    if owner:
        args += ['-DHOST_SOURCE=' + str(owner), '-DMODULE_PREFIX=' + str(prefix)]
    command(label + '-configure', args)
    targets = ['--target', 'gtk-record-compatibility', 'reader-gtk-reading-records-backend'] if owner else []
    command(label + '-build', ['cmake', '--build', binary, '--parallel', '4', *targets])
    if install:
        command(label + '-install', ['cmake', '--install', binary])


def build():
    # Compile the new actual-owner probe first, before repeating the frozen
    # SDK build. Public/private header or probe compiler failures surface early.
    cmake('new-owner-early', Path(__file__).parent, OUT / 'new-owner',
          prefix=ROOT / 'build/account-stage', sdk=ROOT / 'build/reading-library/stage',
          version='3.41.0', owner=ROOT)
    old = OUT / 'old-source'
    old.mkdir()
    with (OUT / 'old-source.tar').open('wb') as target:
        subprocess.run(['git', 'archive', OLD_HOST], cwd=ROOT, stdout=target, check=True)
    command('old-source-unpack', ['tar', '-xf', OUT / 'old-source.tar', '-C', old])
    old_sdk = OUT / 'old-sdk-stage'
    command('old-sdk-configure', ['cmake', '--preset', 'reading-library',
            '-DCMAKE_INSTALL_PREFIX=' + str(old_sdk)], cwd=old)
    command('old-sdk-build', ['cmake', '--build', '--preset', 'reading-library', '--parallel', '4'], cwd=old)
    command('old-sdk-install', ['cmake', '--install', old / 'build/reading-library'], cwd=old)
    old_prefix = OUT / 'old-modules'
    for name, source in [('product', 'apps/reader/store/native'), ('webdav', 'extras/webdav'),
        ('revisions', 'apps/reader/revisions'), ('commands', 'apps/reader/commands'),
        ('metadata', 'apps/reader/desktop-metadata'), ('sync', 'apps/reader/sync'),
        ('session', 'apps/reader/session'), ('credentials', 'extras/credentials'),
        ('sideload', 'extras/sideload'), ('reading-state', 'apps/reader/reading-state'),
        ('reading-commands', 'apps/reader/reading-commands'), ('annotation-view', 'apps/reader/annotation-view')]:
        cmake('old-' + name, old / source, OUT / ('old-' + name), prefix=old_prefix,
              sdk=old_sdk, version='3.40.0', install=True)
    entries = {}
    for name, source, sdk, prefix, version in [
        ('old', old, old_sdk, old_prefix, '3.40.0'),
        ('new', ROOT, ROOT / 'build/reading-library/stage', ROOT / 'build/account-stage', '3.41.0')]:
        binary = OUT / (name + '-owner')
        cmake(name + '-owner', Path(__file__).parent, binary, prefix=prefix, sdk=sdk, version=version, owner=source)
        exe = binary / 'gtk-record-compatibility'
        entries[name] = dict(runtime_version=version, host_source=OLD_HOST if name == 'old' else os.environ['GITHUB_SHA'],
            sdk_source=OLD_SDK if name == 'old' else NEW_SDK, sdk_version=version,
            binary=exe.relative_to(OUT).as_posix(), binary_sha256=sha(exe),
            backend_source_sha256=sha(source / 'examples/linux/reading.c'),
            records_source_sha256=sha(source / 'examples/linux/reading_records_backend.inc'),
            map=(binary / 'owner.map').relative_to(OUT).as_posix(), map_sha256=sha(binary / 'owner.map'))
    return entries


def exercise(entries):
    font = ROOT / 'build/account-package/EXReader-Linux/Reader.otf'
    fixtures = ROOT / 'build/records-command-fixtures'
    formats = {'txt': 'book.txt', 'epub': 'book.epub', 'pdf': 'pages.pdf', 'cbz': 'pages.cbz'}
    cases = []
    process_count = 0
    old_controls = OUT / 'old-original-records'
    old_controls.mkdir(mode=0o700)
    legacy = OUT / 'old-owner/actual-owner/reader-gtk-reading-records-backend'
    for mode, database, filename in [('first', 'library.sqlite', 'book.txt'),
                                     ('resumed', 'library.sqlite', 'book.txt'),
                                     ('routes', 'routes.sqlite', 'book.epub'),
                                     ('graphs', 'graphs.sqlite', 'book.txt')]:
        command('old-original-' + mode, [legacy, old_controls / database, font, fixtures / filename, mode], timeout=240)

    def process(name, profile, book, mode, *, created=None, parser=None, env=None, allow_refusal=False):
        nonlocal process_count
        path = profile / (name + '-' + mode + '-' + str(process_count) + '.json')
        process_count += 1
        entry = entries[name]
        args = [OUT / entry['binary'], profile, font, book, mode, path, entry['runtime_version'],
                parser or entry['runtime_version']]
        local = dict(os.environ)
        if env:
            local.update(env)
        if created is not None:
            local['GTK_RECORD_EXPECT_CREATED'] = str(created)
        done = subprocess.run(list(map(str, args)), env=local, capture_output=True, text=True, timeout=180)
        log = path.with_suffix('.log'); log.write_text(done.stdout + '\n' + done.stderr)
        if done.returncode:
            if allow_refusal:
                refusal = 'compatibility check failed: actual GTK jump independently proves FOUND and emits accepted frame'
                assert done.returncode == 1 and refusal in done.stderr, 'reverse crash or unrelated failure is not a contract refusal'
                return dict(accepted=False, exit=done.returncode, rejection_stage='actual-record-jump',
                            log=log.relative_to(OUT).as_posix(), log_sha256=sha(log))
            raise RuntimeError(str(args) + '\n' + done.stdout + '\n' + done.stderr)
        report = json.loads(path.read_text())
        assert report['accepted'] is True and report['runtime_version'] == entry['runtime_version']
        assert report['check_count'] == len(report['checks']) and all(row['passed'] is True for row in report['checks'])
        if mode == 'retry':
            assert report['created'] == created and report['retained_parser'] == parser
        return dict(accepted=True, report=path.relative_to(OUT).as_posix(), report_sha256=sha(path), checks=report['check_count'],
                    log=log.relative_to(OUT).as_posix(), log_sha256=sha(log))

    for writer, reader in [('old', 'old'), ('new', 'new'), ('old', 'new'), ('new', 'old')]:
        for kind, filename in formats.items():
            profile = OUT / ('profile-' + writer + '-' + reader + '-' + kind)
            profile.mkdir(mode=0o700)
            book = fixtures / filename
            seeded = process(writer, profile, book, 'seed')
            before = {p.name: sha(p) for p in profile.glob('*.json') if len(p.stem) == 32}
            # Preserve the exact writer-closed state before the other SDK ever
            # opens it; uncertain old saves start from this genuine old state.
            shutil.copytree(profile, OUT / ('seed-snapshot-' + writer + '-' + reader + '-' + kind))
            result = process(reader, profile, book, 'verify', allow_refusal=(writer, reader) == ('new', 'old'))
            assert before and all(sha(profile / name) == digest for name, digest in before.items())
            cases.append(dict(name=writer + '-to-' + reader + '-' + kind, kind='reopen', format=kind,
                writer=writer, reader=reader, source_sha256=sha(book), source_bytes=book.stat().st_size,
                writer_process=seeded, reader_process=result, original_wire_count=len(before), original_wire_sha256=before,
                wire_copies_unchanged=True, reverse_observation=(writer, reader) == ('new', 'old')))

    # Both actual process commit boundaries, plus same-version controls. Replayed
    # requests are exact original private bytes, never reconstructed JSON.
    for writer, reader, kinds in [('old', 'old', ['txt']), ('new', 'new', ['txt']),
                                 ('old', 'new', list(formats))]:
        for kind in kinds:
            for stage in ('before', 'after'):
                origin = OUT / ('seed-snapshot-' + writer + '-' + reader + '-' + kind)
                profile = OUT / ('kill-' + writer + '-' + reader + '-' + kind + '-' + stage)
                shutil.copytree(origin, profile)
                os.chmod(profile, 0o700)
                marker = profile / 'commit-boundary'
                report = profile / 'killed-process-partial.json'
                entry = entries[writer]
                args = [OUT / entry['binary'], profile, font, fixtures / formats[kind], 'pending', report,
                        entry['runtime_version'], entry['runtime_version']]
                env = dict(os.environ, GTK_RECORD_KILL_STAGE=stage, GTK_RECORD_KILL_MARKER=str(marker))
                with (profile / 'killed-process.log').open('w') as log:
                    child = subprocess.Popen(list(map(str, args)), env=env, stdout=log, stderr=log)
                    end = time.monotonic() + 60
                    while not marker.exists() and child.poll() is None and time.monotonic() < end:
                        time.sleep(.01)
                    assert marker.exists() and child.poll() is None, 'actual process did not reach product boundary'
                    pending = profile / 'library.sqlite.product.sqlite.reading.pending'
                    original = pending.read_bytes()
                    assert pending.stat().st_mode & 0o077 == 0
                    config = configparser.ConfigParser(interpolation=None); config.read_string(original.decode())
                    assert config['request']['parser'] == entry['runtime_version']
                    revision = config['request']['revision']
                    child.kill(); child.wait(timeout=20)
                    assert child.returncode == -signal.SIGKILL and pending.read_bytes() == original
                    retained = profile / 'original-request.keyfile';retained.write_bytes(original);os.chmod(retained, 0o600)
                expected = 1 if stage == 'before' else 0
                first = process(reader, profile, fixtures / formats[kind], 'retry', created=expected, parser=entry['runtime_version'])
                assert not pending.exists()
                pending.write_bytes(original);os.chmod(pending, 0o600)
                second = process(reader, profile, fixtures / formats[kind], 'retry', created=0, parser=entry['runtime_version'])
                assert not pending.exists()
                cases.append(dict(name=writer + '-to-' + reader + '-' + kind + '-' + stage, kind='kill-retry',
                    writer=writer, reader=reader, format=kind, boundary=stage, killed_by='SIGKILL',
                    request_sha256=hashlib.sha256(original).hexdigest(), original_parser=entry['runtime_version'],
                    original_request=retained.relative_to(OUT).as_posix(),
                    original_revision=revision, first_created=expected, second_created=0,
                    first_retry=first, second_retry=second, no_auto_replay=True,
                    boundary_observation=marker.read_text()))
    return cases


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    OUT.mkdir(parents=True, exist_ok=False)
    report = dict(accepted=False, source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], base=BASE, old_host=OLD_HOST, old_sdk=OLD_SDK, new_sdk=NEW_SDK,
                  complete_product=False, host_ui_compatibility_claimed=False, programs={}, cases=[], problems=[])
    try:
        report['programs'] = build()
        report['cases'] = exercise(report['programs'])
        report['accepted'] = True
    except Exception as error:
        report['problems'].append(str(error))
        # Surface the concrete test failure while the job's always-run evidence
        # upload is finishing; ordinary Actions logs are unavailable until then.
        annotation = str(error)[:6000].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print('::error::' + annotation, flush=True)
    (OUT / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    evidence = ROOT / 'build/gtk-record-compatibility-evidence'
    evidence.mkdir()
    shutil.copy2(OUT / 'result.json', evidence / 'result.json')
    for name in ('old', 'new'):
        folder = evidence / (name + '-owner');folder.mkdir()
        for file in ('gtk-record-compatibility', 'owner.map', 'CMakeCache.txt'):
            source = OUT / (name + '-owner') / file
            if source.exists():
                shutil.copy2(source, folder / file)
    for folder in list(OUT.glob('profile-*')) + list(OUT.glob('kill-*')):
        shutil.copytree(folder, evidence / folder.name)
    for log in OUT.glob('*.log'):
        shutil.copy2(log, evidence / log.name)
    print(json.dumps(report), flush=True)
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
