# SPDX-License-Identifier: MIT
"""Distinct diagnostic protocol; never substitutes for strict native acceptance."""
import json
from pathlib import Path
import re
from contract import BASE, BUNDLE, ROOT, STAGES, guard, require, sha

CASE = 'testDiagnosticContinuationRememberUpdateRestart'


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
