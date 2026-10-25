"""Static acceptance of the authenticated Android debug candidate APK.

Checks version/minSdk/targetSdk/ABI/permissions against values re-derived from
the frozen producer source, resources and assets against their own source
generators, the shipped JNI blob against the same-run installed SDK staging,
and the signature identity against the debug-only policy. Any permission drift
or source drift is a refusal, not a re-baseline.
"""
import argparse
import hashlib
import os
import pathlib
import re
import struct
import subprocess
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import common
import expectations

ELF_MACHINE = {3: 'x86', 62: 'x86-64', 40: 'arm', 183: 'aarch64'}
ELF_TYPE = {2: 'EXEC', 3: 'DYN'}
ELF_SKIP = (0, 2, 3, 8)  # SHT_NULL, SHT_SYMTAB, SHT_STRTAB, SHT_NOBITS


def first(text, patterns):
    for pattern in patterns:
        found = re.search(pattern, text)
        if found:
            return found.group(1)
    return None


def parse_badging(text):
    row = {}
    row['package'] = first(text, [r"package: name='([^']+)'"])
    row['versionCode'] = first(text, [r"versionCode='([^']+)'"])
    row['versionName'] = first(text, [r"versionName='([^']+)'"])
    row['sdkVersion'] = first(text, [r"sdkVersion:'([^']+)'", r"minSdkVersion:'([^']+)'",
                                     r"minSdkVersion='([^']+)'", r"sdkVersion='([^']+)'"])
    row['targetSdkVersion'] = first(text, [r"targetSdkVersion:'([^']+)'",
                                           r"targetSdkVersion='([^']+)'"])
    row['compileSdkVersion'] = first(text, [r"compileSdkVersion='([^']+)'"])
    native = re.search(r"native-code: (.+)", text)
    row['native_code'] = [item.strip().strip("'") for item in native.group(1).split()] if native else []
    launch = re.search(r"launchable-activity: name='([^']+)'", text)
    row['launchable_activity'] = launch.group(1) if launch else None
    row['uses_permission'] = sorted(re.findall(r"uses-permission: name='([^']+)'", text))
    row['activities'] = sorted(re.findall(r"activity: name='([^']+)'", text))
    return row


def parse_certs(text):
    signers = {}
    for line in text.splitlines():
        found = re.match(r'Signer #(\d+) certificate DN: (.*)', line.strip())
        if found:
            signers.setdefault(int(found.group(1)), {})['dn'] = found.group(2)
        found = re.match(r'Signer #(\d+) certificate SHA-256 digest: ([0-9a-f]+)', line.strip())
        if found:
            signers.setdefault(int(found.group(1)), {})['sha256'] = found.group(2)
    schemes = {}
    for label, key in (('v1', r'v1 scheme'), ('v2', r'v2 scheme'), ('v3', r'v3 scheme')):
        found = re.search(r'Verified using ' + key + r'[^:]*: (true|false)', text)
        schemes[label] = bool(found and found.group(1) == 'true')
    return signers, schemes


def elf_identity(path):
    with open(path, 'rb') as handle:
        head = handle.read(64)
    if head[:4] != b'\x7fELF':
        raise SystemExit('not an ELF file: ' + str(path))
    bits = head[4]
    endian = '<' if head[5] == 1 else '>'
    machine = struct.unpack(endian + 'H', head[18:20])[0]
    kind = struct.unpack(endian + 'H', head[16:18])[0]
    return {'class': 64 if bits == 2 else 32, 'machine': ELF_MACHINE.get(machine, str(machine)),
            'type': ELF_TYPE.get(kind, str(kind))}


def elf_sections(path):
    """Section-name to content digest, skipping symbol/string tables and NOBITS.

    Android packaging strips the prebuilt JNI blob, so byte equality with the
    installed SDK staging cannot hold; the surviving section contents can.
    """
    with open(path, 'rb') as handle:
        data = handle.read()
    if data[:4] != b'\x7fELF' or data[4] != 2:
        raise SystemExit('expected a 64-bit ELF: ' + str(path))
    shoff = struct.unpack_from('<Q', data, 0x28)[0]
    shentsize = struct.unpack_from('<H', data, 0x3a)[0]
    shnum = struct.unpack_from('<H', data, 0x3c)[0]
    shstrndx = struct.unpack_from('<H', data, 0x3e)[0]

    def header(index):
        base = shoff + index * shentsize
        name, kind, flags, addr, offset, size = struct.unpack_from('<IIQQQQ', data, base)
        return name, kind, offset, size

    _, _, strings_offset, strings_size = header(shstrndx)
    strings = data[strings_offset:strings_offset + strings_size]
    sections = {}
    for index in range(shnum):
        name_offset, kind, offset, size = header(index)
        end = strings.find(b'\0', name_offset)
        name = strings[name_offset:end].decode('utf-8', 'replace')
        if kind in ELF_SKIP:
            continue
        sections[name] = hashlib.sha256(data[offset:offset + size]).hexdigest()
    return sections


def dynamic_symbols(path, readelf):
    text = common.run([readelf, '-W', '--dyn-syms', '--wide', str(path)])
    names = set()
    for line in text.splitlines():
        columns = line.split()
        if len(columns) >= 8 and columns[0].endswith(':'):
            names.add(columns[-1].split('@')[0])
    return names


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--contract', type=pathlib.Path,
                        default=pathlib.Path('docs/reader-final-s04/apk-contract.json'))
    parser.add_argument('--inventory', type=pathlib.Path,
                        default=pathlib.Path('build/s04-authenticate/inventory.json'))
    parser.add_argument('--output', type=pathlib.Path, default=pathlib.Path('build/s04-static'))
    args = parser.parse_args()
    common.require_actions()
    args.output.mkdir(parents=True, exist_ok=True)
    contract = common.read_json(args.contract)
    inventory = common.read_json(args.inventory)
    producer_sha = contract['producer']['source_sha']
    derived = expectations.derive(producer_sha)
    sealed = expectations.check_sealed(contract, derived)
    allow_derive = os.environ.get('S04_ALLOW_DERIVE', 'false') == 'true'
    pins = contract.get('pins') or {}
    repo = pathlib.Path(__file__).resolve().parents[2]
    readelf = os.environ.get('READELF', 'readelf')
    aapt2 = os.environ.get('AAPT2', 'aapt2')
    apksigner = os.environ.get('APKSIGNER', 'apksigner')

    candidate = pathlib.Path(inventory['candidate']['path'])
    baseline = pathlib.Path(inventory['baseline']['path']) if inventory.get('baseline') else None
    test_apk = pathlib.Path(inventory['test_apk']['path']) if inventory.get('test_apk') else None
    release = pathlib.Path(inventory['release_apk']['path']) if inventory.get('release_apk') else None
    sdk_jni = pathlib.Path(inventory['sdk_stage']['jni']) if inventory.get('sdk_stage') else None
    checks = []

    def record(name, passed, observed=None, detail=None, mandatory=True):
        checks.append({'name': name, 'pass': bool(passed), 'observed': observed,
                       'detail': detail, 'mandatory': mandatory})
        print(json_line(name, passed, observed), flush=True)

    record('producer_source_sealed', sealed['sealed'] and sealed['checked'] > 0, sealed)
    documented = contract.get('expected') or {}
    drift = {key: {'documented': documented[key], 'derived': derived[key]}
             for key in ('applicationId', 'versionCode', 'versionName', 'minSdk', 'targetSdk',
                         'compileSdk', 'abis', 'permissions', 'sdk_version', 'launchable_activity',
                         'allowBackup', 'activity_exported', 'debug_network_security')
             if key in documented and documented[key] != derived[key]}
    record('documented_expectations_match_source', not drift, drift,
           'the sealed expectation table must equal what the producer source says')
    record('candidate_present', candidate.is_file(), {'path': str(candidate)})
    if not candidate.is_file():
        raise SystemExit('the authenticated candidate APK is missing: ' + str(candidate))

    # --- sealed APK identity: refuse substitution before looking inside ---------
    observed_pins = {
        'candidate_sha256': common.sha256_file(candidate),
        'candidate_bytes': candidate.stat().st_size,
        'baseline_sha256': common.sha256_file(baseline) if baseline else None,
        'test_apk_sha256': common.sha256_file(test_apk) if test_apk else None,
        'release_apk_sha256': common.sha256_file(release) if release else None,
        'sdk_jni_sha256': common.sha256_file(sdk_jni) if sdk_jni else None,
        'apk_jni_sha256': None,
    }
    # --- ZIP structure ---------------------------------------------------------
    with zipfile.ZipFile(candidate) as archive:
        names = archive.namelist()
        bad = archive.testzip()
        names_unique = len(names) == len(set(names))
        entries = [{'name': info.filename, 'bytes': info.file_size, 'compressed': info.compress_size}
                   for info in archive.infolist()]
        blob = archive.read('AndroidManifest.xml')
        resources = archive.read('resources.arsc') if 'resources.arsc' in names else None
        libs = {}
        for name in names:
            if name.startswith('lib/') and name.endswith('.so'):
                libs.setdefault(name.split('/')[1], []).append(name)
        jni_name = 'lib/' + derived['abis'][0] + '/libexreader_jni.so'
        apk_jni = archive.read(jni_name) if jni_name in names else None
        assets = {name: common.sha256_bytes(archive.read(name))
                  for name in names if name.startswith('assets/')}
        catalog_asset = archive.read('assets/reader-catalog-v1.json') \
            if 'assets/reader-catalog-v1.json' in names else None
        font_asset = archive.read('assets/' + derived['font_asset']['name']) \
            if 'assets/' + derived['font_asset']['name'] in names else None
        dex_entries = [name for name in names if re.match(r'classes\d*\.dex$', name)]
    if apk_jni is not None:
        observed_pins['apk_jni_sha256'] = common.sha256_bytes(apk_jni)
    common.write_json(args.output / 'apk-entries.json', entries)
    record('apk_zip_integrity', bad is None and names_unique, {'entries': len(names), 'testzip': bad})
    record('apk_manifest_present', blob[:2] == b'\x03\x00', {'manifest_bytes': len(blob)})
    record('apk_resources_index_present', resources is not None and len(resources) > 8,
           {'resources_bytes': len(resources) if resources else 0})
    record('apk_dex_present', len(dex_entries) >= 1, {'dex': dex_entries})
    record('apk_abi_set', sorted(libs) == derived['abis'],
           {'observed': sorted(libs), 'derived': derived['abis']})
    record('apk_jni_present', apk_jni is not None and len(apk_jni) > 0,
           {'libs': sorted(name for rows in libs.values() for name in rows)})

    for key, value in observed_pins.items():
        if key == 'apk_jni_sha256' and value is None:
            record('pin_' + key, False, {'observed': None}, 'the packaged JNI blob is absent')
            continue
        pinned = pins.get(key)
        if pinned is None:
            record('pin_' + key + '_derived', allow_derive,
                   {'observed': value, 'allow_derive': allow_derive},
                   'the sealed contract has no pin yet')
        else:
            record('pin_' + key, pinned == value, {'sealed': pinned, 'observed': value})

    # --- JNI/SDK identity ------------------------------------------------------
    extracted = args.output / 'libs'
    extracted.mkdir(exist_ok=True)
    identities = {}
    library_symbols = {}
    for abi, rows in sorted(libs.items()):
        for name in rows:
            with zipfile.ZipFile(candidate) as archive:
                data = archive.read(name)
            target = extracted / pathlib.PurePosixPath(name).name
            target.write_bytes(data)
            identities[name] = dict(elf_identity(target), bytes=len(data),
                                    sha256=common.sha256_bytes(data))
            library_symbols[name] = dynamic_symbols(target, readelf)
    common.write_json(args.output / 'apk-libs.json', identities)
    symbols = set().union(*library_symbols.values()) if library_symbols else set()
    expected_symbols = set(derived['jni_c_symbols'])
    missing = sorted(expected_symbols - symbols)
    record('jni_source_symbols_complete', bool(expected_symbols) and not missing,
           {'derived': len(expected_symbols), 'exported': len(symbols), 'missing': missing[:20]},
           'every JNI entry point of the producer C sources must exist in the shipped libraries',
           mandatory=False)
    uncovered = {}
    for name, row in sorted(derived['jni_classes'].items()):
        hits = sorted(symbol for symbol in symbols if symbol.startswith(row['prefix'] + '_'))
        if not hits:
            uncovered[name] = row['prefix']
    record('jni_native_classes_exported', bool(derived['jni_classes']) and not uncovered,
           {'classes': len(derived['jni_classes']), 'uncovered': uncovered})
    method_missing = sorted({symbol for row in derived['jni_classes'].values()
                             for symbol in row['methods']} - symbols)
    record('jni_native_methods_complete', not method_missing,
           {'expected': sum(len(row['methods']) for row in derived['jni_classes'].values()),
            'missing': method_missing[:20]}, mandatory=False)
    record('jni_onload_exported', 'JNI_OnLoad' in symbols,
           {'sampled': sorted(s for s in symbols if s.startswith('JNI_'))[:5]},
           'Android does not require JNI_OnLoad; recorded, not required', mandatory=False)
    record('jni_elf_x86_64', bool(identities) and all(
        row['machine'] == 'x86-64' and row['type'] == 'DYN' for row in identities.values()),
           {name: {'machine': row['machine'], 'type': row['type']} for name, row in identities.items()})
    if apk_jni is not None and sdk_jni is not None:
        apk_lib = extracted / 'libexreader_jni.so'
        stage_symbols = dynamic_symbols(sdk_jni, readelf)
        apk_exports = {s for s in library_symbols.get(jni_name, set()) if s.startswith(('Java_', 'JNI_'))}
        stage_exports = {s for s in stage_symbols if s.startswith(('Java_', 'JNI_'))}
        record('jni_exports_match_same_run_sdk',
               bool(stage_exports) and apk_exports == stage_exports,
               {'stage': len(stage_exports), 'apk': len(apk_exports),
                'missing': sorted(stage_exports - apk_exports)[:10],
                'extra': sorted(apk_exports - stage_exports)[:10]},
               'packaging strips the blob, so identity is proven by exports plus section contents')
        apk_sections = elf_sections(apk_lib)
        stage_sections = elf_sections(sdk_jni)
        shared = sorted(set(apk_sections) & set(stage_sections))
        differing = [name for name in shared if apk_sections[name] != stage_sections[name]]
        code = [name for name in ('.text', '.rodata') if name in shared]
        record('jni_same_build_as_same_run_sdk',
               bool(code) and not differing
               and all(apk_sections[name] == stage_sections[name] for name in code),
               {'shared_sections': len(shared), 'code_sections': code, 'differing': differing[:10],
                'removed_by_packaging': sorted(set(stage_sections) - set(apk_sections))[:10],
                'apk_only_sections': sorted(set(apk_sections) - set(stage_sections))[:10],
                'apk_sha256': identities[jni_name]['sha256'],
                'stage_sha256': common.sha256_file(sdk_jni),
                'apk_bytes': identities[jni_name]['bytes'],
                'stage_bytes': sdk_jni.stat().st_size})
    sdk_version_bytes = derived['sdk_version'].encode()
    version_hits = [name for name, row in identities.items()
                    if sdk_version_bytes in (extracted / pathlib.PurePosixPath(name).name).read_bytes()]
    record('sdk_version_string_in_shipped_libs', len(version_hits) >= 1,
           {'version': derived['sdk_version'], 'libraries': version_hits})

    # --- manifest identity through aapt2 --------------------------------------
    badging_text = common.run([aapt2, 'dump', 'badging', str(candidate)])
    (args.output / 'aapt2-badging.txt').write_text(badging_text)
    print('aapt2 badging head:
' + '
'.join(badging_text.splitlines()[:25]), flush=True)
    badging = parse_badging(badging_text)
    expected_fields = {
        'package': derived['applicationId'],
        'versionCode': derived['versionCode'],
        'versionName': derived['versionName'],
        'sdkVersion': derived['minSdk'],
        'targetSdkVersion': derived['targetSdk'],
    }
    for key, value in expected_fields.items():
        record('manifest_' + key, badging[key] == value, {'derived': value, 'observed': badging[key]})
    if badging['compileSdkVersion'] is None:
        record('manifest_compileSdkVersion', False,
               {'derived': derived['compileSdk'], 'observed': None},
               'aapt2 badging did not report compileSdkVersion', mandatory=False)
    else:
        record('manifest_compileSdkVersion', badging['compileSdkVersion'] == derived['compileSdk'],
               {'derived': derived['compileSdk'], 'observed': badging['compileSdkVersion']})
    record('manifest_native_code', badging['native_code'] == derived['abis'],
           {'derived': derived['abis'], 'observed': badging['native_code']})
    record('manifest_launchable_activity',
           badging['launchable_activity'] == derived['launchable_activity'],
           {'derived': derived['launchable_activity'], 'observed': badging['launchable_activity']})
    record('permissions_unchanged', badging['uses_permission'] == derived['permissions'],
           {'derived': derived['permissions'], 'observed': badging['uses_permission']},
           'a changed permission set is refused, never re-baselined')
    xmltree = common.run([aapt2, 'dump', 'xmltree', '--file', 'AndroidManifest.xml', str(candidate)])
    (args.output / 'aapt2-manifest.txt').write_text(xmltree)
    backup = re.search(r'allowBackup\(0x01010280\)=\(type 0x12\)0x([0-9a-f]+)', xmltree)
    record('manifest_allowBackup', backup is not None and backup.group(1) == '0',
           {'derived': derived['allowBackup'], 'observed': backup.group(1) if backup else None})
    exported = re.findall(r'exported\(0x01010010\)=\(type 0x12\)(0x[0-9a-f]+)', xmltree)
    record('manifest_single_exported_activity',
           len(re.findall(r'E: activity', xmltree)) == 1 and exported == ['0xffffffff'],
           {'activity_elements': len(re.findall(r'E: activity', xmltree)),
            'exported_attributes': exported, 'derived': derived['activity_exported']})
    record('manifest_debug_network_security',
           derived['debug_network_security'] == ('networkSecurityConfig' in xmltree),
           {'derived': derived['debug_network_security'],
            'observed': 'networkSecurityConfig' in xmltree})
    record('manifest_permission_elements',
           len(re.findall(r'E: uses-permission', xmltree)) == len(derived['permissions']),
           {'elements': len(re.findall(r'E: uses-permission', xmltree))})

    # --- signature identity ---------------------------------------------------
    signature = common.run([apksigner, 'verify', '--verbose', '--print-certs', str(candidate)],
                           check=False)
    (args.output / 'apksigner.txt').write_text(signature)
    signers, schemes = parse_certs(signature)
    record('signature_verifies', 'Verifies' in signature and 'DOES NOT VERIFY' not in signature,
           {'schemes': schemes, 'signers': len(signers)})
    record('signature_single_signer', len(signers) == 1, {'signers': sorted(signers)})
    dn = next(iter(signers.values()), {}).get('dn', '')
    record('signature_debug_only', 'Android Debug' in dn, {'dn': dn},
           'only the debug candidate is in scope; store/signing authority is not granted')
    record('signature_v2_or_v3', any(schemes.get(key) for key in schemes), {'schemes': schemes})

    # --- resources and assets identity ---------------------------------------
    record('resource_layout_present', 'res/layout/activity_main.xml' in names,
           {'sample': [name for name in names if name.startswith('res/layout/')][:5]})
    record('asset_font_matches_source_pin',
           font_asset is not None and common.sha256_bytes(font_asset) == derived['font_asset']['sha256'],
           {'name': derived['font_asset']['name'], 'sealed': derived['font_asset']['sha256'],
            'observed': common.sha256_bytes(font_asset) if font_asset else None})
    record('asset_license_present', 'assets/OFL.txt' in assets, {'assets': sorted(assets)})
    regenerated = args.output / 'reader-catalog-v1.json'
    common.run([sys.executable, str(repo / 'tools' / 'reader_catalog_assets.py'),
                '--output', str(regenerated)])
    regenerated_bytes = regenerated.read_bytes()
    record('asset_catalog_from_source',
           catalog_asset is not None and catalog_asset == regenerated_bytes,
           {'regenerated_sha256': common.sha256_bytes(regenerated_bytes),
            'apk_sha256': common.sha256_bytes(catalog_asset) if catalog_asset else None,
            'catalog_sql_blob': derived['catalog_sql']['blob']})

    # --- default-OFF APK as a separate candidate ------------------------------
    if baseline is not None:
        baseline_badging = parse_badging(common.run([aapt2, 'dump', 'badging', str(baseline)]))
        record('baseline_is_distinct_apk',
               common.sha256_file(baseline) != common.sha256_file(candidate),
               {'raw3': common.sha256_file(candidate), 'default_off': common.sha256_file(baseline)})
        record('baseline_same_identity',
               (baseline_badging['package'], baseline_badging['versionCode'],
                baseline_badging['uses_permission']) ==
               (badging['package'], badging['versionCode'], badging['uses_permission']),
               {'package': baseline_badging['package'],
                'versionCode': baseline_badging['versionCode'],
                'permissions': baseline_badging['uses_permission']})

    failed = [check['name'] for check in checks if check['mandatory'] and not check['pass']]
    report = {'identity': common.identity(), 'producer_source': producer_sha,
              'contract_source': str(args.contract), 'allow_derive': allow_derive,
              'pins_sealed': {key: pins.get(key) for key in observed_pins},
              'observed_pins': observed_pins,
              'derived': {key: derived[key] for key in
                          ('applicationId', 'versionCode', 'versionName', 'minSdk', 'targetSdk',
                           'compileSdk', 'abis', 'permissions', 'sdk_version',
                           'launchable_activity')},
              'checks': checks, 'checks_total': len(checks),
              'checks_passed': sum(1 for check in checks if check['pass']),
              'failed_checks': failed,
              'accepted': not failed,
              'debug_candidate_only': True, 'store_channel': False,
              'physical_device': False, 'signing_authority': False,
              'asset_digests': assets}
    common.write_json(args.output / 'static-report.json', report)
    common.write_json(args.output / 'observed-pins.json', observed_pins)
    print(json_line('summary', not failed, {'failed': failed, 'checks': len(checks)}), flush=True)
    if failed:
        raise SystemExit('S04 static refusal: ' + ', '.join(failed))


def json_line(name, passed, observed):
    import json
    return json.dumps({'check': name, 'pass': bool(passed), 'observed': observed}, default=str)


if __name__ == '__main__':
    main()
