# SPDX-License-Identifier: MIT
"""Distinct diagnostic protocol; never substitutes for strict native acceptance."""
import json
import copy
import hashlib
from pathlib import Path
import plistlib
import re
import struct
import xml.etree.ElementTree as ET
from contract import BASE, BUNDLE, ROOT, STAGES, guard, require, sha

CASE = 'testDiagnosticContinuationRememberUpdateRestart'
ENTITLEMENT_FILE = ROOT / 'tests/apple_password_privacy_20261028/ios_simulator.entitlements'
ENTITLEMENTS = {'application-identifier': BUNDLE, 'keychain-access-groups': [BUNDLE], 'get-task-allow': True}
APPLEDOUBLE_LIMIT = 16 * 1024 * 1024


def appledouble_content(data):
    """Bounded Apple copyfile layout classification, NEVER admission/exclusion.

    Reference: Apple's copyfile.c AppleDouble/ATTR structures, pinned at
    https://github.com/apple-oss-distributions/copyfile/blob/9f91eb6ced021952278816cdc76ad68da8631ccb/copyfile.c
    and RFC1740. Only this exact two-entry layout is understood. A
    resource fork or xattr may contain executable/private data: structural
    validity does not establish harmlessness, provenance or semantic safety.
    """
    require(type(data) is bytes and 82 <= len(data) <= APPLEDOUBLE_LIMIT, 'metadata unsupported size')
    magic, version, filler, count = struct.unpack_from('>II16sH', data)
    require(magic == 0x00051607 and version == 0x00020000 and count == 2 and
            filler in (b'Mac OS X        ', bytes(16)), 'metadata unsupported header')
    finder, resource = [struct.unpack_from('>III', data, offset) for offset in (26, 38)]
    require(finder[0:2] == (9, 50) and finder[2] >= 32 and resource[0] == 2 and
            resource[1] == 50 + finder[2] and resource[1] + resource[2] == len(data),
            'metadata unsupported entries')
    def content(value):
        return {'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest(), 'all_zero': not any(value)}
    report = {'layout': 'appledouble-v2-copyfile', 'entry_kinds': ['finder-info', 'resource-fork'],
        'finder_info': content(data[50:82]), 'resource_fork': content(data[resource[1]:]),
        'attributes': [], 'content_semantics_verified': False, 'namespace_accepted': False}
    if resource[1] == 82:
        report['attribute_layout'] = 'absent'
        return report
    require(resource[1] >= 120 and data[82:84] == bytes(2), 'metadata unsupported attribute header')
    fields = struct.unpack_from('>8I2H', data, 84)
    attr_magic, debug, total, start, length, r1, r2, r3, flags, count = fields
    require(attr_magic == 0x41545452 and total == resource[1] and 120 <= start <= min(total, 65554) and
            length == total - start and (r1, r2, r3, flags) == (0, 0, 0, 0) and count <= 4096,
            'metadata unsupported attribute header')
    cursor, names, regions = 120, set(), []
    known = {b'com.apple.quarantine': 'quarantine', b'com.apple.provenance': 'provenance',
        b'com.apple.acl.text': 'acl-text', b'com.apple.decmpfs': 'compressed-data',
        b'com.apple.FinderInfo': 'finder-info', b'com.apple.ResourceFork': 'resource-fork'}
    for unused in range(count):
        require(cursor + 11 <= start, 'metadata unsupported attribute entry')
        offset, size, entry_flags, name_length = struct.unpack_from('>IIHB', data, cursor)
        end = cursor + ((11 + name_length + 3) & ~3)
        require(2 <= name_length <= 128 and end <= start and entry_flags == 0,
                'metadata unsupported attribute entry')
        name = data[cursor + 11:cursor + 11 + name_length]
        require(name[-1:] == b'\x00' and b'\x00' not in name[:-1] and name[:-1] not in names and
                not any(data[cursor + 11 + name_length:end]), 'metadata unsupported attribute name')
        try: name[:-1].decode('utf-8', errors='strict')
        except UnicodeDecodeError: raise RuntimeError('metadata unsupported attribute name') from None
        names.add(name[:-1]); cursor = end
        require((size == 0 and offset == 0) or (start <= offset <= total and size <= total - offset),
                'metadata unsupported attribute range')
        if size: regions.append((offset, offset + size))
        report['attributes'].append(dict(content(data[offset:offset + size]),
            name_kind=known.get(name[:-1], 'other'), name_sha256=hashlib.sha256(name[:-1]).hexdigest()))
    require(not any(data[cursor:start]), 'metadata unsupported attribute padding')
    end = start
    for left, right in sorted(regions):
        require(left >= end and not any(data[end:left]), 'metadata unsupported attribute overlap')
        end = right
    require(not any(data[end:total]), 'metadata unsupported attribute padding')
    report['attribute_layout'] = 'copyfile-attr'
    report['debug_tag_zero'] = debug == 0
    return report


def admission_tool(lifecycle, evidence, role, argv, commands):
    """Same bounded owned process path for signing, inspection and controls."""
    require(role in {'pre-sign-display', 'pre-sign-verify', 'pre-sign-archive', 'host-sign',
        'post-sign-display', 'post-sign-verify', 'post-sign-archive', 'installed-path',
        'installed-display', 'installed-verify', 'installed-archive'}, 'unknown admission command')
    done = lifecycle.command(argv, cap=30, check=False, cwd=ROOT, max_capture=None)
    folder = evidence / 'ios-admission'; folder.mkdir(mode=0o700, exist_ok=True)
    (folder / (role + '.stdout')).write_bytes(done.stdout)
    (folder / (role + '.stderr')).write_bytes(done.stderr)
    # Pre-sign verification is evidence of the old admission state, not a
    # required-success native command. Exact exits remain in its phase record.
    if role not in ('pre-sign-display', 'pre-sign-verify'):
        commands.append({'role': 'admission-' + role, 'exit': done.returncode})
    return done


def exact_entitlements(data):
    """Only the bounded XML dictionary; duplicate keys must not be collapsed."""
    require(type(data) is bytes and 0 < len(data) <= 65536 and b'<!ENTITY' not in data,
            'unsupported entitlement input')
    try:
        root = ET.fromstring(data)
        require(root.tag == 'plist' and root.attrib == {'version': '1.0'} and len(root) == 1 and
                root[0].tag == 'dict' and not root[0].attrib, 'entitlement plist shape differs')
        nodes = list(root[0]); keys = []
        require(len(nodes) == 6, 'entitlement key inventory differs')
        for index in range(0, len(nodes), 2):
            key, value = nodes[index:index + 2]
            require(key.tag == 'key' and not key.attrib and not list(key) and key.text not in keys,
                    'duplicate or malformed entitlement key')
            keys.append(key.text)
            require(not value.attrib, 'entitlement value attributes differ')
            if key.text == 'get-task-allow':
                require(value.tag == 'true' and not list(value) and not (value.text or '').strip(), 'entitlement boolean differs')
            elif key.text == 'application-identifier':
                require(value.tag == 'string' and not list(value) and value.text == BUNDLE, 'entitlement application differs')
            elif key.text == 'keychain-access-groups':
                require(value.tag == 'array' and len(value) == 1 and value[0].tag == 'string' and
                        not value[0].attrib and not list(value[0]) and value[0].text == BUNDLE,
                        'entitlement access group differs')
            else: require(False, 'unexpected entitlement key')
        parsed = plistlib.loads(data)
        require(parsed == ENTITLEMENTS and type(parsed['get-task-allow']) is bool,
                'entitlement dictionary differs')
    except (ET.ParseError, plistlib.InvalidFileException, ValueError, TypeError):
        raise RuntimeError('malformed entitlement plist') from None
    return dict(ENTITLEMENTS)


def entitlement_linker_token(path):
    value = str(path)
    require(Path(value).is_absolute() and not any(char in value for char in ',\x00\r\n'), 'invalid entitlement linker path')
    return '-Wl,-sectcreate,__TEXT,__entitlements,' + value


def verify_continuation_project(before, after, probe, entitlement, platform):
    """Exact dictionaries; only test reference and the iOS app linker token differ."""
    require(platform in ('macos', 'iphone', 'ipad'), 'invalid continuation project platform')
    expected = copy.deepcopy(before)
    objects = expected['objects']
    matches = [key for key, item in objects.items() if item.get('isa') == 'PBXFileReference' and
               Path(item.get('path', '')).name == 'PasswordPrivacyUITests.swift']
    require(len(matches) == 1, 'strict test file reference differs')
    objects[matches[0]]['path'] = str(probe); objects[matches[0]]['sourceTree'] = '<absolute>'
    if platform != 'macos':
        targets = [item for item in objects.values() if item.get('isa') == 'PBXNativeTarget' and
                   item.get('name') == 'EXReaderHost-iOS' and item.get('productType') == 'com.apple.product-type.application']
        require(len(targets) == 1, 'exact iOS application target absent')
        configs = objects[targets[0]['buildConfigurationList']]['buildConfigurations']
        require(type(configs) is list and len(configs) == 2 and len(set(configs)) == 2 and
                {objects[key]['name'] for key in configs} == {'Debug', 'Release'}, 'iOS application configurations differ')
        token = entitlement_linker_token(entitlement)
        for key in configs:
            settings = objects[key]['buildSettings']; flags = settings['OTHER_LDFLAGS']
            require(type(flags) is list and flags and all(type(flag) is str for flag in flags) and
                    not any('__entitlements' in flag or '-sectcreate' in flag for flag in flags), 'unexpected original linker flags')
            settings['OTHER_LDFLAGS'] = flags + [token]
    require(expected == after, 'continuation generated project delta differs')
    return {'exact_project_delta': True, 'ios_application_linker_only': platform != 'macos'}


def macho_entitlement_section(data):
    """Fail-closed thin little-endian 64-bit simulator executable reader.

    Layouts follow Apple's mach-o/loader.h; unsupported slices are refusals,
    never an absent-section result or admission inferred from project settings.
    """
    require(type(data) is bytes and 32 <= len(data) <= 256 * 1024 * 1024, 'unsupported executable size')
    magic, cpu, subtype, filetype, count, commands_size, flags, reserved = struct.unpack_from('<IiiIIIII', data)
    require(magic == 0xfeedfacf and cpu in (0x0100000c, 0x01000007) and filetype == 2 and
            0 < count <= 4096 and 8 * count <= commands_size <= len(data) - 32, 'unsupported simulator executable')
    cursor, end = 32, 32 + commands_size
    sections, platforms = [], []
    for unused in range(count):
        require(cursor + 8 <= end, 'truncated Mach-O load command')
        command, size = struct.unpack_from('<II', data, cursor)
        require(size >= 8 and size % 8 == 0 and cursor + size <= end, 'invalid Mach-O load command')
        if command == 0x32:  # LC_BUILD_VERSION; PLATFORM_IOSSIMULATOR == 7.
            require(size >= 24, 'truncated simulator platform command')
            platform, minimum, sdk, tools = struct.unpack_from('<IIII', data, cursor + 8)
            require(size == 24 + tools * 8, 'invalid simulator platform command')
            platforms.append(platform)
        if command == 0x19:  # LC_SEGMENT_64 and section_64.
            require(size >= 72, 'truncated segment command')
            segment = struct.unpack_from('<II16sQQQQiiII', data, cursor)
            segment_name, fileoff, filesize, nsects = segment[2], segment[5], segment[6], segment[9]
            require(nsects <= 4096 and size == 72 + 80 * nsects and fileoff + filesize <= len(data), 'invalid segment bounds')
            for index in range(nsects):
                section = struct.unpack_from('<16s16sQQIIIIIIII', data, cursor + 72 + 80 * index)
                if section[0] == b'__entitlements\x00\x00':
                    require(segment_name == b'__TEXT' + b'\x00' * 10 and section[1] == segment_name and
                            section[8] & 0xff == 0, 'unexpected entitlement section kind')
                    length, offset = section[3], section[4]
                    require(0 < length <= 65536 and offset >= end and fileoff <= offset and
                            offset + length <= fileoff + filesize, 'invalid entitlement section bounds')
                    sections.append(data[offset:offset + length])
        cursor += size
    require(cursor == end and platforms == [7], 'simulator platform identity differs')
    require(len(sections) == 1, 'entitlement section absent or duplicate')
    exact_entitlements(sections[0])
    return {'format': 'thin-little-endian-64', 'architecture': 'arm64' if cpu == 0x0100000c else 'x86_64',
            'platform': 'ios-simulator', 'section': '__TEXT,__entitlements', 'section_bytes': len(sections[0]),
            'section_sha256': hashlib.sha256(sections[0]).hexdigest(), 'expected_dictionary': True}


def signature_summary(display, verify_exit, require_valid=True):
    require(type(display) is bytes and len(display) <= 1024 * 1024 and type(verify_exit) is int,
            'signature evidence shape differs')
    lines = display.decode('utf-8', errors='strict').splitlines()
    fields = {}
    for key in ('Identifier', 'Signature', 'TeamIdentifier'):
        rows = [line[len(key) + 1:] for line in lines if line.startswith(key + '=')]
        require(len(rows) <= 1, 'duplicate signature metadata')
        fields[key] = rows[0] if rows else None
    valid = verify_exit == 0 and fields == {'Identifier': BUNDLE, 'Signature': 'adhoc', 'TeamIdentifier': 'not set'}
    if require_valid: require(valid, 'expected ad-hoc host signature absent')
    return {'verified': valid, 'kind': 'expected-ad-hoc' if valid else 'unverified-or-other',
            'identity_matches': fields['Identifier'] == BUNDLE, 'arbitrary_signature_text_printed': False}


def admission_app_identity(app, source, files):
    require(re.fullmatch(r'[0-9a-f]{40}', source) is not None and 'EXReaderHost' in files and 'Info.plist' in files,
            'admission app files absent')
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    require(info.get('CFBundleIdentifier') == BUNDLE and info.get('CFBundleExecutable') == 'EXReaderHost' and
            info.get('EXRSourceSHA') == source and info.get('EXRSDKVersion') == '3.42.0' and
            info.get('EXRPageThemeEnabled') is True, 'admission app identity differs')
    binary = app / 'EXReaderHost'
    require(binary.stat().st_size <= 256 * 1024 * 1024, 'unsupported executable size')
    section = macho_entitlement_section(binary.read_bytes())
    require(section['section_sha256'] == sha(ENTITLEMENT_FILE), 'linked entitlement source differs')
    libraries = {name: record for name, record in files.items() if name.startswith('Frameworks/')}
    require(libraries and 'Frameworks/libexreader.3.42.0.dylib' in libraries, 'admission packaged SDK absent')
    return {'binary': files['EXReaderHost'], 'info': files['Info.plist'], 'section': section,
            'libraries': libraries, 'files': files}


def verify_admission_transition(before, after, installed):
    def nonsignature_files(proof):
        return {name: value for name, value in proof['files'].items()
                if name != 'EXReaderHost' and not name.startswith('_CodeSignature/')}
    require(nonsignature_files(before) == nonsignature_files(after) and
            after['files'] == installed['files'], 'admission app resource substitution')
    require(before['info'] == after['info'] == installed['info'] and
            before['section'] == after['section'] == installed['section'] and
            before['libraries'] == after['libraries'] == installed['libraries'] and
            after['binary'] == installed['binary'], 'built or installed admission bytes differ')
    require(after['signature']['verified'] is True and installed['signature']['verified'] is True,
            'signed or installed admission unverified')
    return {'built_and_installed_verified': True, 'sdk_bytes_unchanged': True,
            'installed_matches_signed_host': True, 'original_osstatus_proven': False,
            'full_f10_accepted': False}


def case_name(value):
    require(re.findall(r'\btest[A-Za-z0-9_]+\b', value or '') == [CASE], 'unexpected diagnostic case identity')
    return CASE


def verdict(checks):
    require(set(checks) == set(STAGES) and all(type(value) is bool for value in checks.values()),
            'diagnostic strict checkpoint inventory incomplete')
    return {'diagnostic_only': True, 'accepted': False, 'full_f10_accepted': False,
            'strict_privacy_checks_passed': all(checks.values()),
            'failed_strict_checkpoints': [stage for stage in STAGES if not checks[stage]]}


def attachments(directory):
    stages, images = None, {}
    for group in json.loads((directory / 'manifest.json').read_text()):
        case_name(group.get('testIdentifier') or group.get('testName'))
        for item in group['attachments']:
            filename = item['exportedFileName']
            require(Path(filename).name == filename, 'unsafe attachment')
            path = directory / filename
            name = item['suggestedHumanReadableName']
            if name.startswith('privacy-stages.json'):
                require(stages is None, 'duplicate native stages')
                stages = json.loads(path.read_text())
            for stage in STAGES:
                role = 'privacy-' + stage
                if name.startswith(role + '_') or name == role + '.png':
                    require(stage not in images and path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'), 'invalid native screenshot')
                    images[stage] = {'file': str(path.relative_to(directory.parent)), 'sha256': sha(path)}
    require(stages is not None and stages['stages'] == STAGES and set(images) == set(STAGES), 'native stages/screenshots incomplete')
    require(re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', stages['profile']) is not None, 'invalid actual profile')
    require(stages['diagnostic_continuation'] is True and
            stages['operation'] == 'real Remember off and Update; not a dedicated Forget action', 'diagnostic operation mislabeled')
    return stages, images
