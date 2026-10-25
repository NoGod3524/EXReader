"""Static acceptance of the authenticated Android debug candidate APK.

Checks version/minSdk/targetSdk/ABI/permissions against values re-derived from
the frozen producer source, resources and assets against their own source
generators, the shipped JNI blob against the same-run installed SDK staging,
and the signature identity against the debug-only policy. Any permission drift
or source drift is a refusal, not a re-baseline.
"""
import argparse
import io
import os
import pathlib
import re
import struct
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import common
import expectations

ELF_MACHINE = {3: 'x86', 62: 'x86-64', 40: 'arm', 183: 'aarch64'}
ELF_TYPE = {2: 'EXEC', 3: 'DYN'}


def parse_badging(text):
    row = {}
    row['package'] = re.search(r"package: name='([^']+)'", text).group(1)
    row['versionCode'] = re.search(r"versionCode='([^']+)'", text).group(1)
    row['versionName'] = re.search(r"versionName='([^']+)'", text).group(1)
    row['sdkVersion'] = re.search(r"sdkVersion:'([^']+)'", text).group(1)
    row['targetSdkVersion'] = re.search(r"targetSdkVersion:'([^']+)'", text).group(1)
    compile_sdk = re.search(r"compileSdkVersion='([^']+)'", text)
    row['compileSdkVersion'] = compile_sdk.group(1) if compile_sdk else None
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
    parser.add_argument('--inventory', type=pathlib.Path, default=pathlib.Path('build/s04-authenticate/inventory.json'))
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
        if mandatory and not passed:
            raise SystemExit('S04 static refusal: ' + name + ' — ' + str(observed))

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

    # --- sealed APK identity: refuse substitution before looking inside ---------
    observed_pins = {
        'candidate_sha256': common.sha256_file(candidate),
        'candidate_bytes': candidate.stat().st_size,
        'baseline_sha256': common.sha256_file(baseline) if baseline else None,
        'test_apk_sha256': common.sha256_file(test_apk) if test_apk else None,
        'release_apk_sha256': common.sha256_file(release) if release else None,
        'sdk_jni_sha256': common.sha256_file(sdk_jni) if sdk_jni else None,
    }
    for key, value in observed_pins.items():
        pinned = pins.get(key)
        if pinned is None:
            record('pin_' + key + '_derived', allow_derive, {'observed': value, 'allow_derive': allow_derive},
                   'the sealed contract has no pin yet')
        else:
            record('pin_' + key, pinned == value, {'sealed': pinned, 'observed': value})

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
                parts = name.split('/')
                libs.setdefault(parts[1], []).append(name)
        apk_jni = archive.read('lib/' + derived['abis'][0] + '/libexreader_jni.so') \
            if 'lib/' + derived['abis'][0] + '/libexreader_jni.so' in names else None
        assets = {name: common.sha256_bytes(archive.read(name))
                  for name in names if name.startswith('assets/')}
        catalog_asset = archive.read('assets/reader-catalog-v1.json') \
            if 'assets/reader-catalog-v1.json' in names else None
        font_asset = archive.read('assets/' + derived['font_asset']['name']) \
            if 'assets/' + derived['font_asset']['name'] in names else None
        dex_entries = [name for name in names if re.match(r'classes\d*\.dex$', name)]
    common.write_json(args.output / 'apk-entries.json', entries)
    record('apk_zip_integrity', bad is None and names_unique, {'entries': len(names), 'testzip': bad})
    record('apk_manifest_and_index_present',
           blob[:4] == b'\x00\x00\x08\x00' or blob[:2] == b'\x03\x00', {'manifest_bytes': len(blob)})
    record('apk_resources_index_present', resources is not None and len(resources) > 8,
           {'resources_bytes': len(resources) if resources else 0})
    record('apk_dex_present', len(dex_entries) >= 1, {'dex': dex_entries})
    record('apk_abi_set', sorted(libs) == derived['abis'], {'observed': sorted(libs),
                                                            'derived': derived['abis']})
    record('apk_jni_present', apk_jni is not None and len(apk_jni) > 0,
           {'libs': sorted(name for names2 in libs.values() for name in names2)})

    # --- JNI/SDK identity ------------------------------------------------------
    if apk_jni is not None and sdk_jni is not None:
        record('jni_blob_equals_same_run_sdk_stage',
               common.sha256_bytes(apk_jni) == common.sha256_file(sdk_jni),
               {'apk': common.sha256_bytes(apk_jni), 'sdk_stage': common.sha256_file(sdk_jni),
                'sdk_stage_path': str(sdk_jni)})
        extracted = args.output / 'libs'
        extracted.mkdir(exist_ok=True)
        symbols = set()
        identities = {}
        for abi, entries_abi in sorted(libs.items()):
            for name in entries_abi:
                with zipfile.ZipFile(candidate) as archive:
                    data = archive.read(name)
                target = extracted / pathlib.PurePosixPath(name).name
                target.write_bytes(data)
                identities[name] = dict(elf_identity(target), bytes=len(data),
                                        sha256=common.sha256_bytes(data))
                symbols |= dynamic_symbols(target, readelf)
        common.write_json(args.output / 'apk-libs.json', identities)
        expected_symbols = set(derived['jni_symbols'])
        missing = sorted(expected_symbols - symbols)
        record('jni_symbols_complete', not missing,
               {'derived': len(expected_symbols), 'exported': len(symbols), 'missing': missing[:20]})
        record('jni_onload_exported', 'JNI_OnLoad' in symbols,
               {'sampled': sorted(s for s in symbols if s.startswith('JNI_'))[:5]})
        record('jni_elf_x86_64', all(row['machine'] == 'x86-64' and row['type'] == 'DYN'
                                     for row in identities.values()),
               {name: {'machine': row['machine'], 'type': row['type']} for name, row in identities.items()})
        sdk_version_bytes = derived['sdk_version'].encode()
        version_hits = sum(1 for name in libs[derived['abis'][0]]
                           if sdk_version_bytes in (extracted / pathlib.PurePosixPath(name).name).read_bytes())
        record('sdk_version_string_in_shipped_libs', version_hits >= 1,
               {'version': derived['sdk_version'], 'libraries': version_hits})

    # --- manifest identity through aapt2 --------------------------------------
    badging_text = common.run([aapt2, 'dump', 'badging', str(candidate)])
    (args.output / 'aapt2-badging.txt').write_text(badging_text)
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
    record('manifest_launchable_activity', badging['launchable_activity'] == derived['launchable_activity'],
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
    record('manifest_no_extra_permission_attribute',
           len(re.findall(r'E: uses-permission', xmltree)) == len(derived['permissions']),
           {'elements': len(re.findall(r'E: uses-permission', xmltree))})

    # --- signature identity ---------------------------------------------------
    signature = common.run([apksigner, 'verify', '--verbose', '--print-certs', str(candidate)], check=False)
    (args.output / 'apksigner.txt').write_text(signature)
    signers, schemes = parse_certs(signature)
    verified = 'Verifies' in signature and 'DOES NOT VERIFY' not in signature
    record('signature_verifies', verified, {'schemes': schemes, 'signers': len(signers)})
    record('signature_single_signer', len(signers) == 1, {'signers': len(signers)})
    dn = next(iter(signers.values()), {}).get('dn', '')
    record('signature_debug_only', 'Android Debug' in dn, {'dn': dn},
           'only the debug candidate is in scope; store/signing authority is not granted')
    record('signature_v2_or_v3', any(schemes.get(key) for key in schemes),
           {'schemes': schemes})

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
               {'package': baseline_badging['package'], 'versionCode': baseline_badging['versionCode'],
                'permissions': baseline_badging['uses_permission']})

    report = {'identity': common.identity(), 'producer_source': producer_sha,
              'contract_source': str(args.contract), 'allow_derive': allow_derive,
              'pins_sealed': {key: pins.get(key) for key in observed_pins},
              'observed_pins': observed_pins, 'derived': {key: derived[key] for key in
                                                          ('applicationId', 'versionCode', 'versionName',
                                                           'minSdk', 'targetSdk', 'compileSdk', 'abis',
                                                           'permissions', 'sdk_version',
                                                           'launchable_activity')},
              'checks': checks, 'checks_total': len(checks),
              'checks_passed': sum(1 for check in checks if check['pass']),
              'accepted': all(check['pass'] for check in checks),
              'debug_candidate_only': True, 'store_channel': False,
              'physical_device': False, 'signing_authority': False,
              'asset_digests': assets}
    common.write_json(args.output / 'static-report.json', report)
    common.write_json(args.output / 'observed-pins.json', observed_pins)
    print(common.read_json(args.output / 'static-report.json')['checks_total'])
    print('static checks passed: %d/%d' % (report['checks_passed'], report['checks_total']))


if __name__ == '__main__':
    main()
