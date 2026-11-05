"""Actions-only positive/negative scope checks; never performance measurements."""
import copy
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
import measure_reading_real as gate

assert os.environ.get('GITHUB_ACTIONS') == 'true'
source = os.environ['GITHUB_SHA']
current = dict(source_sha=source, sdk_candidate=gate.AUTHORIZED_BACKGROUND_SDK,
               authorized_sdk_candidate=gate.AUTHORIZED_BACKGROUND_SDK, baseline_sdk_candidate=gate.SDK,
               before=dict(sdk_candidate=gate.AUTHORIZED_BACKGROUND_SDK, source_sha=source,
                           source_tree=gate.git('rev-parse', source + '^{tree}'),
                           sdk_trees={p: gate.git('rev-parse', source + ':' + p) for p in gate.PROTECTED}))
assert gate.authorized_background_candidate(current, gate.AUTHORIZED_BACKGROUND_SDK) is True
assert gate.authorized_background_candidate({}) is False
negatives = []
for name, update in (
    ('foreign_authorization', {'authorized_sdk_candidate': '0'*40}),
    ('wrong_candidate', {'sdk_candidate': gate.SDK}),
    ('rewritten_baseline_sdk', {'baseline_sdk_candidate': gate.AUTHORIZED_BACKGROUND_SDK}),
    ('missing_baseline_sdk', {'baseline_sdk_candidate': None}),
    ('old_source_under_new_scope', {'source_sha': gate.SDK}),
):
    bad = copy.deepcopy(current);bad.update(update);negatives.append((name, bad))
bad = copy.deepcopy(current);bad['before']['sdk_candidate'] = gate.SDK;negatives.append(('wrong_actual_sdk', bad))
bad = copy.deepcopy(current);bad['before']['source_tree'] = '0'*40;negatives.append(('wrong_source_tree', bad))
bad = copy.deepcopy(current);bad['before']['source_sha'] = gate.SDK;negatives.append(('wrong_source_claim', bad))
for path in gate.PROTECTED:
    bad = copy.deepcopy(current);bad['before']['sdk_trees'][path] = '0'*40
    negatives.append(('wrong_tree_' + path, bad))
for name, bad in negatives:
    try:
        gate.authorized_background_candidate(bad, gate.AUTHORIZED_BACKGROUND_SDK)
    except ValueError:
        continue
    raise AssertionError('Scope gate accepted ' + name)
try:
    gate.authorized_background_candidate(current)
except ValueError:
    pass
else:
    raise AssertionError('Old default freeze silently accepted new SDK scope')
print(json.dumps(dict(positive_scope_checks=2, scope_rejections=len(negatives),
                      numeric_budgets_changed=False, corpus_changed=False)))
