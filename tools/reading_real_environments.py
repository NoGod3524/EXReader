#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Select exactly one frozen budget for an observed reading environment."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LEGACY = 'tests/reading_real/budgets.json'
REGISTRY = 'tests/reading_real/environments.json'
FIELDS = ('runner_os', 'runner_arch', 'runner_image', 'cpu_model', 'compiler', 'reference')


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate frozen-environment JSON field')
            result[key] = value
        return result

    def invalid(value):
        raise ValueError('Non-finite frozen-environment JSON: ' + value)

    require(path.stat().st_size <= 2 * 1024 * 1024, 'Frozen-environment JSON exceeds limit')
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs, parse_constant=invalid)


def environment_key(environment):
    require(isinstance(environment, dict), 'Missing frozen environment')
    values = tuple(environment.get(field) for field in FIELDS)
    require(all(isinstance(value, str) and 0 < len(value) <= 16384 for value in values),
            'Incomplete frozen environment')
    require(values[:3] == ('Linux', 'X64', 'ubuntu22'), 'Unsupported frozen runner')
    return values


def select_budget(environment, root=ROOT):
    """No CPU aliases or closest-budget fallback. Legacy provenance remains strict."""
    root = root.resolve()
    observed = environment_key(environment)
    registry_path = root / REGISTRY
    if not registry_path.exists():
        path = root / LEGACY
        budget = read(path)
        require(isinstance(budget, dict) and
                (budget.get('cpu_model'), budget.get('compiler')) == (observed[3], observed[4]),
                'Baseline environment refused: no matching registered CPU/compiler')
        return path, {'registry_sha256': None, 'environment_id': 'legacy',
                      'budget_path': LEGACY, 'budget_sha256': digest(path)}
    registry = read(registry_path)
    require(isinstance(registry, dict) and set(registry) == {'schema', 'legacy_budget_sha256', 'environments'} and
            type(registry['schema']) is int and registry['schema'] == 1,
            'Invalid frozen-environment registry')
    legacy_hash = registry['legacy_budget_sha256']
    require(isinstance(legacy_hash, str) and re.fullmatch('[0-9a-f]{64}', legacy_hash) and
            digest(root / LEGACY) == legacy_hash, 'Original budget bytes changed')
    entries = registry['environments']
    require(isinstance(entries, list) and 1 <= len(entries) <= 32, 'Invalid frozen-environment entries')
    ids, keys, paths, matches = set(), set(), set(), []
    legacy_count = 0
    for entry in entries:
        require(isinstance(entry, dict) and set(entry) ==
                {'id', 'environment', 'budget_path', 'budget_sha256'}, 'Invalid environment entry')
        identifier, relative, expected_hash = entry['id'], entry['budget_path'], entry['budget_sha256']
        require(isinstance(identifier, str) and re.fullmatch('[a-z0-9][a-z0-9-]{0,63}', identifier),
                'Invalid frozen-environment ID')
        require(isinstance(entry['environment'], dict) and set(entry['environment']) == set(FIELDS),
                'Frozen environment fields changed')
        key = environment_key(entry['environment'])
        require(relative in (LEGACY, f'tests/reading_real/environments/{identifier}/budgets.json'),
                'Frozen budget path refused')
        require(identifier not in ids and key not in keys and relative not in paths,
                'Duplicate/ambiguous frozen environment')
        ids.add(identifier)
        keys.add(key)
        paths.add(relative)
        path = root / relative
        require(path.resolve().is_relative_to(root) and path.is_file() and
                isinstance(expected_hash, str) and re.fullmatch('[0-9a-f]{64}', expected_hash) and
                digest(path) == expected_hash, 'Frozen budget file/hash refused')
        budget = read(path)
        require(isinstance(budget, dict) and budget.get('cpu_model') == key[3] and budget.get('compiler') == key[4],
                'Registered CPU/compiler differs from budget')
        if relative == LEGACY:
            legacy_count += 1
            require(expected_hash == legacy_hash, 'Legacy budget identity differs')
        if key == observed:
            matches.append((path, {'registry_sha256': digest(registry_path),
                'environment_id': identifier, 'budget_path': relative, 'budget_sha256': expected_hash}))
    require(legacy_count == 1, 'Original frozen environment must remain registered exactly once')
    require(len(matches) == 1, 'Baseline environment refused: no exact frozen environment')
    return matches[0]


def report_budget(summary, root=ROOT):
    path, selection = select_budget(summary['environment'], root)
    require(summary.get('budget_path') == selection['budget_path'] and
            summary.get('budget_sha256') == selection['budget_sha256'] and
            summary.get('budget_selection') == selection,
            'Performance evidence selected a different frozen environment')
    return path
