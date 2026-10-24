#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict same-source collection of the distribution inventory artifacts.

Every claim is re-derived from the uploaded bytes: installed files are re-hashed,
each dependency list is re-parsed from its captured tool output, the static
dependency graph is recomputed from those outputs, and both SBOM documents are
re-validated and optionally checked against the official schemas.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(HERE))
import check_reading_licenses as registered
import contract
import inventory as sdk_inventory
import packages
import sbom

WORKFLOW = '.github/workflows/reader-distribution-inventory.yml'
PROTOCOL_JOB = 'rejection protocol'
REPORT_JOB = 'same-source report'
PLATFORMS = {'linux': ('ubuntu-22.04', 'Linux'), 'windows': ('windows-2022', 'Windows'),
             'macos': ('macos-15', 'Darwin')}
PROFILES = ('reading-core', 'reading-library')
DYNAMIC_KIND = {'Linux': 'readelf-dynamic', 'Windows': 'dumpbin-dependents', 'Darwin': 'otool'}
COMBINED_PROFILE = 'combined'
COMBINED_JOB = 'combined (%s)'
COMBINED_ARTIFACT = 'reader-distribution-combined-%s-%s-%s'
ARTIFACT_PATH = re.compile(
    r'^(?:stage/|tools/|probe/|logs/)'
    r'|^(?:inventory|licenses|probe|combined)(?:\.[a-z]+)*\.(?:json|log|exit)$')


def job_name(key, profile):
    return 'inventory (%s, %s)' % (PLATFORMS[key][0], profile)


def artifact_name(key, profile, run_id, attempt):
    return 'reader-distribution-inventory-%s-%s-%s-%s' % (key, profile, run_id, attempt)


def normalise(payload):
    """Accept both layouts: contents at the archive root, or one shared prefix."""
    if any(name.startswith('stage/') for name in payload):
        return payload
    prefixes = {name.split('/')[0] for name in payload if '/' in name}
    if len(prefixes) == 1:
        prefix = prefixes.pop() + '/'
        return {name[len(prefix):]: data for name, data in payload.items() if name.startswith(prefix)}
    return payload


def api(path):
    done = subprocess.run(['gh', 'api', '-H', 'Accept: application/vnd.github+json', path],
                          capture_output=True, timeout=180)
    contract.need(done.returncode == 0, 'github_api')
    return contract.decode_json(done.stdout)


def pages(path, field):
    result = []
    for page in range(1, 21):
        body = api(path + '?per_page=100&page=%d' % page)
        contract.need(contract.integer(body.get('total_count')) and type(body.get(field)) is list
                      and len(body[field]) <= 100, 'api_pagination')
        result.extend(body[field])
        if len(result) >= body['total_count']:
            contract.need(len(result) == body['total_count'], 'api_page_count')
            return result
        contract.need(bool(body[field]), 'api_incomplete_page')
    raise contract.InventoryError('api_page_limit')


def load_schema(path):
    contract.need(path is not None, 'schema_path_required')
    try:
        import jsonschema
    except ImportError:
        raise contract.InventoryError('jsonschema_unavailable') from None
    return jsonschema, contract.decode_json(Path(path).read_bytes())


def verify_combined(key, payload, inventory, licenses_doc, run, components=None, switches=None,
                    schemas=None):
    """Re-derive the composed prefix (SDK plus thirteen packages) from the bytes."""
    components = components if components is not None else registered.COMPONENTS
    switches = switches if switches is not None else registered.preset_switches(ROOT, 'reading-library')
    contract.need(inventory.get('schema') == 1, 'combined_schema')
    contract.need(inventory.get('profile') == COMBINED_PROFILE, 'combined_profile')
    contract.need(inventory.get('platform') == key, 'combined_platform')
    contract.need(inventory.get('runner_os') == PLATFORMS[key][1], 'combined_runner')
    contract.need(inventory.get('source_sha') == run['head_sha'], 'combined_source')
    recorded = inventory.get('run') or {}
    contract.need(str(recorded.get('id')) == str(run['id'])
                  and str(recorded.get('attempt')) == str(run['run_attempt']), 'combined_run')
    files = inventory.get('installed_files')
    contract.need(type(files) is list and files, 'combined_file_list')
    for name in payload:
        contract.need(ARTIFACT_PATH.match(name) is not None, 'artifact_path')
    problems = []
    problems += contract.verify_installed(payload, files)
    identity = inventory.get('identity') or {}
    contract.need(identity.get('version') and identity.get('config_version') == identity.get('version')
                  and identity.get('targets'), 'combined_identity')

    def enabled(expression):
        return registered.enabled(expression, switches)

    expected = contract.expected_license_paths(components, enabled)
    problems += contract.verify_license_materials(files, payload, expected, components)
    checker = (inventory.get('license_materials') or {}).get('checker') or {}
    contract.need(checker.get('source_sha') == run['head_sha'], 'combined_checker_source')
    contract.need(licenses_doc.get('source_sha') == run['head_sha'], 'combined_licenses_source')
    for field in ('release_ready', 'materials_check_passed'):
        contract.need(bool(checker.get(field)) == bool(licenses_doc.get(field)),
                      'combined_checker_' + field)
    for field in ('failures', 'pending', 'mandatory_missing'):
        contract.need(list(checker.get(field) or []) == list(licenses_doc.get(field) or []),
                      'combined_checker_' + field)
    contract.need(licenses_doc.get('release_ready') is True, 'combined_licenses_not_ready')

    records = inventory.get('dependency_commands')
    contract.need(type(records) is list and records, 'combined_records')
    symbols, directives = {}, {}
    for record in records:
        path = record.get('raw_output_path')
        contract.need(isinstance(path, str) and path in payload, 'dependency_output_missing')
        try:
            text = payload[path].decode('utf-8')
        except UnicodeDecodeError:
            raise contract.InventoryError('dependency_output_encoding') from None
        contract.verify_dependency(record, text)
        if record.get('kind') in contract.SYMBOL_KINDS:
            contract.need(isinstance(record.get('archive'), str), 'symbol_record_archive')
            symbols[record['archive']] = contract.symbol_summary(
                contract.parse_entries(record['kind'], text, record.get('strip_underscore', False)))
        elif record.get('kind') == 'dumpbin-directives':
            contract.need(isinstance(record.get('archive'), str), 'directive_record_archive')
            directives[record['archive']] = [entry['name'] for entry in record['entries']]

    for path in symbols:
        directives.setdefault(path, [])
    static = inventory.get('static_dependency') or {}
    contract.need(contract.symbol_edges(symbols, symbols) == static.get('edges'), 'combined_edges')
    by_path = {record['path']: record for record in files}
    archives = static.get('archives') or []
    contract.need({entry['path'] for entry in archives} == set(symbols), 'combined_archive_coverage')
    for entry in archives:
        record = by_path.get(entry['path'])
        contract.need(record is not None and record['sha256'] == entry['sha256']
                      and record['bytes'] == entry['bytes'], 'combined_archive_identity')
        summary = symbols.get(entry['path'])
        contract.need(summary is not None, 'combined_archive_symbols')
        contract.need(contract.text_digest(summary['defined']) == entry['defined_sha256'],
                      'combined_archive_defined')
        contract.need(contract.text_digest(summary['undefined']) == entry['undefined_sha256'],
                      'combined_archive_undefined')
    sdk_expected = sorted(record['path'] for record in files
                          if re.fullmatch(r'lib/(?:lib)?exr_.+[.](?:a|lib)', record['path']))
    contract.need(sorted(static.get('sdk_archives') or []) == sdk_expected, 'combined_sdk_archives')
    claimed_directives = static.get('directives') or {}
    contract.need(sorted(claimed_directives) == sorted(directives), 'combined_directive_coverage')
    for path in directives:
        contract.need(claimed_directives[path] == directives[path], 'combined_directives')
    archive_names = {entry['name'] for entry in archives}
    index = {path: payload['stage/' + path] for path in by_path
             if 'stage/' + path in payload}

    providers = packages.symbol_providers(symbols)
    sections = {row.get('id'): row for row in inventory.get('packages') or []}
    contract.need(sorted(sections) == sorted(packages.REGISTERED_IDS), 'combined_registered')
    reconciled = []
    for package in packages.PACKAGES:
        section = sections[package['id']]
        resolved = packages.resolve(package, index)
        for field in ('version', 'version_source', 'config_files', 'headers', 'archives',
                      'assets', 'licence', 'missing'):
            contract.need(section.get(field) == resolved.get(field),
                          'combined_package_' + field)
        own = [entry['path'] for entry in resolved['archives']]
        external = packages.external_from_symbols(own, symbols)
        contract.need(section.get('external') == external, 'combined_package_external')
        expected_system = [packages.canonical(name) for name in package['system'][key]]
        contract.need(section.get('external_expected') == expected_system,
                      'combined_package_expected')
        contract.need(not section.get('external_missing'), 'combined_package_unmet')
        claimed_bundled = section.get('bundled') or []
        contract.need(len(claimed_bundled) == len(package['bundled']), 'combined_package_bundled')
        for claimed, expected_bundled in zip(claimed_bundled, package['bundled']):
            contract.need(claimed.get('library') == expected_bundled['library']
                          and claimed.get('archive') == expected_bundled['archive']
                          and claimed.get('material') == expected_bundled['material'],
                          'combined_package_bundled')
            contract.need(claimed.get('providers')
                          == providers.get(expected_bundled['library'], []),
                          'combined_package_providers')
            contract.need(expected_bundled['archive'] in ' '.join(claimed['providers']),
                          'combined_package_bundled_provider')
            contract.need(expected_bundled['material'] in index,
                          'combined_package_bundled_material')
        link = section.get('link') or {}
        contract.need(bool(link.get('raw_output_path')), 'combined_link_missing')
        contract.need(any(record == link for record in records), 'combined_link_record')
        tokens = [entry['name'] for entry in contract.parse_entries(
            'ninja-link', payload[link['raw_output_path']].decode('utf-8'))]
        evidence = packages.link_evidence(tokens, archive_names, package['system'][key])
        contract.need(evidence == section.get('link_evidence'), 'combined_link_evidence')
        contract.need(not evidence['expected_missing'], 'combined_link_expected')
        reconciled.append({'id': package['id'], 'version': resolved['version'],
                           'version_source': resolved.get('version_source'),
                           'archives': resolved['archives'],
                           'licence': resolved['licence'],
                           'external_expected': expected_system,
                           'external_observed': section.get('external_observed'),
                           'system_libraries': evidence['system_libraries'],
                           'frameworks': evidence['frameworks']})

    secrets = contract.scan_test_secrets(payload, 'stage/')
    contract.need(not secrets, 'combined_test_secrets')
    forbidden, observations = contract.scan_forbidden(
        payload, {'config': {'cache_switches': inventory.get('config', {}).get('sdk_switches', {})},
                  'identity': identity, 'dynamic_dependencies': {'entries': []}},
        allow_credentials=True)
    contract.need(not forbidden, 'combined_forbidden')
    contract.need(observations == inventory.get('observations'), 'combined_observations')
    credential = sorted(observations.get('credential_files') or [])
    contract.need(credential and all(any(marker in path for marker in
                                         ('exr_credentials', 'exreader-credentials',
                                          'exreadercredentials'))
                                    for path in credential), 'combined_credential_scope')
    hits = contract.scan_private_paths(payload, contract.GENERIC_PRIVATE_PATHS)
    leaked = sorted({hit['path'] for hit in hits})
    contract.need(leaked == sorted({row['path'] for row in
                                    (inventory.get('private_paths') or {}).get('hits') or []}),
                  'combined_private_path_scan')
    blockers = contract.private_path_blockers(hits)
    contract.need(blockers == sorted(inventory.get('release_blockers') or []),
                  'combined_release_blockers')

    for name, validator in (('combined.spdx.json', sbom.validate_spdx),
                            ('combined.cdx.json', sbom.validate_cyclonedx)):
        contract.need(name in payload, 'combined_sbom_missing')
        data = payload[name]
        pinned = (inventory.get('sbom') or {}).get(name) or {}
        contract.need(pinned.get('bytes') == len(data)
                      and pinned.get('sha256') == contract.digest(data), 'combined_sbom_identity')
        document = contract.decode_json(data)
        structural = validator(document, inventory)
        if structural:
            error = contract.InventoryError('combined_sbom_structure')
            error.detail = [name + ': ' + item for item in structural]
            raise error
        if schemas:
            jsonschema, schema = schemas[name]
            try:
                jsonschema.validate(document, schema)
            except jsonschema.ValidationError as error:
                raise contract.InventoryError('combined_sbom_schema',
                                              str(error.message)[:200]) from None

    contract.need(not inventory.get('problems'), 'combined_problems')
    contract.need(inventory.get('materials_complete') is True, 'combined_materials_complete')
    contract.need(inventory.get('release_ready') == (not blockers), 'combined_release_ready_claim')
    checks = inventory.get('checks') or []
    contract.need(checks and all(check.get('status') in ('pass', 'blocked', 'reported')
                                for check in checks), 'combined_check_status')
    profiles = [packages.by_id(entry['id'])['system'][key] for entry in reconciled]
    if problems:
        error = contract.InventoryError('combined_problems')
        error.detail = problems
        raise error
    return {'profile': COMBINED_PROFILE, 'platform': key, 'packages': reconciled,
            'package_count': len(reconciled),
            'checks': len(checks),
            'checks_passed': sum(1 for check in checks if check['status'] == 'pass'),
            'installed_files': len(files),
            'installed_bytes': sum(record['bytes'] for record in files),
            'archives': len(archives), 'symbol_edges': len(static.get('edges') or []),
            'spdx_sha256': contract.digest(payload['combined.spdx.json']),
            'cyclonedx_sha256': contract.digest(payload['combined.cdx.json']),
            'identity': {field: identity.get(field) for field in ('version', 'abi', 'core_version')},
            'release_blockers': blockers, 'release_ready': not blockers,
            'granted': True}


def verify_platform(key, profile, payload, inventory, licenses_doc, run, components=None, switches=None,
                    schemas=None):
    """Re-derive one installed platform's inventory from the uploaded bytes."""
    components = components if components is not None else registered.COMPONENTS
    switches = switches if switches is not None else registered.preset_switches(ROOT, profile)
    contract.need(inventory.get('schema') == 1, 'inventory_schema')
    contract.need(inventory.get('profile') == profile, 'inventory_profile')
    contract.need(inventory.get('platform') == key, 'inventory_platform')
    contract.need(inventory.get('runner_os') == PLATFORMS[key][1], 'inventory_runner')
    contract.need(inventory.get('source_sha') == run['head_sha'], 'inventory_source')
    recorded_run = inventory.get('run') or {}
    contract.need(str(recorded_run.get('id')) == str(run['id'])
                  and str(recorded_run.get('attempt')) == str(run['run_attempt']), 'inventory_run')
    files = inventory.get('installed_files')
    contract.need(type(files) is list and files, 'inventory_file_list')
    for name in payload:
        contract.need(ARTIFACT_PATH.match(name) is not None, 'artifact_path')
    problems = []
    problems += contract.verify_module_switches(inventory, switches)
    problems += contract.verify_identity(inventory.get('identity') or {})
    problems += contract.verify_installed(payload, files)

    def enabled(expression):
        return registered.enabled(expression, switches)

    expected = contract.expected_license_paths(components, enabled)
    problems += contract.verify_license_materials(files, payload, expected, components)

    checker = (inventory.get('license_materials') or {}).get('checker') or {}
    contract.need(checker.get('source_sha') == run['head_sha'], 'inventory_checker_source')
    contract.need(licenses_doc.get('source_sha') == run['head_sha'], 'licenses_document_source')
    for field in ('release_ready', 'materials_check_passed'):
        contract.need(bool(checker.get(field)) == bool(licenses_doc.get(field)), 'inventory_checker_' + field)
    for field in ('failures', 'pending', 'mandatory_missing'):
        contract.need(list(checker.get(field) or []) == list(licenses_doc.get(field) or []),
                      'inventory_checker_' + field)
    contract.need(licenses_doc.get('release_ready') is True and not licenses_doc.get('failures')
                  and not licenses_doc.get('pending') and not licenses_doc.get('mandatory_missing'),
                  'licenses_not_release_ready')

    records = inventory.get('dependency_commands')
    contract.need(type(records) is list and records, 'dependency_records')
    symbols = {}
    for record in records:
        path = record.get('raw_output_path')
        contract.need(isinstance(path, str) and path in payload, 'dependency_output_missing')
        try:
            text = payload[path].decode('utf-8')
        except UnicodeDecodeError:
            raise contract.InventoryError('dependency_output_encoding') from None
        derived = contract.verify_dependency(record, text)
        if record.get('kind') in contract.SYMBOL_KINDS:
            contract.need(isinstance(record.get('archive'), str), 'symbol_record_archive')
            symbols[record['archive']] = derived

    static = inventory.get('static_dependency') or {}
    contract.need(contract.symbol_edges(symbols, symbols) == static.get('edges'), 'static_edges_mismatch')
    sdk_expected = sorted(record['path'] for record in files
                          if re.fullmatch(r'lib/(?:lib)?exr_.+\.(?:a|lib)', record['path']))
    vendor_expected = sorted(record['path'] for record in files
                             if record['path'].startswith('lib/exreader/'))
    contract.need(sorted(static.get('sdk_archives') or []) == sdk_expected, 'sdk_archives')
    archives = static.get('archives') or []
    contract.need({entry['path'] for entry in archives} == set(sdk_expected) | set(vendor_expected),
                  'archive_coverage')
    by_path = {record['path']: record for record in files}
    for entry in archives:
        record = by_path.get(entry['path'])
        contract.need(record is not None and record['sha256'] == entry['sha256']
                      and record['bytes'] == entry['bytes'], 'archive_identity')
        summary = symbols.get(entry['path'])
        contract.need(summary is not None, 'archive_symbols')
        contract.need(contract.text_digest(summary['defined']) == entry['defined_sha256'],
                      'archive_defined_symbols')
        contract.need(contract.text_digest(summary['undefined']) == entry['undefined_sha256'],
                      'archive_undefined_symbols')
    foreign = static.get('foreign_archives') or []
    foreign_by_path = {entry['path']: entry for entry in foreign}
    contract.need(len(foreign_by_path) == len(foreign), 'foreign_archive_duplicate')
    for entry in foreign:
        record = by_path.get(entry['path'])
        contract.need(record is not None and record['sha256'] == entry['sha256']
                      and record['bytes'] == entry['bytes'], 'foreign_archive_identity')
    contract.need(sorted(foreign_by_path) == sorted(
        record['path'] for record in files
        if re.fullmatch(r'lib/[^/]+[.](?:a|lib)', record['path'])
        and not re.fullmatch(r'lib/(?:lib)?exr_.+[.](?:a|lib)', record['path'])),
        'foreign_archive_coverage')
    unreferenced = sorted(path for path in symbols if path not in sdk_expected
                          and not any(edge['to'] == path for edge in static.get('edges') or []))
    contract.need(unreferenced == sorted(static.get('unreferenced_archives') or []),
                  'unreferenced_archives')

    link = inventory.get('link') or {}
    contract.need(bool(link.get('record')), 'link_evidence')
    contract.need(any(record == link['record'] for record in records), 'link_record')
    link_text = payload[link['record']['raw_output_path']].decode('utf-8')
    tokens = [entry['name'] for entry in contract.parse_entries('ninja-link', link_text)]
    archive_names = {PurePosixPath(entry['path']).name for entry in archives}
    distributed, system, _ = contract.classify_link_tokens(tokens, archive_names)
    contract.need(distributed == link.get('distributed_archives'), 'link_distributed')
    contract.need(system == link.get('system_libraries'), 'link_system_libraries')
    unused = sorted(archive_names - set(distributed))
    problems += ['installed archive is not on the link line: ' + name for name in unused]

    dynamic = inventory.get('dynamic_dependencies') or {}
    contract.need(bool(dynamic.get('record')), 'dynamic_record')
    contract.need(any(record == dynamic['record'] for record in records), 'dynamic_command_record')
    contract.need(dynamic.get('record', {}).get('kind') == DYNAMIC_KIND[PLATFORMS[key][1]],
                  'dynamic_kind')
    contract.need(dynamic.get('entries') == dynamic['record'].get('entries'), 'dynamic_entries')

    forbidden, observations = contract.scan_forbidden(payload, inventory)
    problems += forbidden
    contract.need(observations == inventory.get('observations'), 'observations_mismatch')
    hits = contract.scan_private_paths(payload, contract.GENERIC_PRIVATE_PATHS)
    leaked = sorted({hit['path'] for hit in hits})
    contract.need(leaked == sorted({row['path'] for row in (inventory.get('private_paths') or {}).get('hits') or []}),
                  'private_path_scan')
    blockers = contract.private_path_blockers(hits)
    contract.need(blockers == sorted(inventory.get('release_blockers') or []), 'release_blockers')

    documents = {}
    for name, validator in (('inventory.spdx.json', sbom.validate_spdx),
                            ('inventory.cdx.json', sbom.validate_cyclonedx)):
        contract.need(name in payload, 'sbom_missing')
        data = payload[name]
        pinned = (inventory.get('sbom') or {}).get(name) or {}
        contract.need(pinned.get('bytes') == len(data) and pinned.get('sha256') == contract.digest(data),
                      'sbom_identity')
        document = contract.decode_json(data)
        structural = validator(document, inventory)
        if structural:
            error = contract.InventoryError('sbom_structure')
            error.detail = [name + ': ' + item for item in structural]
            raise error
        documents[name] = document
        if schemas:
            jsonschema, schema = schemas[name]
            try:
                jsonschema.validate(document, schema)
            except jsonschema.ValidationError as error:
                raise contract.InventoryError('sbom_schema', str(error.message)[:200]) from None

    contract.need(not inventory.get('problems'), 'inventory_problems')
    contract.need(inventory.get('materials_complete') is True, 'materials_complete')
    contract.need(inventory.get('release_ready') == (not blockers), 'release_ready_claim')
    checks = inventory.get('checks') or []
    contract.need(checks and all(check.get('status') in ('pass', 'blocked', 'reported') for check in checks),
                  'check_status')
    if problems:
        error = contract.InventoryError('platform_problems')
        error.detail = problems
        raise error
    return {'profile': profile, 'platform': key, 'checks': len(checks),
            'checks_passed': sum(1 for check in checks if check['status'] == 'pass'),
            'installed_files': len(files),
            'installed_bytes': sum(record['bytes'] for record in files),
            'archives': len(archives), 'symbol_edges': len(static.get('edges') or []),
            'dynamic_dependencies': len(dynamic.get('entries') or []),
            'spdx_sha256': contract.digest(payload['inventory.spdx.json']),
            'cyclonedx_sha256': contract.digest(payload['inventory.cdx.json']),
            'identity': {field: inventory['identity'].get(field)
                         for field in ('version', 'abi', 'core_version', 'config_version')},
            'release_blockers': blockers, 'release_ready': not blockers,
            'granted': True}


def collect(repo, run_id, attempt, sha, folder, retrospective, schemas):
    prefix = '/repos/%s/actions/runs/%d' % (repo, run_id)
    run = api('%s/attempts/%d' % (prefix, attempt))
    jobs = pages('%s/attempts/%d/jobs' % (prefix, attempt), 'jobs')
    artifacts = pages(prefix + '/artifacts', 'artifacts')
    contract.unique(jobs, 'job_duplicate')
    contract.unique(artifacts, 'artifact_duplicate')
    contract.need(run.get('id') == run_id and run.get('run_attempt') == attempt, 'run_identity')
    contract.need(run.get('head_sha') == sha, 'run_source')
    contract.need(run.get('path') == WORKFLOW, 'run_workflow')
    contract.need(run.get('repository', {}).get('full_name') == repo
                  and contract.integer(run['repository'].get('id'), 1)
                  and run.get('head_repository', {}).get('id') == run['repository']['id'],
                  'run_repository')
    if retrospective:
        contract.need(run.get('status') == 'completed' and run.get('conclusion') == 'success',
                      'run_conclusion')
    else:
        contract.need(run.get('status') == 'in_progress' and run.get('conclusion') is None,
                      'run_conclusion')
    expected_jobs = {job_name(key, profile) for key in PLATFORMS for profile in PROFILES}
    expected_jobs |= {COMBINED_JOB % PLATFORMS[key][0] for key in PLATFORMS}
    contract.need({row['name'] for row in jobs} == expected_jobs | {PROTOCOL_JOB, REPORT_JOB}, 'job_set')
    for job in jobs:
        contract.need(job.get('run_id') == run_id and job.get('run_attempt') == attempt
                      and job.get('head_sha') == sha, 'job_origin')
        if job['name'] == REPORT_JOB and not retrospective:
            contract.need(job.get('status') == 'in_progress', 'report_job_state')
        else:
            contract.need(job.get('status') == 'completed' and job.get('conclusion') == 'success',
                          'job_conclusion')
    folder.mkdir(parents=True, exist_ok=True)
    result = {'schema': 1, 'workflow': WORKFLOW, 'source_sha': sha, 'run_id': run_id,
              'attempt': attempt, 'retrospective': retrospective,
              'verified_at': datetime.now(timezone.utc).isoformat(), 'accepted': False,
              'inventory_generated': False, 'materials_complete': False, 'release_ready': False,
              'platforms': {}, 'release_blockers': [], 'not_covered': [], 'pending': [],
              'scope': ('Installed reading SDK file inventory, registered licence materials and '
                        'observed static/dynamic dependencies on three desktop operating systems. '
                        'Mobile packaging, host bundles, signing and publication are not covered.')}
    identities = {}
    names = set()
    for key in PLATFORMS:
        for profile in PROFILES:
            name = artifact_name(key, profile, run_id, attempt)
            artifact = contract.select(artifacts, name)
            contract.artifact_identity(artifact, run, datetime.now(timezone.utc))
            path = folder / ('%s.zip' % artifact['id'])
            with path.open('wb') as target:
                done = subprocess.run(['gh', 'api', '/repos/%s/actions/artifacts/%d/zip'
                                       % (repo, artifact['id'])], stdout=target,
                                      stderr=subprocess.PIPE, timeout=300)
            contract.need(done.returncode == 0 and path.stat().st_size <= contract.MAX_ZIP,
                          'archive_download')
            payload = normalise(contract.archive_files(path.read_bytes(), artifact))
            job = contract.select(jobs, job_name(key, profile))
            done = subprocess.run(['gh', 'api', '--allow-escape-sequences',
                                   '/repos/%s/actions/jobs/%d/logs' % (repo, job['id'])],
                                  capture_output=True, timeout=300)
            contract.need(done.returncode == 0 and 0 < len(done.stdout) <= contract.MAX_EXPANDED,
                          'job_log_download')
            (folder / ('job-%d.log' % job['id'])).write_bytes(done.stdout)
            log_sha = contract.upload_binding(done.stdout, artifact)
            contract.need('inventory.json' in payload and 'licenses.json' in payload,
                          'inventory_missing')
            inventory = contract.decode_json(payload['inventory.json'])
            licenses_doc = contract.decode_json(payload['licenses.json'])
            item = verify_platform(key, profile, payload, inventory, licenses_doc, run, schemas=schemas)
            item.update({'job_id': job['id'], 'job_source_sha': job['head_sha'],
                         'producer_log_sha256': log_sha,
                         'artifact': {field: artifact[field] for field in
                                      ('id', 'name', 'size_in_bytes', 'digest', 'expired', 'expires_at')}})
            names.add((key, profile))
            result['platforms']['%s/%s' % (key, profile)] = item
            result['release_blockers'] += item['release_blockers']
            for note in inventory.get('not_covered') or []:
                if note not in result['not_covered']:
                    result['not_covered'].append(note)
            identity = tuple(item['identity'][field] for field in ('version', 'abi', 'core_version'))
            identities.setdefault(identity, []).append('%s/%s' % (key, profile))
    contract.need(len(identities) == 1, 'identity_divergence')
    contract.need(names == {(key, profile) for key in PLATFORMS for profile in PROFILES},
                  'platform_set')
    result['combined'] = {}
    combined_blockers = []
    for key in PLATFORMS:
        name = COMBINED_ARTIFACT % (key, run_id, attempt)
        artifact = contract.select(artifacts, name)
        contract.artifact_identity(artifact, run, datetime.now(timezone.utc))
        path = folder / ('%s.zip' % artifact['id'])
        with path.open('wb') as target:
            done = subprocess.run(['gh', 'api', '/repos/%s/actions/artifacts/%d/zip'
                                   % (repo, artifact['id'])], stdout=target,
                                  stderr=subprocess.PIPE, timeout=600)
        contract.need(done.returncode == 0 and path.stat().st_size <= contract.MAX_ZIP,
                      'combined_archive_download')
        payload = normalise(contract.archive_files(path.read_bytes(), artifact))
        job = contract.select(jobs, COMBINED_JOB % PLATFORMS[key][0])
        done = subprocess.run(['gh', 'api', '--allow-escape-sequences',
                               '/repos/%s/actions/jobs/%d/logs' % (repo, job['id'])],
                              capture_output=True, timeout=300)
        contract.need(done.returncode == 0 and 0 < len(done.stdout) <= contract.MAX_EXPANDED,
                      'combined_job_log_download')
        (folder / ('job-%d.log' % job['id'])).write_bytes(done.stdout)
        log_sha = contract.upload_binding(done.stdout, artifact)
        contract.need('combined.json' in payload and 'licenses.json' in payload,
                      'combined_inventory_missing')
        inventory = contract.decode_json(payload['combined.json'])
        licenses_doc = contract.decode_json(payload['licenses.json'])
        item = verify_combined(key, payload, inventory, licenses_doc, run, schemas=schemas)
        item.update({'job_id': job['id'], 'job_source_sha': job['head_sha'],
                     'producer_log_sha256': log_sha,
                     'artifact': {field: artifact[field] for field in
                                  ('id', 'name', 'size_in_bytes', 'digest', 'expired', 'expires_at')}})
        result['combined'][key] = item
        combined_blockers += item['release_blockers']
        for note in inventory.get('not_covered') or []:
            if note not in result['not_covered']:
                result['not_covered'].append(note)
    for key in PLATFORMS:
        granted = [profile for profile in PROFILES
                   if result['platforms']['%s/%s' % (key, profile)]['granted']]
        result.setdefault('desktops', {})[key] = {'runner': PLATFORMS[key][0], 'granted': granted}
        contract.need(len(granted) == len(PROFILES), 'desktop_incomplete')
    contract.need(sorted(result['combined']) == sorted(PLATFORMS), 'combined_set')
    for key in PLATFORMS:
        contract.need(result['combined'][key]['granted'], 'combined_incomplete')
    result['identity'] = dict(zip(('version', 'abi', 'core_version'), list(identities)[0]))
    result['release_blockers'] = sorted(set(result['release_blockers'] + combined_blockers))
    result['inventory_generated'] = True
    result['materials_complete'] = True
    result['release_ready'] = not result['release_blockers']
    result['pending'] = list(result['release_blockers'])
    result['accepted'] = True
    result['verifier'] = {'source_sha': os.environ.get('GITHUB_SHA'),
                          'run_id': int(os.environ.get('GITHUB_RUN_ID', '0')),
                          'attempt': int(os.environ.get('GITHUB_RUN_ATTEMPT', '0'))}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--downloads', required=True)
    parser.add_argument('--run-id', type=int)
    parser.add_argument('--attempt', type=int)
    parser.add_argument('--source-sha')
    parser.add_argument('--spdx-schema')
    parser.add_argument('--cdx-schema')
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    summary = {'schema': 1, 'accepted': False, 'inventory_generated': False,
               'materials_complete': False, 'release_ready': False}
    try:
        contract.need(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud_required')
        retrospective = args.run_id is not None
        contract.need(retrospective == (args.attempt is not None) == (args.source_sha is not None),
                      'target_arguments')
        schemas = None
        if args.spdx_schema or args.cdx_schema:
            contract.need(args.spdx_schema and args.cdx_schema, 'schema_pair_required')
            jsonschema, spdx_schema = load_schema(args.spdx_schema)
            _, cdx_schema = load_schema(args.cdx_schema)
            schemas = {'inventory.spdx.json': (jsonschema, spdx_schema),
                       'inventory.cdx.json': (jsonschema, cdx_schema),
                       'combined.spdx.json': (jsonschema, spdx_schema),
                       'combined.cdx.json': (jsonschema, cdx_schema)}
        summary = collect(os.environ['GITHUB_REPOSITORY'],
                          args.run_id or int(os.environ['GITHUB_RUN_ID']),
                          args.attempt or int(os.environ['GITHUB_RUN_ATTEMPT']),
                          args.source_sha or os.environ['GITHUB_SHA'],
                          Path(args.downloads), retrospective, schemas)
    except Exception as error:
        summary = {'schema': 1, 'accepted': False, 'inventory_generated': False,
                   'materials_complete': False, 'release_ready': False}
        summary['error'] = str(error) if isinstance(error, contract.InventoryError) else type(error).__name__
        if isinstance(error, contract.InventoryError):
            if error.detail:
                summary['detail'] = error.detail
            if error.code == 'inventory_problems':
                summary['detail'] = error.detail
    text = json.dumps(summary, ensure_ascii=False, indent=2) + '\n'
    (output / 'aggregate.json').write_text(text, encoding='utf-8')
    print(text)
    return 0 if summary.get('accepted') else 1


if __name__ == '__main__':
    sys.exit(main())
