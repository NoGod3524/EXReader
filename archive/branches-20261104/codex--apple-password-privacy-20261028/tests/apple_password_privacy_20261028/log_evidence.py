# SPDX-License-Identifier: MIT
"""Retain complete synthetic-run product logs before any privacy verdict."""
import hashlib
import json
import os
from pathlib import Path
from contract import STAGES, require, sha
from inspect_native import VARIANT_LABELS


def attribute_unified_log(payload, variants):
    """Diagnostic event-message attribution only; never the byte-scan verdict.

    JSON decoding can normalize encoding, so exact encoding evidence remains
    the original streaming scan. No message/path/subsystem values are emitted.
    """
    require(all(label in VARIANT_LABELS for label in variants), 'unexpected attribution variant')
    report = {'arbitrary_event_text_printed': False, 'byte_scan_is_authoritative': True,
              'owner_callsite_proven': False, 'parsed_json_array': False, 'matched_event_groups': []}
    try: events = json.loads(payload)
    except (ValueError, UnicodeDecodeError): return report
    if not isinstance(events, list): return report
    report['parsed_json_array'] = True
    report['event_count'] = len(events)
    counts = {}
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get('eventMessage'), str): continue
        message = event['eventMessage'].encode('utf-8')
        roles = tuple(sorted({label.split(':', 1)[0] for label, value in variants.items() if value in message}))
        if not roles: continue
        sender = event.get('senderImagePath')
        category = 'unknown-or-other-image'
        if isinstance(sender, str):
            if any('/' + name + '.framework/' in sender for name in ('XCTest', 'XCTAutomationSupport')):
                category = 'test-framework-image'
            elif sender.startswith('/System/Library/'):
                if any('/' + name + '.framework/' in sender for name in ('AXRuntime', 'AXCoreUtilities', 'Accessibility')):
                    category = 'apple-accessibility-framework-image'
                elif any('/' + name + '.framework/' in sender for name in ('AppKit', 'UIKitCore', 'UIKit', 'ViewBridge')):
                    category = 'apple-ui-framework-image'
                else: category = 'apple-framework-image'
            elif sender.startswith('/usr/lib/'): category = 'system-library-image'
            elif Path(sender).name == 'EXReaderHost': category = 'application-image'
        key = (category, roles); counts[key] = counts.get(key, 0) + 1
    report['matched_event_groups'] = [{'sender_category': category, 'credential_roles': list(roles), 'event_count': count}
                                      for (category, roles), count in sorted(counts.items())]
    return report


def retain_product_log(evidence, stage, platform, source, run, attempt, stdout, stderr, capture_exit):
    require(stage in STAGES and platform in ('macos', 'iphone', 'ipad'), 'invalid log identity')
    require(type(stdout) is bytes and type(stderr) is bytes and type(capture_exit) is int, 'invalid captured log types')
    parent = Path(evidence) / 'sensitive-synthetic-product-logs'; parent.mkdir(mode=0o700, exist_ok=True)
    folder = parent / stage; folder.mkdir(mode=0o700, exist_ok=False)
    files = {}
    for name, payload in (('host-unified.json', stdout), ('capture-stderr.txt', stderr)):
        path = folder / name
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as file: file.write(payload)
        digest = sha(path)
        require(path.stat().st_size == len(payload) and digest == hashlib.sha256(payload).hexdigest(), 'retained log bytes differ')
        files[name] = {'bytes': len(payload), 'sha256': digest}
    manifest = {'synthetic_run_only': True, 'may_contain_synthetic_credentials': True,
                'purpose': 'retained product-process log bytes; not a privacy acceptance verdict',
                'scope': 'EXReaderHost unified log including framework events; capture stderr separate',
                'source_sha': source, 'run_id': run, 'attempt': attempt, 'stage': stage, 'platform': platform,
                'capture_exit': capture_exit, 'files': files}
    (Path(evidence) / (stage + '-product-log-manifest.json')).write_text(json.dumps(manifest, indent=2) + '\n')
    return folder


def verify_product_log(evidence, stage, platform, source, run, attempt):
    manifest = json.loads((Path(evidence) / (stage + '-product-log-manifest.json')).read_text())
    require((manifest['stage'], manifest['platform'], manifest['source_sha'], manifest['run_id'], manifest['attempt']) ==
            (stage, platform, source, run, attempt), 'retained log identity differs')
    require(manifest['synthetic_run_only'] is True and manifest['may_contain_synthetic_credentials'] is True and
            manifest['capture_exit'] == 0, 'log capture failed or mislabeled')
    require(set(manifest['files']) == {'host-unified.json', 'capture-stderr.txt'} and
            manifest['files']['host-unified.json']['bytes'] > 0, 'captured product log empty or incomplete')
    folder = Path(evidence) / 'sensitive-synthetic-product-logs' / stage
    require({path.name for path in folder.iterdir()} == set(manifest['files']), 'unmanifested retained log entry')
    for name, item in manifest['files'].items():
        path = folder / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == item['bytes'] and
                sha(path) == item['sha256'], 'retained product log differs')
    return manifest
