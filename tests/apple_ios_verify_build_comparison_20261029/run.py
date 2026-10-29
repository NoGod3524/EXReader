#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""One Actions-only retained-SDK build pair. Never launches an app or UI test."""
import copy
import contextlib
import ctypes
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import plistlib
import re
import resource
import shutil
import signal
import stat
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
REPO = 'NoGod3524/EXReader'
PARENT = 'e91e751701c89801b2a92d282697b386efa006bd'
BRANCH = 'codex/apple-ios-verify-build-comparison-20261029'
PATHS = ['tests/apple_ios_verify_build_comparison_20261029/run.py']
PACKAGE = 'tests/apple_ios_organization_verify_phase_probe_20261029'
BASE = ROOT / 'build/ios-verify-build-comparison'
E, PRIVATE, REFUSAL = (BASE / n for n in ('evidence', 'private', 'refusal'))
EMERGENCY = BASE / 'emergency'
SDK_ROOT = ROOT / 'build/apple-sdk342/iphonesimulator'
PHASE = ROOT / 'build/ios-verify-phase-probe'
CONTROL = ROOT / 'build/ios-verify-build-control'
RESOURCES = BASE / 'resources'
DEVELOPER = '/Applications/Xcode_16.4.app/Contents/Developer'
RUNTIME = 'com.apple.CoreSimulator.SimRuntime.iOS-26-2'
DEVICE = 'com.apple.CoreSimulator.SimDeviceType.iPhone-SE-3rd-generation'
OLD_SHA = '6803602e5791eafa69a6e61bc5499d36cd31d92e'
OLD_RUN, OLD_JOB, ARTIFACT = 40858915090, 123397011277, 12891365411
ARTIFACT_NAME = 'password-sdk-iphonesimulator-40858915090-1'
ARTIFACT_BYTES = 20965175
ARTIFACT_SHA = '73df36a535d21520fec28cc08006701fc8131daf35e2be613e15a6c9bc46d46a'
CANDIDATE = '8357eafa28423a7ab93ba08b823af80f01ad1505'
TREES = {'src': '01dbab7c7c28aff175b5a953fea307e21d84eee2',
    'include': 'ef1bbaafc4a250053e5b0f88d329d1a25b22794b',
    'cmake': '505c604a2b30b72b3a251cd3f0bb7628e6d58fc1',
    'CMakeLists.txt': 'a5ed27fcca1d709c2217c585da47dc55dc23c1d0',
    'bindings': '54c12f70a1a63cae6574984a388b66bf6248c38e',
    'apps': '83b70fb9448239e6ad5cee11d4e3f24150191db3',
    'examples': '2346b8dc7f13113e616d663642a55981c58c3fc1',
    'tools': '7c98293965d81117376dab1aeafae12bc0c444b7',
    'extras': '6aea70df724fcf339d636fdf00707c6685cc50a6'}
FROZEN = {'.github/workflows/apple-ios-verify-build-comparison-20261029.yml':
    '3371a64dfd4cdb7cd0e7cb3b3a0f38525a2371344ea4b68c9a4117369f50f50c',
    PACKAGE + '/prepare.py': '6db4739d6f3dd57fe4a8e6e18c949ce88d8d5fd95b7eb5ca4c8dd0c4bc2cca06',
    PACKAGE + '/collect.py': '8da9894c26ca3dba7d3ffa9832abcc1bf177bd98eb53c0bc5abf41945d0a8616',
    PACKAGE + '/AppPhaseRecorder.swift': '163107819572b40b40a41e5a661f62e30c7e2362be704a0413a7c60799d494bb',
    PACKAGE + '/VerifyPhaseTests.swift': '006e98de1b87bf50987a9070b16cb8edd71773d6376a0c8c744248bea05b013d',
    'tests/apple_host/make_xcodeproj.rb': '47ed88d6b06cd9ce5bfd1ffc146c3c7f3115b5322f4b3899d4c1294f9e10e823',
    'tests/reader_team24_apple/make_project.rb': 'a62e6321c04241a30e9046e87dec37e9cd4bb87a2f750547bf61ff9547acf831',
    'tests/apple_ios_organization_20261028/ui/IOSOrganizationAcceptanceTests.swift': 'deeed62b7083fb4a3e85ccd866a9a9eb4fdbca8e0c86bb88136b0fca400161ff',
    'tests/apple_sdk342_package/run.py': '6519047961a37c4fc1bd913edf12c0606a8695d8b964a8b8ed5961008c0271c6',
    'tests/apple_host/prepare_fixtures.py': '8a52d054ec05539ddacaaf1c117672b1d70632e2ab1d0d7e70a6fc4f75e88275'}
MODULES = ['catalog', 'revisions', 'commands', 'webdav', 'sync', 'session', 'credentials',
    'reading-state', 'search', 'navigation', 'reading-commands', 'annotation-view',
    'desktop-metadata', 'annotation-export', 'annotation-import', 'font-library',
    'original-export', 'jump-history', 'sync-status-view']
FAMILY = {'EXReaderRevisions': '0.4.0', 'EXReaderReadingState': '0.2.0',
    'EXReaderReadingCommands': '0.2.0', 'EXReaderAnnotationView': '0.2.0',
    'EXReaderCommands': '0.2.0', 'EXReaderSync': '0.2.0', 'EXReaderSession': '0.2.0'}
IDENTITY = {k: os.environ.get(v, '') for k, v in [('source_sha', 'GITHUB_SHA'),
    ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT'), ('branch', 'GITHUB_REF_NAME')]}
DEADLINE = float(os.environ.get('EXR_BUILD_PAIR_DEADLINE', 'inf'))
COMMANDS, PRINTED = [], 0
ACTIVE = None
PINNED_GROUPS = set()
OWNED_PROCESSES = {}
GUARD_REFUSAL = (b'the response contains terminal escape sequences; '
                 b'pass --allow-escape-sequences to output it anyway\n')
UPLOAD_STEP = 5
UPLOAD_STEP_NAME = 'Run actions/upload-artifact@v4'
HISTORICAL_RECEIPT_SHA = 'dbb44a273da93dd98f73c617186834de07eb78cd5ffea914edcc4f4afd5ec909'
# Exact independently reviewed connector receipt, not fetched by this runner.
# Design review60d12620; owner approved changed criterion2026-10-29T13:43:50Z.
HISTORICAL_RECEIPT_BYTES = b'''{
  "kind": "source_reviewed_connector_observation_not_current_runner_log_replay",
  "repository": "NoGod3524/EXReader",
  "producer_source": "6803602e5791eafa69a6e61bc5499d36cd31d92e",
  "run_id": 40858915090,
  "run_attempt": 1,
  "job_id": 123397011277,
  "job_name": "Privacy SDK iphonesimulator",
  "job_head_sha": "6803602e5791eafa69a6e61bc5499d36cd31d92e",
  "job_status": "completed",
  "job_conclusion": "success",
  "upload_step": {
    "name": "Run actions/upload-artifact@v4",
    "status": "completed",
    "conclusion": "success",
    "number": 5,
    "started_at": "2026-10-29T10:41:12Z",
    "completed_at": "2026-10-29T10:41:17Z"
  },
  "artifact_id": 12891365411,
  "artifact_name": "password-sdk-iphonesimulator-40858915090-1",
  "artifact_bytes": 20965175,
  "artifact_sha256": "73df36a535d21520fec28cc08006701fc8131daf35e2be613e15a6c9bc46d46a",
  "decoded_log_selected_lines": [
    "2026-10-29T10:41:16.8698720Z SHA256 digest of uploaded artifact zip is 73df36a535d21520fec28cc08006701fc8131daf35e2be613e15a6c9bc46d46a",
    "2026-10-29T10:41:17.3205190Z Artifact password-sdk-iphonesimulator-40858915090-1.zip successfully finalized. Artifact ID 12891365411",
    "2026-10-29T10:41:17.3207120Z Artifact password-sdk-iphonesimulator-40858915090-1 has been successfully uploaded! Final size is 20965175 bytes. Artifact ID is 12891365411",
    "2026-10-29T10:41:17.3214800Z Artifact download URL: https://github.com/NoGod3524/EXReader/actions/runs/40858915090/artifacts/12891365411"
  ],
  "source_tools": [
    "GitHub fetch_workflow_job_logs",
    "GitHub REST run jobs metadata"
  ],
  "full_decoded_log_characters": 361326,
  "artifact_bytes_read_locally": false,
  "log_retrieval_is_not_binary_authentication": true
}
'''


class StopGroup(RuntimeError): pass


def require(value, message):
    if not value: raise ValueError(message)


def check():
    if time.monotonic() >= DEADLINE: raise StopGroup('global worker deadline')


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode()


def strict_json(data, cap=2 * 1024 ** 2):
    require(len(data) <= cap, 'JSON byte ceiling')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key'); result[key] = value
        return result
    def bad(value): raise ValueError('nonfinite JSON number')
    value = json.loads(data.decode('utf-8'), object_pairs_hook=pairs, parse_constant=bad)
    todo = [(value, 0)]; count = 0
    while todo:
        item, depth = todo.pop(); count += 1
        require(count <= 100000 and depth <= 40, 'JSON structure ceiling')
        if isinstance(item, float): require(math.isfinite(item), 'nonfinite JSON value')
        if isinstance(item, dict): todo.extend((x, depth + 1) for x in item.values())
        if isinstance(item, list): todo.extend((x, depth + 1) for x in item)
    return value


def save(path, value):
    data = encoded(value); require(len(data) <= 4 * 1024 ** 2, 'receipt ceiling')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


def inode(s): return (s.st_dev, s.st_ino, stat.S_IFMT(s.st_mode))
def snapshot(s): return inode(s) + (s.st_size, s.st_mtime_ns, s.st_ctime_ns)


@contextlib.contextmanager
def directory(path):
    """Hold every parent descriptor; never resolve a live symlink by pathname."""
    path = Path(path).absolute(); require(len(path.parts) <= 64, 'path depth ceiling')
    opened = []; current = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    opened.append(current); bindings = []
    try:
        for name in path.parts[1:]:
            expected = os.stat(name, dir_fd=current, follow_symlinks=False)
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
            opened.append(child); require(inode(os.fstat(child)) == inode(expected), 'directory replaced before open')
            bindings.append((current, name, child, inode(expected))); current = child
        yield current
        for parent, name, child, expected in reversed(bindings):
            require(inode(os.fstat(child)) == expected and
                    inode(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected, 'directory pathname replaced')
    finally:
        for fd in reversed(opened): os.close(fd)


def file_at(folder, name, cap, retain=False, expected=None, hook=None, hashes=True):
    scanned = expected or os.stat(name, dir_fd=folder, follow_symlinks=False)
    require(stat.S_ISREG(scanned.st_mode) and 0 <= scanned.st_size <= cap, 'bounded regular input')
    if hook: hook('file_scanned')
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
    try:
        before = os.fstat(fd)
        require(inode(before) == inode(scanned) and stat.S_ISREG(before.st_mode) and before.st_size <= cap,
                'file replaced/type/size before open')
        if hashes: require(snapshot(before) == snapshot(scanned), 'file changed before read')
        h = hashlib.sha256(); chunks = []; remaining = before.st_size
        if hook: hook('file_opened')
        if hashes:
            while remaining:
                check(); block = os.read(fd, min(1024 ** 2, remaining))
                require(block, 'file shrank during read'); remaining -= len(block); h.update(block)
                if retain: chunks.append(block)
            require(snapshot(os.fstat(fd)) == snapshot(before), 'file grew/changed during bounded read')
        after_path = os.stat(name, dir_fd=folder, follow_symlinks=False)
        require((snapshot(after_path) == snapshot(before)) if hashes else (inode(after_path) == inode(before)),
                'file pathname changed')
        return before.st_size, h.hexdigest() if hashes else None, b''.join(chunks)
    finally: os.close(fd)


def sha_file(path, cap=512 * 1024 ** 2):
    with directory(path.parent) as fd: return file_at(fd, path.name, cap)[1]


def read_bounded(path, cap, hook=None):
    with directory(path.parent) as fd: return file_at(fd, path.name, cap, True, hook=hook)[2]


def inventory(root, cap=512 * 1024 ** 2, entries=20000, hashes=True, allow_links=False, exclude=(), hook=None):
    result = {}; total = count = 0
    def descend(folder, prefix, depth):
        nonlocal total, count
        require(depth <= 64, 'directory depth ceiling')
        with os.scandir(folder) as listing:
            for item in listing:
                check(); count += 1; require(count <= entries, 'entry ceiling')
                name = item.name; key = prefix + name
                s = os.stat(name, dir_fd=folder, follow_symlinks=False)
                if key in exclude: continue
                if stat.S_ISDIR(s.st_mode):
                    if hook: hook('directory_scanned', key)
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
                    try:
                        require(inode(os.fstat(child)) == inode(s), 'scanned directory replaced')
                        descend(child, key + '/', depth + 1)
                        require(inode(os.stat(name, dir_fd=folder, follow_symlinks=False)) == inode(s), 'walk directory replaced')
                    finally: os.close(child)
                elif stat.S_ISREG(s.st_mode):
                    size, digest, _ = file_at(folder, name, cap - total, expected=s, hashes=hashes)
                    total += size; result[key] = {'bytes': size, 'sha256': digest}
                elif stat.S_ISLNK(s.st_mode) and allow_links:
                    target = os.readlink(name, dir_fd=folder)
                    require(inode(os.stat(name, dir_fd=folder, follow_symlinks=False)) == inode(s), 'link replaced')
                    result[key] = {'link': target}  # Never descend/follow it.
                else: raise ValueError('special/link output refused')
    with directory(root) as fd: descend(fd, '', 0)
    return {'entries': count, 'bytes': total, 'files': result}


def seal_evidence(root):
    final = inventory(root, 63 * 1024 ** 2, 1980, exclude=('inventory.json',))
    save(root / 'inventory.json', dict(final, excludes_self='inventory.json'))
    inventory(root, 64 * 1024 ** 2, 2000, False)


def retain_partial(root, refusal):
    """Worker-owned bounded copy; always explicitly unaccepted until supervisor closes."""
    source = inventory(root, 63 * 1024 ** 2, 1980, exclude=('inventory.json',))
    refusal.mkdir(); target = refusal / 'partial'; target.mkdir()
    for name, row in source['files'].items():
        data = read_bounded(root / name, row['bytes'])
        require(hashlib.sha256(data).hexdigest() == row['sha256'], 'partial source changed')
        dest = target / name; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)
    summary = strict_json(read_bounded(target / 'summary.json', 65536))
    summary.update(comparison_complete=False, partial_only=True, supervisor_closed_identity_unconfirmed=True)
    save(target / 'summary.json', summary); seal_evidence(target)
    inventory(refusal, 64 * 1024 ** 2, 2000, False)


def live_bounds():
    total = count = 0
    for root in (BASE, SDK_ROOT, PHASE, CONTROL):
        if root.exists():
            row = inventory(root, 4 * 1024 ** 3, 60000, False, True)
            total += row['bytes']; count += row['entries']
    require(total <= 4 * 1024 ** 3 and count <= 60000, 'aggregate working ceiling')


def shaped(value, limit):
    raw = encoded(value)
    if len(raw) <= limit: return raw, True
    digest = hashlib.sha256(raw).hexdigest()
    for width in (4096, 2048, 1024, 512, 256, 128, 64, 16):
        def clip(x, depth=0):
            if depth > 8: return '[depth clipped]'
            if isinstance(x, str): return x.encode()[:width].decode('utf-8', 'ignore')
            if isinstance(x, list): return [clip(v, depth + 1) for v in x[:24]]
            if isinstance(x, dict): return {k: clip(v, depth + 1) for k, v in list(x.items())[:24]}
            return x
        candidate = encoded({'payload': clip(value), 'payload_clipped': True, 'full_sha256': digest})
        if len(candidate) <= limit: return candidate, False
    return encoded({'complete': False, 'problem': 'bounded output fallback', 'full_sha256': digest}), False


def emit(value):
    global PRINTED
    data, _ = shaped(value, 48 * 1024)
    require(PRINTED + len(data) <= 496 * 1024, 'ordinary stdout ceiling')
    PRINTED += len(data); sys.stdout.buffer.write(data); sys.stdout.buffer.flush()


def redacted(text, tokens=None):
    """Presentation only. Never used to decide log-route eligibility."""
    for token in (tokens if tokens is not None else [os.environ.get('GH_TOKEN', ''), os.environ.get('GITHUB_TOKEN', '')]):
        if token: text = text.replace(token, '[active-token-redacted]')
    text = re.sub(r'(?im)^.*(?:authorization|proxy-authorization|set-cookie|cookie)\s*[:=].*$',
                  '[credential header redacted]', text)
    def url(match):
        try:
            value = urllib.parse.urlsplit(match.group(0))
            # Only host/path survive: no userinfo, signed query or fragment.
            host = value.hostname
            if not host or not re.fullmatch(r'[A-Za-z0-9.:-]+', host): return '[URL redacted]'
            return value.scheme + '://' + host + value.path
        except ValueError: return '[URL redacted]'
    text = re.sub(r'https?://[^\s<>"\x00-\x1f\x7f]+', url, text, flags=re.I)
    # JSON escapes C0 already; visibly escape DEL too, never emit raw ESC.
    return text.replace('\x7f', '\\u007f')


def included_response(raw):
    """Tagged gh2.100 api.go: Fprintln status (LF), printHeaders (CRLF)."""
    first_end = raw.find(b'\n', 0, 1024)
    require(first_end > 0, 'missing bounded first HTTP status')
    first = raw[:first_end]
    match = re.fullmatch(rb'HTTP/(?:1\.[01]|2\.0) ([1-5][0-9]{2}) [\x20-\x7e]+', first)
    require(match is not None, 'unsupported first HTTP status framing')
    pos = first_end + 1; headers = {}; lines = 1
    while True:
        end = raw.find(b'\r\n', pos, 32768)
        require(end >= pos and end + 2 <= 32768, 'missing/bounded CRLF header termination')
        line = raw[pos:end]; pos = end + 2; lines += 1
        require(lines <= 256, 'header line ceiling')
        if not line: break
        h = re.fullmatch(rb'([!#$%&\x27*+.^_`|~0-9A-Za-z-]+): ([\x20-\x7e]*)', line)
        require(h is not None, 'folded/control/malformed response header')
        key, value = h.group(1).decode('ascii').lower(), h.group(2).decode('ascii')
        require(key not in headers and key != 'status', 'duplicate/ambiguous response header')
        headers[key] = value
    body = raw[pos:]
    require(not body.startswith(b'HTTP/'), 'second response header block')
    kind = headers.get('content-type', '')
    request = headers.get('x-github-request-id')
    require(request is None or re.fullmatch('[A-Za-z0-9:-]{1,128}', request), 'unsafe request ID')
    return {'status': int(match.group(1)), 'content_type': kind, 'request_id': request,
            'header_bytes': pos, 'header_sha256': hashlib.sha256(raw[:pos]).hexdigest()}, body


def log_media(value):
    require(re.fullmatch(r'(?:text/plain|application/octet-stream)(?:;\s*charset=(?:utf-8|"utf-8"))?',
                         value, flags=re.I), 'unsupported/ambiguous log media type')


def safe_response(response, tokens=None):
    result = dict(response)
    if result.get('request_id') is not None: result['request_id'] = redacted(result['request_id'], tokens)
    return result


def command_capture(record, out, err, cap, closed, reader=read_bounded, writer=save, sink=emit, tokens=None):
    """Retain safe finite evidence before error handling, raw data stays private."""
    receipt = {'command': {k: record.get(k) for k in ('argv', 'output', 'started', 'finished', 'exit_code', 'problem')},
               'streams_closed': closed is True, 'capture_complete': closed is True, 'streams': {}}
    raw = {}
    for label, path in (('stdout', out), ('stderr', err)):
        row = {'available': False, 'preview_truncated': False}
        try:
            require(closed is True, 'owned command/group not closed; stream not read')
            data = reader(path, cap); row.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            text = data.decode('utf-8')  # Validate the entire bounded stream first.
            raw[label] = data; row['available'] = True
            if label == 'stdout' and '--include' in record.get('argv', []):
                try:
                    response, body = included_response(data)
                    # Never serialize the raw header block, even on error.
                    row['response'] = {k: v for k, v in safe_response(response, tokens).items() if k != 'content_type'}
                    try:
                        log_media(response['content_type'])
                        row['response']['content_type'] = response['content_type']
                    except ValueError:
                        row['response']['content_type'] = '[unsupported media type; bound by raw hash]'
                    text = body.decode('utf-8')
                except (ValueError, UnicodeError):
                    text = ''; row['header_parse_failed'] = True
            safe = redacted(text, tokens)
            row['preview'] = safe[:6000]; row['preview_truncated'] = len(safe) > 6000
        except (ValueError, OSError, UnicodeError) as error:
            receipt['capture_complete'] = False
            row['unavailable_reason'] = type(error).__name__ + ': ' + redacted(str(error), tokens)[:300]
        receipt['streams'][label] = row
    data, complete = shaped(receipt, 48 * 1024)
    # An explicitly clipped presentation never replaces the complete raw decision input.
    shown = strict_json(data, 48 * 1024)
    writer(E / 'command-observations' / (record['output'] + '.json'), shown)
    sink({'command_observation': shown})
    require(receipt['capture_complete'] is True, 'command capture incomplete')
    return raw, receipt


def upload_identity(body):
    text = body.decode('utf-8')
    require(body and all(ord(c) >= 32 and ord(c) != 127 or c in '\r\n\t' for c in text), 'nontext/control log body')
    # Match unique complete lines, including name, not independent substrings.
    lines = [re.sub(r'^\d{4}-\d\d-\d\dT[0-9:.]+Z ', '', line) for line in text.splitlines()]
    digests = [s for s in lines if 'SHA256 digest of uploaded artifact zip is ' in s]
    finalized = [s for s in lines if s.startswith('Artifact ') and '.zip successfully finalized.' in s]
    uploaded = [s for s in lines if s.startswith('Artifact ') and 'has been successfully uploaded!' in s]
    require(digests == ['SHA256 digest of uploaded artifact zip is ' + ARTIFACT_SHA]
            and finalized == ['Artifact ' + ARTIFACT_NAME + '.zip successfully finalized. Artifact ID ' + str(ARTIFACT)]
            and uploaded == ['Artifact ' + ARTIFACT_NAME + ' has been successfully uploaded! Final size is ' +
                            str(ARTIFACT_BYTES) + ' bytes. Artifact ID is ' + str(ARTIFACT)], 'unique original upload conjunction')


def upload_step(job):
    require(job.get('id') == OLD_JOB and job.get('run_id') == OLD_RUN and job.get('head_sha') == OLD_SHA
            and job.get('status') == 'completed' and job.get('conclusion') == 'success'
            and job.get('name') == 'Privacy SDK iphonesimulator', 'step parent provenance')
    rows = [s for s in job['steps'] if s.get('number') == UPLOAD_STEP or s.get('name') == UPLOAD_STEP_NAME]
    require(len(rows) == 1 and type(rows[0].get('number')) is int and rows[0]['number'] == UPLOAD_STEP
            and rows[0].get('name') == UPLOAD_STEP_NAME and rows[0].get('status') == 'completed'
            and rows[0].get('conclusion') == 'success', 'exact successful upload step')
    return rows[0]


def log_route(code, raw, version, allow_step):
    require(type(code) is int and set(raw) == {'stdout', 'stderr'}, 'complete raw response required')
    # Eligibility is decided exclusively from complete unredacted bytes.
    response, body = included_response(raw['stdout'])
    require(response['status'] == 200, 'HTTP status refuses log admission/alternative')
    log_media(response['content_type'])
    if code == 0:
        require(raw['stderr'] == b'', 'unexpected successful log stderr')
        upload_identity(body)
        return 'admitted', response, body
    require(allow_step is True and version == '2.100.0' and code == 1 and body == b''
            and raw['stderr'] == GUARD_REFUSAL, 'not the exact supported CLI content refusal')
    return 'exact_cli_guard_step_eligible', response, body


def authenticated_upload(job, version, request):
    code, raw = request(False)
    route, response, body = log_route(code, raw, version, True)
    source_route = 'whole_job'; first_response = response
    if route != 'admitted':
        upload_step(job)  # No alternative request before exact provenance passes.
        code, raw = request(True)
        route, response, body = log_route(code, raw, version, False)
        source_route = 'same_job_upload_step_5'
    return {'source': OLD_SHA, 'run_id': OLD_RUN, 'job_id': OLD_JOB, 'artifact_id': ARTIFACT,
        'artifact_name': ARTIFACT_NAME, 'artifact_bytes': ARTIFACT_BYTES, 'artifact_sha256': ARTIFACT_SHA,
        'route': source_route, 'step': UPLOAD_STEP if source_route != 'whole_job' else None,
        'cli_version': version, 'whole_response': safe_response(first_response), 'admitted_response': safe_response(response),
        'body_bytes': len(body), 'body_sha256': hashlib.sha256(body).hexdigest(),
        'older_failed_request_cause_proved': False}


def build_argv(profile, uid):
    require(profile in ('control', 'phase') and re.fullmatch(r'[0-9A-Fa-f-]{36}', uid), 'build identity')
    root = CONTROL if profile == 'control' else PHASE
    return ['xcodebuild', 'build-for-testing', '-project', str(root / 'generated/project/EXReaderHost.xcodeproj'),
        '-scheme', 'EXReaderHost-iOS', '-derivedDataPath', str(root / 'DerivedData'),
        'EXR_SDK_DIR=' + str(SDK_ROOT / 'sdk'), 'EXR_PRODUCTS_DIR=' + str(SDK_ROOT / 'products'),
        'CODE_SIGNING_ALLOWED=NO', '-destination', 'platform=iOS Simulator,id=' + uid]


def validate_build(argv, profile, uid):
    require(argv == build_argv(profile, uid), 'exact build-only command differs')


def command_allowed(argv, name, build):
    if build is not None:
        validate_build(argv, *build)
        require(name == build[0] + '-build', 'build name differs'); return
    fixed = {'head': ['git', 'rev-parse', 'HEAD'], 'parent': ['git', 'rev-parse', 'HEAD^'],
        'delta': ['git', 'diff', '--name-status', PARENT, 'HEAD'],
        'clean': ['git', 'status', '--porcelain', '--untracked-files=all'],
        'version': ['xcodebuild', '-version'], 'sdk-version': ['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version'],
        'os-version': ['sw_vers', '-productVersion'], 'arch': ['uname', '-m'],
        'xcodeproj-version': ['ruby', '-e', "require 'xcodeproj'; puts Xcodeproj::VERSION"],
        'fixtures': [sys.executable, 'tests/apple_host/prepare_fixtures.py', '--resources', str(RESOURCES)],
        'runtimes': ['xcrun', 'simctl', 'list', 'runtimes', '-j'],
        'create': ['xcrun', 'simctl', 'create', 'EXR-build-pair-' + IDENTITY['run_id'], DEVICE, RUNTIME]}
    for source in (PARENT, OLD_SHA, IDENTITY['source_sha']):
        fixed['trees-' + source[:8]] = ['git', 'rev-parse', *[source + ':' + p for p in TREES]]
    for label, endpoint in [('original-run', 'runs/' + str(OLD_RUN)), ('original-job', 'jobs/' + str(OLD_JOB)),
        ('original-artifact', 'artifacts/' + str(ARTIFACT)),
        ('original-sdk', 'artifacts/' + str(ARTIFACT) + '/zip')]:
        fixed[label] = ['gh', 'api', 'repos/' + REPO + '/actions/' + endpoint]
    for label, root in (('control', CONTROL), ('phase', PHASE)):
        fixed[label + '-generate'] = ['ruby', str(root / 'generated' / ('make_project_' + label + '.rb')),
            str(root / 'generated/project'), str(RESOURCES), str(root / 'generated/ui'), 'base']
        fixed[label + '-pbx-convert'] = ['plutil', '-convert', 'json', '-o', str(PRIVATE / (label + '-pbx.json')),
            str(root / 'generated/project/EXReaderHost.xcodeproj/project.pbxproj')]
    if name == 'delete-owned-device':
        require(len(argv) == 4 and argv[:3] == ['xcrun', 'simctl', 'delete']
                and argv[3] == CREATED_UUID and re.fullmatch(r'[0-9A-Fa-f-]{36}', argv[3]), 'owned cleanup identity')
    else: require(name in fixed and argv == fixed[name], 'fixed command allowlist')


CREATED_UUID = None


def command(argv, name, timeout=60, cap=16 * 1024 ** 2, allowed_exit=False, build=None):
    global ACTIVE
    check(); argv = list(map(str, argv))
    command_allowed(argv, name, build)
    require(len(COMMANDS) < 48 and name not in [r['output'] for r in COMMANDS], 'duplicate/excess command')
    if build is not None: require(timeout == 120 and cap == 16 * 1024 ** 2 and allowed_exit is True, 'fixed build limits')
    output = PRIVATE / (name + '.stdout'); error = PRIVATE / (name + '.stderr')
    record = {'argv': argv, 'started': time.monotonic(), 'output': name, 'timeout': timeout,
              'fsize_limit': 256 * 1024 ** 2, 'shared_owned_group': os.getpgrp()}
    COMMANDS.append(record); process = None
    try:
        launcher = [sys.executable, '-c', 'import os,resource,sys; n=int(sys.argv[1]); '
            'resource.setrlimit(resource.RLIMIT_FSIZE,(n,n)); os.execvp(sys.argv[2],sys.argv[2:])',
            str(256 * 1024 ** 2), *argv]
        record['launcher_argv'] = launcher
        with output.open('xb') as out, error.open('xb') as err:
            process = subprocess.Popen(launcher, cwd=ROOT, stdout=out, stderr=err)
            record['pid'] = process.pid
            ACTIVE = process
            next_scan = 0
            while True:
                check(); now = time.monotonic()
                if now - record['started'] >= timeout: raise StopGroup('command deadline: ' + name)
                if output.stat().st_size > cap or error.stat().st_size > cap: raise StopGroup('command output ceiling: ' + name)
                if now >= next_scan: live_bounds(); next_scan = time.monotonic() + 1
                code = process.poll()
                if code is not None:
                    record['exit_code'] = code; record['reaped'] = True; ACTIVE = None
                    require(code == 0 or allowed_exit, 'command failed: ' + name + ' exit=' + str(code))
                    return code, output, error
                time.sleep(.1)
    except BaseException as failure:
        record['problem'] = type(failure).__name__ + ': ' + str(failure)[:600]
        raise
    finally:
        record['finished'] = time.monotonic()
        save(E / 'commands.json', COMMANDS)
        if record.get('exit_code') != 0 or 'problem' in record:
            try: closed = record.get('reaped') is True and group_members(os.getpgrp()) == {os.getpid()}
            except (ValueError, OSError): closed = False
            command_capture(record, output, error, cap, closed)
        # A live child is not abandoned: the outer supervisor owns/stops this
        # entire group. Worker catches StopGroup only to emit a bounded refusal.


def text_command(argv, name, **kwargs):
    _, out, _ = command(argv, name, **kwargs)
    return read_bounded(out, kwargs.get('cap', 16 * 1024 ** 2)).decode('utf-8').strip()


def api(endpoint, name):
    _, out, _ = command(['gh', 'api', 'repos/' + REPO + '/' + endpoint], name, cap=2 * 1024 ** 2)
    return strict_json(read_bounded(out, 2 * 1024 ** 2))


def validate_metadata(run, job, artifact):
    require(all(type(v) is int for v in (run['id'], run['run_attempt'], job['id'], job['run_id'],
        artifact['id'], artifact['size_in_bytes'], artifact['workflow_run']['id'])), 'metadata integer domain')
    require(run['id'] == OLD_RUN and run['run_attempt'] == 1 and run['head_sha'] == OLD_SHA
            and run['status'] == 'completed', 'original run differs')
    require(job['id'] == OLD_JOB and job['run_id'] == OLD_RUN and job['name'] == 'Privacy SDK iphonesimulator'
            and job['status'] == 'completed' and job['conclusion'] == 'success', 'SDK producer job differs')
    require(artifact['id'] == ARTIFACT and artifact['name'] == ARTIFACT_NAME
            and artifact['size_in_bytes'] == ARTIFACT_BYTES and artifact['expired'] is False
            and artifact['digest'] == 'sha256:' + ARTIFACT_SHA
            and artifact['workflow_run']['id'] == OLD_RUN
            and artifact['workflow_run']['head_sha'] == OLD_SHA, 'original SDK artifact differs')


def archive_hash(path, size=ARTIFACT_BYTES, digest=ARTIFACT_SHA):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size == size, 'original ZIP size')
    require(sha_file(path) == digest, 'original ZIP digest')


def zip_names(infos):
    require(len(infos) <= 20000 and sum(i.file_size for i in infos) <= 512 * 1024 ** 2, 'ZIP size/count ceiling')
    explicit = set(); nodes = {}
    for item in infos:
        name = item.filename; directory = item.is_dir()
        require(name == item.orig_filename and name and '\\' not in name
                and not any(ord(c) < 32 or ord(c) == 127 for c in name), 'ZIP unsafe name')
        parts = (name[:-1] if directory else name).split('/')
        require(all(p not in ('', '.', '..') and ':' not in p for p in parts), 'ZIP unsafe path')
        require(parts[0] in ('identity.json', 'sdk', 'products'), 'ZIP unexpected root')
        require(parts[0] != 'identity.json' or (len(parts) == 1 and not directory), 'ZIP identity shape')
        key = unicodedata.normalize('NFC', '/'.join(parts)).casefold()
        require(key not in explicit, 'ZIP duplicate/alias explicit entry'); explicit.add(key)
        require(not item.flag_bits & 1 and item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), 'ZIP unsupported encoding')
        require(stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFDIR if directory else stat.S_IFREG), 'ZIP link/type')
        for n in range(1, len(parts) + 1):
            raw = '/'.join(parts[:n]); canonical = unicodedata.normalize('NFC', raw).casefold()
            kind = 'dir' if n < len(parts) or directory else 'file'
            require(canonical not in nodes or nodes[canonical] == (raw, kind), 'ZIP implicit alias/type')
            nodes[canonical] = (raw, kind)
        if directory: require(item.file_size == 0 and item.CRC == 0, 'ZIP directory data/CRC')


def unpack(path, destination):
    require(not destination.exists(), 'extraction destination exists')
    rows = []
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist(); zip_names(infos)
        destination.mkdir(parents=True, mode=0o700)
        for item in infos:
            check(); target = destination / item.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            size = 0; h = hashlib.sha256()
            with archive.open(item) as source:
                if item.is_dir():
                    require(source.read(1) == b'', 'ZIP directory payload'); target.mkdir(exist_ok=True)
                else:
                    with target.open('xb') as output:
                        while True:
                            check(); block = source.read(1024 ** 2)
                            if not block: break
                            size += len(block); require(size <= item.file_size, 'ZIP streamed size')
                            output.write(block); h.update(block)
            require(size == item.file_size, 'ZIP exact expanded size')
            rows.append({'name': item.filename, 'kind': 'directory' if item.is_dir() else 'file',
                         'bytes': size, 'sha256': h.hexdigest()})
    return rows


def installed_schema(identity, product):
    require(identity['source_sha'] == OLD_SHA and identity['run_id'] == str(OLD_RUN) and identity['attempt'] == '1'
            and identity['target'] == 'iphonesimulator' and identity['sdk_content_candidate'] == CANDIDATE
            and identity['sdk_content_paths'] == ['src', 'include', 'cmake', 'CMakeLists.txt', 'bindings']
            and identity['page_theme_enabled'] is True and identity['product'] == product, 'SDK identity schema')
    require(product['source_sha'] == OLD_SHA and product['target'] == 'iphonesimulator' and product['sdk_version'] == '3.42.0'
            and product['installed_modules'] == MODULES and product['exact_candidate_family'] == FAMILY
            and product['sqlite_provider'] == 'libreader_catalog_sqlite.a' and product['system_sqlite_fallback'] is False
            and product['reading_resolver_linked'] is False and product['webdav_transport'] == 'Foundation URLSession'
            and all(product[k] is True for k in ('wave3_enabled', 'organization_enabled', 'selector_bytes_candidate')),
            'installed product schema')
    require(product['sdk_prefix'] == str(SDK_ROOT / 'sdk') and product['product_prefix'] == str(SDK_ROOT / 'products'),
            'original installed path differs; no rewrite')


def source_guard():
    require(IDENTITY['branch'] == BRANCH and IDENTITY['attempt'] == '1', 'branch/attempt')
    head = text_command(['git', 'rev-parse', 'HEAD'], 'head')
    parent = text_command(['git', 'rev-parse', 'HEAD^'], 'parent')
    delta = text_command(['git', 'diff', '--name-status', PARENT, 'HEAD'], 'delta').splitlines()
    validate_source(head, parent, delta)
    require(not text_command(['git', 'status', '--porcelain', '--untracked-files=all'], 'clean'), 'dirty source')
    for path, digest in FROZEN.items(): require(sha_file(ROOT / path) == digest, 'frozen source differs: ' + path)
    for source in (PARENT, OLD_SHA, IDENTITY['source_sha']):
        values = text_command(['git', 'rev-parse', *[source + ':' + p for p in TREES]], 'trees-' + source[:8]).splitlines()
        require(values == list(TREES.values()), 'source-family tree mismatch')
    require(os.environ.get('DEVELOPER_DIR') == DEVELOPER, 'developer directory')
    version = text_command(['xcodebuild', '-version'], 'version')
    require(version == 'Xcode 16.4\nBuild version 16F6', 'Xcode version')
    require(text_command(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version'], 'sdk-version') == '18.5', 'SDK version')
    require(text_command(['sw_vers', '-productVersion'], 'os-version').startswith('15.'), 'macOS version')
    require(text_command(['uname', '-m'], 'arch') == 'arm64', 'architecture')
    text_command(['ruby', '-e', "require 'xcodeproj'; puts Xcodeproj::VERSION"], 'xcodeproj-version')
    save(E / 'source-guard.json', dict(IDENTITY, parent=PARENT, frozen=FROZEN, trees=TREES,
        sdk_producer_source=OLD_SHA, xcode=version, developer_dir=DEVELOPER,
        image=os.environ.get('ImageVersion'), native_cases_run=0, formal_credit=0))


def validate_source(head, parent, delta):
    require(head == IDENTITY['source_sha'] and re.fullmatch('[a-f0-9]{40}', head), 'source SHA')
    require(parent == PARENT, 'exact parent')
    require(sorted(delta) == sorted('M\t' + p for p in PATHS), 'exact one driver modification')


def installed_files(root):
    required = ['sdk/include/exreader.h', 'sdk/include/exr/base.h', 'sdk/lib/libexreader.dylib',
                'products/lib/libreader_original_export.a', 'products/include/reader_original_export.h']
    for name in required:
        with directory((root / name).parent) as fd: file_at(fd, Path(name).name, 512 * 1024 ** 2, hashes=False)
    require(re.search(r'#define EXR_VERSION "3\.42\.0"', read_bounded(root / 'sdk/include/exr/base.h', 65536).decode('utf-8')),
            'installed header version')


def historical_receipt(data=HISTORICAL_RECEIPT_BYTES):
    require(type(data) is bytes and len(data) <= 8192 and hashlib.sha256(data).hexdigest() == HISTORICAL_RECEIPT_SHA,
            'historical connector receipt bytes/hash differ')
    value = strict_json(data, 8192)
    require(value['kind'] == 'source_reviewed_connector_observation_not_current_runner_log_replay'
        and value['repository'] == REPO and value['producer_source'] == OLD_SHA
        and value['run_id'] == OLD_RUN and value['run_attempt'] == 1
        and value['job_id'] == OLD_JOB and value['job_head_sha'] == OLD_SHA
        and value['job_name'] == 'Privacy SDK iphonesimulator' and value['job_status'] == 'completed'
        and value['job_conclusion'] == 'success' and value['artifact_id'] == ARTIFACT
        and value['artifact_name'] == ARTIFACT_NAME and value['artifact_bytes'] == ARTIFACT_BYTES
        and value['artifact_sha256'] == ARTIFACT_SHA and value['artifact_bytes_read_locally'] is False
        and value['log_retrieval_is_not_binary_authentication'] is True, 'historical receipt identity')
    require(value['upload_step'] == {'name': UPLOAD_STEP_NAME, 'status': 'completed', 'conclusion': 'success',
        'number': UPLOAD_STEP, 'started_at': '2026-10-29T10:41:12Z', 'completed_at': '2026-10-29T10:41:17Z'},
        'historical upload step/time')
    require(len(value['decoded_log_selected_lines']) == 4, 'historical four-line receipt')
    upload_identity(('\n'.join(value['decoded_log_selected_lines']) + '\n').encode())
    return value


def pinned_artifact_admission(lookup, download, checkpoint, verify=archive_hash, receipt_bytes=HISTORICAL_RECEIPT_BYTES):
    """The sole new mode: historical upload observation + fresh API + actual ZIP."""
    receipt = historical_receipt(receipt_bytes)
    checkpoint({'historical_upload_receipt_verified': True, 'historical_upload_receipt_used': True})
    run = lookup('actions/runs/' + str(OLD_RUN), 'original-run')
    job = lookup('actions/jobs/' + str(OLD_JOB), 'original-job')
    artifact = lookup('actions/artifacts/' + str(ARTIFACT), 'original-artifact')
    validate_metadata(run, job, artifact)
    require(type(job.get('run_attempt')) is int and job['run_attempt'] == 1 and job.get('head_sha') == OLD_SHA,
            'fresh SDK job attempt/source differs')
    require(upload_step(job) == receipt['upload_step'], 'fresh upload-step metadata/time differs')
    checkpoint({'fresh_artifact_metadata_verified': True})
    archive = download(['gh', 'api', 'repos/' + REPO + '/actions/artifacts/' + str(ARTIFACT) + '/zip'],
                       'original-sdk', ARTIFACT_BYTES)
    verify(archive)  # Production uses exact original size/hash, not metadata alone.
    checkpoint({'downloaded_archive_verified': True})
    return archive, artifact, receipt


def retained_sdk(summary):
    progress = {'mode': 'source_pinned_historical_upload_plus_fresh_artifact', 'historical_upload_receipt_used': False,
        'historical_upload_receipt_verified': False, 'fresh_artifact_metadata_verified': False,
        'downloaded_archive_verified': False, 'fresh_upload_log_replayed': False,
        'historical_receipt_sha256': HISTORICAL_RECEIPT_SHA, 'original_source': OLD_SHA,
        'original_run': OLD_RUN, 'original_job': OLD_JOB, 'original_artifact': ARTIFACT}
    def checkpoint(fields):
        progress.update(fields); summary.update(progress)
        save(E / 'pinned-artifact-admission.json', progress); emit({'pinned_artifact_admission': progress})
    checkpoint({})
    def download(argv, name, cap): return command(argv, name, cap=cap)[1]
    archive, artifact, receipt = pinned_artifact_admission(api, download, checkpoint)
    save(E / 'historical-upload-receipt.json', receipt)
    archive.chmod(0o400)
    rows = unpack(archive, SDK_ROOT)
    identity = strict_json(read_bounded(SDK_ROOT / 'identity.json', 65536))
    product = strict_json(read_bounded(SDK_ROOT / 'products/share/exreader-apple/product.json', 65536))
    installed_schema(identity, product)
    installed_files(SDK_ROOT)
    manifest = inventory(SDK_ROOT)
    save(E / 'retained-sdk.json', {'source': OLD_SHA, 'run': OLD_RUN, 'job': OLD_JOB, 'artifact': artifact,
        'identity': identity, 'members': rows, 'manifest': manifest, 'new_source_build': False,
        'input_admission': progress, 'historical_upload_receipt': receipt})
    emit({'retained_sdk_admitted': True, 'original_source': OLD_SHA, 'artifact_id': ARTIFACT,
          'sha256': ARTIFACT_SHA, 'source_trees_equal': True, 'new_source_build': False,
          'fresh_upload_log_replayed': False, 'historical_upload_receipt_used': True})
    return archive, manifest


def once(text, old, new):
    require(text.count(old) == 1, 'source anchor differs')
    result = text.replace(old, new)
    require(result.count(new) == 1 and result.replace(new, old) == text, 'source roundtrip differs')
    return result


def generate():
    spec = importlib.util.spec_from_file_location('paired_phase_prepare', ROOT / PACKAGE / 'prepare.py')
    phase = importlib.util.module_from_spec(spec); spec.loader.exec_module(phase)
    def reject(*args, **kwargs): raise ValueError('command during pure generation')
    phase.run = phase.command = reject
    original_popen, original_run, original_system = subprocess.Popen, subprocess.run, os.system
    try:
        subprocess.Popen = subprocess.run = os.system = reject
        content = phase.generated(ROOT)
        require(content == phase.generated(ROOT), 'second generation differs')
    finally:
        subprocess.Popen, subprocess.run, os.system = original_popen, original_run, original_system
    expected = {'host/' + n for n in phase.HOSTS} | {'host/AppPhaseRecorder.swift', 'ui/VerifyPhaseTests.swift',
        'make_xcodeproj_phase.rb', 'make_project_phase.rb'}
    require(set(content) == expected, 'seven phase outputs')
    for name, value in content.items():
        path = PHASE / 'generated' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(value)
    original = (ROOT / 'tests/apple_host/make_xcodeproj.rb').read_text()
    baseline = once(original, "['3.40.0', '3.41.0'].include?(sdk_version)", "['3.40.0', '3.41.0', '3.42.0'].include?(sdk_version)")
    baseline = once(baseline, "page_theme == 'ON' && sdk_version != '3.41.0'", "page_theme == 'ON' && !['3.41.0', '3.42.0'].include?(sdk_version)")
    gen = CONTROL / 'generated'; (gen / 'ui').mkdir(parents=True)
    (gen / 'make_xcodeproj_control.rb').write_text(baseline)
    team = once((ROOT / 'tests/reader_team24_apple/make_project.rb').read_text(), "'tests/apple_host/make_xcodeproj.rb'",
                repr(str(gen / 'make_xcodeproj_control.rb')))
    (gen / 'make_project_control.rb').write_text(team)
    shutil.copyfile(ROOT / phase.FORMAL, gen / 'ui/IOSOrganizationAcceptanceTests.swift')
    command([sys.executable, 'tests/apple_host/prepare_fixtures.py', '--resources', RESOURCES], 'fixtures')
    require(sha_file(RESOURCES / 'Sample.epub') == phase.BOOK_SHA, 'fixture identity')
    for name, root in (('control', CONTROL), ('phase', PHASE)):
        project = root / 'generated/project'; project.mkdir()
        if name == 'phase': (project / 'PhaseTests-Info.plist').write_bytes(plistlib.dumps({'NSAppTransportSecurity': phase.ATS}))
        command(['ruby', root / 'generated' / ('make_project_' + name + '.rb'), project, RESOURCES,
                 root / 'generated/ui', 'base'], name + '-generate')
        for platform in ('iOS', 'macOS'):
            path = project / ('Info-' + platform + '.plist'); value = plistlib.loads(path.read_bytes())
            require(value == {'EXRSourceSHA': IDENTITY['source_sha'], 'EXRSDKVersion': '3.42.0', 'EXRPageThemeEnabled': True}, 'app Info baseline')
            if name == 'phase': value['NSAppTransportSecurity'] = phase.ATS; path.write_bytes(plistlib.dumps(value))
        command(['plutil', '-convert', 'json', '-o', PRIVATE / (name + '-pbx.json'),
                 project / 'EXReaderHost.xcodeproj/project.pbxproj'], name + '-pbx-convert')
    manifests = {name: project_manifest(name, phase.ATS) for name in ('control', 'phase')}
    compare_projects(manifests)
    project_controls(phase.ATS)
    save(E / 'project-equality.json', {'equal_except_declared_profile': True, 'normalized': manifests['control'],
        'delta': ['three host replacements', 'recorder addition', 'generated UI', 'test/app scoped ATS Info']})
    for name, root in (('control', CONTROL), ('phase', PHASE)):
        shutil.copytree(root / 'generated', E / 'generated' / name)
    return inventory(RESOURCES), {name: inventory(root / 'generated') for name, root in (('control', CONTROL), ('phase', PHASE))}


def compare_projects(manifests):
    require(set(manifests) == {'control', 'phase'} and manifests['control'] == manifests['phase'],
            'unexpected normalized project difference')


def source_topology(data, profile, project):
    objects = data['objects']; require(0 < len(objects) <= 4000, 'PBX object ceiling')
    targets = {uid: obj for uid, obj in objects.items() if obj.get('isa') == 'PBXNativeTarget'}
    require(sorted(o['name'] for o in targets.values()) == ['EXReaderHost-iOS', 'EXReaderHost-macOS',
            'EXReaderHostUITests-iOS', 'EXReaderHostUITests-macOS'], 'exact targets')
    seen = set()
    def reachable(value):
        if isinstance(value, str) and value in objects and value not in seen:
            seen.add(value); reachable(objects[value])
        elif isinstance(value, dict):
            for child in value.values(): reachable(child)
        elif isinstance(value, list):
            for child in value: reachable(child)
    reachable(data['rootObject']); require(seen == set(objects), 'unreachable PBX object')
    root = CONTROL if profile == 'control' else PHASE
    baseline = sorted((ROOT / 'examples/apple').glob('*.swift')) + [ROOT / 'bindings/swift/EXReader.swift']
    hosts = {str((PHASE / 'generated/host' / p.name) if profile == 'phase' and
            p.name in ('HostViews.swift', 'HostModel.swift', 'HostOrganization.swift') else p) for p in baseline}
    recorder = str(PHASE / 'generated/host/AppPhaseRecorder.swift')
    if profile == 'phase': hosts.add(recorder)
    ui = {str(root / 'generated/ui' / ('VerifyPhaseTests.swift' if profile == 'phase' else 'IOSOrganizationAcceptanceTests.swift'))}
    recorder_refs = []; recorder_builds = []; source_phases = set()
    for target in targets.values():
        sources = [uid for uid in target['buildPhases'] if objects[uid]['isa'] == 'PBXSourcesBuildPhase']
        require(len(sources) == 1 and sources[0] not in source_phases, 'unique target sources phase')
        source_phases.add(sources[0]); paths = []
        for build_id in objects[sources[0]]['files']:
            build = objects[build_id]; require(build['isa'] == 'PBXBuildFile', 'source build object type')
            ref_id = build['fileRef']; ref = objects[ref_id]
            require(ref['isa'] == 'PBXFileReference' and ref['sourceTree'] == '<group>', 'source file binding')
            path = os.path.normpath(str(project / ref['path'])); paths.append(path)
            if path == recorder:
                recorder_refs.append(ref_id); recorder_builds.append((build_id, sources[0]))
        expected = ui if target['productType'] == 'com.apple.product-type.bundle.ui-testing' else hosts
        require(len(paths) == len(expected) and set(paths) == expected, 'exact target source membership')
    if profile == 'control': require(not recorder_refs, 'control recorder membership'); return
    require(len(recorder_refs) == 2 and len(set(recorder_refs)) == 1 and len(set(recorder_builds)) == 2,
            'exact two host recorder memberships')
    ref = recorder_refs[0]; builds = {b: phase for b, phase in recorder_builds}
    record = objects[ref]
    require(set(record) >= {'isa', 'lastKnownFileType', 'path', 'sourceTree'} and
            set(record) <= {'isa', 'lastKnownFileType', 'path', 'sourceTree', 'name', 'includeInIndex'} and
            record['lastKnownFileType'] == 'sourcecode.swift' and
            record['path'] == os.path.relpath(recorder, project), 'recorder reference exact shape/type/path')
    if 'name' in record: require(record['name'] == 'AppPhaseRecorder.swift', 'recorder name')
    if 'includeInIndex' in record:
        require(type(record['includeInIndex']) in (int, str) and record['includeInIndex'] in (1, '1'), 'recorder index flag')
    for build in builds:
        require(objects[build] == {'isa': 'PBXBuildFile', 'fileRef': ref}, 'recorder per-file settings/keys')
    main_group = objects[data['rootObject']]['mainGroup']
    host_groups = [uid for uid, obj in objects.items() if obj.get('isa') == 'PBXGroup' and obj.get('name') == 'Host']
    require(len(host_groups) == 1, 'exact Host group')
    edges = []
    def references(value, parent, key):
        if isinstance(value, str) and (value == ref or value in builds): edges.append((parent, key, value))
        elif isinstance(value, list):
            for v in value: references(v, parent, key)
        elif isinstance(value, dict):
            for k, v in value.items(): references(v, parent, k)
    for uid, obj in objects.items(): references(obj, uid, '')
    expected_edges = [(b, 'fileRef', ref) for b in builds] + [(phase, 'files', b) for b, phase in builds.items()]
    expected_edges += [(g, 'children', ref) for g in (main_group, host_groups[0])]
    require(sorted(edges) == sorted(expected_edges), 'recorder edge escapes declared topology')


def project_manifest(profile, ats, supplied=None):
    root = CONTROL if profile == 'control' else PHASE
    project = root / 'generated/project'
    data = supplied if supplied is not None else strict_json(read_bounded(PRIVATE / (profile + '-pbx.json'), 2 * 1024 ** 2))
    source_topology(data, profile, project)
    objects = copy.deepcopy(data['objects']); removed = set(); actual_files = {}
    for uid, obj in objects.items():
        if obj['isa'] != 'PBXFileReference' or 'path' not in obj: continue
        if obj.get('sourceTree') == 'BUILT_PRODUCTS_DIR': continue
        if obj.get('sourceTree') in ('SDKROOT', 'DEVELOPER_DIR'):
            require(not obj['path'].startswith('/') and '..' not in Path(obj['path']).parts, 'system reference path')
            continue  # Compared unchanged in the full normalized graph.
        require(obj.get('sourceTree') == '<group>', 'unexpected sourceTree')
        path = str((project / obj['path']).resolve()); actual_files[uid] = path
        if path == str(PHASE / 'generated/host/AppPhaseRecorder.swift'):
            require(profile == 'phase', 'recorder in control'); removed.add(uid); continue
        host = next((n for n in ('HostViews.swift', 'HostModel.swift', 'HostOrganization.swift')
            if path == str((ROOT / 'examples/apple' / n) if profile == 'control' else (PHASE / 'generated/host' / n))), None)
        if host: obj['path'] = '<PROFILE_HOST>/' + host
        elif path == str(root / 'generated/ui' / ('IOSOrganizationAcceptanceTests.swift' if profile == 'control' else 'VerifyPhaseTests.swift')):
            obj['path'] = '<PROFILE_UI>/Tests.swift'
            if 'name' in obj:
                require(obj['name'] == Path(path).name, 'UI reference display name')
                obj['name'] = 'Tests.swift'
        else: obj['path'] = path
    require(len(removed) == (1 if profile == 'phase' else 0), 'exact recorder reference count')
    removed |= {uid for uid, obj in objects.items() if obj['isa'] == 'PBXBuildFile' and obj.get('fileRef') in removed}
    targets = {uid: obj for uid, obj in objects.items() if obj['isa'] == 'PBXNativeTarget'}
    require(sorted(o['name'] for o in targets.values()) == ['EXReaderHost-iOS', 'EXReaderHost-macOS', 'EXReaderHostUITests-iOS', 'EXReaderHostUITests-macOS'], 'exact targets')
    for target in targets.values():
        test = target['productType'] == 'com.apple.product-type.bundle.ui-testing'
        configs = objects[target['buildConfigurationList']]['buildConfigurations']
        for config in configs:
            settings = objects[config]['buildSettings']
            if test:
                if profile == 'phase':
                    require(settings.pop('INFOPLIST_FILE') == str(project / 'PhaseTests-Info.plist'), 'exact test Info setting')
                else: require('INFOPLIST_FILE' not in settings, 'baseline test Info setting')
            elif 'INFOPLIST_FILE' in settings:
                require(settings['INFOPLIST_FILE'] in [str(project / ('Info-' + p + '.plist')) for p in ('iOS', 'macOS')], 'app Info path')
    for uid in removed: del objects[uid]
    def clean(value):
        if isinstance(value, list): return [clean(v) for v in value if not (isinstance(v, str) and v in removed)]
        if isinstance(value, dict): return {k: clean(v) for k, v in value.items()}
        if isinstance(value, str):
            require(value not in removed, 'removed recorder referenced unexpectedly')
            return value.replace(str(root / 'generated'), '<PROFILE_GENERATED>')
        return value
    objects = {uid: clean(obj) for uid, obj in objects.items()}
    expanded_count = [0]
    def expand(value, active=()):
        expanded_count[0] += 1; require(expanded_count[0] <= 200000 and len(active) <= 32, 'project graph bound')
        if isinstance(value, str) and value in objects:
            if value in active:
                obj = objects[value]; return {'cycle': obj['isa'], 'name': obj.get('name')}
            return expand(objects[value], active + (value,))
        if isinstance(value, dict): return {k: expand(v, active) for k, v in value.items()}
        if isinstance(value, list): return [expand(v, active) for v in value]
        return value
    graph = {k: expand(v) for k, v in data.items() if k != 'objects'}
    schemes = {}
    for platform in ('iOS', 'macOS'):
        file = project / 'EXReaderHost.xcodeproj/xcshareddata/xcschemes' / ('EXReaderHost-' + platform + '.xcscheme')
        tree = ET.fromstring(file.read_bytes())
        for node in tree.iter():
            if 'BlueprintIdentifier' in node.attrib:
                uid = node.attrib['BlueprintIdentifier']; require(uid in targets, 'scheme unknown target')
                node.attrib['BlueprintIdentifier'] = targets[uid]['name']
        schemes[platform] = ET.tostring(tree, encoding='unicode')
        info = plistlib.loads((project / ('Info-' + platform + '.plist')).read_bytes())
        if profile == 'phase': require(info.pop('NSAppTransportSecurity') == ats, 'exact app ATS')
        require(info == {'EXRSourceSHA': IDENTITY['source_sha'], 'EXRSDKVersion': '3.42.0', 'EXRPageThemeEnabled': True}, 'app Info identity')
    if profile == 'phase': require(plistlib.loads((project / 'PhaseTests-Info.plist').read_bytes()) == {'NSAppTransportSecurity': ats}, 'test ATS Info')
    return {'graph': graph, 'schemes': schemes}


def project_controls(ats):
    """Mutate the actual generated graph through the actual admission helper."""
    baseline = strict_json(read_bounded(PRIVATE / 'phase-pbx.json', 2 * 1024 ** 2)); results = {}
    objects = baseline['objects']
    recorder = next(uid for uid, obj in objects.items() if obj.get('isa') == 'PBXFileReference'
        and obj.get('path', '').endswith('/AppPhaseRecorder.swift'))
    build = next(uid for uid, obj in objects.items() if obj.get('fileRef') == recorder)
    phase = next(uid for uid, obj in objects.items() if obj.get('isa') == 'PBXSourcesBuildPhase' and build in obj['files'])
    other = next(uid for uid, obj in objects.items() if obj.get('isa') == 'PBXResourcesBuildPhase')
    def negative(name, mutate):
        altered = copy.deepcopy(baseline); mutate(altered['objects'])
        try: project_manifest('phase', ats, altered)
        except ValueError: results[name] = True
        else: raise ValueError('actual project mutation admitted: ' + name)
    negative('missing_recorder_membership', lambda o: o[phase]['files'].remove(build))
    negative('duplicate_recorder_membership', lambda o: o[phase]['files'].append(build))
    negative('recorder_extra_resource_edge', lambda o: o[other]['files'].append(build))
    negative('recorder_wrong_source_tree', lambda o: o[recorder].update(sourceTree='SOURCE_ROOT'))
    negative('recorder_compiler_flags', lambda o: o[build].update(settings={'COMPILER_FLAGS': '-DOTHER'}))
    negative('recorder_wrong_file_type', lambda o: o[recorder].update(lastKnownFileType='sourcecode.c.c'))
    negative('recorder_unknown_attribute', lambda o: o[recorder].update(unexpected='value'))
    negative('unreachable_object', lambda o: o.update({'UNREACHABLE': {'isa': 'PBXGroup', 'children': []}}))
    negative('recorder_missing_build_file', lambda o: o[phase].update(files=[x for x in o[phase]['files'] if x != build]))
    save(E / 'project-controls.json', results); emit({'actual_project_controls': results})


def runtime_create():
    global CREATED_UUID
    _, path, _ = command(['xcrun', 'simctl', 'list', 'runtimes', '-j'], 'runtimes', timeout=180, cap=256 * 1024)
    data = strict_json(read_bounded(path, 256 * 1024), 256 * 1024)
    choices = [r for r in data['runtimes'] if r.get('identifier') == RUNTIME]
    require(len(choices) == 1 and choices[0].get('isAvailable') is True
            and DEVICE in [d.get('identifier') for d in choices[0]['supportedDeviceTypes']], 'pinned runtime/device')
    uid = text_command(['xcrun', 'simctl', 'create', 'EXR-build-pair-' + IDENTITY['run_id'], DEVICE, RUNTIME],
                       'create', timeout=180, cap=4096)
    require(re.fullmatch(r'[0-9A-Fa-f-]{36}', uid), 'created UUID')
    CREATED_UUID = uid
    save(E / 'destination.json', {'uuid': uid, 'runtime': choices[0], 'fresh_created': True, 'booted': False})
    return uid


def observe_build(profile, uid):
    code, out, err = command(build_argv(profile, uid), profile + '-build', timeout=120, allowed_exit=True, build=(profile, uid))
    # Fixed numeric-only own-group API; no metadata child or global process scan.
    members = group_members(os.getpgrp())
    require(members == {os.getpid()}, 'unclosed owned descendants after build')
    texts = []; logs = []
    for path in (out, err):
        data = read_bounded(path, 16 * 1024 ** 2); text = data.decode('utf-8'); texts.append(text)
        target = E / 'logs' / path.name; target.parent.mkdir(exist_ok=True); target.write_bytes(data)
        preview = {'path': target.relative_to(E).as_posix(), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                   'prefix': text[:18000], 'suffix': text[-6000:] if len(text) > 18000 else '', 'preview_truncated': len(text) > 24000}
        emit({'build_log': preview}); logs.append({k: v for k, v in preview.items() if k not in ('prefix', 'suffix')})
    full = '\n'.join(texts)
    root = CONTROL if profile == 'control' else PHASE
    runs = []
    folder = root / 'DerivedData/Build/Products'
    if folder.exists():
        for path in folder.glob('*.xctestrun'):
            require(len(runs) < 8 and path.is_file() and not path.is_symlink() and path.stat().st_size <= 1024 ** 2, 'xctestrun bound')
            runs.append({'name': path.name, 'bytes': path.stat().st_size, 'sha256': sha_file(path)})
    row = {'profile': profile, 'exit_code': code, 'reaped': True, 'owned_descendants_closed': True,
        'owned_group_snapshot': sorted(members), 'logs': logs,
        'description_stage': 'CreateBuildDescription' in full,
        'description_signatures': re.findall(r'Build description signature: ([0-9a-f]{32})', full),
        'service_crash': 'The Xcode build system has crashed.' in full,
        'xctestrun': runs, 'build_succeeded': code == 0 and bool(runs),
        'native_cases_run': 0, 'root_cause_proved': False}
    save(E / (profile + '-result.json'), row); emit({'build_outcome': row})
    return row


def pair(run_arm, unchanged, remaining):
    require(remaining() >= 270, 'insufficient reserved pair/finalization budget')
    result = []
    for index, profile in enumerate(('control', 'phase')):
        require(remaining() >= (2 - index) * 120 + 30, 'pair budget no longer intact')
        require(unchanged(), 'shared/project input mutation')
        row = run_arm(profile); result.append(row)
        require(row.get('profile') == profile and row.get('reaped') is True
                and row.get('owned_descendants_closed') is True and type(row.get('exit_code')) is int,
                'arm lifecycle identity')
        require(unchanged(), 'post-arm input mutation')
    return result


def completed_pair(run_arm, unchanged, remaining):
    rows = pair(run_arm, unchanged, remaining)
    require(unchanged() is True, 'final shared/project input revalidation failed')
    return rows


def interpretation(rows):
    require([r['profile'] for r in rows] == ['control', 'phase'], 'pair order')
    a, b = rows
    if not all(r['description_stage'] and r['description_signatures'] for r in rows): return 'inconclusive_before_shared_description_boundary'
    if a['build_succeeded'] and b['service_crash']: return 'phase_profile_discriminates_in_this_single_ordered_pair'
    if a['service_crash'] and b['service_crash']: return 'shared_crash_not_unique_to_phase_profile'
    if a['build_succeeded'] and b['build_succeeded']: return 'non_reproduction_not_a_fix'
    return 'inconclusive_other_or_order_sensitive_outcome'


def log_controls(result, reject):
    """Actions-only synthetic cases through the actual capture/route helpers."""
    global PRINTED
    body = ('SHA256 digest of uploaded artifact zip is ' + ARTIFACT_SHA + '\nArtifact ' + ARTIFACT_NAME +
        '.zip successfully finalized. Artifact ID ' + str(ARTIFACT) + '\nArtifact ' + ARTIFACT_NAME +
        ' has been successfully uploaded! Final size is ' + str(ARTIFACT_BYTES) +
        ' bytes. Artifact ID is ' + str(ARTIFACT) + '\n').encode()
    def response(payload=b'', status=200, media='text/plain', extra=b''):
        return ('HTTP/2.0 ' + str(status) + ' Status\nContent-Type: ' + media + '\r\n').encode() + extra + b'\r\n' + payload
    step = {'number': 5, 'name': UPLOAD_STEP_NAME, 'status': 'completed', 'conclusion': 'success'}
    job = {'id': OLD_JOB, 'run_id': OLD_RUN, 'head_sha': OLD_SHA, 'name': 'Privacy SDK iphonesimulator',
           'status': 'completed', 'conclusion': 'success', 'steps': [step]}
    good = (0, {'stdout': response(body), 'stderr': b''})
    guard = (1, {'stdout': response(), 'stderr': GUARD_REFUSAL})
    def exercise(first, second=good, version='2.100.0', metadata=job):
        calls = []
        def request(alternative):
            calls.append(alternative)
            require(calls in ([False], [False, True]), 'duplicate alternative request')
            return second if alternative else first
        return calls, lambda: authenticated_upload(metadata, version, request)
    calls, action = exercise(good)
    require(action()['route'] == 'whole_job' and calls == [False], 'whole log positive')
    result['whole_log_positive'] = True
    for media in ('text/plain', 'application/octet-stream', 'text/plain; charset=utf-8'):
        first = (1, {'stdout': response(media=media), 'stderr': GUARD_REFUSAL})
        second = (0, {'stdout': response(body, media=media), 'stderr': b''})
        calls, action = exercise(first, second)
        value = action()
        require(value['route'] == 'same_job_upload_step_5' and calls == [False, True]
                and value['body_sha256'] == hashlib.sha256(body).hexdigest(), 'exact guard step positive')
    result['exact_cli_guard_both_mime_routes'] = True
    failures = [(str(status), (1, {'stdout': response(status=status), 'stderr': GUARD_REFUSAL}))
                for status in (401, 403, 404, 410, 429, 500, 502, 503)]
    failures += [
        ('no_status', (1, {'stdout': b'', 'stderr': GUARD_REFUSAL})),
        ('partial_header', (1, {'stdout': response()[:-1], 'stderr': GUARD_REFUSAL})),
        ('two_blocks', (1, {'stdout': response(response()), 'stderr': GUARD_REFUSAL})),
        ('status_crlf', (1, {'stdout': response().replace(b'Status\n', b'Status\r\n'), 'stderr': GUARD_REFUSAL})),
        ('header_lf', (1, {'stdout': response().replace(b'\r\n', b'\n'), 'stderr': GUARD_REFUSAL})),
        ('folded_header', (1, {'stdout': response(extra=b' folded\r\n'), 'stderr': GUARD_REFUSAL})),
        ('duplicate_content_type', (1, {'stdout': response(extra=b'Content-Type: text/plain\r\n'), 'stderr': GUARD_REFUSAL})),
        ('duplicate_status_field', (1, {'stdout': response(extra=b'Status: 200\r\n'), 'stderr': GUARD_REFUSAL})),
        ('json_media', (1, {'stdout': response(media='application/json'), 'stderr': GUARD_REFUSAL})),
        ('comma_media', (1, {'stdout': response(media='text/plain, text/plain'), 'stderr': GUARD_REFUSAL})),
        ('wrong_charset', (1, {'stdout': response(media='text/plain; charset=latin1'), 'stderr': GUARD_REFUSAL})),
        ('guard_extra_denial', (1, {'stdout': response(), 'stderr': GUARD_REFUSAL + b'gh: permission denied\n'})),
        ('guard_hidden_late_line', (1, {'stdout': response(), 'stderr': GUARD_REFUSAL + b' ' * 50000 + b'denied\n'})),
        ('guard_redaction_cannot_erase', (1, {'stdout': response(), 'stderr': GUARD_REFUSAL + b'Authorization: token\n'})),
        ('guard_wrong_exit', (4, {'stdout': response(), 'stderr': GUARD_REFUSAL})),
        ('guard_body_present', (1, {'stdout': response(b'partial'), 'stderr': GUARD_REFUSAL})),
        ('guard_missing_stderr', (1, {'stdout': response()})),
        ('guard_invalid_utf8', (1, {'stdout': response(), 'stderr': GUARD_REFUSAL + b'\xff'}))]
    for label, first in failures:
        calls, action = exercise(first); reject('log_' + label, action)
        require(calls == [False], 'refused case attempted alternative: ' + label)
    calls, action = exercise(guard, version='2.99.0'); reject('log_unknown_cli_version', action)
    require(calls == [False], 'unknown version alternative attempted')
    for field, wrong in [('id', OLD_JOB + 1), ('run_id', OLD_RUN + 1), ('head_sha', '0' * 40), ('conclusion', 'failure')]:
        calls, action = exercise(guard, metadata=dict(job, **{field: wrong})); reject('step_parent_' + field, action)
        require(calls == [False], 'invalid parent requested step')
    for field, wrong in [('number', 6), ('number', True), ('name', 'Other'), ('conclusion', 'failure')]:
        calls, action = exercise(guard, metadata=dict(job, steps=[dict(step, **{field: wrong})]))
        reject('step_' + field + '_' + str(wrong), action); require(calls == [False], 'invalid step requested')
    calls, action = exercise(guard, metadata=dict(job, steps=[step, step])); reject('step_duplicate', action)
    require(calls == [False], 'duplicate step requested')
    calls, action = exercise(guard, second=guard); reject('step_second_guard_no_third_route', action)
    require(calls == [False, True], 'unexpected third route')
    mutated = [('wrong_digest', body.replace(ARTIFACT_SHA.encode(), b'0' * 64)),
        ('wrong_id', body.replace(str(ARTIFACT).encode(), str(ARTIFACT + 1).encode())),
        ('wrong_name', body.replace(ARTIFACT_NAME.encode(), b'other-artifact')),
        ('wrong_size', body.replace(str(ARTIFACT_BYTES).encode(), str(ARTIFACT_BYTES + 1).encode())),
        ('missing_line', body.split(b'\n', 1)[1]), ('duplicate_upload', body + body),
        ('ansi', body + b'\x1b[0m'), ('del', body + b'\x7f'), ('nul', body + b'\x00'), ('invalid_utf8', body + b'\xff')]
    for label, wrong in mutated:
        for alternative in (False, True):
            bad = (0, {'stdout': response(wrong), 'stderr': b''})
            calls, action = exercise(guard if alternative else bad, second=bad)
            reject('upload_' + label + ('_step' if alternative else '_whole'), action)
            require(calls == ([False, True] if alternative else [False]), 'wrong identity retry')
    reject('source_workflow_modified', lambda: validate_source(IDENTITY['source_sha'], PARENT,
        ['M\t' + PATHS[0], 'M\t.github/workflows/apple-ios-verify-build-comparison-20261029.yml']))
    reject('source_driver_added_instead', lambda: validate_source(IDENTITY['source_sha'], PARENT, ['A\t' + PATHS[0]]))
    reject('escape_override_command', lambda: command_allowed(
        ['gh', 'api', '--allow-escape-sequences', 'repos/' + REPO + '/actions/jobs/' + str(OLD_JOB) + '/logs'],
        'original-upload-log', None))
    # Actual failure receipt helper; raw inputs are synthetic private fixtures.
    record = {'output': 'capture-control', 'argv': ['gh', 'api', '--include', 'fixed'], 'exit_code': 1,
              'started': 1.0, 'finished': 2.0}
    out, err = PRIVATE / 'capture.stdout', PRIVATE / 'capture.stderr'
    out.write_bytes(response(b'hello https://user:secret@host/path?signature=PRIVATE#secret\n'))
    err.write_bytes(('Authorization: PRIVATE\nCookie: PRIVATE\n' + 'ACTIVE-TOKEN\x00\x1b\x7fé😀' * 20000).encode())
    receipts, emissions = [], []
    raw, receipt = command_capture(record, out, err, 2 * 1024 ** 2, True,
        writer=lambda p, v: receipts.append(v), sink=emissions.append, tokens=['ACTIVE-TOKEN'])
    rendered = encoded(receipts[-1])
    require(len(rendered) <= 48 * 1024 and b'ACTIVE-TOKEN' not in rendered and b'PRIVATE' not in rendered
            and b'user:secret' not in rendered and b'\x1b' not in rendered and b'\x7f' not in rendered
            and raw['stderr'] == read_bounded(err, 2 * 1024 ** 2), 'safe preview changed raw decision or leaked credential')
    result['capture_encoded_redaction_raw_separation'] = True
    def capture(**kw):
        return command_capture(record, out, err, 2 * 1024 ** 2, kw.pop('closed', True),
            writer=kw.pop('writer', lambda p, v: None), sink=kw.pop('sink', lambda v: None), **kw)
    reject('capture_unclosed_not_read', lambda: capture(closed=False,
        reader=lambda *a: (_ for _ in ()).throw(AssertionError('live stream read'))))
    reject('capture_missing_stderr', lambda: command_capture(record, out, PRIVATE / 'missing-stderr', 2 * 1024 ** 2,
        True, writer=lambda p, v: None, sink=lambda v: None))
    err.write_bytes(b'\xff'); reject('capture_invalid_utf8', capture)
    err.write_bytes(b'finite')
    reject('capture_oversized', lambda: command_capture(record, out, err, 1, True, writer=lambda p, v: None, sink=lambda v: None))
    def changed_reader(path, cap):
        def grow(event):
            if event == 'file_opened':
                with path.open('ab') as f: f.write(b'x')
        return read_bounded(path, cap, grow)
    reject('capture_changing_stream', lambda: capture(reader=changed_reader))
    def fail(*args): raise OSError('synthetic observation receipt/sink failure')
    reject('capture_receipt_failure', lambda: capture(writer=fail))
    reject('capture_sink_failure', lambda: capture(sink=fail))
    require(safe_response({'request_id': 'ACTIVE-TOKEN'}, ['ACTIVE-TOKEN'])['request_id'] == '[active-token-redacted]',
            'request ID token redaction')
    result['request_id_token_redaction'] = True
    printed = PRINTED
    try:
        PRINTED = 496 * 1024
        reject('actual_emit_ordinary_reservation', lambda: emit({'must_not_reach_sink': True}))
        require(PRINTED == 496 * 1024, 'failed emit changed reservation')
    finally: PRINTED = printed
    result['old_controls_retained_no_new_native_budget'] = True


def pinned_artifact_controls(result, reject):
    original = historical_receipt(); result['historical_receipt_exact_bytes'] = True
    for field, wrong in [('producer_source', '0' * 40), ('run_id', OLD_RUN + 1), ('run_attempt', 2),
        ('job_id', OLD_JOB + 1), ('artifact_id', ARTIFACT + 1), ('artifact_name', 'different'),
        ('artifact_bytes', ARTIFACT_BYTES + 1), ('artifact_sha256', '0' * 64)]:
        changed = dict(original, **{field: wrong})
        reject('historical_' + field, lambda changed=changed: historical_receipt(encoded(changed)))
    changed = copy.deepcopy(original); changed['upload_step']['number'] = 6
    reject('historical_step', lambda: historical_receipt(encoded(changed)))
    for label, lines in [('missing_line', original['decoded_log_selected_lines'][:-1]),
                         ('duplicate_line', original['decoded_log_selected_lines'] * 2)]:
        changed = dict(original, decoded_log_selected_lines=lines)
        reject('historical_' + label, lambda changed=changed: historical_receipt(encoded(changed)))
    reject('historical_reformatted_bytes', lambda: historical_receipt(encoded(original)))
    run = {'id': OLD_RUN, 'run_attempt': 1, 'head_sha': OLD_SHA, 'status': 'completed'}
    job = {'id': OLD_JOB, 'run_id': OLD_RUN, 'head_sha': OLD_SHA, 'run_attempt': 1,
        'name': 'Privacy SDK iphonesimulator', 'status': 'completed', 'conclusion': 'success',
        'steps': [copy.deepcopy(original['upload_step'])]}
    art = {'id': ARTIFACT, 'name': ARTIFACT_NAME, 'size_in_bytes': ARTIFACT_BYTES, 'expired': False,
        'digest': 'sha256:' + ARTIFACT_SHA, 'workflow_run': {'id': OLD_RUN, 'head_sha': OLD_SHA}}
    expected = [('actions/runs/' + str(OLD_RUN), 'original-run'),
        ('actions/jobs/' + str(OLD_JOB), 'original-job'), ('actions/artifacts/' + str(ARTIFACT), 'original-artifact')]
    archive_argv = ['gh', 'api', 'repos/' + REPO + '/actions/artifacts/' + str(ARTIFACT) + '/zip']
    fixture = PRIVATE / 'pinned-admission-fixture'; fixture.write_bytes(b'four')
    def exercise(artifact=art, producer=job, original_run=run, verify=None, missing=False, receipt=HISTORICAL_RECEIPT_BYTES):
        calls, checkpoints = [], []
        values = {'original-run': original_run, 'original-job': producer, 'original-artifact': artifact}
        def lookup(endpoint, name):
            calls.append((endpoint, name)); require(calls == expected[:len(calls)], 'unexpected live metadata sequence')
            if missing and name == 'original-artifact': raise OSError('synthetic original artifact404')
            return values[name]
        def download(argv, name, cap):
            require(calls == expected and argv == archive_argv and name == 'original-sdk' and cap == ARTIFACT_BYTES,
                    'unexpected archive request or duplicate')
            calls.append(('archive', name)); return fixture
        # The synthetic positive uses the actual hashing helper with a tiny
        # declared fixture. Production has no override and verifies20965175B.
        check_archive = verify or (lambda p: archive_hash(p, 4, hashlib.sha256(b'four').hexdigest()))
        return calls, checkpoints, lambda: pinned_artifact_admission(lookup, download, checkpoints.append,
                                                                     check_archive, receipt)
    calls, checkpoints, action = exercise(); action()
    require(calls == expected + [('archive', 'original-sdk')] and checkpoints == [
        {'historical_upload_receipt_verified': True, 'historical_upload_receipt_used': True},
        {'fresh_artifact_metadata_verified': True}, {'downloaded_archive_verified': True}],
        'actual pinned-admission request sequence/checkpoints')
    result['pinned_mode_exact_requests_no_log_route'] = True
    for field, wrong in [('digest', 'sha256:' + '0' * 64), ('expired', True), ('id', ARTIFACT + 1),
                         ('size_in_bytes', ARTIFACT_BYTES + 1), ('name', 'other')]:
        calls, checkpoints, action = exercise(artifact=dict(art, **{field: wrong}))
        reject('pinned_api_' + field, action)
        require(calls == expected and not any('downloaded_archive_verified' in x for x in checkpoints), 'bad API downloaded')
    calls, checkpoints, action = exercise(missing=True); reject('pinned_artifact_missing_no_fallback', action)
    require(calls == expected, 'missing artifact extra route')
    for field, wrong in [('head_sha', '0' * 40), ('run_attempt', 2), ('run_attempt', True)]:
        calls, checkpoints, action = exercise(producer=dict(job, **{field: wrong}))
        reject('pinned_job_' + field + '_' + str(wrong), action); require(calls == expected, 'bad job downloaded')
    altered = copy.deepcopy(job); altered['steps'][0]['completed_at'] = '2026-10-29T10:41:18Z'
    calls, checkpoints, action = exercise(producer=altered); reject('pinned_step_time_changed', action)
    require(calls == expected, 'bad step downloaded')
    calls, checkpoints, action = exercise(original_run=dict(run, run_attempt=2))
    reject('pinned_run_attempt', action); require(calls == expected, 'bad attempt downloaded')
    calls, checkpoints, action = exercise(verify=archive_hash)
    reject('pinned_actual_original_size_gate', action)
    require(calls == expected + [('archive', 'original-sdk')] and not any('downloaded_archive_verified' in x for x in checkpoints),
            'wrong actual archive marked verified')
    calls, checkpoints, action = exercise(verify=lambda p: archive_hash(p, 4, hashlib.sha256(b'foor').hexdigest()))
    reject('pinned_same_size_wrong_download_hash', action)
    require(not any('downloaded_archive_verified' in x for x in checkpoints), 'bad hash marked verified')
    calls, checkpoints, action = exercise(receipt=HISTORICAL_RECEIPT_BYTES + b' ')
    reject('pinned_receipt_invalid_before_requests', action); require(calls == [] and checkpoints == [], 'bad receipt made request')
    for name, argv in [('original-upload-log', ['gh', 'api', '--include', 'repos/' + REPO + '/actions/jobs/' + str(OLD_JOB) + '/logs']),
        ('original-upload-step', ['gh', 'api', '--include', 'repos/' + REPO + '/actions/jobs/' + str(OLD_JOB) + '/steps/5/logs']),
        ('original-run-logs', ['gh', 'api', 'repos/' + REPO + '/actions/runs/' + str(OLD_RUN) + '/logs']),
        ('gh-version', ['gh', '--version'])]:
        reject('removed_live_' + name, lambda argv=argv, name=name: command_allowed(argv, name, None))


def controls():
    result = {}
    def reject(name, action):
        try: action()
        except (ValueError, OSError, zipfile.BadZipFile, UnicodeError): result[name] = True
        else: raise ValueError('negative control admitted: ' + name)
    uid = '11111111-1111-1111-1111-111111111111'
    for name, position, value in [('test_action', 1, 'test'), ('wrong_destination', -1, 'platform=macOS'),
                                  ('wrong_scheme', 5, 'Other'), ('wrong_sdk', 8, 'EXR_SDK_DIR=/tmp')]:
        argv = build_argv('control', uid); argv[position] = value
        reject(name, lambda argv=argv: validate_build(argv, 'control', uid))
    reject('duplicate_build_arg', lambda: validate_build(build_argv('control', uid) + ['-quiet'], 'control', uid))
    reject('sdk_rebuild_command', lambda: command_allowed([sys.executable, 'tests/apple_sdk342_package/run.py'], 'fixtures', None))
    reject('unexpected_command', lambda: command_allowed(['sh', '-c', 'true'], 'version', None))
    reject('nonfinite_json', lambda: strict_json(b'{"x":NaN}'))
    reject('duplicate_json', lambda: strict_json(b'{"x":1,"x":2}'))
    reject('oversized_json', lambda: strict_json(b' ' * 20, 10))
    reject('unexpected_project_delta', lambda: compare_projects({'control': {'graph': 1}, 'phase': {'graph': 2}}))
    reject('missing_project_arm', lambda: compare_projects({'control': {}}))
    valid_delta = ['M\t' + p for p in PATHS]
    validate_source(IDENTITY['source_sha'], PARENT, valid_delta)
    reject('source_wrong_head', lambda: validate_source('0' * 40, PARENT, valid_delta))
    reject('source_wrong_parent', lambda: validate_source(IDENTITY['source_sha'], '0' * 40, valid_delta))
    reject('source_missing_path', lambda: validate_source(IDENTITY['source_sha'], PARENT, []))
    reject('source_modified_old_path', lambda: validate_source(IDENTITY['source_sha'], PARENT, valid_delta + ['M\texamples/apple/HostModel.swift']))
    def infos(names): return [zipfile.ZipInfo(n) for n in names]
    for name, names in [('traversal', ['sdk/../x']), ('case_alias', ['sdk/X', 'sdk/x']),
        ('unicode_alias', ['sdk/é', 'sdk/é']), ('file_directory', ['sdk/a', 'sdk/a/b']),
        ('backslash', ['sdk/a\\b']), ('control_character', ['sdk/\x01']), ('extra_root', ['tools/a'])]:
        reject('zip_' + name, lambda names=names: zip_names(infos(names)))
    z = zipfile.ZipInfo('sdk/a'); z.external_attr = (stat.S_IFLNK | 0o777) << 16
    reject('zip_link', lambda: zip_names([z]))
    z = zipfile.ZipInfo('sdk/a/'); z.file_size = 1
    reject('zip_directory_data', lambda: zip_names([z]))
    z = zipfile.ZipInfo('sdk/a'); z.file_size = 512 * 1024 ** 2 + 1
    reject('zip_expanded_limit', lambda: zip_names([z]))
    reject('zip_count', lambda: zip_names(infos(['sdk/a'] * 20001)))
    good_zip = PRIVATE / 'zip-control.zip'
    with zipfile.ZipFile(good_zip, 'w', compression=zipfile.ZIP_STORED) as fixture_zip:
        fixture_zip.writestr('sdk/', b''); fixture_zip.writestr('identity.json', b'fixture-marker')
    rows = unpack(good_zip, PRIVATE / 'zip-control-good')
    require(len(rows) == 2 and rows[0]['kind'] == 'directory', 'actual ZIP positive')
    result['zip_actual_directory_and_file'] = True
    data = bytearray(good_zip.read_bytes()); data[30] = ord('x')
    bad_zip = PRIVATE / 'zip-control-bad-header.zip'; bad_zip.write_bytes(data)
    reject('zip_directory_header', lambda: unpack(bad_zip, PRIVATE / 'zip-control-header-out'))
    data = bytearray(good_zip.read_bytes()); position = data.index(b'fixture-marker'); data[position] ^= 1
    bad_crc = PRIVATE / 'zip-control-bad-crc.zip'; bad_crc.write_bytes(data)
    reject('zip_actual_crc', lambda: unpack(bad_crc, PRIVATE / 'zip-control-crc-out'))
    run = {'id': OLD_RUN, 'run_attempt': 1, 'head_sha': OLD_SHA, 'status': 'completed'}
    job = {'id': OLD_JOB, 'run_id': OLD_RUN, 'name': 'Privacy SDK iphonesimulator', 'status': 'completed', 'conclusion': 'success'}
    art = {'id': ARTIFACT, 'name': ARTIFACT_NAME, 'size_in_bytes': ARTIFACT_BYTES, 'expired': False,
        'digest': 'sha256:' + ARTIFACT_SHA, 'workflow_run': {'id': OLD_RUN, 'head_sha': OLD_SHA}}
    validate_metadata(run, job, art); result['metadata_positive'] = True
    for name, field, value in [('artifact_id', 'id', ARTIFACT + 1), ('artifact_size', 'size_in_bytes', 1),
        ('artifact_expired', 'expired', True), ('artifact_digest', 'digest', 'sha256:wrong')]:
        altered = dict(art, **{field: value}); reject(name, lambda altered=altered: validate_metadata(run, job, altered))
    reject('wrong_run', lambda: validate_metadata(dict(run, head_sha='0' * 40), job, art))
    reject('bool_attempt', lambda: validate_metadata(dict(run, run_attempt=True), job, art))
    reject('failed_job', lambda: validate_metadata(run, dict(job, conclusion='failure'), art))
    fixture = PRIVATE / 'hash-control'; fixture.write_bytes(b'abcd')
    reject('same_size_wrong_digest', lambda: archive_hash(fixture, 4, hashlib.sha256(b'abce').hexdigest()))
    reject('wrong_zip_length', lambda: archive_hash(fixture, 3, hashlib.sha256(b'abcd').hexdigest()))
    # Replacement/growth are exercised at the shared FD helper boundaries.
    probe = PRIVATE / 'fd-controls'; probe.mkdir(); (probe / 'child').mkdir(); (probe / 'child/data').write_bytes(b'owned')
    def replace_directory(event, name):
        if event == 'directory_scanned' and name == 'child':
            (probe / 'child').rename(probe / 'old'); (probe / 'child').symlink_to(probe / 'old', target_is_directory=True)
    reject('fd_directory_replacement', lambda: inventory(probe, hook=replace_directory))
    f = PRIVATE / 'fd-file'; f.write_bytes(b'four')
    def replace_file(event):
        if event == 'file_scanned': f.rename(PRIVATE / 'old-fd-file'); f.write_bytes(b'new!')
    reject('fd_file_replacement', lambda: read_bounded(f, 4, replace_file))
    def grow_file(event):
        if event == 'file_opened':
            with f.open('ab') as out: out.write(b'growth')
    reject('fd_growth_after_open', lambda: read_bounded(f, 4, grow_file))
    installed = PRIVATE / 'installed-controls'
    for name in ['sdk/include/exreader.h', 'sdk/include/exr/base.h', 'sdk/lib/libexreader.dylib',
                 'products/lib/libreader_original_export.a', 'products/include/reader_original_export.h']:
        p = installed / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b'fixture')
    header = installed / 'sdk/include/exr/base.h'; header.write_text('#define EXR_VERSION "3.42.0"\n')
    installed_files(installed); result['installed_files_positive'] = True
    header.write_text('#define EXR_VERSION "3.41.0"\n')
    reject('installed_header_wrong_version', lambda: installed_files(installed))
    header.write_text('#define EXR_VERSION "3.42.0"\n'); (installed / 'sdk/lib/libexreader.dylib').unlink()
    reject('installed_required_library_missing', lambda: installed_files(installed))
    product = {'source_sha': OLD_SHA, 'target': 'iphonesimulator', 'sdk_version': '3.42.0',
        'installed_modules': MODULES, 'exact_candidate_family': FAMILY, 'sqlite_provider': 'libreader_catalog_sqlite.a',
        'system_sqlite_fallback': False, 'reading_resolver_linked': False, 'webdav_transport': 'Foundation URLSession',
        'wave3_enabled': True, 'organization_enabled': True, 'selector_bytes_candidate': True,
        'sdk_prefix': str(SDK_ROOT / 'sdk'), 'product_prefix': str(SDK_ROOT / 'products')}
    identity = {'source_sha': OLD_SHA, 'run_id': str(OLD_RUN), 'attempt': '1', 'target': 'iphonesimulator',
        'sdk_content_candidate': CANDIDATE, 'sdk_content_paths': ['src', 'include', 'cmake', 'CMakeLists.txt', 'bindings'],
        'page_theme_enabled': True, 'product': product}
    installed_schema(identity, product); result['installed_schema_positive'] = True
    for field, wrong in [('source_sha', '0' * 40), ('sdk_version', '3.41.0'), ('wave3_enabled', 1),
                          ('installed_modules', []), ('system_sqlite_fallback', True), ('sdk_prefix', '/tmp')]:
        altered = dict(product, **{field: wrong})
        reject('installed_' + field, lambda altered=altered: installed_schema(dict(identity, product=altered), altered))
    calls = []
    def arm(name): calls.append(name); return {'profile': name, 'reaped': True, 'owned_descendants_closed': True, 'exit_code': 70 if name == 'control' else 0}
    pair(arm, lambda: True, lambda: 300)
    require(calls == ['control', 'phase'], 'first70 suppressed second'); result['first70_then_second'] = True
    checks = iter([True, True, True, True, False]); calls.clear()
    reject('final_fifth_input_check_false', lambda: completed_pair(arm, lambda: next(checks), lambda: 300))
    require(calls == ['control', 'phase'], 'final-false control did not run both arms')
    reject('unreaped_arm', lambda: pair(lambda n: {'profile': n, 'reaped': False, 'exit_code': 70}, lambda: True, lambda: 300))
    reject('mutated_input', lambda: pair(arm, lambda: False, lambda: 300))
    reject('insufficient_pair_budget', lambda: pair(arm, lambda: True, lambda: 269))
    reject('wrong_arm_order', lambda: pair(lambda n: {'profile': 'phase', 'reaped': True, 'owned_descendants_closed': True, 'exit_code': 0}, lambda: True, lambda: 300))
    reject('unclosed_descendants', lambda: pair(lambda n: {'profile': n, 'reaped': True, 'owned_descendants_closed': False, 'exit_code': 70}, lambda: True, lambda: 300))
    output, complete = shaped({'x': '\x00é😀' * 100000}, 16384)
    require(len(output) <= 16384 and not complete, 'escaped output bound'); result['encoded_output_bound'] = True
    output, complete = shaped({str(n): {str(m): ['x' * 1000] * 24 for m in range(24)} for n in range(24)}, 16384)
    require(len(output) <= 16384 and not complete, 'minimal output fallback'); result['minimal_output_fallback'] = True
    finalization_controls(result)
    log_controls(result, reject)
    pinned_artifact_controls(result, reject)
    save(E / 'controls.json', result); emit({'controls': result})


def worker():
    E.mkdir(parents=True, exist_ok=True); PRIVATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    summary = dict(IDENTITY, comparison_complete=False, interpretation='incomplete', outcomes=[], problems=[],
        native_cases_run=0, product_accepted=False, formal_credit=0, root_cause_proved=False,
        historical_upload_receipt_used=False, historical_upload_receipt_verified=False,
        fresh_artifact_metadata_verified=False, downloaded_archive_verified=False, fresh_upload_log_replayed=False,
        sdk_rebuilt=False, ui_run=False, source_profile_factor='baseline versus PhaseB',
        order_caveat='single ordered pair; shared daemon state is not controlled')
    uid = None; unsafe = False
    try:
        controls(); source_guard(); archive, sdk_before = retained_sdk(summary)
        fixture_before, generated_before = generate(); uid = runtime_create()
        def unchanged():
            archive_hash(archive)
            return inventory(SDK_ROOT) == sdk_before and inventory(RESOURCES) == fixture_before and all(
                inventory(root / 'generated') == generated_before[name] for name, root in (('control', CONTROL), ('phase', PHASE)))
        rows = completed_pair(lambda name: observe_build(name, uid), unchanged, lambda: DEADLINE - time.monotonic())
        summary.update(outcomes=rows, interpretation=interpretation(rows), comparison_complete=True,
                       shared_inputs_revalidated=True, sdk_original_source=OLD_SHA,
                       reached_shared_description_boundary=all(r['description_stage'] and r['description_signatures'] for r in rows),
                       comparison_complete_scope='two authenticated observed build outcomes, not cause or acceptance')
    except StopGroup as error:
        unsafe = True; summary['problems'].append(str(error))
    except BaseException as error:
        summary['problems'].append(type(error).__name__ + ': ' + str(error)[:1800])
        unsafe = ACTIVE is not None and ACTIVE.poll() is None
    finally:
        if uid is not None and not unsafe:
            try: command(['xcrun', 'simctl', 'delete', uid], 'delete-owned-device', timeout=10, cap=8192)
            except BaseException as error:
                summary['problems'].append('owned-device cleanup: ' + str(error)[:600]); summary['comparison_complete'] = False
                unsafe = ACTIVE is not None and ACTIVE.poll() is None
        if summary['problems']: summary['comparison_complete'] = False
        summary['unsafe_live_child'] = unsafe
        try:
            save(E / 'summary.json', summary)
            emit({'worker_outcome': summary})
            if not unsafe:
                seal_evidence(E)
                retain_partial(E, PRIVATE / 'partial-refusal')
                save(PRIVATE / 'worker-ready.json', {'sealed': True, 'comparison_complete': summary['comparison_complete'],
                    'problems': summary['problems'], 'evidence_path': str(E.relative_to(ROOT)), 'identity': IDENTITY})
        except BaseException as error:
            summary['comparison_complete'] = False
            emit({'worker_finalization_failure': type(error).__name__ + ': ' + str(error)[:1000]})
    if unsafe: return 2  # Supervisor sees/reaps the remaining owned group now.
    return 0 if summary['comparison_complete'] else 1


# Darwin ABI: apple-oss-distributions/xnu @ f6217f891ac0bb64f3d375211650a4c1ff8ca1ea
# bsd/sys/signal.h (__siginfo), bsd/sys/wait.h (P_PID/WEXITED/WNOHANG/WNOWAIT),
# bsd/sys/proc_info.h (PROC_PGRP_ONLY), libsyscall/wrappers/libproc/libproc.h.
# CPython exposed os.waitid on macOS only in3.13; use the existing OS ABI,
# not a Python/toolchain upgrade. No process names, argv or other groups read.
class DarwinSigval(ctypes.Union):
    _fields_ = [('integer', ctypes.c_int), ('pointer', ctypes.c_void_p)]


class DarwinSiginfo(ctypes.Structure):
    _fields_ = [('signo', ctypes.c_int), ('error', ctypes.c_int), ('code', ctypes.c_int),
        ('pid', ctypes.c_int), ('uid', ctypes.c_uint), ('status', ctypes.c_int),
        ('address', ctypes.c_void_p), ('value', DarwinSigval), ('band', ctypes.c_long),
        ('padding', ctypes.c_ulong * 7)]


DARWIN = None
def darwin():
    global DARWIN
    if DARWIN is None:
        require(sys.platform == 'darwin' and ctypes.sizeof(ctypes.c_void_p) == 8 and
                ctypes.sizeof(DarwinSiginfo) == 104 and ctypes.alignment(DarwinSiginfo) == 8 and
                [getattr(DarwinSiginfo, k).offset for k in ('pid', 'status', 'address', 'value', 'padding')]
                == [12, 20, 24, 32, 48], 'Darwin64 waitid ABI')
        libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
        libc.waitid.argtypes = [ctypes.c_int, ctypes.c_uint, ctypes.POINTER(DarwinSiginfo), ctypes.c_int]
        libc.waitid.restype = ctypes.c_int
        proc = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        proc.proc_listpids.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_int]
        proc.proc_listpids.restype = ctypes.c_int
        DARWIN = (libc, proc)
    return DARWIN


def exited_unreaped(pid):
    require(pid in PINNED_GROUPS, 'waitid requires retained child ownership')
    info = DarwinSiginfo(); status = darwin()[0].waitid(1, pid, ctypes.byref(info), 0x04 | 0x01 | 0x20)
    if status != 0: raise OSError(ctypes.get_errno(), 'owned-child waitid')
    require(info.pid in (0, pid), 'waitid child identity')
    if info.pid:
        require(info.signo == signal.SIGCHLD and info.code in (1, 2, 3), 'waitid exit status domain')
        return True
    return False


def group_members(pgid):
    require(pgid in PINNED_GROUPS or pgid == os.getpgrp(), 'numeric owned-group query scope')
    values = (ctypes.c_int * 1024)()
    ctypes.set_errno(0)
    size = darwin()[1].proc_listpids(2, pgid, values, ctypes.sizeof(values))
    require(ctypes.get_errno() == 0 and 0 <= size < ctypes.sizeof(values) and size % ctypes.sizeof(ctypes.c_int) == 0,
            'owned-group query failure/ceiling')
    result = list(values[:size // 4])
    require(all(0 < pid < 2 ** 31 for pid in result) and len(set(result)) == len(result), 'owned-group PID domain')
    return set(result)


def signal_owned(pid, sig, signals):
    require(pid in PINNED_GROUPS, 'signal after final reap refused')
    try: os.killpg(pid, sig)
    except ProcessLookupError: pass
    signals.append(int(sig))


def hard_deadline(seconds):
    # Native default action is not delayed until Python regains control from C.
    # Earlier supervised cleanup remains separate; native termination promises
    # only the durable emergency receipt, never successful stdout/closure.
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL, max(.001, seconds))


def supervise(argv, deadline, grace=5, control=False):
    started = time.monotonic()
    process = subprocess.Popen(argv, cwd=ROOT, start_new_session=True,
        stdout=subprocess.DEVNULL if control else None, stderr=subprocess.DEVNULL if control else None)
    PINNED_GROUPS.add(process.pid)
    OWNED_PROCESSES[process.pid] = process  # Prevent Popen.__del__ from reaping an unconfirmed leader.
    result = {'pid': process.pid, 'pgid': process.pid, 'started': started, 'deadline': deadline,
              'forced': False, 'reaped': False, 'group_closed': False, 'signals_before_reap': []}
    while time.monotonic() < deadline - grace:
        if exited_unreaped(process.pid): break
        time.sleep(.05)
    dead = exited_unreaped(process.pid); others = group_members(process.pid) - {process.pid}
    if not dead or others:
        result['forced'] = True
        signal_owned(process.pid, signal.SIGTERM, result['signals_before_reap'])
        end = min(deadline, time.monotonic() + .5)
        while time.monotonic() < end:
            if exited_unreaped(process.pid) and not group_members(process.pid) - {process.pid}: break
            time.sleep(.02)
        if not exited_unreaped(process.pid) or group_members(process.pid) - {process.pid}:
            signal_owned(process.pid, signal.SIGKILL, result['signals_before_reap'])
    while time.monotonic() < deadline:
        if exited_unreaped(process.pid) and not group_members(process.pid) - {process.pid}:
            # Pin is removed immediately before the one final reap. No probes or
            # signals for this numeric ID occur after this ownership boundary.
            PINNED_GROUPS.remove(process.pid)
            code = process.wait()
            del OWNED_PROCESSES[process.pid]
            result.update(exit_code=code, reaped=True, group_closed=True)
            break
        time.sleep(.02)
    if not result['reaped']:
        signal_owned(process.pid, signal.SIGKILL, result['signals_before_reap'])
        result['problem'] = 'group closure unconfirmed; leader remains pinned until hard parent cutoff'
    result['finished'] = time.monotonic()
    return result


def may_select(lifecycle):
    return lifecycle.get('reaped') is True and lifecycle.get('group_closed') is True and lifecycle.get('forced') is False


def supervisor_controls():
    require(os.getpid() in group_members(os.getpgrp()), 'actual own-group positive control')
    natural = supervise([sys.executable, '-B', str(SELF), '--control-exit'], time.monotonic() + 3, 1, True)
    stalled = supervise([sys.executable, '-B', str(SELF), '--control-stall'], time.monotonic() + 2, 1, True)
    held = supervise([sys.executable, '-B', str(SELF), '--control-child-held'], time.monotonic() + 3, 2, True)
    timer = supervise([sys.executable, '-B', str(SELF), '--control-parent-stall'], time.monotonic() + 3, 1, True)
    require(may_select(natural) and not may_select(stalled) and stalled['forced'] is True
            and stalled['reaped'] is True and stalled['group_closed'] is True, 'real supervisor controls')
    require(natural['signals_before_reap'] == [] and held['forced'] is True and held['group_closed'] is True
            and held['reaped'] is True and timer['exit_code'] == -signal.SIGALRM and may_select(timer), 'actual child-group/parent timer controls')
    try: signal_owned(natural['pid'], 0, [])
    except ValueError: pass
    else: raise ValueError('stale reaped group signal admitted')
    require(not may_select(dict(natural, group_closed=False)), 'unconfirmed group admitted')
    return {'natural': natural, 'real_stalled_worker': stalled, 'child_held_group': held,
            'actual_parent_hard_timer': timer, 'stale_reaped_signal_refused': True, 'unconfirmed_group_refused': True}


def terminal_data(value):
    data = encoded(value)
    # 15KiB ordinary final +1KiB emergency hard-timer record share16KiB.
    if len(data) <= 15 * 1024: return data
    value['comparison_complete'] = False
    digest = hashlib.sha256(data).hexdigest()
    compact = {'identity': IDENTITY, 'comparison_complete': False, 'problem': 'terminal details exceeded reservation',
               'details_sha256': digest, 'native_cases_run': 0, 'formal_credit': 0}
    result = encoded(compact); require(len(result) <= 15 * 1024, 'finite terminal fallback')
    return result


def downgrade(root, result):
    summary = strict_json(read_bounded(root / 'summary.json', 65536))
    summary.update(comparison_complete=False, supervisor_final_failure=result['problems'])
    # The group is already closed. Only this known receipt changes now; do not
    # repeat bulk source hashing/inventory in the small outer supervisor.
    old = strict_json(read_bounded(root / 'inventory.json', 4 * 1024 ** 2), 4 * 1024 ** 2)
    require(old.get('excludes_self') == 'inventory.json' and 'summary.json' in old['files'], 'sealed inventory shape')
    data = encoded(summary); previous = old['files']['summary.json']['bytes']
    old['files']['summary.json'] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    old['bytes'] += len(data) - previous
    inventory_bytes = encoded(old)
    require(old['entries'] + 1 <= 2000 and old['bytes'] + len(inventory_bytes) <= 64 * 1024 ** 2, 'final updated evidence ceiling')
    save(root / 'summary.json', summary); save(root / 'inventory.json', old)


def final_receipt(path, value):
    require(len(encoded(value)) <= 65536, 'final receipt encoded ceiling')
    save(path, value)


def final_bound(root): return inventory(root, 64 * 1024 ** 2, 2000, False)


def finalize(result, selected, refusal, publish, sink, down=downgrade, receipt=final_receipt, bound=final_bound, emergency=EMERGENCY):
    """One <=15KiB terminal emission, leaving1KiB for the hard-timer failure."""
    def failure(stage, error):
        result['comparison_complete'] = False
        result['output_sealed'] = False
        result['problems'].append(stage + ': ' + type(error).__name__ + ': ' + str(error)[:600])
    def attempt_downgrade():
        if selected != refusal:
            try: down(selected, result)
            except BaseException as error: failure('retained receipt downgrade', error)
    result['output_sealed'] = False
    data = terminal_data(result); errors_before = len(result['problems'])
    if not result['comparison_complete']: attempt_downgrade()
    try:
        require(len(result['problems']) == errors_before, 'downgrade failed; only emergency upload eligible')
        if selected == refusal or not result['comparison_complete']:
            receipt(refusal / 'refusal.json', result); candidate = refusal
        else: candidate = selected
        bound(candidate)  # After the last retained receipt, before path publication.
        result['output_sealed'] = True
        publish(candidate)
    except BaseException as error:
        failure('output finalization', error); attempt_downgrade()
        try: receipt(emergency / 'path-failure.json', result)
        except BaseException as refused: failure('refusal receipt', refused)
        # A failed driver selects only fixed tiny emergency, even if a path was
        # partially published. It never selects E or an unsealed refusal tree.
    data = terminal_data(result)
    try:
        sink(data)
    except BaseException as error:
        failure('terminal output', error); attempt_downgrade()
        try: receipt(emergency / 'terminal-failure.json', result)
        except BaseException: pass
        raise
    return result['comparison_complete']


def finalization_controls(result):
    def fixture(name):
        root = PRIVATE / ('final-' + name); refusal = PRIVATE / ('refuse-' + name)
        root.mkdir(); refusal.mkdir(); save(root / 'summary.json', {'comparison_complete': True}); seal_evidence(root)
        return root, refusal, {'comparison_complete': True, 'problems': []}
    root, refusal, value = fixture('path')
    output = []
    def fail_path(path): raise OSError('synthetic late path failure')
    require(not finalize(value, root, refusal, fail_path, output.append, emergency=refusal / 'emergency'), 'path failure complete')
    require(strict_json(read_bounded(root / 'summary.json', 65536))['comparison_complete'] is False
            and len(output) == 1 and len(output[0]) <= 16384, 'path failure false receipt/output')
    result['actual_late_path_failure_false'] = True
    root, refusal, value = fixture('sink')
    def fail_sink(data): raise OSError('synthetic sink failure')
    try: finalize(value, root, refusal, lambda p: None, fail_sink, emergency=refusal / 'emergency')
    except OSError: pass
    else: raise ValueError('sink failure not propagated')
    require(strict_json(read_bounded(root / 'summary.json', 65536))['comparison_complete'] is False, 'sink stale success')
    result['actual_sink_failure_false'] = True
    root, refusal, value = fixture('shape'); value['large'] = '\x00é😀' * 20000; output = []
    require(not finalize(value, root, refusal, lambda p: None, output.append, emergency=refusal / 'emergency'), 'formatter fallback complete')
    require(strict_json(read_bounded(root / 'summary.json', 65536))['comparison_complete'] is False
            and strict_json(output[0])['comparison_complete'] is False and len(output[0]) <= 16384, 'formatter stale result')
    result['actual_terminal_fallback_false'] = True
    root, refusal, value = fixture('double-failure'); value['comparison_complete'] = False; output = []
    def fail_receipt(*args): raise OSError('synthetic receipt/fsync failure')
    require(not finalize(value, root, refusal, fail_path, output.append, fail_receipt, fail_receipt,
                         emergency=refusal / 'emergency'), 'double failure complete')
    require(len(output) == 1 and strict_json(output[0])['comparison_complete'] is False
            and any('downgrade' in p for p in strict_json(output[0])['problems']), 'failed receipts hid terminal reason')
    result['actual_downgrade_and_receipt_failure_visible'] = True
    root, refusal, value = fixture('bound'); output = []
    def fail_bound(path): raise ValueError('synthetic final entry ceiling')
    require(not finalize(value, root, refusal, lambda p: None, output.append, bound=fail_bound, emergency=refusal / 'emergency')
            and value['output_sealed'] is False and strict_json(output[0])['comparison_complete'] is False,
            'final inventory failure upload admitted')
    result['actual_final_inventory_failure_refused'] = True


def main():
    global DEADLINE
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin', 'macOS Actions only')
    if len(sys.argv) == 2 and sys.argv[1] == '--control-exit': return 0
    if len(sys.argv) == 2 and sys.argv[1] == '--control-stall': time.sleep(60); return 0
    if len(sys.argv) == 2 and sys.argv[1] == '--control-child-held':
        subprocess.Popen([sys.executable, '-B', str(SELF), '--control-stall'])
        os._exit(0)
    if len(sys.argv) == 2 and sys.argv[1] == '--control-parent-stall':
        hard_deadline(.3); time.sleep(60); return 1
    if len(sys.argv) == 2 and sys.argv[1] == '--worker':
        hard_deadline(DEADLINE - time.monotonic()); return worker()
    require(len(sys.argv) == 1, 'explicit supported mode')
    started = time.monotonic(); deadline = started + 540
    hard_deadline(540)
    DEADLINE = deadline
    EMERGENCY.mkdir(parents=True, exist_ok=True)
    final_receipt(EMERGENCY / 'bootstrap.json', dict(IDENTITY, comparison_complete=False, output_sealed=False,
        native_cases_run=0, formal_credit=0, hard_parent_seconds=540,
        problem='No final sealed driver receipt: native hard termination/runner/sink failure remains possible; cause unresolved'))
    REFUSAL.mkdir(parents=True, exist_ok=True)
    save(REFUSAL / 'bootstrap.json', dict(IDENTITY, comparison_complete=False, native_cases_run=0, formal_credit=0))
    result = dict(IDENTITY, comparison_complete=False, problems=[], native_cases_run=0,
                  formal_credit=0, product_accepted=False, sdk_rebuilt=False, ui_run=False)
    selected = REFUSAL
    try:
        result['supervisor_controls'] = supervisor_controls()
        # Ten seconds of the same540 budget remain for finite outer receipts;
        # the worker itself has five earlier seconds to seal/exit normally.
        os.environ['EXR_BUILD_PAIR_DEADLINE'] = str(deadline - 20)
        lifecycle = supervise([sys.executable, '-B', str(SELF), '--worker'], deadline - 10)
        result['lifecycle'] = lifecycle
        require(may_select(lifecycle), 'worker/group closure incomplete or forced; live evidence refused')
        ready_path = PRIVATE / 'worker-ready.json'
        require(ready_path.is_file() and not ready_path.is_symlink() and ready_path.stat().st_size <= 16384, 'worker final seal absent')
        ready = strict_json(read_bounded(ready_path, 16384), 16384)
        require(ready['sealed'] is True and ready['identity'] == IDENTITY and ready['evidence_path'] == str(E.relative_to(ROOT)), 'worker seal identity')
        # The partial tree stayed private while any worker/group could write it.
        # Only confirmed closure permits this constant-time publication.
        os.replace(PRIVATE / 'partial-refusal/partial', REFUSAL / 'partial')
        final_receipt(REFUSAL / 'closure.json', {'lifecycle': lifecycle, 'identity': IDENTITY, 'comparison_complete': False})
        selected = E; result['comparison_complete'] = ready['comparison_complete'] is True
        result['problems'] = ready['problems']
    except BaseException as error:
        result['problems'].append(type(error).__name__ + ': ' + str(error)[:1200])
        # Unknown cleanup can never expose E/private partial data. IDs remain
        # pinned here, so the last bounded stop cannot target a recycled group.
        for pid in tuple(PINNED_GROUPS): signal_owned(pid, signal.SIGKILL, [])
    # Only closed evidence reaches this helper. A partially published path must
    # never point at a still-true summary after a handled finalization failure.
    def publish(path):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write('evidence_path=' + str(path.relative_to(ROOT)) + '\ncomparison_complete=' +
                         str(result['comparison_complete']).lower() + '\n'); stream.flush()
    def sink(data): sys.stdout.buffer.write(data); sys.stdout.buffer.flush()
    finalize(result, selected, REFUSAL, publish, sink)
    # Transport/closure success is distinct from the diagnostic result. The next
    # workflow status step still fails every incomplete comparison.
    return 0 if result.get('output_sealed') is True else 1


if __name__ == '__main__':
    sys.exit(main())
