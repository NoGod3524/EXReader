#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pure rejection regression for this package's decisions (no build, no bundle).

A checker that only ever sees a good candidate proves nothing. Every decision in
spec.py is fed a good input and then one single mutation, and must reject exactly
that mutation with a named code.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import spec

SOURCE = spec.PRODUCER_SHA
CASES = []


def register(function):
    CASES.append(function)
    return function


def expect(problems, code, label):
    joined = '|'.join(problems)
    if code not in joined:
        raise AssertionError(label + ': expected ' + code + ' in ' + joined if joined
                             else label + ': expected ' + code + ', got no problem')
    return problems


def expect_clean(problems, label):
    if problems:
        raise AssertionError(label + ': expected no problem, got ' + '|'.join(problems))
    return problems


def good_plist(name='default'):
    info = dict(spec.INFO_PINS)
    info['CFBundleVersion'] = '1'
    info['EXRSourceSHA'] = SOURCE
    info['EXRRawSelectorEnabled'] = spec.candidate(name)['selector_bytes']
    return info


GOOD_DEPENDENCIES = [
    {'owner': spec.BUNDLE_EXECUTABLE, 'install_name': '@rpath/libexreader.1.dylib',
     'kind': 'bundle', 'resolved': 'Contents/Frameworks/libexreader.1.dylib'},
    {'owner': spec.BUNDLE_EXECUTABLE, 'install_name': '/usr/lib/libSystem.B.dylib',
     'kind': 'system', 'resolved': None},
]
GOOD_FILES = {
    spec.BUNDLE_EXECUTABLE: {'bytes': 10, 'sha256': 'a'},
    'Contents/Frameworks/libexreader.1.dylib': {'bytes': 10, 'sha256': 'b'},
    'Contents/Resources/Sample.epub': {'bytes': 10, 'sha256': 'c'},
}


def good_report(name='default'):
    return {'schema': 1, 'passed': True, 'check_count': 22,
            'checks': ['check_%02d' % index for index in range(22)],
            'engine_version': spec.SDK_VERSION, 'source_sha': SOURCE, 'platform': 'macOS'}


@register
def plist_accepts_and_rejects():
    expect_clean(spec.plist_problems(good_plist(), 'default', SOURCE), 'plist good')
    info = good_plist()
    info['CFBundleShortVersionString'] = '3.40.0'
    expect(spec.plist_problems(info, 'default', SOURCE), 'info_plist_value:CFBundleShortVersionString',
           'plist version')
    info = good_plist()
    info['EXRSourceSHA'] = '0' * 40
    expect(spec.plist_problems(info, 'default', SOURCE), 'info_plist_value:EXRSourceSHA', 'plist source')
    info = good_plist()
    info['EXRRawSelectorEnabled'] = True
    expect(spec.plist_problems(info, 'default', SOURCE), 'info_plist_value:EXRRawSelectorEnabled',
           'plist selector')
    info = good_plist()
    del info['LSMinimumSystemVersion']
    expect(spec.plist_problems(info, 'default', SOURCE), 'info_plist_value:LSMinimumSystemVersion',
           'plist minimum')
    expect_clean(spec.plist_problems(good_plist('raw'), 'raw', SOURCE), 'plist raw good')


@register
def architecture_and_build_version():
    expect_clean(spec.architecture_problems({spec.BUNDLE_EXECUTABLE: ['arm64']}), 'arch good')
    expect(spec.architecture_problems({spec.BUNDLE_EXECUTABLE: ['x86_64']}),
           'architecture:' + spec.BUNDLE_EXECUTABLE, 'arch fat')
    expect(spec.architecture_problems({spec.BUNDLE_EXECUTABLE: ['arm64', 'x86_64']}),
           'architecture:', 'arch universal')
    framework = 'Contents/Frameworks/libexreader.1.dylib'
    good = {spec.BUNDLE_EXECUTABLE: {'platform': '1', 'minos': '12.0', 'sdk': '15.0'},
            framework: {'platform': '1', 'minos': '15.0', 'sdk': '15.0'}}
    expect_clean(spec.build_version_problems(good), 'build version good')
    wrong = {spec.BUNDLE_EXECUTABLE: {'platform': '2', 'minos': '12.0', 'sdk': '15.0'}}
    expect(spec.build_version_problems(wrong), 'build_platform:', 'build platform')
    wrong = {spec.BUNDLE_EXECUTABLE: {'platform': '1', 'minos': '11.0', 'sdk': '15.0'}}
    expect(spec.build_version_problems(wrong), 'minimum_os:', 'build minos')
    wrong = {framework: {'platform': '1', 'minos': '11.0', 'sdk': '15.0'}}
    expect_clean(spec.build_version_problems(wrong), 'recorded framework minimum')
    wrong = {spec.BUNDLE_EXECUTABLE: {'platform': '1', 'minos': '12.0'}}
    expect(spec.build_version_problems(wrong), 'build_sdk_missing:', 'build sdk')
    wrong = {spec.BUNDLE_EXECUTABLE: {'platform': '1', 'sdk': '15.0'}}
    expect(spec.build_version_problems(wrong), 'minimum_os_missing:', 'build minimum missing')


@register
def dependency_closure():
    bundle_root = '/tmp/x/EXReader.app'
    executable_dir = bundle_root + '/Contents/MacOS'
    loader_dir = bundle_root + '/Contents/Frameworks'
    kind, resolved = spec.resolve_install_name('@rpath/libexreader.1.dylib',
                                               ['@executable_path/../Frameworks'],
                                               executable_dir, loader_dir, bundle_root)
    if (kind, resolved) != ('bundle', 'Contents/Frameworks/libexreader.1.dylib'):
        raise AssertionError('rpath resolution: ' + str((kind, resolved)))
    kind, resolved = spec.resolve_install_name('/usr/lib/libc++.1.dylib', [], executable_dir,
                                               loader_dir, bundle_root)
    if (kind, resolved) != ('system', None):
        raise AssertionError('system classification: ' + str((kind, resolved)))
    kind, resolved = spec.resolve_install_name('@rpath/libexreader.1.dylib', [],
                                               executable_dir, loader_dir, bundle_root)
    if kind != 'external':
        raise AssertionError('unresolved rpath must be external: ' + kind)
    kind, resolved = spec.resolve_install_name('/usr/local/lib/libfoo.dylib', [],
                                               executable_dir, loader_dir, bundle_root)
    if kind != 'external':
        raise AssertionError('absolute foreign dependency must be external: ' + kind)
    expect_clean(spec.dependency_problems(GOOD_DEPENDENCIES, GOOD_FILES), 'dependencies good')
    broken = [dict(GOOD_DEPENDENCIES[0], kind='external', resolved=None)]
    expect(spec.dependency_problems(broken, GOOD_FILES), 'dependency_external:', 'dependency external')
    missing = [dict(GOOD_DEPENDENCIES[0], resolved='Contents/Frameworks/absent.dylib')]
    expect(spec.dependency_problems(missing, GOOD_FILES), 'dependency_missing:', 'dependency missing')


@register
def reachability_and_sdk_uniqueness():
    primary = 'Contents/Frameworks/libexreader.1.dylib'
    alias = 'Contents/Frameworks/libexreader.3.41.0.dylib'
    machos = [spec.BUNDLE_EXECUTABLE, primary, alias]
    identities = {spec.BUNDLE_EXECUTABLE: None, primary: '@rpath/libexreader.1.dylib',
                  alias: '@rpath/libexreader.1.dylib'}
    expect_clean(spec.reachability_problems(GOOD_DEPENDENCIES, machos, identities),
                 'reachability good')
    orphan = 'Contents/Frameworks/libother.dylib'
    orphaned = dict(identities)
    orphaned[orphan] = '@rpath/libother.dylib'
    expect(spec.reachability_problems(GOOD_DEPENDENCIES, machos + [orphan], orphaned),
           'framework_not_referenced:' + orphan, 'framework orphan')
    libraries = {primary: {'install_name': '@rpath/libexreader.1.dylib', 'code_digest': 'c'},
                 alias: {'install_name': '@rpath/libexreader.1.dylib', 'code_digest': 'c'}}
    files = dict(GOOD_FILES)
    files[alias] = {'bytes': 1, 'sha256': 'd'}
    expect_clean(spec.sdk_uniqueness_problems(files, GOOD_DEPENDENCIES, libraries), 'sdk unique good')
    split = dict(libraries)
    split[alias] = {'install_name': '@rpath/libexreader.2.dylib', 'code_digest': 'c'}
    expect(spec.sdk_uniqueness_problems(files, GOOD_DEPENDENCIES, split), 'sdk_library_identity:',
           'sdk identity')
    recoded = dict(libraries)
    recoded[alias] = {'install_name': '@rpath/libexreader.1.dylib', 'code_digest': 'z'}
    expect(spec.sdk_uniqueness_problems(files, GOOD_DEPENDENCIES, recoded), 'sdk_library_code:',
           'sdk code')
    copy = dict(files)
    copy['Contents/Resources/libexreader.1.dylib'] = {'bytes': 1, 'sha256': 'd'}
    expect(spec.sdk_uniqueness_problems(copy, GOOD_DEPENDENCIES, libraries), 'sdk_library_duplicate:',
           'sdk duplicate')
    expect(spec.sdk_uniqueness_problems(GOOD_FILES, GOOD_DEPENDENCIES, {}), 'sdk_library_count:0',
           'sdk none')
    unmatched = [dict(GOOD_DEPENDENCIES[0], install_name='@rpath/libexreader.9.dylib'),
                 GOOD_DEPENDENCIES[1]]
    expect(spec.sdk_uniqueness_problems(files, unmatched, libraries), 'sdk_library_reference_name:',
           'sdk reference')
    doubled = list(GOOD_DEPENDENCIES) + [dict(GOOD_DEPENDENCIES[0],
                                              install_name='@rpath/libexreader.2.dylib')]
    expect(spec.sdk_uniqueness_problems(files, doubled, libraries), 'sdk_library_references:',
           'sdk two references')
    static = dict(files)
    static['Contents/Frameworks/libreader_catalog.a'] = {'bytes': 1, 'sha256': 'd'}
    expect(spec.sdk_uniqueness_problems(static, GOOD_DEPENDENCIES, libraries),
           'static_archive_shipped:', 'static archive')


@register
def resources_and_licences():
    digests = {name: spec.FONT_PINS.get(name, 'x') for name in spec.REQUIRED_RESOURCES}
    digests[spec.LICENSE_DIR + '/sqlite.txt'] = 'l'
    resources = {name: {'bytes': 1, 'sha256': digests.get(name, 'x')}
                 for name in spec.REQUIRED_RESOURCES if name != spec.LICENSE_DIR}
    resources[spec.LICENSE_DIR + '/sqlite.txt'] = {'bytes': 1, 'sha256': 'l'}
    expect_clean(spec.resource_problems(resources, digests), 'resources good')
    missing = dict(resources)
    del missing['Sample.epub']
    expect(spec.resource_problems(missing, digests), 'resource_missing:Sample.epub', 'resource missing')
    bad_font = dict(digests)
    bad_font['Reader.otf'] = '0' * 64
    expect(spec.resource_problems(resources, bad_font), 'font_pin:Reader.otf', 'font pin')
    expect_clean(spec.license_copy_problems({'sqlite.txt': 'l'}, digests), 'licences good')
    expect(spec.license_copy_problems({'sqlite.txt': 'other'}, digests), 'license_copy_mismatch:',
           'licence copy')
    extra = dict(digests)
    extra[spec.LICENSE_DIR + '/unregistered.txt'] = 'z'
    expect(spec.license_copy_problems({'sqlite.txt': 'l'}, extra), 'license_unregistered:',
           'licence unregistered')


@register
def producer_build_manifest():
    files = {path: {'bytes': 1, 'sha256': 'h' + path} for path in
             (spec.BUNDLE_EXECUTABLE, spec.INFO_PLIST)}
    manifest = {'schema': 1, 'source_sha': SOURCE, 'sdk_version': spec.SDK_VERSION,
                'platform': 'macos', 'selector_bytes_candidate': False,
                'files': {path: entry['sha256'] for path, entry in files.items()}}
    expect_clean(spec.build_manifest_problems(manifest, files, SOURCE, 'default'), 'manifest good')
    mutated = dict(manifest, platform='ios')
    expect(spec.build_manifest_problems(mutated, files, SOURCE, 'default'),
           'build_manifest_platform', 'manifest platform')
    mutated = dict(manifest, selector_bytes_candidate=True)
    expect(spec.build_manifest_problems(mutated, files, SOURCE, 'default'),
           'build_manifest_selector_flag', 'manifest selector')
    mutated = dict(manifest, files={spec.BUNDLE_EXECUTABLE: 'other'})
    expect(spec.build_manifest_problems(mutated, files, SOURCE, 'default'),
           'build_manifest_file:' + spec.BUNDLE_EXECUTABLE, 'manifest digest')
    extra_files = dict(manifest['files'])
    extra_files['Contents/Extra.txt'] = 'x'
    mutated = dict(manifest, files=extra_files)
    expect(spec.build_manifest_problems(mutated, files, SOURCE, 'default'),
           'build_manifest_extra_file:Contents/Extra.txt', 'manifest extra')


@register
def native_report():
    expect_clean(spec.report_problems(good_report(), 'default', SOURCE), 'report good')
    expect(spec.report_problems(good_report(), 'default', SOURCE, minimum=23),
           'report_check_count:', 'report minimum')
    for mutation, code in (({'passed': False}, 'report_not_passed'),
                           ({'check_count': 19}, 'report_check_count:19'),
                           ({'engine_version': '3.40.0'}, 'report_engine_version:3.40.0'),
                           ({'source_sha': '0' * 40}, 'report_source_sha'),
                           ({'platform': 'iOS'}, 'report_platform'),
                           ({'error': 'EXReaderError.invalidResult'}, 'report_error:'),
                           ({'checks': ['a']}, 'report_check_list')):
        value = dict(good_report(), **mutation)
        expect(spec.report_problems(value, 'default', SOURCE), code, 'report ' + code)
    duplicated = dict(good_report(), checks=['same'] * 22)
    expect(spec.report_problems(duplicated, 'default', SOURCE), 'report_duplicate_checks',
           'report duplicate')


@register
def relocation_and_offline():
    source = {spec.BUNDLE_EXECUTABLE: 'h1', spec.INFO_PLIST: 'h2'}
    expect_clean(spec.relocation_problems(source, dict(source),
                                          '/tmp/最终 空间/EXReader.app'), 'relocation good')
    expect(spec.relocation_problems(source, dict(source), '/tmp/plain/EXReader.app'),
           'relocation_path_without_space', 'relocation space')
    expect(spec.relocation_problems(source, dict(source), '/tmp/space only/EXReader.app'),
           'relocation_path_without_unicode', 'relocation unicode')
    expect(spec.relocation_problems(source, {'Contents/MacOS/EXReader': 'h1'},
                                    '/tmp/最终 空间/EXReader.app'), 'relocation_file_set',
           'relocation file set')
    changed = dict(source)
    changed[spec.INFO_PLIST] = 'other'
    expect(spec.relocation_problems(source, changed, '/tmp/最终 空间/EXReader.app'),
           'relocation_file_bytes:', 'relocation bytes')
    good = {'mechanism': 'sandbox-exec', 'profile': spec.OFFLINE_PROFILE,
            'control_reachable': True, 'denied': True}
    expect_clean(spec.offline_problems(good), 'offline good')
    expect(spec.offline_problems(dict(good, mechanism=None)), 'offline_mechanism:', 'offline mechanism')
    expect(spec.offline_problems(dict(good, denied=False)), 'offline_not_denied', 'offline denied')
    expect(spec.offline_problems(dict(good, control_reachable=False)),
           'offline_control_not_reachable', 'offline control')
    expect(spec.offline_problems(dict(good, profile='(version 1)')),
           'offline_profile_changed', 'offline profile')


@register
def source_identity():
    identity = {'start_sha': spec.START_SHA, 'verifier_sha': 'a' * 40,
                'producer': {'sha': spec.PRODUCER_SHA, 'branch': spec.PRODUCER_BRANCH},
                'sdk': {'source_sha': spec.SDK_SHA, 'version': spec.SDK_VERSION,
                        'abi': spec.SDK_ABI},
                'runner': {'machine': 'arm64'}, 'problems': []}
    expect_clean(spec.identity_problems(identity, 'a' * 40), 'identity good')
    expect(spec.identity_problems(dict(identity, producer={'sha': 'b' * 40,
                                                           'branch': spec.PRODUCER_BRANCH}),
                                  'a' * 40), 'producer_sha:', 'identity producer')
    expect(spec.identity_problems(dict(identity, verifier_sha='b' * 40), 'a' * 40),
           'verifier_sha:', 'identity verifier')
    expect(spec.identity_problems(dict(identity, runner={'machine': 'x86_64'}), 'a' * 40),
           'runner_machine:', 'identity runner')
    expect(spec.identity_problems(dict(identity, problems=['sdk_source_path:include']), 'a' * 40),
           'sdk_source_path:include', 'identity sdk path')


def main():
    failures = []
    for function in CASES:
        try:
            function()
        except AssertionError as error:
            failures.append(function.__name__ + ': ' + str(error))
        else:
            print('ok   ' + function.__name__)
    print('%d decision groups, %d failing' % (len(CASES), len(failures)))
    for failure in failures:
        print('FAIL ' + failure)
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
