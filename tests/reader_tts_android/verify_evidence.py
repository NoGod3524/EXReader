#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict same-run artifact verification for the Android TTS package.

Downloads this run's artifact through the API, recomputes the ZIP digest,
checks identity (source, run, attempt, name, bytes, expiry), opens both device
reports and the published audio file, and compares the named case sets of the
two real engine states.
"""
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch, pages, require  # noqa: E402

WORKFLOW = '.github/workflows/reader-tts-android.yml'
DEVICE_JOB = 'tts-android-device'
MINIMUM_CASES = 46


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
    run_id = int(os.environ['GITHUB_RUN_ID'])
    attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
    source = os.environ['GITHUB_SHA']
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        'accepted': False,
        'scope': 'Android TextToSpeech backend on an API 34 emulator, engine present and engine removed',
        'source_sha': source,
        'run_id': run_id,
        'attempt': attempt,
        'artifact': None,
        'jobs': [],
        'modes': {},
        'audio': None,
        'packages': None,
        'problems': [],
        'audio_verified': False,
        'real_device_accepted': False,
        'android_host_wired': False,
    }
    try:
        run = fetch('actions/runs/%d' % run_id)
        require(run['head_sha'] == source and run['run_attempt'] == attempt, 'caller identity differs')
        require(run['path'].split('@')[0] == WORKFLOW, 'wrong workflow')
        jobs = pages('actions/runs/%d/attempts/%d/jobs' % (run_id, attempt), 'jobs')
        device = [job for job in jobs if job['name'] == DEVICE_JOB]
        require(len(device) == 1, 'missing or duplicate device job')
        require(device[0]['head_sha'] == source and device[0]['run_attempt'] == attempt and
                device[0]['conclusion'] == 'success', 'device job failed or came from another source')
        summary['jobs'].append({key: device[0][key] for key in ('id', 'name', 'conclusion', 'head_sha')})
        name = 'reader-tts-android-%d-%d' % (run_id, attempt)
        artifacts = pages('actions/runs/%d/artifacts' % run_id, 'artifacts')
        matches = [artifact for artifact in artifacts if artifact['name'] == name]
        require(len(matches) == 1, 'missing or duplicate artifact ' + name)
        artifact = matches[0]
        require(artifact['expired'] is False, 'artifact is expired')
        require(artifact['size_in_bytes'] > 0, 'artifact is empty')
        require(artifact['workflow_run']['head_sha'] == source and
                artifact['workflow_run']['id'] == run_id, 'artifact identity differs')
        expires = datetime.strptime(artifact['expires_at'], '%Y-%m-%dT%H:%M:%SZ')
        require(expires.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc),
                'artifact expiry is in the past')
        with tempfile.TemporaryFile() as stream:
            download_artifact_zip(artifact['id'], stream)
            stream.seek(0)
            data = stream.read()
        require(len(data) == artifact['size_in_bytes'], 'ZIP bytes differ from the API record')
        digest = 'sha256:' + hashlib.sha256(data).hexdigest()
        require(digest == artifact['digest'], 'ZIP digest differs')
        summary['artifact'] = {'id': artifact['id'], 'name': artifact['name'],
                               'bytes': artifact['size_in_bytes'], 'digest': digest,
                               'expires_at': artifact['expires_at']}
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()

            def locate(suffix):
                found = [entry for entry in names if entry.endswith(suffix)]
                require(len(found) == 1, 'expected exactly one ' + suffix)
                return found[0]

            reports = {mode: json.loads(archive.read(locate(mode + '/device-report.json')))
                       for mode in ('engine', 'none')}
            result = json.loads(archive.read(locate('reader-tts-android/result.json')))
            packages = json.loads(archive.read(locate('packages/packages.json')))
            audio_bytes = archive.read(locate('engine/tts-sample.wav'))
        audio_digest = hashlib.sha256(audio_bytes).hexdigest()

        for mode, report in reports.items():
            require(report.get('source_sha') == source, mode + ': report source differs')
            require(str(report.get('run_id')) == str(run_id), mode + ': report run differs')
            require(str(report.get('attempt')) == str(attempt), mode + ': report attempt differs')
            require(report.get('mode') == mode, mode + ': report mode differs')
            require(report.get('pass') is True, mode + ': report refused')
            require(report.get('mode_consistent') is True, mode + ': the engine state was not real')
            require(not report.get('failed_cases'), mode + ': a named case failed')
            engine_expected = bool(report.get('engine_expected'))
            require(bool(report.get('engine_packages')) == engine_expected,
                    mode + ': engine inventory contradicts the declared mode')
            cases = {case['name']: case['result'] for case in report.get('cases') or []}
            require(len(cases) >= MINIMUM_CASES, mode + ': the named case set is incomplete')
            require(all(value in ('pass', 'skip') for value in cases.values()),
                    mode + ': a named case is neither pass nor skip')
            summary['modes'][mode] = {
                'cases': len(cases),
                'passed': sum(1 for value in cases.values() if value == 'pass'),
                'skipped': sum(1 for value in cases.values() if value == 'skip'),
                'engine_packages': report.get('engine_packages'),
                'engine_package': report.get('engine_package') or '',
                'default_voice': report.get('default_voice') or '',
                'init_result': report.get('init_result'),
                'audio': report.get('audio'),
                'case_results': cases,
            }

        engine_cases = summary['modes']['engine']['case_results']
        missing_cases = summary['modes']['none']['case_results']
        require(set(engine_cases) == set(missing_cases), 'the runs report different named cases')
        require(missing_cases.get('service_unavailable_when_engine_missing') == 'pass',
                'the removed-engine run did not observe the missing engine')
        require(engine_cases.get('service_unavailable_when_engine_missing') == 'skip',
                'the engine-present run must not claim the missing-engine path')
        require(engine_cases.get('synthesize_to_file_audio') == 'pass',
                'the audio case did not pass with a real engine')
        require(missing_cases.get('synthesize_to_file_audio') != 'pass',
                'the removed-engine run must not pass the audio case')
        for required_case in ('speak_started_and_finished', 'range_utf8_boundaries',
                              'stop_single_stopped', 'busy_while_active',
                              'long_text_chunked_requests', 'voices_lifetime_after_destroy',
                              'rotation_during_speaking', 'chunker_boundaries_and_surrogates',
                              'stop_and_close_single_terminal', 'duplicate_terminal_dropped',
                              'overflow_utterance_id_ignored',
                              'stale_callback_after_destroy_ignored',
                              'voice_names_match_engine', 'voice_selection_returns_to_default'):
            require(engine_cases.get(required_case) == 'pass',
                    required_case + ' did not pass with a real engine')

        audio = reports['engine'].get('audio') or {}
        require(audio.get('sha256') == audio_digest, 'the published audio digest differs from the report')
        require(audio.get('bytes') == len(audio_bytes), 'the published audio bytes differ from the report')
        pulled = reports['engine'].get('audio_pulled_sha256')
        require(pulled is None or pulled == audio_digest, 'the on-device pull digest differs')
        summary['audio'] = {'bytes': len(audio_bytes), 'sha256': audio_digest,
                            'header': audio.get('header'), 'engine': audio.get('engine'),
                            'voice': audio.get('voice')}
        summary['audio_verified'] = True
        summary['packages'] = {
            'aar_bytes': packages['aar']['bytes'],
            'aar_sha256': packages['aar']['sha256'],
            'aar_native_libraries': packages['aar']['native_libraries'],
            'probe_debug_apk_bytes': packages['probe_debug_apk']['bytes'],
            'probe_debug_apk_sha256': packages['probe_debug_apk']['sha256'],
            'baseline_apk_bytes': packages['baseline_apk']['bytes'],
            'apk_bytes_delta': packages['probe_apk_bytes_delta'],
            'probe_native_libraries': packages['probe_native_libraries'],
            'runtime_dependencies': packages['runtime_dependencies'],
        }
        require(not packages['aar']['native_libraries'], 'the AAR must not ship native code')
        require(packages['probe_native_libraries'], 'the probe APK shipped no native library')
        require(result.get('pass') is True, 'the device orchestrator refused')
        require(result.get('source_sha') == source and int(result.get('run_id')) == run_id,
                'orchestrator identity differs')
        summary['accepted'] = True
    except Exception as error:  # noqa: BLE001 - a refusal is evidence
        summary['problems'].append(str(error))
    (output / 'artifact-summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'accepted': summary['accepted'], 'problems': summary['problems'],
                      'artifact': summary['artifact'], 'jobs': summary['jobs'],
                      'audio': summary['audio'], 'packages': summary['packages'],
                      'modes': summary['modes']}), flush=True)
    return 0 if summary['accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())
