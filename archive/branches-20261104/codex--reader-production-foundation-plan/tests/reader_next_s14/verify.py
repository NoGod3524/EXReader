#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict same-run evidence verifier; also exposes an offline contract self-test."""
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import zipfile
from cases import (HARNESS_COMMON, NATIVE_COMMON, NATIVE_POSIX, NEGATIVE, ORIGINAL_COMMON, ORIGINAL_POSIX,
                   ORIGINAL_WINDOWS, ROLES_COMMON, ROLES_POSIX, ROLES_WINDOWS, S14_COMMON, S14_HARNESS)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch, pages, require

WORKFLOW = '.github/workflows/reader-next-s14.yml'
MODULE = 'apps/reader/font-library'
PINNED_MODULE = '1563f4abb85ccd28c3a0aae3e9913f4330536215'
SDK_COMMITS = {'3.40.0': '9854061be331fe603a1822d9b2b36ee357154927',
               '3.41.0': 'edddc463c06ed5731195cdb8f06b2df6dff7699e'}
REUSED = ('include/reader_font_library.h', 'src/library.cpp', 'src/sha256.hpp')
NEGATIVE_ROLES = {'configure-invalid-sdk', 'configure-wrong-sdk', 'consumer-wrong-sdk'}
PLATFORMS = [
    {'platform': 'Linux', 'runner': 'ubuntu-22.04', 'system': 'Linux', 'label': 'SDK341', 'sdk': '3.41.0'},
    {'platform': 'Windows', 'runner': 'windows-2022', 'system': 'Windows', 'label': 'SDK341', 'sdk': '3.41.0'},
    {'platform': 'macOS', 'runner': 'macos-15', 'system': 'Darwin', 'label': 'SDK341', 'sdk': '3.41.0'},
    {'platform': 'Linux', 'runner': 'ubuntu-22.04', 'system': 'Linux', 'label': 'SDK340', 'sdk': '3.40.0'},
]


def tag(version):
    return 'sdk' + ''.join(version.split('.')[:2])


def expected_checks(spec):
    return ORIGINAL_COMMON + S14_COMMON + S14_HARNESS + (ORIGINAL_WINDOWS if spec['system'] == 'Windows' else ORIGINAL_POSIX)


def strict_json(data):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, 'duplicate JSON key')
            out[key] = value
        return out
    return json.loads(data, object_pairs_hook=pairs)


def validate_preloaded(report, logs, spec, source, run_id, attempt, helper_hash):
    require(report.get('accepted') is True and report.get('source_sha') == source and
            str(report.get('run_id')) == str(run_id) and str(report.get('attempt')) == str(attempt) and
            report.get('sdk_version') == spec['sdk'] and report.get('platform') == spec['platform'] and
            report.get('helper_sha256') == helper_hash, 'preloaded source/SDK/helper identity')
    expected = {mode + suffix for mode in ('source', 'installed')
                for suffix in ('-same-prefix', '-foreign-prefix')}
    rows = report.get('cases', [])
    require(len(rows) == 4 and {row['name'] for row in rows} == expected, 'exact preloaded controls')
    for row in rows:
        foreign = row['name'].endswith('-foreign-prefix')
        raw = logs[row['name']]
        require(row.get('passed') is True and row.get('expected_refusal') is foreign and
                row.get('refused') is foreign and type(row.get('exit')) is int and
                (row['exit'] != 0 if foreign else row['exit'] == 0) and
                row.get('log_sha256') == hashlib.sha256(raw).hexdigest(), 'actual preloaded configure outcome')
        if foreign:
            require(b'SDK imported target' in raw and re.search(rb'origin\s+mismatch', raw),
                    'SDK target provenance refusal marker')
    return True


def validate(run, jobs, artifacts, blobs, source, run_id, attempt, module_tree, pinned):
    require(run['head_sha'] == source and run['id'] == run_id and run['run_attempt'] == attempt
            and run['path'] == WORKFLOW, 'caller identity')
    require(len({j['id'] for j in jobs}) == len(jobs), 'duplicate job id')
    require(len({a['id'] for a in artifacts}) == len(artifacts), 'duplicate artifact id')
    require(len({a['name'] for a in artifacts}) == len(artifacts), 'duplicate artifact name')
    accepted = []
    for spec in PLATFORMS:
        system = spec['system']
        job_name = 'font library (%s, %s)' % (spec['runner'], spec['label'])
        matching = [j for j in jobs if j['name'] == job_name]
        require(len(matching) == 1, 'missing/duplicate job: ' + job_name)
        job = matching[0]
        require(job['head_sha'] == source and job['run_attempt'] == attempt and job['status'] == 'completed'
                and job['conclusion'] == 'success', 'upstream job identity/status')
        name = 'reader-s14-font-library-%s-%s-%d-%d' % (spec['platform'], spec['label'], run_id, attempt)
        matches = [a for a in artifacts if a['name'] == name]
        require(len(matches) == 1, 'missing/duplicate artifact: ' + name)
        a = matches[0]
        require(a['workflow_run']['id'] == run_id and a['workflow_run']['head_sha'] == source
                and not a['expired'] and a['size_in_bytes'] > 0, 'artifact identity/size/expiry')
        require(datetime.fromisoformat(a['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc),
                'expired timestamp')
        require(re.fullmatch('sha256:[0-9a-f]{64}', a.get('digest', '')) is not None, 'missing API digest')
        data = blobs[a['id']]
        require(len(data) == a['size_in_bytes'] and 'sha256:' + hashlib.sha256(data).hexdigest() == a['digest'],
                'ZIP size/digest')
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            require(len(names) == len(set(names)), 'duplicate ZIP member')
            require(all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n
                        for n in names), 'unsafe ZIP path')
            require(names.count('result.json') == 1, 'missing original report')
            r = strict_json(z.read('result.json'))
            require(r['accepted'] is True and not r['failures'] and r['source_sha'] == source
                    and r['run_id'] == run_id and r['attempt'] == attempt and r['platform'] == system,
                    'report identity/status')
            require(r['module_source_tree'] == module_tree, 'original module source binding')
            require(r['sdk_version'] == spec['sdk'] and r['sdk_tag'] == tag(spec['sdk'])
                    and r['sdk_commit'] == SDK_COMMITS[spec['sdk']], 'reported SDK selection')
            require(r['start'] == 'e67d87cbeabb2457e0852f681ef0b27b2c0da4d8', 'fixed start binding')
            require(r['module_ref'] == PINNED_MODULE, 'reused module reference')
            for flag in ('host_ui_accepted', 'mobile_accepted', 'power_loss_accepted', 'sdk_changed',
                         'schema_changed', 'font_library_api_changed'):
                require(r[flag] is False, 'excess claim: ' + flag)
            require(r['font_surface_unchanged'] is True, 'font surface not proven unchanged')
            require(r['reused_module_bytes'] == pinned, 'reused module bytes differ from the pinned library')
            expected = expected_checks(spec)
            require(len(r['checks']) == len(set(r['checks'])) and set(r['checks']) == set(expected),
                    'exact required named cases')
            ids = r['identities']
            paths = [i['path'] for i in ids]
            require(len(paths) == len(set(paths)) and len(paths) > 8, 'identity list')
            binary = 'binary/font-probe.exe' if system == 'Windows' else 'binary/font-probe'
            cname = 'binary/font-c.exe' if system == 'Windows' else 'binary/font-c'
            module = ('installed/lib/reader_font_library.lib' if system == 'Windows'
                      else 'installed/lib/libreader_font_library.a')
            required_files = {binary, cname, 'binary/font-probe.map', module,
                              'installed/include/reader_font_library.h', 'materials/LICENSE.md',
                              'materials/font.ttf', 'materials/font.otf', 'materials/font.ttc',
                              'sdk-font-header.h', 'sdk-exreader-config.cmake',
                              r['package_config']['path']}
            require(required_files <= set(paths), 'missing original module/binary/license/input')
            for item in ids:
                content = z.read(item['path'])
                require(len(content) == item['bytes'] > 0
                        and hashlib.sha256(content).hexdigest() == item['sha256'],
                        'bound file changed: ' + item['path'])
            bound = {i['path']: i for i in ids}
            require(bound[r['package_config']['path']]['sha256'] == r['package_config']['sha256'],
                    'installed package config binding')
            config_text = z.read(r['package_config']['path']).decode()
            bindings = re.findall(r'find_dependency\(EXReader ([0-9]+\.[0-9]+\.[0-9]+) EXACT CONFIG COMPONENTS core\)',
                                  config_text)
            require(bindings == [spec['sdk']], 'installed package SDK binding')
            require(len(re.findall(r'find_dependency\(EXReader ', config_text)) == 1, 'multiple SDK dependencies')
            sdk_config_bytes = z.read('sdk-exreader-config.cmake')
            require(hashlib.sha256(sdk_config_bytes).hexdigest() == r['sdk_exreader_config_sha256'],
                    'installed SDK config binding')
            sdk_config = sdk_config_bytes.decode()
            require('set(EXReader_VERSION "%s")' % spec['sdk'] in sdk_config, 'installed SDK version')
            require(hashlib.sha256(z.read('sdk-font-header.h')).hexdigest() == r['sdk_font_header_sha256'],
                    'installed SDK header binding')
            commands = r['commands']
            require(8 <= len(commands) <= 200, 'native command inventory')
            require([c['number'] for c in commands] == list(range(1, len(commands) + 1)), 'command numbering')
            require(len({c['log'] for c in commands}) == len(commands), 'native logs not unique')
            require(all(c['log'] in paths for c in commands), 'native logs not bound')
            required_roles = set(ROLES_COMMON) | set(ROLES_WINDOWS if system == 'Windows' else ROLES_POSIX)
            roles = {c['role'] for c in commands}
            require(required_roles <= roles, 'missing command role: %s' % (required_roles - roles))
            failures = {c['role'] for c in commands if not c['expected_success']}
            require(failures == NEGATIVE_ROLES | ({'locked-manifest'} if system == 'Windows' else set()),
                    'unexpected native failure inventory')
            for command in commands:
                require(command['returncode'] == 0 if command['expected_success'] else command['returncode'] != 0,
                        'native command exit differs: ' + command['role'])
            consumer = [c for c in commands if c['role'] == 'c-consumer']
            require(len(consumer) == 1 and consumer[0]['arguments'][0].replace('\\', '/').endswith(cname.split('/')[-1]),
                    'original C consumer binding')
            require(z.read(consumer[0]['log']).decode().strip() == 'installed-c-abi-' + tag(spec['sdk']),
                    'original C consumer result')
            suite = [c for c in commands if c['role'] == 'suite']
            require(len(suite) == 1 and suite[0]['arguments'][1] == 'suite', 'original C++ consumer binding')
            native = [line[5:] for line in z.read(suite[0]['log']).decode().splitlines() if line.startswith('CASE ')]
            native_expected = set(NATIVE_COMMON) | (set() if system == 'Windows' else set(NATIVE_POSIX))
            require(len(native) == len(set(native)) and set(native) == native_expected, 'original native named cases differ')
            extended = [c for c in commands if c['role'] == 's14']
            require(len(extended) == 1, 'missing S14 native binding')
            s14 = [line[5:] for line in z.read(extended[0]['log']).decode().splitlines() if line.startswith('CASE ')]
            require(s14 == S14_COMMON, 'S14 native named cases differ')
            events = r['terminations']
            require(len(events) == 4 and {e['stage'] for e in events} ==
                    {'copy', 'validated', 'file-published', 'committed'}, 'missing actual termination boundary')
            input_hashes = {i['name']: i['sha256'] for i in r['inputs']}
            for event in events:
                require(type(event['pid']) is int and event['pid'] > 0 and event['returncode'] != 0
                        and event['readiness_file'] in paths, 'termination identity/exit')
                require(z.read(event['readiness_file']).decode() == event['stage'], 'termination readiness binding')
                wanted = sorted([input_hashes['font.ttf'], input_hashes['font.otf']]
                                if event['stage'] == 'committed' else [input_hashes['font.ttf']])
                require(event['recovered_hashes'] == wanted, 'termination recovered set')
            linkmap = z.read('binary/font-probe.map').decode(errors='replace')
            require('reader_font_library' in linkmap and 'rfl_import_file' in linkmap, 'installed module not linked')
            require({i['name'] for i in r['inputs']} == {'font.ttf', 'font.otf', 'font.ttc', 'LICENSE.md'},
                    'input inventory')
            for item in r['inputs']:
                content = z.read('materials/' + item['name'])
                require(len(content) == item['bytes'] and hashlib.sha256(content).hexdigest() == item['sha256']
                        and item['license'] == 'SIL Open Font License 1.1' and item['license_spdx'] == 'OFL-1.1',
                        'font material licence binding')
            require('SIL OPEN FONT LICENSE Version 1.1' in z.read('materials/LICENSE.md').decode(), 'licence text')
            accepted.append({'platform': spec['platform'], 'label': spec['label'], 'sdk': spec['sdk'],
                             'job_id': job['id'], 'checks': len(r['checks']),
                             'artifact': {k: a[k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
                             'identities': ids, 'inputs': r['inputs'], 'c_consumer_token': r['c_consumer_token'],
                             'gaps': r['gaps']})
    return accepted


def negative_tests(run, jobs, artifacts, blobs, source, run_id, attempt, module_tree, pinned):
    outcomes = []
    target = next(a for a in artifacts if a['name'] ==
                  'reader-s14-font-library-Linux-SDK341-%d-%d' % (run_id, attempt))['id']
    for case in NEGATIVE:
        r, j, a = copy.deepcopy(run), copy.deepcopy(jobs), copy.deepcopy(artifacts)
        b = dict(blobs)
        first = next(x for x in a if x['id'] == target)
        job = next(x for x in j if x['name'] == 'font library (ubuntu-22.04, SDK341)')
        if case == 'wrong-source':
            r['head_sha'] = '0' * 40
        elif case == 'wrong-run':
            r['id'] += 1
        elif case == 'wrong-attempt':
            r['run_attempt'] += 1
        elif case == 'unfinished-job':
            job['status'] = 'in_progress'
        elif case == 'failed-job':
            job['conclusion'] = 'failure'
        elif case == 'duplicate-job':
            j.append(copy.deepcopy(job))
        elif case == 'missing-artifact':
            a.remove(first)
        elif case == 'duplicate-artifact-name':
            other = copy.deepcopy(first)
            other['id'] += 1000000000
            a.append(other)
        elif case == 'duplicate-artifact-id':
            other = copy.deepcopy(first)
            other['name'] += '-other'
            a.append(other)
        elif case == 'empty-artifact':
            first['size_in_bytes'] = 0
        elif case == 'expired-artifact':
            first['expired'] = True
        elif case == 'expired-timestamp':
            first['expires_at'] = '2000-01-01T00:00:00Z'
        elif case == 'wrong-artifact-source':
            first['workflow_run']['head_sha'] = '0' * 40
        elif case == 'wrong-artifact-run':
            first['workflow_run']['id'] += 1
        elif case == 'wrong-zip-size':
            first['size_in_bytes'] += 1
        elif case == 'wrong-zip-digest':
            first['digest'] = 'sha256:' + '0' * 64
        else:
            with zipfile.ZipFile(io.BytesIO(b[target])) as z:
                content = {name: z.read(name) for name in z.namelist()}
            report = strict_json(content['result.json'])
            if case == 'duplicate-json-key':
                content['result.json'] = content['result.json'].replace(b'{', b'{"accepted": false,', 1)
            elif case == 'missing-case':
                report['checks'].pop()
            elif case == 'extra-case':
                report['checks'].append('fabricated-pass')
            elif case == 'duplicate-case':
                report['checks'].append(report['checks'][0])
            elif case == 'missing-original-module':
                report['identities'] = [i for i in report['identities']
                                        if not i['path'].endswith('libreader_font_library.a')]
            elif case == 'altered-binary':
                content['binary/font-probe'] += b'changed'
            elif case == 'altered-license':
                content['materials/LICENSE.md'] += b'changed'
            elif case == 'wrong-report-source':
                report['source_sha'] = '0' * 40
            elif case == 'wrong-report-attempt':
                report['attempt'] += 1
            elif case == 'wrong-report-run':
                report['run_id'] += 1
            elif case == 'failed-report':
                report['accepted'] = False
            elif case == 'wrong-platform':
                report['platform'] = 'Windows'
            elif case == 'unbound-module-source':
                report['module_source_tree'] = '0' * 40
            elif case == 'altered-native-log':
                suite, = [command for command in report['commands'] if command['role'] == 'suite']
                content[suite['log']] += b'changed'
            elif case == 'forged-native-case':
                suite, = [command for command in report['commands'] if command['role'] == 'suite']
                log = suite['log']
                require(content[log].count(b'CASE empty-library') == 1,
                        'negative fixture must alter the actual unique native case')
                content[log] = content[log].replace(b'CASE empty-library', b'CASE fabricated-native-pass')
                for item in report['identities']:
                    if item['path'] == log:
                        item['bytes'] = len(content[log])
                        item['sha256'] = hashlib.sha256(content[log]).hexdigest()
            elif case == 'missing-native-command':
                require(sum(command['role'] == 'suite' for command in report['commands']) == 1,
                        'negative fixture requires the actual unique suite command')
                report['commands'] = [command for command in report['commands'] if command['role'] != 'suite']
            elif case == 'missing-termination':
                report['terminations'].pop()
            elif case == 'zero-termination-exit':
                report['terminations'][0]['returncode'] = 0
            elif case == 'wrong-sdk-version':
                report['sdk_version'] = '3.42.0'
            elif case == 'wrong-sdk-tag':
                report['sdk_tag'] = 'sdk340'
            elif case == 'altered-installed-package-config':
                path = report['package_config']['path']
                content[path] = content[path] + b'# drifted'
                for item in report['identities']:
                    if item['path'] == path:
                        item['bytes'] = len(content[path])
                        item['sha256'] = hashlib.sha256(content[path]).hexdigest()
            elif case == 'wrong-package-sdk-binding':
                path = report['package_config']['path']
                content[path] = content[path].replace(b'EXReader 3.41.0 EXACT', b'EXReader 3.40.0 EXACT')
                for item in report['identities']:
                    if item['path'] == path:
                        item['bytes'] = len(content[path])
                        item['sha256'] = hashlib.sha256(content[path]).hexdigest()
            elif case == 'missing-command-role':
                report['commands'] = [c for c in report['commands'] if c['role'] != 's14']
            elif case == 'unexpected-command-failure':
                report['commands'][0]['returncode'] = 3
            if case != 'duplicate-json-key':
                content['result.json'] = json.dumps(report).encode()
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as z:
                for name, data in content.items():
                    z.writestr(name, data)
                if case == 'duplicate-zip-member':
                    z.writestr('result.json', content['result.json'])
            b[target] = stream.getvalue()
            first['size_in_bytes'] = len(b[target])
            first['digest'] = 'sha256:' + hashlib.sha256(b[target]).hexdigest()
        current = dict(pinned)
        if case == 'reused-module-differs':
            current['src/library.cpp'] = '0' * 40
        try:
            validate(r, j, a, b, source, run_id, attempt, module_tree, current)
        except (ValueError, KeyError, AssertionError, zipfile.BadZipFile) as error:
            outcomes.append({'case': case, 'rejected': True, 'reason': str(error)})
        else:
            raise AssertionError('verifier accepted ' + case)
    require(len(outcomes) == len(NEGATIVE), 'negative coverage')
    return outcomes


def synthetic(spec, source, run_id, attempt, module_tree, pinned):
    """Build one internally consistent dataset; used only by --self-test."""
    system = spec['system']
    tag_name = tag(spec['sdk'])
    binary = 'font-probe.exe' if system == 'Windows' else 'font-probe'
    cname = 'font-c.exe' if system == 'Windows' else 'font-c'
    module = 'installed/lib/reader_font_library.lib' if system == 'Windows' else 'installed/lib/libreader_font_library.a'
    config_path = 'installed/lib/cmake/EXReaderFontLibrary/EXReaderFontLibraryConfig.cmake'
    config_bytes = ('@PACKAGE_INIT@\ninclude(CMakeFindDependencyMacro)\n'
                    'find_dependency(EXReader %s EXACT CONFIG COMPONENTS core)\nfind_dependency(Threads)\n'
                    % spec['sdk']).encode()
    sdk_config = ('set(EXReader_VERSION "%s")\n' % spec['sdk']).encode()
    native = [c for c in ORIGINAL_COMMON if c not in HARNESS_COMMON]
    if system != 'Windows':
        native += NATIVE_POSIX
    commands = [
        ('c-consumer', 'installed-c-abi-' + tag_name, True),
        ('configure-invalid-sdk', 'Unsupported exact reader SDK version', False),
        ('configure-wrong-sdk', 'Could not find a package', False),
        ('consumer-wrong-sdk', 'Could not find a package', False),
        ('suite', '\n'.join('CASE ' + c for c in native), True),
        ('s14', '\n'.join('CASE ' + c for c in S14_COMMON), True),
        ('list', '', True),
        ('import', '', True),
        ('status', 'STATUS 8', True),
    ]
    if system == 'Windows':
        commands.append(('locked-manifest', '4: write', False))
    else:
        commands.append(('write-full', '', True))
    files = {
        'binary/' + binary: b'probe-binary',
        'binary/' + cname: b'c-binary',
        'binary/font-probe.map': b'reader_font_library rfl_import_file',
        module: b'libreader_font_library',
        'installed/include/reader_font_library.h': b'header',
        config_path: config_bytes,
        'materials/LICENSE.md': b'SIL OPEN FONT LICENSE Version 1.1',
        'materials/font.ttf': b'ttf',
        'materials/font.otf': b'otf',
        'materials/font.ttc': b'ttc',
        'sdk-font-header.h': b'text header',
        'sdk-exreader-config.cmake': sdk_config,
    }
    terminations = []
    hashes = {'font.ttf': hashlib.sha256(b'ttf').hexdigest(), 'font.otf': hashlib.sha256(b'otf').hexdigest()}
    for stage in ('copy', 'validated', 'file-published', 'committed'):
        files['ready-' + stage] = stage.encode()
        terminations.append({'stage': stage, 'pid': 4242, 'returncode': -9,
                             'recovered_hashes': sorted([hashes['font.ttf'], hashes['font.otf']]
                                                        if stage == 'committed' else [hashes['font.ttf']]),
                             'readiness_file': 'ready-' + stage})
    command_records = []
    for index, (role, output, okay) in enumerate(commands, 1):
        files['command-%02d.log' % index] = (output + chr(10)).encode()
        arguments = [cname] if role == 'c-consumer' else ['probe', role]
        command_records.append({'number': index, 'role': role, 'arguments': arguments,
                                'log': 'command-%02d.log' % index,
                                'returncode': 0 if okay else 1, 'expected_success': okay})
    identities = []
    for path in sorted(files):
        data = files[path]
        identities.append({'path': path, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    report = {
        'accepted': True, 'source_sha': source, 'run_id': run_id, 'attempt': attempt, 'platform': system,
        'start': 'e67d87cbeabb2457e0852f681ef0b27b2c0da4d8', 'sdk_version': spec['sdk'], 'sdk_tag': tag_name,
        'sdk_commit': SDK_COMMITS[spec['sdk']], 'module_ref': PINNED_MODULE,
        'checks': expected_checks(spec), 'failures': [], 'identities': identities,
        'inputs': [{'name': name, 'bytes': len(files['materials/' + name]),
                    'sha256': hashlib.sha256(files['materials/' + name]).hexdigest(),
                    'license': 'SIL Open Font License 1.1', 'license_spdx': 'OFL-1.1', 'url': 'synthetic',
                    'commit': 'synthetic', 'git_blob': 'synthetic'} for name in
                   ('font.ttf', 'font.otf', 'font.ttc', 'LICENSE.md')],
        'commands': command_records, 'terminations': terminations, 'host_ui_accepted': False,
        'mobile_accepted': False, 'power_loss_accepted': False, 'sdk_changed': False, 'schema_changed': False,
        'font_library_api_changed': False, 'font_surface_unchanged': True, 'reused_module_bytes': dict(pinned),
        'module_source_tree': module_tree, 'package_config': {'path': config_path, 'bytes': len(config_bytes),
                                                              'sha256': hashlib.sha256(config_bytes).hexdigest()},
        'sdk_font_header_sha256': hashlib.sha256(b'text header').hexdigest(),
        'sdk_exreader_config_sha256': hashlib.sha256(sdk_config).hexdigest(),
        'c_consumer_token': 'installed-c-abi-' + tag_name, 'gaps': ['synthetic'], 'reused_module_header': 'x'}
    files['result.json'] = json.dumps(report).encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as z:
        for path, data in files.items():
            z.writestr(path, data)
    artifact = {'id': 900 + PLATFORMS.index(spec), 'name': 'reader-s14-font-library-%s-%s-%d-%d' %
                (spec['platform'], spec['label'], run_id, attempt), 'size_in_bytes': len(stream.getvalue()),
                'digest': 'sha256:' + hashlib.sha256(stream.getvalue()).hexdigest(),
                'expires_at': '2999-01-01T00:00:00Z', 'expired': False,
                'workflow_run': {'id': run_id, 'head_sha': source}}
    return artifact, stream.getvalue()


def self_test():
    source, run_id, attempt, module_tree = 'a' * 40, 7, 1, 'b' * 40
    pinned = {path: 'c' * 40 for path in REUSED}
    run = {'head_sha': source, 'id': run_id, 'run_attempt': attempt, 'path': WORKFLOW}
    jobs, artifacts, blobs = [], [], {}
    for index, spec in enumerate(PLATFORMS):
        artifact, data = synthetic(spec, source, run_id, attempt, module_tree, pinned)
        artifacts.append(artifact)
        blobs[artifact['id']] = data
        jobs.append({'id': 100 + index, 'name': 'font library (%s, %s)' % (spec['runner'], spec['label']),
                     'head_sha': source, 'run_attempt': attempt, 'status': 'completed', 'conclusion': 'success'})
    accepted = validate(run, jobs, artifacts, blobs, source, run_id, attempt, module_tree, pinned)
    require(len(accepted) == len(PLATFORMS), 'self-test platform coverage')
    outcomes = negative_tests(run, jobs, artifacts, blobs, source, run_id, attempt, module_tree, pinned)
    print(json.dumps({'self_test': True, 'accepted_platforms': len(accepted),
                      'negative_cases': len(outcomes)}, indent=2))


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    out = Path('build/s14-verified')
    out.mkdir(parents=True, exist_ok=True)
    source = os.environ['GITHUB_SHA']
    run_id = int(os.environ['GITHUB_RUN_ID'])
    attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
    summary = {'accepted': False, 'source_sha': source, 'run_id': run_id, 'attempt': attempt, 'failures': []}
    try:
        run = fetch('actions/runs/%d' % run_id)
        jobs = pages('actions/runs/%d/attempts/%d/jobs' % (run_id, attempt), 'jobs')
        artifacts = pages('actions/runs/%d/artifacts' % run_id, 'artifacts')
        blobs = {}
        for a in artifacts:
            if a['name'].startswith('reader-s14-font-library-'):
                with tempfile.TemporaryFile() as stream:
                    download_artifact_zip(a['id'], stream)
                    stream.seek(0)
                    blobs[a['id']] = stream.read()
        module_tree = subprocess.check_output(['git', 'rev-parse', source + ':' + MODULE], text=True).strip()
        pinned = {path: subprocess.check_output(
            ['git', 'rev-parse', PINNED_MODULE + ':' + MODULE + '/' + path], text=True).strip() for path in REUSED}
        summary['platforms'] = validate(run, jobs, artifacts, blobs, source, run_id, attempt, module_tree, pinned)
        helper_hash = hashlib.sha256(Path(MODULE + '/EXReaderSdkTargetGuard.cmake').read_bytes()).hexdigest()
        summary['preloaded_target_controls'] = []
        for spec in PLATFORMS:
            name = 'reader-s14-font-library-%s-%s-%d-%d' % (spec['platform'], spec['label'], run_id, attempt)
            artifact, = [item for item in artifacts if item['name'] == name]
            with zipfile.ZipFile(io.BytesIO(blobs[artifact['id']])) as archive:
                report = strict_json(archive.read('preloaded/result.json'))
                logs = {row['name']: archive.read('preloaded/' + row['name'] + '.log') for row in report['cases']}
            validate_preloaded(report, logs, spec, source, run_id, attempt, helper_hash)
            for row_index in range(4):
                bad = copy.deepcopy(report)
                bad['cases'][row_index]['passed'] = False
                try:
                    validate_preloaded(bad, logs, spec, source, run_id, attempt, helper_hash)
                except ValueError:
                    pass
                else:
                    raise ValueError('preloaded negative control accepted')
            summary['preloaded_target_controls'].append({'platform': spec['platform'], 'sdk': spec['sdk'],
                                                        'controls': 4, 'strict_refusals': 4, 'accepted': True})
        summary['negative_tests'] = negative_tests(run, jobs, artifacts, blobs, source, run_id, attempt,
                                                   module_tree, pinned)
        summary['accepted'] = True
    except BaseException as error:
        summary['failures'].append(repr(error))
        raise
    finally:
        (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    (self_test() if '--self-test' in sys.argv else main())
