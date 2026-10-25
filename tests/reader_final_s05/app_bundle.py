#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read an Apple mobile app bundle into a simulator distribution install manifest.

Every fact comes from the bytes on the machine that runs the verification: the
Info.plist, the file tree, the Mach-O headers and load commands, and the code
signature that is actually present. An unsigned bundle is reported as unsigned
and keeps its simulator installation as simulator-only evidence. Nothing here
grants a device signature, an App Store delivery or a physical device run.
"""
import hashlib
import os
from pathlib import Path
import plistlib
import posixpath
import re
import stat
import struct
import subprocess
import sys

SCHEMA = 1
KNOWN_SDK_VERSIONS = ('3.40.0', '3.41.0')
CPU_NAMES = {0x0100000C: 'arm64', 0x01000007: 'x86_64', 12: 'arm', 7: 'i386'}
PLATFORM_NAMES = {1: 'macos', 2: 'ios', 3: 'tvos', 4: 'watchos', 5: 'bridgeos',
                  6: 'maccatalyst', 7: 'iossimulator', 8: 'tvossimulator',
                  9: 'watchossimulator', 10: 'driverkit', 11: 'visionos',
                  12: 'visionossimulator'}
MACHO_MAGICS = (0xFEEDFACE, 0xFEEDFACF)
FAT_MAGICS = (0xCAFEBABE, 0xCAFEBABF)
LC_BUILD_VERSION = 0x32
LC_VERSION_MIN_IPHONEOS = 0x25
IDENTIFIER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9-]*(\.[A-Za-z0-9][A-Za-z0-9-]*)+$')
LIMITS = [
    'simulator installation only; no physical device run',
    'no device signing identity, provisioning profile or notarization',
    'no App Store or TestFlight delivery',
    'file sharing is only the declaration found in the actual Info.plist',
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    value = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            value.update(block)
    return value.hexdigest()


def jsonable(value):
    """Make a plist value deterministic JSON without losing its meaning."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (bytes, bytearray)):
        return {'data_sha256': hashlib.sha256(bytes(value)).hexdigest(), 'bytes': len(value)}
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in sorted(value.items(), key=lambda row: str(row[0]))}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return {'value': str(value), 'type': type(value).__name__}


def packed_version(value):
    return '%d.%d.%d' % (value >> 16, (value >> 8) & 0xFF, value & 0xFF)


def version_tuple(value):
    if not isinstance(value, str):
        return None
    parts = re.findall(r'\d+', value)
    return tuple(int(part) for part in parts[:3]) if parts else None


def is_macho(path):
    try:
        with open(path, 'rb') as stream:
            head = stream.read(4)
    except OSError:
        return False
    if len(head) != 4:
        return False
    little = struct.unpack('<I', head)[0]
    big = struct.unpack('>I', head)[0]
    return little in MACHO_MAGICS + FAT_MAGICS or big in MACHO_MAGICS + FAT_MAGICS


def parse_mach_header(data, base):
    require(base + 28 <= len(data), 'truncated Mach-O header')
    little = struct.unpack_from('<I', data, base)[0]
    big = struct.unpack_from('>I', data, base)[0]
    if little in MACHO_MAGICS:
        endian, magic = '<', little
    elif big in MACHO_MAGICS:
        endian, magic = '>', big
    else:
        raise ValueError('not a Mach-O header')
    wide = magic == 0xFEEDFACF
    cputype, _cpusubtype = struct.unpack_from(endian + 'II', data, base + 4)
    ncmds, _sizeofcmds = struct.unpack_from(endian + 'II', data, base + 16)
    offset = base + (32 if wide else 28)
    commands = []
    platform = None
    minimum_os = None
    sdk = None
    for _index in range(ncmds):
        require(offset + 8 <= len(data), 'truncated load command')
        cmd, cmdsize = struct.unpack_from(endian + 'II', data, offset)
        require(cmdsize >= 8 and offset + cmdsize <= len(data), 'invalid load command size')
        commands.append({'cmd': cmd, 'offset': offset, 'size': cmdsize})
        if cmd == LC_BUILD_VERSION and cmdsize >= 24:
            value, minimum, sdk_value = struct.unpack_from(endian + 'III', data, offset + 8)
            platform = PLATFORM_NAMES.get(value, 'platform-%d' % value)
            minimum_os = packed_version(minimum)
            sdk = packed_version(sdk_value)
        elif cmd == LC_VERSION_MIN_IPHONEOS and cmdsize >= 16:
            minimum, sdk_value = struct.unpack_from(endian + 'II', data, offset + 8)
            platform = 'ios'
            minimum_os = packed_version(minimum)
            sdk = packed_version(sdk_value)
        offset += cmdsize
    return {'cputype': CPU_NAMES.get(cputype, 'cpu-0x%x' % cputype), 'cputype_raw': cputype,
            'endian': endian, 'offset': base, 'platform': platform,
            'minimum_os': minimum_os, 'sdk': sdk, 'commands': commands}


def parse_binary(path):
    data = Path(path).read_bytes()
    require(len(data) >= 8, 'truncated Mach-O: ' + str(path))
    big = struct.unpack_from('>I', data, 0)[0]
    if big in FAT_MAGICS:
        count = struct.unpack_from('>I', data, 4)[0]
        require(count > 0 and count <= 64, 'invalid fat slice count')
        width = 32 if big == 0xCAFEBABF else 20
        offset = 8
        slices = []
        for _index in range(count):
            require(offset + width <= len(data), 'truncated fat header')
            if big == 0xCAFEBABF:
                _cpu, _sub, base, size, _align, _reserved = struct.unpack_from('>IIQQII', data, offset)
            else:
                _cpu, _sub, base, size, _align = struct.unpack_from('>IIIII', data, offset)
            require(size > 0 and base + size <= len(data), 'invalid fat slice bounds')
            slices.append(parse_mach_header(data, base))
            offset += width
        return {'fat': True, 'bytes': len(data), 'slices': slices}
    return {'fat': False, 'bytes': len(data), 'slices': [parse_mach_header(data, 0)]}


def symlink_fact(app, path):
    target = os.readlink(path)
    relative = path.relative_to(app).as_posix()
    if os.path.isabs(target):
        escapes = True
    else:
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(relative), target))
        escapes = resolved == '..' or resolved.startswith('../')
    return {'path': relative, 'target': target, 'absolute': os.path.isabs(target), 'escapes': escapes}


def walk(app):
    files = []
    symlinks = []
    special = []
    for root, dirnames, filenames in os.walk(str(app), followlinks=False):
        root_path = Path(root)
        kept = []
        for name in dirnames:
            path = root_path / name
            if path.is_symlink():
                symlinks.append(symlink_fact(app, path))
            else:
                kept.append(name)
        dirnames[:] = kept
        for name in filenames:
            path = root_path / name
            relative = path.relative_to(app).as_posix()
            if path.is_symlink():
                symlinks.append(symlink_fact(app, path))
                continue
            mode = os.lstat(path).st_mode
            if not stat.S_ISREG(mode):
                special.append({'path': relative, 'mode': oct(stat.S_IMODE(mode))})
                continue
            files.append({'path': relative, 'bytes': os.lstat(path).st_size,
                          'sha256': sha256(path), 'mode': oct(stat.S_IMODE(mode))})
    return files, symlinks, special


def signature(app):
    entry = {'signed': False, 'state': 'absent', 'verify': None, 'verify_log': '',
             'identifier': None, 'team_identifier': None, 'authorities': [],
             'entitlements': None, 'entitlements_sha256': None, 'entitlements_error': None,
             'bundle_sealed': (Path(app) / '_CodeSignature' / 'CodeResources').is_file(),
             'tool': 'codesign'}
    if sys.platform != 'darwin':
        entry['state'] = 'unavailable'
        entry['tool'] = 'not-darwin'
        return entry
    describe = subprocess.run(['codesign', '-d', '--verbose=4', str(app)],
                              capture_output=True, text=True)
    log = describe.stderr or ''
    entry['describe_exit'] = describe.returncode
    if describe.returncode != 0:
        entry['state'] = 'absent'
        entry['verify_log'] = log.strip()[-4000:]
        return entry
    entry['signed'] = True
    for line in log.splitlines():
        if line.startswith('Identifier='):
            entry['identifier'] = line.split('=', 1)[1].strip()
        elif line.startswith('TeamIdentifier='):
            entry['team_identifier'] = line.split('=', 1)[1].strip()
        elif line.startswith('Authority='):
            entry['authorities'].append(line.split('=', 1)[1].strip())
    verify = subprocess.run(['codesign', '--verify', '--deep', '--strict', '--verbose=2', str(app)],
                            capture_output=True, text=True)
    entry['verify'] = verify.returncode == 0
    entry['verify_log'] = ((verify.stdout or '') + (verify.stderr or '')).strip()[-4000:]
    entry['state'] = 'ad-hoc' if (not entry['authorities'] or
                                  all('adhoc' in value.lower() or value.startswith('-') for value in entry['authorities'])) else 'signed'
    rights = subprocess.run(['codesign', '-d', '--entitlements', ':-', str(app)],
                            capture_output=True, text=True)
    raw = (rights.stdout or '').strip()
    if raw:
        entry['entitlements_sha256'] = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        try:
            value = plistlib.loads(raw.encode('utf-8'))
            require(isinstance(value, dict), 'entitlements are not a dictionary')
            entry['entitlements'] = jsonable(value)
        except Exception as error:  # record, never accept a half parsed entitlement set
            entry['entitlements_error'] = str(error)
    return entry


def read_info(app):
    path = app / 'Info.plist'
    if not path.is_file():
        return {'path': 'Info.plist', 'exists': False, 'error': 'Info.plist is missing',
                'sha256': None, 'format': None, 'keys': {}}
    raw = path.read_bytes()
    entry = {'path': 'Info.plist', 'exists': True,
             'format': 'binary' if raw[:8] == b'bplist00' else 'xml',
             'sha256': hashlib.sha256(raw).hexdigest(), 'keys': {}, 'error': None}
    try:
        value = plistlib.loads(raw)
        require(isinstance(value, dict), 'Info.plist is not a dictionary')
        entry['keys'] = {str(key): jsonable(item) for key, item in sorted(value.items(), key=lambda row: str(row[0]))}
    except Exception as error:
        entry['error'] = str(error)
    return entry


def nested_code(app, files, binaries):
    known = {entry['path']: entry for entry in binaries}
    paths = {entry['path'] for entry in files}
    folders = sorted({posixpath.join(*part.split('/')[:2]) for part in paths
                      if part.startswith('Frameworks/') and part.split('/')[1].endswith('.framework')})
    folders += sorted({posixpath.join(*part.split('/')[:2]) for part in paths
                       if part.startswith('PlugIns/') and part.split('/')[1].endswith('.appex')})
    records = []
    for folder in sorted(set(folders)):
        kind = 'framework' if folder.endswith('.framework') else 'plugin'
        record = {'path': folder, 'kind': kind, 'info_plist': False, 'executable': None,
                  'binary': False, 'platforms': []}
        info_path = app / folder / 'Info.plist'
        if info_path.is_file():
            record['info_plist'] = True
            try:
                value = plistlib.loads(info_path.read_bytes())
                record['executable'] = value.get('CFBundleExecutable')
                record['nested_identifier'] = value.get('CFBundleIdentifier')
            except Exception as error:
                record['error'] = str(error)
        executable = record.get('executable')
        if executable:
            inner = posixpath.join(folder, executable)
            if inner in known:
                record['binary'] = True
                record['platforms'] = sorted({str(item['platform']) for item in known[inner]['slices']})
                record['executable_sha256'] = known[inner]['sha256']
        records.append(record)
    loose = []
    for entry in files:
        parts = entry['path'].split('/')
        if parts[0] != 'Frameworks' or len(parts) != 2:
            continue
        if parts[1].endswith('.dylib') and entry['path'] not in known:
            loose.append(entry['path'])
    return {'folders': records, 'loose_binaries': loose}


def manifest(app, with_files=True):
    app = Path(app).absolute()
    require(app.is_dir() and app.suffix == '.app', 'not an .app bundle: ' + str(app))
    info = read_info(app)
    keys = info.get('keys') or {}
    files, symlinks, special = walk(app)
    if not with_files:
        for entry in files:
            entry['sha256'] = None
    binaries = []
    for entry in files:
        path = app / entry['path']
        if not is_macho(path):
            continue
        try:
            parsed = parse_binary(path)
            binaries.append({'path': entry['path'], 'sha256': entry['sha256'],
                             'bytes': entry['bytes'], 'fat': parsed['fat'],
                             'slices': [{'cputype': item['cputype'], 'platform': item['platform'],
                                         'minimum_os': item['minimum_os'], 'sdk': item['sdk'],
                                         'command_count': len(item['commands'])}
                                        for item in parsed['slices']]})
        except Exception as error:
            binaries.append({'path': entry['path'], 'sha256': entry['sha256'],
                             'bytes': entry['bytes'], 'error': str(error), 'slices': []})
    executable = keys.get('CFBundleExecutable')
    executable_entry = next((entry for entry in files if entry['path'] == executable), None) if executable else None
    executable_binary = next((item for item in binaries if item['path'] == executable), None) if executable else None
    file_sharing = {'UIFileSharingEnabled': keys.get('UIFileSharingEnabled'),
                    'LSSupportsOpeningDocumentsInPlace': keys.get('LSSupportsOpeningDocumentsInPlace'),
                    'declared_in': 'Info.plist'}
    fixture_flag = bool(keys.get('S05Fixture'))
    return {
        'schema': SCHEMA,
        'reading': 'bundle bytes on this machine',
        'app': {'name': app.name, 'bytes': sum(entry['bytes'] for entry in files),
                'files': len(files), 'directories': len({posixpath.dirname(entry['path']) for entry in files})},
        'info_plist': info,
        'product': {key: keys.get(key) for key in
                    ('CFBundleIdentifier', 'CFBundleName', 'CFBundleDisplayName', 'CFBundlePackageType',
                     'CFBundleShortVersionString', 'CFBundleVersion', 'MinimumOSVersion',
                     'CFBundleSupportedPlatforms', 'UIDeviceFamily', 'LSRequiresIPhoneOS',
                     'UISupportedInterfaceOrientations', 'UISupportedInterfaceOrientations~ipad')},
        'source': {'EXRSourceSHA': keys.get('EXRSourceSHA'), 'EXRSDKVersion': keys.get('EXRSDKVersion'),
                   'S05Fixture': fixture_flag},
        'file_sharing': file_sharing,
        'executable': {'name': executable, 'present': executable_entry is not None,
                       'mode': executable_entry['mode'] if executable_entry else None,
                       'bytes': executable_entry['bytes'] if executable_entry else None,
                       'sha256': executable_entry['sha256'] if executable_entry else None,
                       'macho': executable_binary is not None},
        'binaries': binaries,
        'nested': nested_code(app, files, binaries),
        'resources': {'files': files, 'count': len(files),
                      'bytes': sum(entry['bytes'] for entry in files),
                      'symlinks': symlinks, 'special': special,
                      'assets_car': any(entry['path'].endswith('.car') for entry in files),
                      'frameworks': sorted({entry['path'].split('/')[1] for entry in files
                                            if entry['path'].startswith('Frameworks/') and
                                            len(entry['path'].split('/')) >= 2}),
                      'plugins': sorted({entry['path'].split('/')[1] for entry in files
                                         if entry['path'].startswith('PlugIns/') and
                                         len(entry['path'].split('/')) >= 2})},
        'signature': signature(app),
    }


def check(manifest_value, device_class, mode='fixture', runtime_version=None, expected_source=None):
    require(device_class in ('iphone', 'ipad'), 'unknown device class: ' + str(device_class))
    checks = []

    def add(ident, status, detail):
        checks.append({'id': ident, 'status': status, 'detail': detail})

    def passed(ident, condition, detail, failure='fail'):
        add(ident, 'pass' if condition else failure, detail)

    info = manifest_value.get('info_plist') or {}
    keys = info.get('keys') or {}
    product = manifest_value.get('product') or {}
    if not info.get('exists', True):
        add('bundle.info_plist', 'fail', info.get('error') or 'Info.plist is missing')
    elif info.get('error'):
        add('bundle.info_plist', 'fail', 'Info.plist does not parse: ' + str(info['error']))
    else:
        add('bundle.info_plist', 'pass',
            '%s plist sha256=%s keys=%d' % (info.get('format'), info.get('sha256'), len(keys)))
    readable = info.get('exists', True) and not info.get('error')

    identifier = product.get('CFBundleIdentifier')
    if not readable:
        add('bundle.identifier', 'fail', 'cannot read CFBundleIdentifier without Info.plist')
        add('bundle.package_type', 'fail', 'cannot read CFBundlePackageType without Info.plist')
        add('bundle.version', 'fail', 'cannot read the bundle version without Info.plist')
        add('bundle.platform', 'fail', 'cannot read CFBundleSupportedPlatforms without Info.plist')
        add('bundle.family', 'fail', 'cannot read UIDeviceFamily without Info.plist')
        add('bundle.minimum_os', 'fail', 'cannot read MinimumOSVersion without Info.plist')
    else:
        passed('bundle.identifier',
               isinstance(identifier, str) and bool(IDENTIFIER.match(identifier)),
               'CFBundleIdentifier=%r' % (identifier,))
        passed('bundle.package_type', product.get('CFBundlePackageType') == 'APPL',
               'CFBundlePackageType=%r' % (product.get('CFBundlePackageType'),))
        short_version = product.get('CFBundleShortVersionString')
        build_version = product.get('CFBundleVersion')
        passed('bundle.version',
               bool(short_version) and bool(build_version) and all(isinstance(value, str) for value in (short_version, build_version)),
               'CFBundleShortVersionString=%r CFBundleVersion=%r' % (short_version, build_version))
        platforms = product.get('CFBundleSupportedPlatforms')
        passed('bundle.platform',
               isinstance(platforms, list) and platforms == ['iPhoneSimulator'],
               'CFBundleSupportedPlatforms=%r' % (platforms,))
        family = product.get('UIDeviceFamily')
        wanted = 1 if device_class == 'iphone' else 2
        passed('bundle.family',
               isinstance(family, list) and wanted in family,
               'UIDeviceFamily=%r required=%d for %s' % (family, wanted, device_class))
        minimum = version_tuple(product.get('MinimumOSVersion'))
        runtime = version_tuple(runtime_version)
        if minimum is None:
            add('bundle.minimum_os', 'fail', 'MinimumOSVersion is missing or unparsable: %r' % (product.get('MinimumOSVersion'),))
        elif runtime is None:
            add('bundle.minimum_os', 'skip', 'MinimumOSVersion=%s; no simulator runtime recorded' % (product.get('MinimumOSVersion'),))
        else:
            passed('bundle.minimum_os', minimum <= runtime,
                   'MinimumOSVersion=%s simulator=%s' % (product.get('MinimumOSVersion'), runtime_version))

    executable = manifest_value.get('executable') or {}
    mode_bits = executable.get('mode')
    executable_mode = int(mode_bits, 8) if isinstance(mode_bits, str) else 0
    passed('bundle.executable',
           bool(executable.get('name')) and executable.get('present') is True and
           executable.get('macho') is True and bool(executable_mode & 0o111),
           'CFBundleExecutable=%r present=%r macho=%r mode=%s' % (executable.get('name'), executable.get('present'),
                                                                executable.get('macho'), mode_bits))

    source = manifest_value.get('source') or {}
    if mode in ('fixture', 'producer'):
        passed('bundle.source_binding', source.get('EXRSourceSHA') == expected_source,
               'EXRSourceSHA=%r expected=%r' % (source.get('EXRSourceSHA'), expected_source))
    else:
        if source.get('EXRSourceSHA'):
            add('bundle.source_binding', 'pass', 'EXRSourceSHA=%r (diagnostic record)' % (source.get('EXRSourceSHA'),))
        else:
            add('bundle.source_binding', 'pending', 'no EXRSourceSHA in the packaged Info.plist')
    if mode == 'producer':
        passed('bundle.sdk_version', source.get('EXRSDKVersion') in KNOWN_SDK_VERSIONS,
               'EXRSDKVersion=%r known=%r' % (source.get('EXRSDKVersion'), list(KNOWN_SDK_VERSIONS)))
        passed('bundle.not_fixture', not source.get('S05Fixture'),
               'S05Fixture=%r' % (source.get('S05Fixture'),))
    elif mode == 'fixture':
        passed('bundle.fixture_marked', bool(source.get('S05Fixture')),
               'S05Fixture=%r' % (source.get('S05Fixture'),))
    else:
        add('bundle.sdk_version', 'pass' if source.get('EXRSDKVersion') else 'pending',
            'EXRSDKVersion=%r (diagnostic record)' % (source.get('EXRSDKVersion'),))
        add('bundle.not_fixture', 'pass' if not source.get('S05Fixture') else 'fail',
            'S05Fixture=%r' % (source.get('S05Fixture'),))

    binaries = manifest_value.get('binaries') or []
    main_path = executable.get('name')
    main_binary = next((item for item in binaries if item['path'] == main_path), None)
    main_cpus = [item['cputype'] for item in (main_binary or {}).get('slices', [])]
    passed('arch.main_arm64', 'arm64' in main_cpus,
           'executable=%r slices=%r' % (main_path, main_cpus))
    offenders = []
    no_arm64 = []
    for item in binaries:
        if item.get('error'):
            offenders.append('%s: %s' % (item['path'], item['error']))
            continue
        if not any(slice_value['cputype'] == 'arm64' for slice_value in item['slices']):
            no_arm64.append(item['path'])
        for slice_value in item['slices']:
            if slice_value['platform'] != 'iossimulator':
                offenders.append('%s: %s/%s' % (item['path'], slice_value['cputype'], slice_value['platform']))
    passed('arch.simulator_platform', not offenders,
           'binaries=%d offenders=%r' % (len(binaries), offenders[:8]))
    passed('arch.device_slice_absent',
           not any(slice_value['platform'] in ('ios', 'watchos', 'tvos') for item in binaries
                   for slice_value in item.get('slices', [])),
           'device platform slices=%r' % ([ '%s:%s' % (item['path'], slice_value['platform'])
                                           for item in binaries for slice_value in item.get('slices', [])
                                           if slice_value['platform'] in ('ios', 'watchos', 'tvos')][:8],))
    passed('arch.consistent_arm64', bool(binaries) and not no_arm64,
           'binaries without arm64=%r' % (no_arm64[:8],))

    nested = manifest_value.get('nested') or {'folders': [], 'loose_binaries': []}
    nested_problems = list(nested.get('loose_binaries') or [])
    for folder in nested.get('folders') or []:
        if not folder.get('info_plist'):
            nested_problems.append(folder['path'] + ' has no Info.plist')
        if not folder.get('executable'):
            nested_problems.append(folder['path'] + ' declares no CFBundleExecutable')
        elif not folder.get('binary'):
            nested_problems.append(folder['path'] + '/' + str(folder['executable']) + ' is not a Mach-O binary')
        elif folder.get('platforms') and folder['platforms'] != ['iossimulator']:
            nested_problems.append(folder['path'] + ' platforms=' + repr(folder.get('platforms')))
    passed('arch.nested_code', not nested_problems,
           'nested folders=%d loose=%r problems=%r' % (len(nested.get('folders') or []),
                                                       nested.get('loose_binaries'), nested_problems[:8]))

    resources = manifest_value.get('resources') or {}
    files = resources.get('files') or []
    hashed = all(entry.get('sha256') for entry in files)
    passed('resources.inventory', bool(files) and hashed,
           'files=%d bytes=%r hashed=%r' % (len(files), resources.get('bytes'), hashed))
    symlinks = resources.get('symlinks') or []
    escaping = [entry for entry in symlinks if entry.get('absolute') or entry.get('escapes')]
    passed('resources.symlink', not escaping,
           'symlinks=%d escaping=%r' % (len(symlinks), [(entry['path'], entry['target']) for entry in escaping[:8]]))
    special = resources.get('special') or []
    passed('resources.special', not special, 'special files=%r' % (special[:8],))
    seen = {}
    collisions = []
    for entry in files:
        lowered = entry['path'].lower()
        if lowered in seen:
            collisions.append((seen[lowered], entry['path']))
        else:
            seen[lowered] = entry['path']
    passed('resources.case_collision', not collisions, 'case collisions=%r' % (collisions[:8],))

    signature_value = manifest_value.get('signature') or {}
    signature_state = signature_value.get('state')
    sealed = signature_value.get('bundle_sealed') is True
    signature_log = (signature_value.get('verify_log') or '')[-400:]
    if not signature_value.get('signed'):
        add('signature.verify', 'pending',
            'bundle is not signed (state=%r); a simulator installation does not need a signature and no signing is granted'
            % (signature_state,))
    elif signature_state == 'ad-hoc' and not sealed:
        add('signature.verify', 'pending',
            'executable-only ad-hoc signature without _CodeSignature/CodeResources (verify=%r); the executable is signed but the bundle is not, so no signing is established and none is granted; log=%r'
            % (signature_value.get('verify'), signature_log))
    else:
        passed('signature.verify', signature_value.get('verify') is True,
               'state=%r sealed=%r authorities=%r log=%r' % (signature_state, sealed,
                                                             (signature_value.get('authorities') or [])[:3],
                                                             signature_log))
    rights = signature_value.get('entitlements')
    if signature_value.get('signed') and signature_value.get('entitlements_error'):
        add('entitlements.parse', 'fail', 'entitlements do not parse: ' + str(signature_value['entitlements_error']))
        rights = None
    elif isinstance(rights, dict) and rights:
        add('entitlements.parse', 'pass', 'entitlements sha256=%s keys=%d' % (signature_value.get('entitlements_sha256'), len(rights)))
    elif signature_value.get('signed'):
        add('entitlements.parse', 'skip', 'signed bundle carries no entitlements')
    else:
        add('entitlements.parse', 'skip', 'unsigned bundle carries no entitlements')
    if isinstance(rights, dict):
        private = sorted(key for key in rights if str(key).startswith('com.apple.private.'))
        passed('entitlements.no_private', not private, 'private entitlements=%r' % (private,))
        application = rights.get('application-identifier')
        team = rights.get('com.apple.developer.team-identifier')
        if application and team and isinstance(application, str) and isinstance(team, str):
            passed('entitlements.application_identifier', application.startswith(team + '.'),
                   'application-identifier=%r team=%r' % (application, team))
        else:
            add('entitlements.application_identifier', 'skip',
                'application-identifier=%r team=%r' % (application, team))
        debuggable = rights.get('get-task-allow')
        if debuggable is True:
            add('entitlements.debug_marker', 'pending', 'get-task-allow=true: debug build marker, no device signing granted')
        else:
            add('entitlements.debug_marker', 'skip', 'get-task-allow=%r' % (debuggable,))
    else:
        add('entitlements.no_private', 'skip', 'no entitlement set to inspect')
        add('entitlements.application_identifier', 'skip', 'no entitlement set to inspect')
        add('entitlements.debug_marker', 'skip', 'no entitlement set to inspect')
    return checks
