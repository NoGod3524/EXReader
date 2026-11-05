#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only exact environment selection and evidence-substitution regressions."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import reading_real_environments as gate

if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('Run frozen-environment checks in Actions')


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


environment = dict(zip(gate.FIELDS, ('Linux', 'X64', 'ubuntu22', 'old CPU', 'compiler', 'reference')))
new_environment = dict(environment, cpu_model='new CPU')
checks = 0
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    legacy = root / gate.LEGACY
    write(legacy, {'cpu_model': 'old CPU', 'compiler': 'compiler'})
    original = legacy.read_bytes()
    path, selection = gate.select_budget(environment, root)
    assert path == legacy and selection['environment_id'] == 'legacy'
    checks += 1
    try:
        gate.select_budget(new_environment, root)
    except ValueError:
        checks += 1
    else:
        raise AssertionError('Unknown CPU used legacy budgets')

    new_path = 'tests/reading_real/environments/new-cpu/budgets.json'
    write(root / new_path, {'cpu_model': 'new CPU', 'compiler': 'compiler'})
    registry = {'schema': 1, 'legacy_budget_sha256': gate.digest(legacy), 'environments': [
        {'id': 'old-cpu', 'environment': environment, 'budget_path': gate.LEGACY,
         'budget_sha256': gate.digest(legacy)},
        {'id': 'new-cpu', 'environment': new_environment, 'budget_path': new_path,
         'budget_sha256': gate.digest(root / new_path)},
    ]}
    registry_path = root / gate.REGISTRY
    write(registry_path, registry)
    for expected, identifier, relative in ((environment, 'old-cpu', gate.LEGACY),
                                           (new_environment, 'new-cpu', new_path)):
        path, selection = gate.select_budget(expected, root)
        assert path == root / relative and selection['environment_id'] == identifier
        assert selection['registry_sha256'] == gate.digest(registry_path)
        report = {'environment': expected, 'budget_path': relative,
                  'budget_sha256': selection['budget_sha256'], 'budget_selection': selection}
        assert gate.report_budget(report, root) == path
        checks += 2
        for name, change in (
                ('wrong path', lambda r: r.update(budget_path=gate.LEGACY if relative != gate.LEGACY else new_path)),
                ('wrong hash', lambda r: r.update(budget_sha256='0' * 64)),
                ('missing selection', lambda r: r.pop('budget_selection')),
                ('wrong registry', lambda r: r['budget_selection'].update(registry_sha256='0' * 64)),
                ('wrong selection', lambda r: r['budget_selection'].update(environment_id='other'))):
            altered = copy.deepcopy(report)
            change(altered)
            try:
                gate.report_budget(altered, root)
            except ValueError:
                checks += 1
            else:
                raise AssertionError('Accepted substituted evidence: ' + name)
    for field in gate.FIELDS:
        changed = dict(new_environment, **{field: 'unknown'})
        try:
            gate.select_budget(changed, root)
        except ValueError:
            checks += 1
        else:
            raise AssertionError('Accepted mismatched environment: ' + field)

    mutations = {
        'schema': lambda r: r.update(schema=True),
        'missing legacy': lambda r: r['environments'].pop(0),
        'duplicate environment': lambda r: r['environments'].append(copy.deepcopy(r['environments'][1])),
        'duplicate id': lambda r: r['environments'][1].update(id='old-cpu'),
        'unknown entry field': lambda r: r['environments'][1].update(fallback=True),
        'wrong hash': lambda r: r['environments'][1].update(budget_sha256='0' * 64),
        'escaping path': lambda r: r['environments'][1].update(budget_path='../budgets.json'),
        'absolute path': lambda r: r['environments'][1].update(budget_path=str(legacy.resolve())),
        'unregistered path': lambda r: r['environments'][1].update(budget_path='tests/reading_real/other.json'),
        'wrong cpu': lambda r: r['environments'][1]['environment'].update(cpu_model='invented'),
        'wrong compiler': lambda r: r['environments'][1]['environment'].update(compiler='invented'),
        'missing reference': lambda r: r['environments'][1]['environment'].pop('reference'),
        'unknown environment field': lambda r: r['environments'][1]['environment'].update(any_cpu=True),
        'empty environment': lambda r: r['environments'][1].update(environment=None),
        'extra registry field': lambda r: r.update(default='new-cpu'),
    }
    for name, change in mutations.items():
        mutant = copy.deepcopy(registry)
        change(mutant)
        write(registry_path, mutant)
        try:
            gate.select_budget(environment, root)
        except ValueError:
            checks += 1
        else:
            raise AssertionError('Accepted malformed registry: ' + name)
    write(registry_path, registry)
    legacy.write_bytes(original + b' ')
    try:
        gate.select_budget(new_environment, root)
    except ValueError:
        checks += 1
    else:
        raise AssertionError('Allowed changed original budget while selecting another CPU')
    legacy.write_bytes(original)
    registry_path.write_text('{"schema":1,"schema":1}', encoding='utf-8')
    try:
        gate.select_budget(environment, root)
    except ValueError:
        checks += 1
    else:
        raise AssertionError('Allowed duplicate JSON keys')
print({'passed': True, 'checks': checks, 'performance_credit': 0, 'scope': 'frozen environment selection only'})
