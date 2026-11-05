# SPDX-License-Identifier: MIT
"""Build, install, and exercise the Apple speech module on a macOS runner.

Order: module -> install prefix -> platform-neutral logic suite (from source) ->
installed-package probe (real AVSpeechSynthesizer) -> installed-package example.
All assertions are on real output; nothing is mocked beyond the logic suite's own
fake engine, whose cases are reported separately.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_report  # noqa: E402


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'this driver runs in GitHub Actions only'
    root = Path.cwd()
    out = root / 'build/tts-apple-macos'
    if out.exists():
        shutil.rmtree(out)
    logs = out / 'logs'
    stage, module, logic, probe, examples = out / 'install', out / 'module', out / 'logic', out / 'probe', out / 'examples'
    for path in (logs, out):
        path.mkdir(parents=True, exist_ok=True)

    def run(name, command, timeout=900, check=True):
        result = subprocess.run([str(x) for x in command], capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout)
        (logs / (name + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
        if check and result.returncode:
            print((result.stdout + result.stderr)[-12000:], flush=True)
        assert not check or result.returncode == 0, (name, result.returncode)
        return result

    def text(name, command, timeout=120):
        return run(name, command, timeout=timeout).stdout.strip()

    state = {'logic': None, 'probe': None, 'consumer': ''}

    def provisional(note):
        """Write a parseable platform report even when a producer failed, so the
        evidence job can print the failing cases from the artifact (never a pass)."""
        checks = []
        for key in ('logic', 'probe'):
            if state[key]:
                checks += state[key]['checks']
        counts = {'pass': 0, 'fail': 0, 'pending': 0}
        for check in checks:
            counts[check['status']] = counts.get(check['status'], 0) + 1
        probe = state['probe'] or {}
        report = {
            'schema': 1,
            'platform': 'macos',
            'execution_platform': 'macos-native',
            'source_sha': os.environ['GITHUB_SHA'],
            'run_id': int(os.environ['GITHUB_RUN_ID']),
            'attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
            'consumer_sha256': state['consumer'],
            'speech_available': bool(probe.get('speech_available')),
            'speech_note': probe.get('speech_note', ''),
            'checks': checks,
            'counts': counts,
            'provisional_failure': note,
        }
        (out / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')

    generator = ['-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release']
    module_dir = root / 'extras/reader-tts-apple'

    # ---- module build and install ----
    run('module-configure', ['cmake', '-S', module_dir, '-B', module, *generator,
                             '-DCMAKE_INSTALL_PREFIX=' + str(stage)])
    run('module-build', ['cmake', '--build', module])
    run('module-install', ['cmake', '--install', module])

    installed_header = stage / 'include/reader_tts.h'
    assert installed_header.is_file(), 'installed header missing'
    assert installed_header.read_bytes() == (module_dir / 'include/reader_tts.h').read_bytes(), \
        'installed header differs from the source header'
    libraries = sorted(stage.rglob('libreader_tts.a'))
    assert libraries, 'installed library missing'
    package_config = stage / 'lib/cmake/EXReaderTTSApple/EXReaderTTSAppleConfig.cmake'
    assert package_config.is_file(), 'installed package config missing'

    # ---- platform-neutral logic suite ----
    run('logic-configure', ['cmake', '-S', root / 'tests/reader_tts_apple', '-B', logic, *generator,
                            '-DEXR_TTS_APPLE_LOGIC=ON', '-DEXR_TTS_APPLE_MODULE_DIR=' + str(module_dir)])
    run('logic-build', ['cmake', '--build', logic])
    logic_run = run('logic-run', [logic / 'reader-tts-logic'], timeout=600, check=False)
    logic_stdout = logic_run.stdout
    (out / 'logic-run.stdout.txt').write_text(logic_stdout + logic_run.stderr, encoding='utf-8')
    if logic_run.returncode != 0:
        print('---- logic suite output (tail) ----', flush=True)
        print((logic_stdout + logic_run.stderr)[-20000:], flush=True)
    assert 'RESULT_JSON_BEGIN' in logic_stdout, 'the logic suite printed no result block'
    start = logic_stdout.index('RESULT_JSON_BEGIN')
    end = logic_stdout.index('RESULT_JSON_END')
    logic_report = json.loads(logic_stdout[logic_stdout.index('{', start):logic_stdout.rindex('}', 0, end) + 1])
    (out / 'logic-result.json').write_text(json.dumps(logic_report, indent=2), encoding='utf-8')
    state['logic'] = logic_report
    if logic_run.returncode != 0 or logic_report['counts']['fail'] != 0:
        failing = [case for case in logic_report['checks'] if case['status'] != 'pass']
        print('---- failing logic cases ----', flush=True)
        for case in failing:
            print('%s %s: %s' % (case['status'], case['name'], case['detail']), flush=True)
        provisional('logic suite reported failing cases')
        raise SystemExit('logic suite reported a failing case: %s' % logic_report['counts'])

    # ---- installed-package probe (real backend) ----
    run('probe-configure', ['cmake', '-S', root / 'tests/reader_tts_apple', '-B', probe, *generator,
                            '-DCMAKE_PREFIX_PATH=' + str(stage),
                            '-DEXReaderTTSApple_DIR=' + str(stage / 'lib/cmake/EXReaderTTSApple')])
    run('probe-build', ['cmake', '--build', probe])
    probe_binary = probe / 'ReaderTTSProbe'
    assert probe_binary.is_file(), 'probe binary missing'
    probe_report_path = out / 'speech-result.json'
    probe_run = run('probe-run', [probe_binary, probe_report_path], timeout=900, check=False)
    (out / 'probe-run.stdout.txt').write_text(probe_run.stdout + probe_run.stderr, encoding='utf-8')
    if probe_run.returncode != 0:
        print('---- installed probe output (tail) ----', flush=True)
        print((probe_run.stdout + probe_run.stderr)[-20000:], flush=True)
    assert probe_report_path.is_file(), 'probe did not write a report'
    probe_report = check_report.load(probe_report_path)
    state['probe'] = probe_report
    state['consumer'] = check_report.sha256_file(probe_binary)
    if probe_run.returncode != 0 or probe_report['counts']['fail'] != 0:
        for case in probe_report['checks']:
            if case['status'] == 'fail':
                print('fail %s: %s' % (case['name'], case['detail']), flush=True)
        provisional('installed probe reported failing cases')
        raise SystemExit('probe reported a failing case: %s' % (probe_report['counts'],))

    # ---- installed-package example ----
    run('example-configure', ['cmake', '-S', module_dir / 'examples', '-B', examples, *generator,
                              '-DCMAKE_PREFIX_PATH=' + str(stage),
                              '-DEXReaderTTSApple_DIR=' + str(stage / 'lib/cmake/EXReaderTTSApple')])
    run('example-build', ['cmake', '--build', examples])
    example_binary = examples / 'reader_tts_example'
    assert example_binary.is_file(), 'example binary missing'
    example_run = run('example-voices', [example_binary, 'voices', '--limit', '3'], timeout=300, check=False)
    example_output = example_run.stdout + example_run.stderr
    # A machine without installed voices legitimately answers UNAVAILABLE; the
    # point of this step is that the installed package links and runs.
    assert '"voices":' in example_output or '"error": "voices"' in example_output, \
        'example produced neither a voice list nor a recorded UNAVAILABLE: %r' % example_output[-400:]

    # ---- installed artifacts and consumer identity ----
    probe_sha = check_report.sha256_file(probe_binary)
    example_sha = check_report.sha256_file(example_binary)
    arch = text('architecture', ['lipo', '-archs', probe_binary])
    dependencies = text('dependencies', ['otool', '-L', probe_binary])
    assert 'AVFoundation.framework' in dependencies, 'probe does not link AVFoundation'
    assert 'WebKit' not in dependencies and 'JavaScriptCore' not in dependencies, 'unexpected web dependency'
    audio_run = run('audio-devices', ['system_profiler', 'SPAudioDataType'], timeout=180, check=False)
    audio = (audio_run.stdout + audio_run.stderr).strip()

    merged = {
        'schema': 1,
        'platform': 'macos',
        'execution_platform': 'macos-native',
        'source_sha': os.environ['GITHUB_SHA'],
        'run_id': int(os.environ['GITHUB_RUN_ID']),
        'attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
        'consumer_sha256': probe_sha,
        'speech_available': bool(probe_report.get('speech_available')),
        'speech_note': probe_report.get('speech_note', ''),
        'checks': logic_report['checks'] + probe_report['checks'],
        'counts': {},
        'os': text('os', ['sw_vers', '-productVersion']),
        'arch': arch,
        'logic_counts': logic_report['counts'],
        'probe_counts': probe_report['counts'],
        'probe': {
            'consumer_sha256': probe_sha,
            'arch': arch,
            'dependencies': [line.strip() for line in dependencies.splitlines()[1:] if line.strip()],
            'state_at_create': probe_report.get('state_at_create'),
            'capabilities': probe_report.get('capabilities'),
            'voice_count': probe_report.get('voice_count'),
            'pcm': probe_report.get('pcm'),
            'os': probe_report.get('os'),
        },
        'example': {'sha256': example_sha, 'voices_output': example_output.strip().splitlines()[:4]},
        'install': {
            'header_matches_source': True,
            'library': str(libraries[0].relative_to(stage)),
            'package_config': str(package_config.relative_to(stage)),
        },
        'audio_inventory': audio.splitlines()[-6:],
    }
    counts = {'pass': 0, 'fail': 0, 'pending': 0}
    for check in merged['checks']:
        counts[check['status']] += 1
    merged['counts'] = counts

    check_report.verify_identity(merged, 'macos')
    check_report.verify_checks(merged, 'logic')
    check_report.verify_checks(merged, 'probe')
    check_report.verify_consumer(merged, probe_binary)

    wav = out / 'speech-result.json.wav'
    if merged['probe'].get('pcm') and wav.is_file():
        digest = check_report.sha256_file(wav)
        assert digest == merged['probe']['pcm']['sha256'], 'PCM file digest does not match the report'
        merged['probe']['pcm']['recomputed_sha256'] = digest
        merged['probe']['pcm']['file_bytes'] = wav.stat().st_size
        merged['probe']['pcm']['file'] = wav.name

    (out / 'result.json').write_text(json.dumps(merged, indent=2), encoding='utf-8')
    print(json.dumps({'platform': 'macos', 'counts': counts, 'speech_available': merged['speech_available'],
                      'logic': logic_report['counts'], 'probe': probe_report['counts']}), flush=True)


if __name__ == '__main__':
    main()
