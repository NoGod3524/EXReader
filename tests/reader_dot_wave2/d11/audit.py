"""Immutable source routing index. Declarations never grant UI operation."""
import json,os,pathlib,subprocess,hashlib
from common import TARGETS,ACTIONS
assert os.environ.get('GITHUB_ACTIONS')=='true'
BASE='0889f7d1e9a537c6c1b05456547e016b26e1cd85'
def git(*a):return subprocess.check_output(['git',*a],text=True).strip()
assert git('rev-parse','HEAD')==os.environ['GITHUB_SHA'];subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],check=True)
changed=git('diff','--name-only',BASE,'HEAD').splitlines();assert changed and all(p.startswith(('tests/reader_dot_wave2/d11/','docs/reader-dot-wave2/d11/')) or p in ('.github/workflows/reader-dot-d11.yml','HANDOFF-RESULT-D11.md') for p in changed)
sources={}
for host,sha in TARGETS.items():
 subprocess.run(['git','fetch','origin',sha],check=True)
 paths={'windows':['apps/reader/desktop/windows_compact_ui.inc','apps/reader/desktop/windows_search.inc','apps/reader/desktop/windows_navigation.inc','apps/reader/desktop/windows_records.inc','apps/reader/desktop/windows_preferences_ui.inc'],'gtk':['examples/linux/reader.c','examples/linux/preferences_ui.inc'],'android':['examples/android/app/src/main/java/org/exreader/host/MainActivity.java']}.get(host,['examples/apple/HostViews.swift','examples/apple/HostSearchViews.swift','examples/apple/HostNavigationViews.swift','examples/apple/HostReadingRecordViews.swift','examples/apple/HostPageThemeViews.swift'])
 rows=[]
 for path in paths:
  result=subprocess.run(['git','show',sha+':'+path],capture_output=True,text=True)
  if result.returncode:rows.append(dict(path=path,status='missing'));continue
  raw=result.stdout;rows.append(dict(path=path,sha256=hashlib.sha256(raw.encode()).hexdigest(),declarations=[dict(line=i,text=line.strip()) for i,line in enumerate(raw.splitlines(),1) if any(k in line for k in ('WM_KEYDOWN','WM_SYSKEYDOWN','GDK_KEY','grab_focus','SetFocus','Button(','accessibilityIdentifier','dispatchKeyEvent','setOnClickListener','requestFocus','IDC_COMPACT','AppendMenu','keycode'))]))
 sources[host]=dict(target_sha=sha,scope='source declarations only, exposed/enabled/operable unknown until native observation',files=rows)
out=pathlib.Path('build/d11');out.mkdir(parents=True,exist_ok=True);report=dict(harness_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],sources=sources,required_actions=ACTIONS,changed=changed,accepted=False)
(out/'source-index.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(source_targets=list(sources),accepted=False)),flush=True)
