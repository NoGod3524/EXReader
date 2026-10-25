"""Additional real input ownership and repeat focus observations, Actions only."""
import argparse,hashlib,json,os,pathlib,sys,traceback
assert os.environ.get('GITHUB_ACTIONS')=='true' and os.name=='nt'
p=argparse.ArgumentParser()
for name in ('target','candidate','font','output'):p.add_argument('--'+name,type=pathlib.Path,required=True)
a=p.parse_args();sys.path.insert(0,str(a.target/'tests/reader_windows_search'))
from check_ui import SearchApp,U,text
from check_keyboard import A,QUERY
out=a.output;out.mkdir(parents=True);app=None;records=[];accepted=False
try:
 source=out/'Focus.txt';source.write_text('focus token\n'+'long reading page\n'*1200,encoding='utf-8')
 app=SearchApp(a.candidate,a.font,out/'profile');app.wait_initial_shelf();app.wait_idle();app.import_file(source);app.wait_idle();app.open('Focus');app.wait_idle()
 A.USER32.SetForegroundWindow(app.window);A.tap(ord('F'),(A.VK_CONTROL,));d=app.dialog();q=U.GetDlgItem(d,QUERY);app.wait(lambda:A.focus_of(app.process.pid)==q)
 before=text(U.GetDlgItem(app.window,124))
 A.auto.ControlFromHandle(q).GetValuePattern().SetValue('abc')
 for key in (0x25,0x27,0x20,ord('A')):
  focus0=A.focus_of(app.process.pid);A.tap(key);app.wait_idle();focus1=A.focus_of(app.process.pid)
  after=text(U.GetDlgItem(app.window,124))
  records.append(dict(action='text-input-key',key=key,focus_before=focus0,focus_after=focus1,query=text(q),page_before=before,page_after=after,passed=focus1==q and before==after))
  assert records[-1]['passed']
 for i in range(3):
  A.tap(ord('F'),(A.VK_CONTROL,));app.wait_idle();records.append(dict(action='repeat-open-search',iteration=i,dialog=int(app.dialog()),focus=A.focus_of(app.process.pid),passed=app.dialog()==d));assert records[-1]['passed']
 A.tap(A.VK_ESCAPE);app.wait(lambda:not U.IsWindow(d));app.wait(lambda:A.focus_of(app.process.pid)==app.control('page'))
 records.append(dict(action='escape-focus-restore',focus=A.focus_of(app.process.pid),passed=True));accepted=True
except Exception:
 traceback.print_exc()
finally:
 if app:app.close()
 report=dict(accepted=accepted,checks=records,harness_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],program_sha256=hashlib.sha256(a.candidate.read_bytes()).hexdigest(),scope='search input ownership and repeated open only; repeated submit pending')
 (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
assert accepted
