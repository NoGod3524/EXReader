"""Real AT-SPI and X11 semantic paths on freshly built, fixed-source GTK."""
import argparse,configparser,json,os,pathlib,sys,time,traceback
from common import *
root=pathlib.Path.cwd();target=root/'target';out=root/'build/d11/gtk-actions';out.mkdir(parents=True)
sys.path.insert(0,str(target/'tools'));sys.path.insert(0,str(target/'tests/reader_a11y_gtk'))
from check_linux_host import Session,command
import atspi_client as bus
binary=target/'build/d11-package-ON/EXReader-Linux/bin/exreader-linux';font=binary.parent.parent/'Reader.otf'
host=Session(binary,font,out);app=None;rows=pending('gtk');report=dict(**identity('gtk'),actions=rows,accepted=False,program_sha256=sha(binary),keyboard_accepted=False,screen_reader_accepted=False)
def nodes(name=None,roles=None):return [n for n in bus.walk(app) if (name is None or bus.name(n)==name) and (roles is None or bus.role(n) in roles) and bus.states(n).get('showing')]
def wait(fn):
 end=time.monotonic()+35
 while time.monotonic()<end:
  assert host.process.poll() is None
  value=fn()
  if value:return value
  time.sleep(.1)
 raise TimeoutError('native state not reached: '+repr(host.read()))
def element(name,roles=None):return wait(lambda:nodes(name,roles))[0]
def focus():return [dict(name=bus.name(n),role=bus.role(n),states=bus.states(n)) for n in bus.focused_all(app)]
def click_node(n):
 b=bus.extents(n);assert b and b['width']>0 and b['height']>0 and bus.states(n).get('sensitive')
 command('xdotool','mousemove','--sync',b['x']+b['width']//2,b['y']+b['height']//2);command('xdotool','click',1)
def click(name,roles=None):click_node(element(name,roles))
def record(key,passed=True,**raw):
 rows[key]=dict(action=key,exposed=True,enabled=raw.pop('enabled',True),executed=True,result='passed' if passed else 'failed',input='X11 pointer/keyboard',focus=focus(),raw=raw)
 (out/(key+'.tree.json')).write_text(json.dumps(bus.dump(app),indent=2));print('D11_ACTION '+json.dumps(rows[key]),flush=True);assert passed,key
def idle():host.wait(lambda s:not s['saving'] and not s.get('shelf_loading',0))
def menu(title):
 command('xdotool','windowactivate','--sync',host.window);click('More reader actions');click('Reading',{'menu'});host.key('Right');click(title,{'menu item'})
def state():return tuple(host.read().get(k) for k in ('book','part','page','start'))
try:
 assert bus.init()[0];host.launch();app=bus.wait_application('exreader-linux');idle()
 # Native disabled input: mouse click in exposed disabled Continue cannot open a reader.
 n=element('Continue reading');assert not bus.states(n).get('sensitive');b=bus.extents(n);before=host.read();command('xdotool','mousemove',b['x']+b['width']//2,b['y']+b['height']//2);command('xdotool','click',1);idle();record('disabled_noop',host.read()['reader_visible']==0,control='Continue reading',enabled=False,before=before,after=host.read())
 click('Import book');chooser=element('Import book',{'file chooser'});wait(lambda:any(bus.is_ancestor(chooser,n) and bus.states(n).get('showing') for n in bus.focused_all(app)));host.key('Escape');wait(lambda:not nodes('Import book',{'file chooser'}));record('cancel',host.read()['books']==0)
 source=out/'D11.txt';source.write_text('D11 semantic audit\n'+'A long reading page with searchable sample text.\n'*1600);original=sha(source)
 click('Import book');dialog=command('xdotool','search','--sync','--onlyvisible','--name','^Import book$').splitlines()[-1];command('xdotool','windowactivate','--sync',dialog);host.key('ctrl+l');chooser=element('Import book',{'file chooser'});entry=next(n for n in bus.walk(chooser) if bus.role(n)=='text' and bus.states(n).get('showing') and bus.states(n).get('sensitive'));click_node(entry);host.key('ctrl+a');host.paste(str(source.resolve()))
 def selection_ready():
  p=configparser.ConfigParser(interpolation=None);p.read(host.observe);v=dict(p['native_import']) if p.has_section('native_import') else {};wanted=__import__('hashlib').sha256(str(source.resolve()).encode()).hexdigest();return v.get('entry_sha256')==wanted and v.get('selected_sha256')==wanted and v.get('accept_sensitive')=='1'
 wait(selection_ready);host.key('Return');host.wait(lambda s:s['reader_visible']==1 and not s['saving']);wait(lambda:not nodes('Import book',{'file chooser'}));record('import',host.read()['books']==1)
 initial=state();click('Next page');host.wait(lambda s:not s['saving'] and state()!=initial);record('next',state()!=initial,before=initial,after=state());click('Previous page');host.wait(lambda s:not s['saving'] and state()==initial);record('previous',state()==initial)
 inventory=database_inventory(out/'profile')
 for key,title,caption in [('search','Search within book…','Search within book'),('directory','Directory / page entries…','Directory and page entries'),('records','Reading records…','Reading records'),('settings','Reading settings…','Reading settings')]:
  menu(title);modal=element(caption);wait(lambda:any(bus.is_ancestor(modal,n) and bus.states(n).get('showing') and bus.states(n).get('sensitive') for n in bus.focused_all(app)));record(key,True,modal=caption,entry_path='More reader actions > Reading > '+title,focused_inside=True)
  host.key('Escape');wait(lambda:not nodes(caption));idle();record('close.'+key,bool(focus()) and state()==initial,page=state())
 record('no_unexpected_revision',sha(source)==original and valid_inventory(inventory) and inventory==database_inventory(out/'profile'),before=inventory,after=database_inventory(out/'profile'),source_before=original,source_after=sha(source))
 click('Back to library');host.wait(lambda s:s['reader_visible']==0);record('back');click('Continue reading');host.wait(lambda s:s['reader_visible']==1 and not s['saving']);record('resume',state()==initial);click('Next page');host.wait(lambda s:not s['saving'] and state()!=initial);record('continue_after_return')
 report['accepted']=True
except Exception:report['error']=traceback.format_exc();print(report['error'],flush=True)
finally:
 if app is not None:
  try:(out/'final-tree.json').write_text(json.dumps(bus.dump(app),indent=2))
  except Exception:pass
 if host.process:
  try:host.close()
  except Exception:
   host.process.kill();host.process.wait();host.log.close()
 (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
assert report['accepted']
