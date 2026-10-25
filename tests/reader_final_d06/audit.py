"""Scope/ancestor guard and exact source evidence index, not a behavioral verdict."""
import hashlib,json,os,pathlib,subprocess
assert os.environ.get('GITHUB_ACTIONS')=='true'
BASE='0889f7d1e9a537c6c1b05456547e016b26e1cd85'
def git(*a):return subprocess.check_output(['git',*a],text=True).strip()
assert git('rev-parse','HEAD')==os.environ['GITHUB_SHA']
subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],check=True)
paths=git('diff','--name-only',BASE,'HEAD').splitlines()
assert paths and all(p.startswith(('tests/reader_final_d06/','docs/reader-final-d06/')) or p in ('.github/workflows/reader-final-d06.yml','docs/validation/reader-final-d06.json','HANDOFF-RESULT.md') for p in paths)
subprocess.run(['git','diff','--exit-code',BASE,'HEAD','--','apps','examples','src','include','bindings','CMakeLists.txt','tests/fixtures'],check=True)
sources=['examples/reader.c','apps/reader/desktop/windows_compact_ui.inc','apps/reader/desktop/windows_search.inc','apps/reader/desktop/windows_navigation.inc','apps/reader/desktop/windows_records.inc','apps/reader/desktop/windows_preferences_ui.inc','examples/linux/reader.c','examples/linux/preferences_ui.inc','examples/apple/HostViews.swift','examples/apple/HostSearchViews.swift','examples/apple/HostNavigationViews.swift','examples/apple/HostReadingRecordViews.swift','examples/apple/HostAccountViews.swift','examples/android/app/src/main/java/org/exreader/host/MainActivity.java']
rows=[]
for f in sources:
 raw=pathlib.Path(f).read_bytes();lines=raw.decode().splitlines()
 rows.append(dict(path=f,sha256=hashlib.sha256(raw).hexdigest(),routes=[{'line':i,'text':line.strip()} for i,line in enumerate(lines,1) if any(s in line for s in ('WM_KEYDOWN','WM_SYSKEYDOWN','translate(','SetFocus(','GDK_KEY','grab_focus','keyboardShortcut','Button(','accessibilityIdentifier','dispatchKeyEvent','onBackPressed','KEYCODE','requestFocus'))]))
out=pathlib.Path('build/d06');out.mkdir(parents=True,exist_ok=True)
report=dict(harness_sha=os.environ['GITHUB_SHA'],implementation_source=BASE,sdk_source='edddc463c06ed5731195cdb8f06b2df6dff7699e',run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],scope='static routing index only',accepted=False,paths_changed=paths,sources=rows)
(out/'source-index.json').write_text(json.dumps(report,indent=2));print(json.dumps({'guard_passed':True,'source_files':len(rows),'accepted':False}))
