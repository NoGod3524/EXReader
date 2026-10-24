# SPDX-License-Identifier: MIT
"""Job-local real WebDAV service interoperability of the installed sync modules.

One pinned service per invocation. The service, its TLS identity, the test
account, every original, every transfer and every verification exist only
inside the GitHub Actions job. Nothing here reimplements the client or the
sync protocol: the installed consumer drives the modules, and an independent
Python HTTPS client plus the server's own access log check the results.
"""
import argparse
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import sqlite3
import ssl
import subprocess
import sys
import time
import traceback
from urllib.parse import quote, unquote
import uuid
import xml.etree.ElementTree as ET

START = '210403d121d6484a8fff4ea7ffd911efa3163535'
HARNESS_UA = 'exreader-interop-independent/1'
USER = 'interop'
MISMATCH = 'mismatch.interop.test'
PROPFIND = (b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:displayname/><d:resourcetype/>'
            b'<d:getcontentlength/><d:getetag/></d:prop></d:propfind>')
SERVICES = {
    'apache': {
        'title': 'Apache httpd mod_dav + mod_dav_fs',
        'image': 'httpd:2.4.68@sha256:03f858efb82c25cb0f9962946615cdcdaf26927cb971722149b563197cfd0fdd',
        'host': 'apache.interop.test', 'port': 8443, 'untrusted_port': 9443, 'base': '/dav/',
    },
    'nextcloud': {
        'title': 'Nextcloud server (SabreDAV) behind its image Apache',
        'image': 'nextcloud:33.0.10-apache@sha256:e02fb1a7558bae683188eb94471cdb1b4550970f905e615c8e9d10c4760f13a1',
        'host': 'nextcloud.interop.test', 'port': 18443, 'untrusted_port': 19443,
        'base': '/remote.php/dav/files/' + USER + '/',
    },
}
# Status codes of the installed public headers; asserted, never remapped.
DAV = {'ok': 0, 'argument': 1, 'io': 3, 'tls': 4, 'http': 5, 'limit': 8, 'exists': 11}
SYNC = {'ok': 0, 'dav': 3, 'hash': 5, 'cancelled': 6, 'limit': 7}
# A group stops at its first failure (later state would be meaningless); every
# other group still runs, so one real failure never hides the remaining evidence.
GROUPS = [
    ('tls-identity', ['tls_service_presents_generated_identity_and_verifies_through_system_trust']),
    ('tls-untrusted', ['untrusted_certificate_is_refused_before_any_http_request']),
    ('tls-hostname', ['hostname_mismatch_is_refused_before_any_http_request']),
    ('discovery', ['propfind_depth_one_discovers_direct_children_only',
                   'utf8_and_space_names_list_as_normalized_encoded_resources',
                   'lowered_entry_and_listing_byte_ceilings_reject_instead_of_truncating']),
    ('percent-child', ['literal_percent_child_lists_and_downloads_without_double_decoding']),
    ('percent-root', ['literal_percent_root_is_supported_and_second_encoding_is_refused']),
    ('mkcol', ['mkcol_creates_accepts_existing_405_and_reports_missing_parent_409']),
    ('put', ['conditional_put_creates_once_then_412_without_changing_bytes',
             'preexisting_foreign_content_is_never_overwritten',
             'download_over_lowered_byte_ceiling_is_refused_without_publication']),
    ('exchange', ['offline_local_history_and_outbox_exist_before_any_network',
                  'device_a_publishes_original_before_revision_and_acks_after_get',
                  'device_b_uploads_its_original_and_discovers_device_a_bytes',
                  'device_a_discovers_device_b_original_and_exact_revision',
                  'server_objects_match_independent_length_hash_and_wire_bytes',
                  'existing_remote_objects_return_412_and_are_get_verified_before_ack',
                  'damaged_existing_remote_original_is_refused_then_recovers_after_repair',
                  'utf8_space_root_two_device_exchange_keeps_exact_bytes']),
    ('heads', ['concurrent_heads_are_preserved_on_both_devices',
               'delete_tombstone_is_retained_remotely_and_in_both_histories']),
    ('limit-2000', ['shard_with_2000_entries_is_listed_and_paged_by_cursor']),
    ('limit-2001', ['shard_over_2000_entries_is_rejected_whole']),
    ('limit-payload', ['listed_revision_over_1_mib_is_rejected_before_download']),
    ('cancel', ['pre_cancel_sends_nothing_and_retains_outbox',
                'mid_upload_cancel_never_acknowledges_a_partial_object']),
    ('offline', ['stopped_service_fails_as_io_and_retains_outbox',
                 'restarted_service_accepts_one_retry_without_duplicate']),
    ('rerun', ['rerun_is_read_only_and_leaves_history_outbox_and_server_unchanged',
               'reapplying_identical_local_wire_does_not_requeue']),
    ('hygiene', ['all_module_writes_are_conditional_and_every_listing_is_depth_one']),
]
DEPENDS = {'heads': 'exchange', 'rerun': 'heads'}
FINAL_CHECK = 'credentials_absent_from_logs_payloads_databases_and_artifacts'
EXPECTED = [name for _, names in GROUPS for name in names] + [FINAL_CHECK]


class Refused(Exception):
    pass


def require(value, message):
    if not value:
        raise Refused(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def raw(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


def rid(shard, number):
    return '%02x%030x' % (shard, number)


def tag(shard, number, key, name='书架', parents=(), operation='put'):
    return {'version': 1, 'id': rid(shard, number), 'entity_kind': 'tag', 'entity_key': key,
            'operation': operation, 'location_kind': 'none', 'parents': list(parents),
            'payload': None if operation == 'delete' else {'name': name}}


def book(shard, number, data, title):
    digest = sha(data)
    return {'version': 1, 'id': rid(shard, number), 'entity_kind': 'book', 'entity_key': 'txt:' + digest,
            'operation': 'put', 'location_kind': 'none', 'parents': [],
            'payload': {'format': 'txt', 'source_sha256': digest, 'source_bytes': len(data),
                        'title': title, 'author': 'EXReader interop', 'favorite': False}}


def object_rel(data):
    digest = sha(data)
    return 'exreader-sync-v1/objects/' + digest[:2] + '/' + digest + '.txt'


def revision_rel(value):
    return 'exreader-sync-v1/revisions/' + value['id'][:2] + '/' + value['id'] + '-' + sha(raw(value)) + '.json'


def original(seed, size):
    # Generated per run inside the job: text plus non-UTF-8 bytes, never a fixture.
    head = ('EXReader interop original ' + seed + ' 书 \n').encode()
    body = hashlib.shake_256((seed + os.environ.get('GITHUB_RUN_ID', '')).encode()).digest(size)
    return (head + body)[:size]


def run(command, *, input=None, check=True, timeout=600):
    stdin = {'input': input} if input is not None else {'stdin': subprocess.DEVNULL}
    return subprocess.run(command, capture_output=True, check=check, timeout=timeout, **stdin)


class AccessLog:
    """The server's own per-request record. Module lines carry no harness UA."""

    def __init__(self, path):
        self.path = path

    def size(self):
        return self.path.stat().st_size if self.path.exists() else 0

    def settle(self):
        time.sleep(0.3)
        last, deadline = -1, time.time() + 8
        while time.time() < deadline:
            current = self.size()
            if current == last:
                return
            last = current
            time.sleep(0.4)

    def mark(self):
        self.settle()
        return self.size()

    def lines(self, mark=0):
        self.settle()
        if not self.path.exists():
            return []
        with self.path.open('rb') as stream:
            stream.seek(mark)
            data = stream.read()
        out = []
        for line in data.decode('utf-8', 'replace').splitlines():
            parts = line.split('\t')
            if len(parts) != 8:
                out.append({'raw': line, 'malformed': True, 'method': '', 'target': '', 'status': '',
                            'agent': '', 'depth': '', 'if_none_match': ''})
                continue
            when, port, status, depth, condition, agent, size, request = parts
            words = request.split(' ')
            out.append({'time': when, 'port': port, 'status': int(status) if status.isdigit() else status,
                        'depth': depth, 'if_none_match': condition, 'agent': agent, 'bytes': size,
                        'method': words[0], 'target': words[1] if len(words) > 1 else '', 'raw': line})
        return out

    def module(self, mark=0):
        return [line for line in self.lines(mark) if line.get('agent') != HARNESS_UA]


def find(lines, method, target, statuses=None):
    return [n for n, line in enumerate(lines) if line.get('method') == method and line.get('target') == target and
            (statuses is None or line.get('status') in statuses)]


class Independent:
    """Python stdlib HTTPS with CA and hostname verification; separate from the module."""

    def __init__(self, host, port, ca, authorization):
        self.host, self.port, self.authorization = host, port, authorization
        self.context = ssl.create_default_context(cafile=str(ca))

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPSConnection(self.host, self.port, context=self.context, timeout=120)
        try:
            values = {'Authorization': self.authorization, 'User-Agent': HARNESS_UA}
            values.update(headers or {})
            connection.request(method, path, body=body, headers=values)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def mkcol(self, path):
        status, _ = self.request('MKCOL', path)
        require(status == 201, 'independent MKCOL %s returned %s' % (path, status))

    def put(self, path, data):
        status, _ = self.request('PUT', path, data, {'Content-Type': 'application/octet-stream'})
        require(status in (201, 204), 'independent PUT %s returned %s' % (path, status))

    def get(self, path):
        return self.request('GET', path)

    def propfind(self, path):
        return self.request('PROPFIND', path, PROPFIND, {'Depth': '1', 'Content-Type': 'application/xml; charset=utf-8'})

    def children(self, path):
        status, data = self.propfind(path)
        if status == 404:
            return {}, data
        require(status == 207, 'independent PROPFIND %s returned %s' % (path, status))
        out = {}
        for response in ET.fromstring(data).findall('{DAV:}response'):
            href = response.findtext('{DAV:}href').strip()
            target = href.split('://', 1)[-1]
            target = target[target.find('/'):] if '://' in href else target
            if unquote(target).rstrip('/') == unquote(path).rstrip('/'):
                continue
            folder = response.find('.//{DAV:}resourcetype/{DAV:}collection') is not None
            length = None
            for propstat in response.findall('{DAV:}propstat'):
                if ' 200 ' in (propstat.findtext('{DAV:}status') or '') + ' ':
                    text = propstat.findtext('{DAV:}prop/{DAV:}getcontentlength')
                    if text is not None and text.strip():
                        length = int(text)
            out[unquote(target.rstrip('/').rsplit('/', 1)[-1])] = {'collection': folder, 'bytes': length, 'href': href}
        return out, data

    def tree(self, path):
        nodes, pending = {}, [path]
        while pending:
            current = pending.pop()
            listed, _ = self.children(current)
            for name, node in listed.items():
                child = current + quote(name, safe='') + ('/' if node['collection'] else '')
                nodes[child] = node['bytes']
                if node['collection']:
                    pending.append(child)
        return nodes


class Service:
    def __init__(self, name, work, evidence, ca, secret):
        self.name, self.work, self.evidence, self.secret = name, work, evidence, secret
        self.spec = SERVICES[name]
        self.host, self.port, self.base = self.spec['host'], self.spec['port'], self.spec['base']
        self.untrusted_port = self.spec['untrusted_port']
        self.container = 'exreader-interop-' + name
        self.tls = work / 'tls'
        self.ca = ca

    def docker(self, *args, input=None, check=True, timeout=600):
        return run(['docker', *args], input=input, check=check, timeout=timeout)

    def wait_https(self, client, seconds):
        deadline, last = time.time() + seconds, None
        while time.time() < deadline:
            try:
                status, _ = client.propfind(self.base)
                if status == 207:
                    return
                last = status
            except (OSError, http.client.HTTPException) as error:
                last = type(error).__name__
            time.sleep(2)
        raise Refused('service did not become ready over verified HTTPS: %s' % last)

    def pull(self):
        self.docker('pull', self.spec['image'], timeout=1800)

    def stop(self):
        self.docker('stop', '-t', '20', self.container)

    def start_again(self, client):
        self.docker('start', self.container)
        self.wait_https(client, 600)

    def image_identity(self):
        image = self.spec['image']
        digests = json.loads(self.docker('image', 'inspect', image, '--format', '{{json .RepoDigests}}').stdout)
        image_id = self.docker('image', 'inspect', image, '--format', '{{.Id}}').stdout.decode().strip()
        running = self.docker('inspect', self.container, '--format', '{{.Image}}').stdout.decode().strip()
        pinned = image.split('@', 1)[1]
        require(any(d.endswith('@' + pinned) for d in digests) and running == image_id,
                'running container image differs from the pinned digest')
        return {'reference': image, 'pinned_index_digest': pinned, 'repo_digests': digests, 'image_id': image_id,
                'container_image_id': running,
                'docker_server': self.docker('version', '--format', '{{.Server.Version}}').stdout.decode().strip()}

    def collect_common(self):
        logs = self.evidence / 'http'
        logs.mkdir(parents=True, exist_ok=True)
        result = self.docker('logs', self.container, check=False)
        (logs / 'container-stdout.log').write_bytes(result.stdout)
        (logs / 'container-stderr.log').write_bytes(result.stderr)
        if self.log.path.exists():
            shutil.copyfile(self.log.path, logs / 'access.log')

    def remove(self):
        self.docker('rm', '-f', '-v', self.container, check=False)


class Apache(Service):
    def start(self, client):
        root = self.work / 'apache'
        for folder in ('dav', 'lock', 'logs', 'config'):
            (root / folder).mkdir(parents=True, exist_ok=True)
            os.chmod(root / folder, 0o777)
        hashed = run(['openssl', 'passwd', '-apr1', '-stdin'], input=self.secret.encode()).stdout.decode().strip()
        (root / 'config' / 'htpasswd').write_text(USER + ':' + hashed + '\n', encoding='ascii')
        os.chmod(root / 'config' / 'htpasswd', 0o644)
        conf = Path(__file__).resolve().parent / 'services' / 'apache' / 'httpd.conf'
        self.log = AccessLog(root / 'logs' / 'access.log')
        self.docker('run', '-d', '--name', self.container, '--label', 'exreader-interop=1',
                    '-p', '127.0.0.1:%d:8443' % self.port, '-p', '127.0.0.1:%d:9443' % self.untrusted_port,
                    '-v', '%s:/usr/local/apache2/conf/httpd.conf:ro' % conf, '-v', '%s:/tls:ro' % self.tls,
                    '-v', '%s:/config:ro' % (root / 'config'), '-v', '%s:/srv/dav' % (root / 'dav'),
                    '-v', '%s:/srv/lock' % (root / 'lock'), '-v', '%s:/srv/logs' % (root / 'logs'), self.spec['image'])
        self.wait_https(client, 180)

    def versions(self):
        return {'httpd': self.docker('exec', self.container, 'httpd', '-v').stdout.decode().strip().splitlines(),
                'modules': [m.strip() for m in self.docker('exec', self.container, 'httpd', '-M').stdout.decode().splitlines()
                            if 'dav' in m or 'ssl' in m or 'auth' in m]}

    def place(self, root_name, relative, files):
        folder = self.work / 'apache' / 'dav' / root_name / relative
        folder.mkdir(parents=True, exist_ok=True)
        current = self.work / 'apache' / 'dav' / root_name
        for part in [''] + list(Path(relative).parts):
            current = current / part if part else current
            os.chmod(current, 0o777)
        for leaf, data in files.items():
            (folder / leaf).write_bytes(data)

    def collect(self):
        self.collect_common()
        error = self.work / 'apache' / 'logs' / 'error.log'
        if error.exists():
            shutil.copyfile(error, self.evidence / 'http' / 'error.log')
        return [self.work / 'apache' / 'dav']


class Nextcloud(Service):
    DATA = '/var/www/html/data/' + USER + '/files/'

    def occ(self, *args, input=None, check=True):
        return self.docker('exec', '-i', '-u', 'www-data', self.container, 'php', 'occ', *args, input=input, check=check)

    def start(self, client):
        root = self.work / 'nextcloud'
        (root / 'logs').mkdir(parents=True, exist_ok=True)
        private = self.work / 'private'
        private.mkdir(exist_ok=True)
        os.chmod(private, 0o700)
        env = private / 'nextcloud.env'
        env.write_text('NEXTCLOUD_ADMIN_USER=interop-admin\nNEXTCLOUD_ADMIN_PASSWORD=' + self.admin + '\n'
                       'SQLITE_DATABASE=nextcloud\nNEXTCLOUD_TRUSTED_DOMAINS=' + self.host + '\n', encoding='ascii')
        os.chmod(env, 0o600)
        conf = Path(__file__).resolve().parent / 'services' / 'nextcloud' / 'zz-interop-tls.conf'
        self.log = AccessLog(root / 'logs' / 'access.log')
        self.docker('run', '-d', '--name', self.container, '--label', 'exreader-interop=1', '--env-file', str(env),
                    '-p', '127.0.0.1:%d:8443' % self.port, '-p', '127.0.0.1:%d:9443' % self.untrusted_port,
                    '-v', '%s:/etc/apache2/conf-enabled/zz-interop-tls.conf:ro' % conf, '-v', '%s:/tls:ro' % self.tls,
                    '-v', '%s:/interop-logs' % (root / 'logs'), self.spec['image'])
        env.unlink()
        deadline, status = time.time() + 900, None
        while time.time() < deadline:
            result = self.occ('status', '--output=json', check=False)
            match = re.search(rb'\{.*\}', result.stdout)
            if result.returncode == 0 and match:
                status = json.loads(match.group(0))
                if status.get('installed') is True and status.get('maintenance') is False:
                    break
            time.sleep(5)
        require(status and status.get('installed') is True, 'Nextcloud did not finish installation')
        self.occ('config:system:set', 'skeletondirectory', '--value=')
        # The password reaches occ through stdin -> environment, never argv or
        # logs. The entrypoint may still hold the SQLite file briefly: retry.
        for attempt in range(6):
            added = self.docker('exec', '-i', '-u', 'www-data', self.container, 'sh', '-c',
                                'OC_PASS="$(cat)"; export OC_PASS; exec php occ user:add --password-from-env '
                                '--display-name="EXReader interop" ' + USER, input=self.secret.encode(), check=False)
            if added.returncode == 0 or self.occ('user:info', USER, check=False).returncode == 0:
                break
            time.sleep(10)
        require(self.occ('user:info', USER, check=False).returncode == 0, 'Nextcloud test account was not created')
        self.wait_https(client, 600)

    def versions(self):
        status = json.loads(re.search(rb'\{.*\}', self.occ('status', '--output=json').stdout).group(0))
        sabre = self.docker('exec', '-u', 'www-data', self.container, 'php', '-r',
                            'require "/var/www/html/3rdparty/autoload.php"; echo \\Sabre\\DAV\\Version::VERSION;',
                            check=False)
        return {'nextcloud': {k: status.get(k) for k in ('version', 'versionstring', 'productname', 'edition')},
                'sabre_dav': sabre.stdout.decode().strip() if sabre.returncode == 0 else None,
                'apache': self.docker('exec', self.container, 'apache2', '-v').stdout.decode().strip().splitlines(),
                'php': self.docker('exec', self.container, 'php', '-v').stdout.decode().strip().splitlines()[:1]}

    def place(self, root_name, relative, files):
        stage = self.work / 'stage' / uuid.uuid4().hex
        stage.mkdir(parents=True)
        for leaf, data in files.items():
            (stage / leaf).write_bytes(data)
        target = self.DATA + root_name + '/' + relative.strip('/')
        self.docker('exec', self.container, 'mkdir', '-p', target)
        self.docker('cp', str(stage) + '/.', self.container + ':' + target)
        self.docker('exec', self.container, 'chown', '-R', 'www-data:www-data', self.DATA + root_name)
        self.occ('files:scan', '--path=/' + USER + '/files/' + root_name)
        shutil.rmtree(stage)

    def collect(self):
        self.collect_common()
        self.docker('cp', self.container + ':/var/www/html/data/nextcloud.log', str(self.evidence / 'http' / 'nextcloud.log'),
                    check=False)
        files = self.work / 'nextcloud' / 'files-copy'
        self.docker('cp', self.container + ':' + self.DATA.rstrip('/'), str(files), check=False)
        return [files]


class Device:
    def __init__(self, harness, name):
        self.h, self.name = harness, name
        base = harness.evidence / 'devices' / name
        self.cache, self.originals = base / 'cache', base / 'originals'
        self.cache.mkdir(parents=True)
        self.originals.mkdir()
        self.db = base / 'catalog.sqlite'

    def keep(self, data):
        (self.originals / (sha(data) + '.txt')).write_bytes(data)

    def local(self, value, created=1):
        wire = self.h.evidence / 'wires' / (value['id'] + '-' + self.name + '.json')
        wire.parent.mkdir(exist_ok=True)
        wire.write_bytes(raw(value))
        result = self.h.consumer('local', self.db, wire)
        require(result['status'] == 0 and result['created'] == created, 'local revision differs: %s' % result)
        require(not created or result['sha256'] == sha(raw(value)), 'local revision SHA differs: %s' % result)
        return result

    def sync(self, root, shard, after='-', limit=100, cancel='-', expected=0):
        result = self.h.consumer('sync', root, self.db, self.cache, self.originals, shard, after or '-', limit, cancel)
        require(result['status'] == expected, 'sync %s shard %02x expected %s: %s' % (self.name, shard, expected, result))
        if expected == 0:
            require(result['shard_count'] == 256 and result['full_library_complete'] == 0, 'sync report contract differs')
        return result

    def query(self, sql, *args):
        connection = sqlite3.connect('file:' + str(self.db) + '?mode=ro', uri=True)
        try:
            return connection.execute(sql, args).fetchall()
        finally:
            connection.close()

    def counts(self):
        return tuple(self.query('SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox)')[0])

    def body(self, revision_id):
        rows = self.query('SELECT CAST(body_json AS BLOB),body_sha256 FROM reader_revisions WHERE revision_id=?', revision_id)
        require(len(rows) == 1, 'revision absent from product history')
        return bytes(rows[0][0]), rows[0][1]

    def exported(self, revision_id):
        out = self.h.work / 'exports' / (self.name + '-' + revision_id + '.json')
        out.parent.mkdir(exist_ok=True)
        result = self.h.consumer('get', self.db, revision_id, out)
        require(result['status'] == 0, 'installed revision get failed: %s' % result)
        return out.read_bytes()

    def heads(self, key):
        result = self.h.consumer('heads', self.db, 'tag', key)
        require(result['status'] == 0, 'heads failed: %s' % result)
        return result

    def temporaries(self):
        return sorted(p.name for p in self.cache.iterdir() if p.name.startswith(('.reader-sync-', '.exr-webdav-')))


class Harness:
    def __init__(self, args):
        self.args = args
        self.name = args.service
        self.exe = args.consumer.resolve()
        self.evidence = args.output.resolve() / args.service
        self.work = args.work.resolve()
        self.evidence.mkdir(parents=True)
        self.work.mkdir(parents=True)
        self.secret = secrets.token_hex(24)
        self.admin = secrets.token_hex(24)
        token = base64.b64encode((USER + ':' + self.secret).encode()).decode()
        self.auth = 'Basic ' + token
        for value in (self.secret, self.admin, token):
            print('::add-mask::' + value, flush=True)
        self.results, self.invocations, self.findings, self.problems = [], [], [], []
        self.observed = {}

    # ----------------------------------------------------------------- consumer
    def consumer(self, *argv, auth=True):
        env = {k: v for k, v in os.environ.items() if k != 'READER_INTEROP_AUTH'}
        if auth:
            env['READER_INTEROP_AUTH'] = self.auth
        result = subprocess.run([str(self.exe), *map(str, argv)], env=env, capture_output=True, timeout=900)
        stdout = result.stdout.decode('utf-8', 'strict')
        self.invocations.append({'argv': [str(a) for a in argv], 'returncode': result.returncode, 'stdout': stdout,
                                 'stderr': result.stderr.decode('utf-8', 'replace')[-2000:]})
        require(result.returncode == 0, 'installed consumer exited %s' % result.returncode)
        return json.loads(stdout)

    def url(self, root_path, host=None, port=None):
        return 'https://%s:%d%s' % (host or self.service.host, port or self.service.port, root_path)

    def root(self, name, create=True):
        path = self.service.base + quote(name, safe='') + '/'
        if create:
            self.client.mkcol(path)
        return path

    # ------------------------------------------------------------------ certs
    def certificates(self):
        tls, host = self.work / 'tls', SERVICES[self.name]['host']
        tls.mkdir()
        ca_key, ca = tls / 'ca.key', tls / 'ca.crt'
        run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2', '-sha256', '-keyout', str(ca_key),
             '-out', str(ca), '-subj', '/CN=EXReader interop test CA ' + os.environ['GITHUB_RUN_ID'] + ' ' + self.name,
             '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign'])
        run(['openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(tls / 'trusted.key'), '-out',
             str(tls / 'trusted.csr'), '-subj', '/CN=' + host])
        (tls / 'server.ext').write_text('subjectAltName=DNS:%s\nbasicConstraints=critical,CA:FALSE\n'
                                        'keyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n'
                                        % host, encoding='ascii')
        run(['openssl', 'x509', '-req', '-in', str(tls / 'trusted.csr'), '-CA', str(ca), '-CAkey', str(ca_key),
             '-CAcreateserial', '-days', '2', '-sha256', '-extfile', str(tls / 'server.ext'), '-out', str(tls / 'trusted.crt')])
        run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2', '-sha256', '-keyout',
             str(tls / 'untrusted.key'), '-out', str(tls / 'untrusted.crt'), '-subj', '/CN=' + host,
             '-addext', 'subjectAltName=DNS:' + host])
        for key in tls.glob('*.key'):
            os.chmod(key, 0o644)  # read by the container's root master only; never copied to evidence
        public = self.evidence / 'tls'
        public.mkdir()
        for name in ('ca.crt', 'trusted.crt', 'untrusted.crt'):
            shutil.copyfile(tls / name, public / name)
        self.trust = '/usr/local/share/ca-certificates/exreader-interop-%s.crt' % self.name
        run(['sudo', 'cp', str(ca), self.trust])
        run(['sudo', 'update-ca-certificates'])
        hosts = run(['cat', '/etc/hosts']).stdout.decode()
        if host not in hosts:
            run(['sudo', 'tee', '-a', '/etc/hosts'], input=('127.0.0.1 %s %s\n' % (host, MISMATCH)).encode())
        return ca

    def describe(self, certificate):
        text = run(['openssl', 'x509', '-in', str(certificate), '-noout', '-subject', '-issuer', '-dates',
                    '-fingerprint', '-sha256', '-ext', 'subjectAltName']).stdout.decode()
        return [line.strip() for line in text.splitlines() if line.strip()]

    # ----------------------------------------------------------------- checks
    def record(self, name, function):
        mark = self.log.mark()
        try:
            details = function() or {}
            self.results.append({'id': name, 'pass': True, 'details': details, 'http': self.window(mark)})
            return True
        except Exception as error:
            self.results.append({'id': name, 'pass': False, 'error': '%s: %s' % (type(error).__name__, error),
                                 'trace': traceback.format_exc()[-4000:], 'http': self.window(mark)})
            return False

    def window(self, mark):
        lines = self.log.module(mark)
        return {'module_requests': len(lines), 'lines': [line['raw'] for line in lines[:240]],
                'truncated': max(0, len(lines) - 240)}

    def execute(self):
        checks = self.checks()
        outcome = {}
        for group, names in GROUPS:
            dependency = DEPENDS.get(group)
            blocked = dependency and not outcome.get(dependency)
            ok = True
            for name in names:
                if blocked or not ok:
                    self.results.append({'id': name, 'pass': False, 'error': 'not run: ' +
                                         ('dependency %s failed' % dependency if blocked else 'earlier check in group failed')})
                    ok = False
                    continue
                ok = self.record(name, checks[name])
            outcome[group] = ok

    def checks(self):
        h, client, log, s = self, self.client, self.log, self.service
        state = {}

        def no_module_requests(mark):
            lines = log.module(mark)
            require(not lines, 'module reached HTTP: %s' % [l['raw'] for l in lines])

        # ------------------------------------------------------------- TLS
        def tls_identity():
            presented = ssl.PEM_cert_to_DER_cert(ssl.get_server_certificate((s.host, s.port)))
            generated = ssl.PEM_cert_to_DER_cert((self.work / 'tls' / 'trusted.crt').read_text())
            require(presented == generated, 'served certificate differs from the generated identity')
            with socket.create_connection((s.host, s.port), timeout=30) as raw_socket:
                with ssl.create_default_context().wrap_socket(raw_socket, server_hostname=s.host) as stream:
                    version, cipher = stream.version(), stream.cipher()[0]
            device = Device(h, 'tls-positive')
            v = device.sync(h.url(h.root('tls-positive')), 0)
            require(v['pulled'] == 0, 'empty shard must not pull')
            self.observed['tls'] = {'host': s.host, 'port': s.port, 'certificate_sha256': sha(generated),
                                    'protocol': version, 'cipher': cipher,
                                    'trusted': self.describe(self.work / 'tls' / 'trusted.crt'),
                                    'ca': self.describe(self.work / 'tls' / 'ca.crt'),
                                    'untrusted': self.describe(self.work / 'tls' / 'untrusted.crt'),
                                    'verification': 'system trust store with hostname; module libcurl VERIFYPEER=1 VERIFYHOST=2'}
            return self.observed['tls']

        def untrusted():
            presented = ssl.PEM_cert_to_DER_cert(ssl.get_server_certificate((s.host, s.untrusted_port)))
            require(presented == ssl.PEM_cert_to_DER_cert((self.work / 'tls' / 'untrusted.crt').read_text()),
                    'untrusted port did not present the untrusted certificate')
            try:
                with socket.create_connection((s.host, s.untrusted_port), timeout=30) as raw_socket:
                    ssl.create_default_context().wrap_socket(raw_socket, server_hostname=s.host).close()
                raise Refused('independent client accepted an untrusted certificate')
            except ssl.SSLCertVerificationError:
                pass
            mark = log.mark()
            v = Device(h, 'tls-untrusted').sync(h.url(s.base + 'tls/', port=s.untrusted_port), 0, expected=SYNC['dav'])
            require(v['dav_code'] == DAV['tls'], 'untrusted certificate not reported as TLS: %s' % v)
            no_module_requests(mark)
            return {'dav_code': v['dav_code'], 'certificate_sha256': sha(presented)}

        def mismatch():
            try:
                with socket.create_connection((MISMATCH, s.port), timeout=30) as raw_socket:
                    ssl.create_default_context().wrap_socket(raw_socket, server_hostname=MISMATCH).close()
                raise Refused('independent client accepted a hostname mismatch')
            except ssl.SSLCertVerificationError:
                pass
            mark = log.mark()
            v = Device(h, 'tls-hostname').sync(h.url(s.base + 'tls/', host=MISMATCH), 0, expected=SYNC['dav'])
            require(v['dav_code'] == DAV['tls'], 'hostname mismatch not reported as TLS: %s' % v)
            no_module_requests(mark)
            return {'dav_code': v['dav_code'], 'connected_name': MISMATCH, 'certificate_names': [s.host]}

        # ------------------------------------------------------- discovery
        def listing_setup():
            root = h.root('listing')
            client.put(root + quote('a b.txt'), b'space name\n')
            client.put(root + quote('书.txt'), '中文名\n'.encode())
            client.mkcol(root + quote('sub dir') + '/')
            client.mkcol(root + quote('ü') + '/')
            client.put(root + quote('sub dir') + '/nested.txt', b'nested\n')
            client.mkcol(root + quote('sub dir') + '/deeper/')
            client.put(root + quote('sub dir') + '/deeper/leaf.txt', b'leaf\n')
            status, xml = client.propfind(root)
            (self.evidence / 'raw').mkdir(exist_ok=True)
            (self.evidence / 'raw' / 'listing-propfind.xml').write_bytes(xml)
            state['listing'] = root
            return xml

        def depth_one():
            xml = listing_setup()
            root = state['listing']
            v = h.consumer('dav-list', h.url(root), '', 0, 0)
            require(v['status'] == 0, 'listing failed: %s' % v)
            names = {e['resource'] for e in v['entries']}
            require(names == {'a%20b.txt', '%E4%B9%A6.txt', 'sub%20dir/', '%C3%BC/'}, 'direct children differ: %s' % names)
            nested = h.consumer('dav-list', h.url(root), 'sub%20dir/', 0, 0)
            require(nested['status'] == 0 and {e['resource'] for e in nested['entries']} ==
                    {'sub%20dir/nested.txt', 'sub%20dir/deeper/'}, 'nested Depth-one children differ: %s' % nested)
            lines = log.module(0)
            require(find(lines, 'PROPFIND', root, (207,)) and find(lines, 'PROPFIND', root + 'sub%20dir/', (207,)),
                    'server did not record the module Depth-one listings')
            require(all(l['depth'] == '1' for l in lines if l.get('method') == 'PROPFIND'), 'non Depth-one listing sent')
            state['entries'] = v['entries']
            escapes = re.findall(rb'%[0-9A-Fa-f]{2}', xml)
            case = ('lower' if any(re.search(rb'[a-f]', e) for e in escapes) else
                    'upper' if any(re.search(rb'[A-F]', e) for e in escapes) else 'digits-only')
            return {'entries': v['entries'], 'nested': nested['entries'], 'server_href_hex_case': case,
                    'server_displayname_elements': xml.count(b'displayname>')}

        def utf8_names():
            observed = {}
            for entry in state['entries']:
                component = entry['resource'].rstrip('/')
                require(entry['display_name'] == unquote(component), 'decoded display name differs: %s' % entry)
                require(bool(entry['collection']) == entry['resource'].endswith('/'), 'collection flag differs')
                require(entry['collection'] or entry['etag'] != '', 'server file ETag absent')
                observed[unquote(component)] = {'display_name': entry['display_name'],
                                                'display_decoded': entry['display_name'] == unquote(component),
                                                'bytes': entry['bytes'], 'has_size': entry['has_size']}
            sizes = {unquote(e['resource']): e['bytes'] for e in state['entries'] if not e['collection']}
            require(sizes == {'a b.txt': 11, '书.txt': len('中文名\n'.encode())}, 'file sizes differ: %s' % sizes)
            return {'names': observed}

        def percent_child():
            root = h.root('percent')
            client.put(root + 'ok.txt', b'ok\n')
            client.put(root + quote('100%.txt'), b'percent\n')
            status, xml = client.propfind(root)
            require(status == 207 and b'100%25.txt' in xml, 'server did not list the percent-named child')
            (self.evidence / 'raw' / 'percent-propfind.xml').write_bytes(xml)
            mark = log.mark()
            v = h.consumer('dav-list', h.url(root), '', 0, 0)
            require(v['status'] == 0 and {e['resource'] for e in v['entries']} == {'ok.txt', '100%25.txt'},
                    'percent child listing result: %s' % v)
            require(next(e for e in v['entries'] if e['resource'] == '100%25.txt')['display_name'] == '100%.txt',
                    'percent display name differs')
            download = self.work / 'percent-download'
            download.mkdir()
            got = h.consumer('dav-get', h.url(root), '100%25.txt', download, 'percent.txt', 0)
            require(got['status'] == 0 and (download / 'percent.txt').read_bytes() == b'percent\n',
                    'literal percent download differs')
            lines = log.module(mark)
            require(find(lines, 'PROPFIND', root, (207,)) and find(lines, 'GET', root + '100%25.txt', (200,)),
                    'server did not record exact encoded percent requests')
            return {'dav_status': v['status'], 'resource': '100%25.txt', 'display_name': '100%.txt', 'download_sha256': sha(b'percent\n')}

        def percent_root():
            client.mkcol(s.base + '100%25/')
            client.put(s.base + '100%25/child.txt', b'percent root\n')
            mark = log.mark()
            v = h.consumer('dav-list', h.url(s.base + '100%25/'), '', 0, 0)
            require(v['status'] == 0 and {e['resource'] for e in v['entries']} == {'child.txt'}, 'percent root differs: %s' % v)
            require(find(log.module(mark), 'PROPFIND', s.base + '100%25/', (207,)), 'percent root request absent')
            ambiguous_mark = log.mark()
            refused = h.consumer('dav-list', h.url(s.base + '100%2520/'), '', 0, 0)
            require(refused['status'] == DAV['argument'], 'second encoded root accepted: %s' % refused)
            no_module_requests(ambiguous_mark)
            return {'dav_status': v['status'], 'second_encoding_status': refused['status'], 'server_collection_exists': True}

        def lowered():
            root = state['listing']
            mark = log.mark()
            entries = h.consumer('dav-list', h.url(root), '', 0, 3)
            listing = h.consumer('dav-list', h.url(root), '', 256, 0)
            require(entries['status'] == DAV['limit'] and entries['entries'] == [], 'entry ceiling result: %s' % entries)
            require(listing['status'] == DAV['limit'] and listing['entries'] == [], 'listing byte ceiling result: %s' % listing)
            require(len(find(log.module(mark), 'PROPFIND', root)) == 2, 'server did not record the bounded listings')
            return {'max_entries_3': entries['status'], 'max_listing_256_bytes': listing['status']}

        # ----------------------------------------------------------- MKCOL
        def mkcol():
            root = h.root('mkcol')
            mark = log.mark()
            first = h.consumer('dav-mkcol', h.url(root), 'made/')
            again = h.consumer('dav-mkcol', h.url(root), 'made/')
            missing = h.consumer('dav-mkcol', h.url(root), 'absent/child/')
            require(first['status'] == 0 and again['status'] == 0, 'MKCOL results: %s %s' % (first, again))
            require(missing['status'] == DAV['http'] and missing['http_status'] == 409, 'missing parent: %s' % missing)
            lines = log.module(mark)
            require(find(lines, 'MKCOL', root + 'made/', (201,)) and find(lines, 'MKCOL', root + 'made/', (405,)) and
                    find(lines, 'MKCOL', root + 'absent/child/', (409,)), 'server MKCOL statuses differ')
            listed, _ = client.children(root)
            require(listed.get('made', {}).get('collection') and 'absent' not in listed, 'server collections differ')
            return {'statuses': [l['status'] for l in lines if l['method'] == 'MKCOL']}

        # ------------------------------------------------------------- PUT
        def conditional_put():
            root = h.root('put')
            state['put'] = root
            folder = self.work / 'put'
            folder.mkdir()
            first, second = original('put-first', 70001), original('put-second', 70001)
            (folder / 'first.bin').write_bytes(first)
            (folder / 'second.bin').write_bytes(second)
            mark = log.mark()
            created = h.consumer('dav-put', h.url(root), 'object.bin', folder / 'first.bin', len(first))
            same = h.consumer('dav-put', h.url(root), 'object.bin', folder / 'first.bin', len(first))
            other = h.consumer('dav-put', h.url(root), 'object.bin', folder / 'second.bin', len(second))
            require(created['status'] == 0, 'create: %s' % created)
            require(same['status'] == DAV['exists'] and same['http_status'] == 412, 'second identical PUT: %s' % same)
            require(other['status'] == DAV['exists'] and other['http_status'] == 412, 'different PUT: %s' % other)
            lines = log.module(mark)
            puts = [l for l in lines if l['method'] == 'PUT']
            require([l['status'] for l in puts] == [201, 412, 412] and all(l['if_none_match'] == '*' for l in puts),
                    'server PUT record differs: %s' % [l['raw'] for l in puts])
            status, data = client.get(root + 'object.bin')
            require(status == 200 and data == first, 'server bytes changed after 412')
            download = self.work / 'put-download'
            download.mkdir()
            got = h.consumer('dav-get', h.url(root), 'object.bin', download, 'object.bin', 0)
            require(got['status'] == 0 and (download / 'object.bin').read_bytes() == first, 'module download differs')
            return {'sha256': sha(first), 'bytes': len(first), 'statuses': [l['status'] for l in puts]}

        def foreign():
            root, folder = state['put'], self.work / 'put'
            existing = original('foreign', 4096)
            client.put(root + 'foreign.bin', existing)
            mark = log.mark()
            v = h.consumer('dav-put', h.url(root), 'foreign.bin', folder / 'first.bin', (folder / 'first.bin').stat().st_size)
            require(v['status'] == DAV['exists'] and v['http_status'] == 412, 'foreign overwrite result: %s' % v)
            require(find(log.module(mark), 'PUT', root + 'foreign.bin', (412,)), 'server did not record 412')
            status, data = client.get(root + 'foreign.bin')
            require(status == 200 and data == existing, 'foreign content changed')
            return {'sha256': sha(existing)}

        def ceiling():
            root = state['put']
            big = original('ceiling', 2 * 1024 * 1024 + 1)
            client.put(root + 'large.bin', big)
            folder = self.work / 'ceiling'
            folder.mkdir()
            mark = log.mark()
            v = h.consumer('dav-get', h.url(root), 'large.bin', folder, 'large.bin', 1024 * 1024)
            require(v['status'] == DAV['limit'] and v['published'] == 0, 'download ceiling result: %s' % v)
            require(not list(folder.iterdir()), 'download ceiling left files: %s' % list(folder.iterdir()))
            require(find(log.module(mark), 'GET', root + 'large.bin'), 'server did not record the bounded GET')
            return {'remote_bytes': len(big), 'ceiling': 1024 * 1024}

        # -------------------------------------------------------- exchange
        def exchange_setup():
            root = h.root('sync')
            a, b = Device(h, 'device-a'), Device(h, 'device-b')
            one, two = original('book-one', 300007), original('book-two', 200003)
            b1, b2 = book(0x10, 1, one, '互操作 一'), book(0x11, 1, two, 'Interop two')
            a.keep(one)
            b.keep(two)
            state.update(root=root, url=h.url(root), a=a, b=b, one=one, two=two, b1=b1, b2=b2)

        def offline_local():
            exchange_setup()
            a, b = state['a'], state['b']
            a.local(state['b1'])
            b.local(state['b2'])
            require(a.counts() == (1, 1) and b.counts() == (1, 1), 'offline counts differ')
            for device, value in ((a, state['b1']), (b, state['b2'])):
                body, digest = device.body(value['id'])
                require(body == raw(value) and digest == sha(raw(value)), 'retained bytes differ')
            return {'a': a.counts(), 'b': b.counts()}

        def publish_a():
            a, root = state['a'], state['root']
            mark = log.mark()
            v = a.sync(state['url'], 0x10)
            require(v['pushed'] == 1 and v['pulled'] == 1 and a.counts() == (1, 0), 'device A sync: %s' % v)
            lines = log.module(mark)
            obj, rev = root + object_rel(state['one']), root + revision_rel(state['b1'])
            put_obj, put_rev = find(lines, 'PUT', obj, (201,)), find(lines, 'PUT', rev, (201,))
            require(put_obj and put_rev and put_obj[0] < put_rev[0], 'original was not created before its revision')
            require(any(n > put_obj[0] for n in find(lines, 'GET', obj, (200,))) and
                    any(n > put_rev[0] for n in find(lines, 'GET', rev, (200,))), 'ack lacked a fresh verifying GET')
            require(find(lines, 'MKCOL', root + 'exreader-sync-v1/', (201,)), 'namespace creation not recorded')
            return {'report': v}

        def upload_b():
            b, root = state['b'], state['root']
            mark = log.mark()
            v = b.sync(state['url'], 0x10)
            require(v['pushed'] == 1 and v['pulled'] == 1 and b.counts() == (2, 0), 'device B sync: %s' % v)
            require((b.cache / (sha(state['one']) + '.txt')).read_bytes() == state['one'], 'B cache differs')
            require(b.exported(state['b1']['id']) == raw(state['b1']), 'B exact revision differs')
            lines = log.module(mark)
            require(find(lines, 'PUT', root + object_rel(state['two']), (201,)) and
                    find(lines, 'PUT', root + revision_rel(state['b2']), (201,)), 'B uploads not recorded')
            require(find(lines, 'MKCOL', root + 'exreader-sync-v1/', (405,)), 'existing collection 405 not recorded')
            return {'report': v}

        def discover_a():
            a = state['a']
            v = a.sync(state['url'], 0x11)
            require(v['pushed'] == 0 and v['pulled'] == 1 and a.counts() == (2, 0), 'device A discovery: %s' % v)
            require((a.cache / (sha(state['two']) + '.txt')).read_bytes() == state['two'], 'A cache differs')
            require(a.exported(state['b2']['id']) == raw(state['b2']), 'A exact revision differs')
            return {'report': v}

        def server_objects():
            root, out = state['root'], {}
            for data in (state['one'], state['two']):
                status, got = client.get(root + object_rel(data))
                require(status == 200 and len(got) == len(data) and sha(got) == sha(data), 'server original differs')
                out[sha(data)] = len(data)
            for value in (state['b1'], state['b2']):
                status, got = client.get(root + revision_rel(value))
                require(status == 200 and got == raw(value), 'server revision bytes differ')
            for device in (state['a'], state['b']):
                for value in (state['b1'], state['b2']):
                    require(device.body(value['id'])[0] == raw(value), 'product history bytes differ')
            listed, _ = client.children(root + 'exreader-sync-v1/objects/' + sha(state['one'])[:2] + '/')
            require(listed[sha(state['one']) + '.txt']['bytes'] == len(state['one']), 'server listed length differs')
            return {'originals': out}

        def existing():
            c = Device(h, 'device-c-existing')
            c.keep(state['one'])
            c.local(state['b1'])
            mark = log.mark()
            v = c.sync(state['url'], 0x10)
            require(v['pushed'] == 1 and c.counts() == (1, 0), 'existing-object sync: %s' % v)
            lines, root = log.module(mark), state['root']
            obj, rev = root + object_rel(state['one']), root + revision_rel(state['b1'])
            p_obj, p_rev = find(lines, 'PUT', obj, (412,)), find(lines, 'PUT', rev, (412,))
            require(p_obj and p_rev, 'server did not answer 412 for existing objects')
            require(any(n > p_obj[0] for n in find(lines, 'GET', obj, (200,))) and
                    any(n > p_rev[0] for n in find(lines, 'GET', rev, (200,))), '412 was not followed by GET verification')
            return {'report': v}

        def damaged():
            d = Device(h, 'device-d-damaged')
            d.keep(state['one'])
            d.local(state['b1'])
            obj = state['root'] + object_rel(state['one'])
            client.put(obj, bytes([state['one'][0] ^ 0xff]) + state['one'][1:])
            mark = log.mark()
            d.sync(state['url'], 0x10, expected=SYNC['hash'])
            require(d.counts() == (1, 1) and not d.temporaries(), 'damaged remote acknowledged or left temporaries')
            lines = log.module(mark)
            require(find(lines, 'PUT', obj, (412,)) and find(lines, 'GET', obj, (200,)) and
                    not find(lines, 'PUT', state['root'] + revision_rel(state['b1'])), 'damaged flow differs')
            client.put(obj, state['one'])
            v = d.sync(state['url'], 0x10)
            require(v['pushed'] == 1 and d.counts() == (1, 0), 'repair retry: %s' % v)
            status, got = client.get(obj)
            require(status == 200 and got == state['one'], 'repaired original differs')
            return {'retry': v}

        def utf8_root():
            name = '书 库 sync'
            root = h.root(name)
            g, k = Device(h, 'device-g-utf8'), Device(h, 'device-h-utf8')
            value = tag(0x30, 1, '6' * 32, 'UTF-8 书 库')
            g.local(value)
            mark = log.mark()
            pushed = g.sync(h.url(root), 0x30)
            pulled = k.sync(h.url(root), 0x30)
            require(pushed['pushed'] == 1 and pulled['pulled'] == 1 and k.counts() == (1, 0), 'UTF-8 exchange differs')
            require(k.exported(value['id']) == raw(value), 'UTF-8 root exact bytes differ')
            status, got = client.get(root + revision_rel(value))
            require(status == 200 and got == raw(value), 'server bytes under UTF-8 root differ')
            require(find(log.module(mark), 'PUT', root + revision_rel(value), (201,)), 'encoded root PUT not recorded')
            return {'root_path': root, 'decoded': name}

        # ----------------------------------------------------------- heads
        def heads():
            a, b, key = state['a'], state['b'], '5' * 32
            ta, tb = tag(0x20, 1, key, 'A 并发'), tag(0x20, 2, key, 'B 并发')
            a.local(ta)
            b.local(tb)
            require(a.sync(state['url'], 0x20)['pushed'] == 1, 'A tag push')
            require(b.sync(state['url'], 0x20)['pulled'] == 2, 'B concurrent pull')
            require(a.sync(state['url'], 0x20)['pulled'] == 2, 'A concurrent pull')
            out = {}
            for device in (a, b):
                result = device.heads(key)
                require(result['state']['heads'] == 2 and not result['state']['projection_safe'] and
                        result['state']['revisions'] == 2, 'concurrent heads differ: %s' % result)
                out[device.name] = result['heads']
            state['tags'] = (ta, tb)
            return out

        def tombstone():
            a, b, key = state['a'], state['b'], '5' * 32
            ta, tb = state['tags']
            deleted = tag(0x20, 3, key, operation='delete', parents=[ta['id']])
            a.local(deleted)
            require(a.sync(state['url'], 0x20)['pushed'] == 1 and b.sync(state['url'], 0x20)['pulled'] == 3, 'delete exchange')
            for device in (a, b):
                result = device.heads(key)
                require(result['state']['heads'] == 2 and result['state']['revisions'] == 3 and
                        not result['state']['projection_safe'], 'tombstone heads differ: %s' % result)
                rows = device.query('SELECT revision_id,CAST(body_json AS BLOB) FROM reader_tombstones')
                require([(r[0], bytes(r[1])) for r in rows] == [(deleted['id'], raw(deleted))], 'tombstone history differs')
                require(device.counts() == (5, 0), 'device counts differ: %s' % (device.counts(),))
            shard = state['root'] + 'exreader-sync-v1/revisions/20/'
            listed, _ = client.children(shard)
            require(set(listed) == {revision_rel(v).rsplit('/', 1)[1] for v in (ta, tb, deleted)}, 'remote shard differs')
            status, got = client.get(state['root'] + revision_rel(deleted))
            require(status == 200 and got == raw(deleted), 'remote tombstone bytes differ')
            return {'remote_leaves': sorted(listed)}

        # ---------------------------------------------------------- limits
        def bulk(root_name, count):
            values = [tag(0x00, n + 1, '%032x' % (n + 1), 'bulk') for n in range(count)]
            s.place(root_name, 'exreader-sync-v1/revisions/00', {revision_rel(v).rsplit('/', 1)[1]: raw(v) for v in values})
            root = s.base + root_name + '/'
            shard = root + 'exreader-sync-v1/revisions/00/'
            # Independent record of the exact server answer to the module's own
            # PROPFIND body, and the module's own direct listing reason.
            status, xml = client.propfind(shard)
            require(status == 207, 'server did not list the bulk shard: %s' % status)
            (self.evidence / 'raw').mkdir(exist_ok=True)
            (self.evidence / 'raw' / (root_name + '-propfind.xml')).write_bytes(xml)
            document = ET.fromstring(xml)
            shape = {'responses': len(document.findall('{DAV:}response')), 'xml_elements': sum(1 for _ in document.iter()),
                     'bytes': len(xml)}
            direct = h.consumer('dav-list', h.url(root), 'exreader-sync-v1/revisions/00/', 0, 0)
            shape.update(module_list_status=direct['status'], module_list_message=direct['message'],
                         module_list_entries=len(direct['entries']))
            self.invocations[-1]['stdout'] = '[%d entries elided; see result details]' % len(direct['entries'])
            return values, root, shard, shape

        def at_ceiling():
            values, root, shard, shape = bulk('ceiling2000', 2000)
            if shape['module_list_status'] != 0:
                self.findings.append({
                    'id': 'xml_structure_bound_rejects_shard_below_2000_entry_ceiling', 'severity': 'capacity',
                    'service': self.name,
                    'summary': 'A Depth:1 answer for exactly 2000 entries is refused before the documented '
                               '2000-entry/4 MiB shard ceiling: %(module_list_message)s (server sent %(responses)d '
                               'responses, %(xml_elements)d XML elements, %(bytes)d bytes).' % shape,
                    'minimal_repro': '2000 files in one collection; exr_webdav_list(collection) with default limits',
                    'evidence': ['raw/ceiling2000-propfind.xml', 'http/access.log'],
                    'proposed_shared_file': 'extras/webdav/src/webdav.cpp (xml() element bound vs max_entries)'})
            o = Device(h, 'device-o-ceiling')
            mark = log.mark()
            v = o.sync(h.url(root), 0x00, limit=100)
            leaves = sorted(revision_rel(x).rsplit('/', 1)[1] for x in values)
            require(v['pulled'] == 100 and v['remaining_in_shard'] == 1900 and not v['shard_complete'] and
                    v['after'] == leaves[99] and o.counts() == (100, 0), 'ceiling page differs: %s' % v)
            lines = log.module(mark)
            require(find(lines, 'PROPFIND', shard, (207,)) and
                    len([l for l in lines if l['method'] == 'GET' and l['status'] == 200]) == 100, 'server paging record differs')
            return {'report': v, 'server_listing': shape}

        def over_ceiling():
            values, root, shard, shape = bulk('overflow2001', 2001)
            require(shape['module_list_status'] == DAV['limit'] and shape['module_list_entries'] == 0,
                    'direct over-ceiling listing was not refused whole: %s' % shape)
            fresh = Device(h, 'device-o-overflow')
            mark = log.mark()
            v = fresh.sync(h.url(root), 0x00, expected=SYNC['limit'])
            require(fresh.counts() == (0, 0), 'overflow changed history')
            lines = log.module(mark)
            require(find(lines, 'PROPFIND', shard, (207,)) and not [l for l in lines if l['method'] == 'GET'],
                    'server overflow record differs')
            return {'module': v, 'server_listing': shape}

        def payload_limit():
            body = b'{"pad":"' + b'a' * (1024 * 1024) + b'"}'
            leaf = rid(0x01, 1) + '-' + sha(body) + '.json'
            s.place('payload', 'exreader-sync-v1/revisions/01', {leaf: body})
            root = s.base + 'payload/'
            p = Device(h, 'device-p-payload')
            mark = log.mark()
            v = p.sync(h.url(root), 0x01, expected=SYNC['hash'])
            require(p.counts() == (0, 0), 'oversized revision reached history')
            lines = log.module(mark)
            require(find(lines, 'PROPFIND', root + 'exreader-sync-v1/revisions/01/', (207,)) and
                    not find(lines, 'GET', root + 'exreader-sync-v1/revisions/01/' + leaf), 'oversized revision was downloaded')
            return {'listed_bytes': len(body), 'module': v}

        # ---------------------------------------------------------- cancel
        def pre_cancel():
            root = h.root('cancel')
            state['cancel'] = root
            f = Device(h, 'device-f-precancel')
            f.local(tag(0x41, 1, '7' * 32))
            mark = log.mark()
            f.sync(h.url(root), 0x41, cancel=0, expected=SYNC['cancelled'])
            require(f.counts() == (1, 1), 'pre-cancel acknowledged')
            no_module_requests(mark)
            return {'counts': f.counts()}

        def mid_cancel():
            root = state['cancel']
            f = Device(h, 'device-f-midcancel')
            big = original('cancel-big', 6 * 1024 * 1024 + 3)
            value = book(0x42, 1, big, 'Cancelled')
            f.keep(big)
            f.local(value)
            mark = log.mark()
            f.sync(h.url(root), 0x42, cancel=65536, expected=SYNC['cancelled'])
            require(f.counts() == (1, 1) and not f.temporaries(), 'cancel acknowledged or left temporaries')
            obj = root + object_rel(big)
            lines = log.module(mark)
            require(not [l for l in lines if l['method'] == 'PUT' and l['target'] == obj and 200 <= l['status'] < 300],
                    'server committed the cancelled upload')
            status, got = client.get(obj)
            if status == 404:
                retry = f.sync(h.url(root), 0x42)
                require(retry['pushed'] == 1 and f.counts() == (1, 0), 'retry after cancel: %s' % retry)
                status, got = client.get(obj)
                require(status == 200 and got == big, 'retried original differs')
                branch = 'absent_then_retried'
            else:
                require(status == 200 and got != big, 'unexpected remote state after cancel: %s' % status)
                f.sync(h.url(root), 0x42, expected=SYNC['hash'])
                require(f.counts() == (1, 1), 'partial remote object was acknowledged')
                branch = 'partial_visible_and_retained_as_failure'
            return {'branch': branch, 'cancelled_put_statuses': [l['status'] for l in lines if l['target'] == obj]}

        # --------------------------------------------------------- offline
        def stopped():
            root = h.root('offline')
            e = Device(h, 'device-e-offline')
            value = tag(0x40, 1, '8' * 32)
            e.local(value)
            s.stop()
            v = e.sync(h.url(root), 0x40, expected=SYNC['dav'])
            require(v['dav_code'] == DAV['io'] and e.counts() == (1, 1), 'offline result: %s' % v)
            state['offline'] = (e, value, root)
            return {'dav_code': v['dav_code']}

        def restarted():
            e, value, root = state['offline']
            s.start_again(client)
            v = e.sync(h.url(root), 0x40)
            require(v['pushed'] == 1 and e.counts() == (1, 0), 'recovered sync: %s' % v)
            status, got = client.get(root + revision_rel(value))
            require(status == 200 and got == raw(value), 'recovered bytes differ')
            puts = find(log.module(0), 'PUT', root + revision_rel(value))
            require(len(puts) == 1, 'duplicate or missing PUT across the outage')
            return {'report': v}

        # ----------------------------------------------------------- rerun
        def rerun():
            a, b = state['a'], state['b']
            before = (a.counts(), b.counts(), client.tree(state['root']))
            mark = log.mark()
            for device in (a, b):
                for shard in (0x10, 0x11, 0x20):
                    require(device.sync(state['url'], shard)['pushed'] == 0, 'rerun pushed')
            after = (a.counts(), b.counts(), client.tree(state['root']))
            require(before == after, 'rerun changed history, outbox or server tree')
            methods = sorted({l['method'] for l in log.module(mark)})
            require(set(methods) <= {'PROPFIND', 'GET'}, 'rerun wrote: %s' % methods)
            return {'counts': [before[0], before[1]], 'server_objects': len(before[2]), 'methods': methods}

        def reapply():
            a = state['a']
            a.local(state['b1'], created=0)
            require(a.counts() == (5, 0), 'reapply requeued')
            return {'counts': a.counts()}

        # --------------------------------------------------------- hygiene
        def hygiene():
            lines = log.module(0)
            require(lines and not [l for l in lines if l.get('malformed')], 'access log missing or malformed')
            methods = {}
            for line in lines:
                key = '%s %s' % (line['method'], line['status'])
                methods[key] = methods.get(key, 0) + 1
            require({l['method'] for l in lines} <= {'PROPFIND', 'GET', 'PUT', 'MKCOL'}, 'unexpected module method')
            require(all(l['if_none_match'] == '*' for l in lines if l['method'] == 'PUT'), 'unconditional module PUT')
            require(all(l['depth'] == '1' for l in lines if l['method'] == 'PROPFIND'), 'non Depth-one PROPFIND')
            require(not [l for l in lines if re.search(r'\.(sqlite|db)(-wal|-shm)?$', l['target'])], 'database uploaded')
            require(methods.get('PUT 412', 0) >= 1, 'no real 412 observed')
            self.observed['http_summary'] = methods
            return {'module_requests': len(lines), 'by_method_status': methods}

        functions = [tls_identity, untrusted, mismatch, depth_one, utf8_names, lowered, percent_child, percent_root,
                     mkcol, conditional_put, foreign, ceiling,
                     offline_local, publish_a, upload_b, discover_a, server_objects, existing, damaged, utf8_root,
                     heads, tombstone, at_ceiling, over_ceiling, payload_limit, pre_cancel, mid_cancel,
                     stopped, restarted, rerun, reapply, hygiene]
        names = [name for _, group in GROUPS for name in group]
        require(len(functions) == len(names), 'check table differs')
        return dict(zip(names, functions))

    # -------------------------------------------------------- credentials
    def scrub(self, server_copies):
        needles = [self.secret.encode(), self.admin.encode(), self.auth.encode(), self.auth.split(' ', 1)[1].encode()]
        found = []
        roots = [self.evidence] + [p for p in server_copies if p.exists()]
        scanned = 0
        for root in roots:
            for path in [root] if root.is_file() else root.rglob('*'):
                if not path.is_file() or path.is_symlink():
                    continue
                scanned += 1
                data = path.read_bytes()
                if any(n in data for n in needles):
                    found.append(str(path))
                    if self.evidence in path.parents:
                        path.write_text('removed by credential scan: this file contained a test credential\n', encoding='ascii')
        for path in self.evidence.rglob('*.key'):
            path.unlink()
            found.append(str(path))
        return found, scanned

    # --------------------------------------------------------------- main
    def main(self):
        report = {'schema': 'reader-webdav-interop-service-v1', 'service': self.name,
                  'service_title': SERVICES[self.name]['title'], 'accepted': False,
                  'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                  'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'job': os.environ.get('GITHUB_JOB'),
                  'runner': os.environ.get('ImageOS'), 'start_point': START, 'platform': sys.platform,
                  'client_backend': 'libcurl (Linux EXReaderWebDAV backend)',
                  'scope': 'Job-local pinned %s; installed EXReaderWebDAV/Revisions/Sync with product SQLite; '
                           'two independent product databases and private original directories.' % SERVICES[self.name]['title'],
                  'real_user_cloud': False, 'public_writable_server': False, 'six_platform_client_accepted': False,
                  'windows_winhttp_covered': False, 'inherits_tls_fixture_conclusions': False, 'complete_product': False,
                  'expected_checks': EXPECTED, 'problems': []}
        service_cls = Apache if self.name == 'apache' else Nextcloud
        server_copies = []
        try:
            curl = run(['curl-config', '--version'], check=False).stdout.decode().strip()
            report['client_backend'] = 'libcurl ' + curl.replace('libcurl ', '')
            ca = self.certificates()
            self.service = service_cls(self.name, self.work, self.evidence, ca, self.secret)
            self.service.admin = self.admin
            self.client = Independent(self.service.host, self.service.port, ca, self.auth)
            self.service.pull()
            self.service.start(self.client)
            self.log = self.service.log
            report['image'] = self.service.image_identity()
            report['versions'] = self.service.versions()
            self.execute()
        except Exception as error:
            report['problems'].append('%s: %s' % (type(error).__name__, error))
            report['setup_trace'] = traceback.format_exc()[-6000:]
        finally:
            if hasattr(self, 'service'):
                try:
                    server_copies = self.service.collect()
                except Exception as error:
                    report['problems'].append('collect: %s' % error)
                self.service.remove()
            (self.evidence / 'invocations.json').write_text(json.dumps(self.invocations, ensure_ascii=False, indent=1),
                                                            encoding='utf-8')
            found, scanned = self.scrub(server_copies)
            self.results.append({'id': FINAL_CHECK, 'pass': not found and scanned > 0,
                                 'details': {'files_scanned': scanned, 'matches': found,
                                             'needles': ['test password', 'admin password', 'Authorization value',
                                                         'Basic token']}})
            run(['sudo', 'rm', '-f', getattr(self, 'trust', '/nonexistent')], check=False)
            run(['sudo', 'update-ca-certificates', '--fresh'], check=False)
            run(['sudo', 'rm', '-rf', str(self.work)], check=False)
            ids = [r['id'] for r in self.results]
            report.update({'checks': self.results, 'count': len(self.results),
                           'passed': sum(1 for r in self.results if r.get('pass') is True),
                           'tls': self.observed.get('tls'), 'http_summary': self.observed.get('http_summary'),
                           'findings': self.findings})
            report['accepted'] = (not report['problems'] and ids == EXPECTED and
                                  all(r.get('pass') is True for r in self.results))
            text = json.dumps(report, ensure_ascii=False, indent=2)
            for needle in (self.secret, self.admin, self.auth.split(' ', 1)[1]):
                text = text.replace(needle, '[credential removed]')
            (self.evidence / 'result.json').write_text(text + '\n', encoding='utf-8')
            print(json.dumps({'service': self.name, 'accepted': report['accepted'], 'passed': report['passed'],
                              'count': report['count'], 'problems': report['problems'],
                              'failed': [{'id': r['id'], 'error': r.get('error')} for r in self.results
                                         if r.get('pass') is not True],
                              'findings': [{'id': f['id'], 'summary': f['summary']} for f in self.findings]},
                             ensure_ascii=False, indent=1))
        return 0 if report['accepted'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', choices=sorted(SERVICES), required=True)
    parser.add_argument('--consumer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('real-service interop runs only inside GitHub Actions')
    sys.exit(Harness(args).main())


if __name__ == '__main__':
    main()
