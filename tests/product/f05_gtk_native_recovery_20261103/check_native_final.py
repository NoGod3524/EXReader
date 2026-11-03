"""Local preflight controls; no GTK execution or native acceptance credit."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
from case_alignment import CASES, NOT_RUN_REASON, align_cases

coverage=[{'name':c[0],'outcome':'passed'} for c in CASES[:2]]
receipt=[{'id':c[0],'outcome':'passed'} if i<2 else
    {'id':'not-run-'+c[1],'outcome':'not-run','reason':NOT_RUN_REASON} for i,c in enumerate(CASES)]
claims={c[1]:[{'case_id':c[0] if i<2 else 'not-run-'+c[1],
    'role':c[2] if i<2 else c[3]}] for i,c in enumerate(CASES)}
rows=align_cases(coverage,receipt,claims)
assert [r['outcome'] for r in rows]==['passed']*2+['not-run']*4
print('coverage=2 / receipt=6')
for row in rows:print(row['id']+' / '+row['outcome'])
print('2 通过 + 4 not-run')
print('comparator=OK; acceptance=not-complete')

source=Path(__file__).with_name('gtk.py').read_text()
node=next(n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.FunctionDef) and n.name=='start_sync')
for mode in ('ready','fixture-not-ready','zero-session'):
    ticks=[0.0];keys=[];report={};observed=[]
    def monotonic():return ticks[0]
    def sleep(seconds):ticks[0]+=seconds
    def account(host):
        state={'session_present':'1' if mode=='ready' else '0','session_generation':'7' if mode=='ready' else '0'}
        observed.append(state);return state
    host=SimpleNamespace(folder=SimpleNamespace(name='control'),key=lambda key:keys.append(key))
    scope=dict(time=SimpleNamespace(monotonic=monotonic,sleep=sleep),json=json,report=report,checks=[],
        fixture_ready=lambda:{'thread_alive':mode!='fixture-not-ready','tls_ready':True},account=account)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'start_sync-control','exec'),scope)
    try:scope['start_sync'](host)
    except AssertionError:
        assert mode!='ready'
        if mode=='fixture-not-ready':assert not keys
        else:assert keys==['alt+s'] and 'stop_reason' in report and ticks[0]<5.2
    else:assert mode=='ready' and keys==['alt+s']
    print('preflight '+mode+': OK')
print('No runner used; controls do not count as product case results')
