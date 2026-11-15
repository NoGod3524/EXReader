"""Export the captured rows without inferring keyboard or speech acceptance."""
import csv
import json
from pathlib import Path

root = Path(__file__).resolve().parent
capture = json.loads((root / 'F09-current-uia-named/all-controls.json').read_text(encoding='utf-8'))
fields = ['surface', 'address', 'id', 'name', 'role', 'role_name', 'name_ok',
          'role_ok', 'keyboard_focusable', 'observed_keyboard_steps', 'focus_order', 'screen_reader']
rows = []
for surface, result in capture['captures'].items():
    for control in result['controls']:
        row = dict(control, surface=surface)
        row['observed_keyboard_steps'] = json.dumps(row['observed_keyboard_steps'], ensure_ascii=False)
        rows.append(row)
with (root / 'F09-controls.csv').open('w', encoding='utf-8', newline='') as stream:
    writer = csv.DictWriter(stream, fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
summary = {
    'source': 'F09-current-uia-named/all-controls.json',
    'scope': 'captured rows across eight surfaces; recurring controls are counted once per surface, not unique product controls',
    'counts': {'rows': len(rows), 'named': sum(r['name_ok'] for r in rows),
               'valid_roles': sum(r['role_ok'] for r in rows),
               'observed_keyboard': sum(r['observed_keyboard_steps'] != '[]' for r in rows)},
    'surfaces': {surface: result['counts'] for surface, result in capture['captures'].items()},
    'missing_names': [dict(row) for row in rows if not row['name_ok']],
    'child_exit_code': capture['child_exit_code'],
    'audit_completed': capture['audit_completed'],
    'name_role_passed': capture['name_role_passed'],
    'complete_keyboard_verified': capture['complete_keyboard_verified'],
    'screen_reader_verified': capture['screen_reader_verified']}
(root / 'F09-control-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(summary['counts'], ensure_ascii=False))
print('Name/role=' + str(capture['name_role_passed']) + '; complete keyboard/speech=false')
