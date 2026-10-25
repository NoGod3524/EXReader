"""Actual GTK compact pointer/keyboard transitions; observe real processing."""
import configparser,sys,time,subprocess
from pathlib import Path
from contract import digest
ROOT=Path('target').resolve();sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(Path('atspi').resolve()))
from check_linux_host import Session,command
import atspi_client as bus
class Driver:
    def __init__(self,out,program,font):
        self.out=out;self.host=Session(program,font,out);assert bus.init()[0]
    def launch(self,stage):
        self.host.launch();self.app=bus.wait_application('exreader-linux');self.idle();return self.host.process
    def state(self):return dict(self.host.read(),search=self.section('inbook_search'),native_import=self.section('native_import'))
    def section(self,name):
        p=configparser.ConfigParser(interpolation=None);p.read(self.host.observe,encoding='utf-8');return dict(p[name]) if p.has_section(name) else {}
    def wait(self,fn,seconds=30):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            assert self.host.process.poll() is None,'product exited'
            value=fn()
            if value:return value
            time.sleep(.02)
        raise TimeoutError('GTK transition: '+repr(self.state()))
    def nodes(self,name,roles=None):return [n for n in bus.walk(self.app) if bus.name(n)==name and (roles is None or bus.role(n) in roles) and bus.states(n).get('showing')]
    def element(self,name,roles=None):return self.wait(lambda:self.nodes(name,roles))[0]
    def click_node(self,n):
        r=bus.extents(n);assert r and r['width']>0 and r['height']>0 and bus.states(n).get('sensitive')
        command('xdotool','mousemove','--sync',r['x']+r['width']//2,r['y']+r['height']//2);command('xdotool','click','1')
    def click(self,name,roles=None):self.click_node(self.element(name,roles))
    def idle(self):self.host.wait(lambda v:not v['saving'] and not v.get('shelf_loading',0),timeout=30)
    def menu(self,title):
        command('xdotool','windowactivate','--sync',self.host.window);self.click('More reader actions');self.click('Reading',{'menu'});self.host.key('Right');self.click(title,{'menu item'})
    def position(self):return tuple(self.host.read()[k] for k in ('book','part','page','start'))
    def open(self,path,importing=False):
        if self.host.read()['reader_visible']:self.click('Back to library');self.host.wait(lambda v:v['reader_visible']==0)
        if importing:
            before=self.host.read()['generation'];self.click('Import book')
            dialog=command('xdotool','search','--sync','--onlyvisible','--name','^Import book$').splitlines()[-1]
            command('xdotool','windowactivate','--sync',dialog);self.host.key('ctrl+l')
            chooser=self.element('Import book',{'file chooser'})
            entry=next(n for n in bus.walk(chooser) if bus.role(n)=='text' and bus.states(n).get('showing') and bus.states(n).get('sensitive'))
            self.click_node(entry);self.host.key('ctrl+a');self.host.paste(str(path.resolve()))
            import hashlib
            wanted=hashlib.sha256(str(path.resolve()).encode()).hexdigest()
            self.wait(lambda:self.section('native_import').get('entry_sha256')==wanted and self.section('native_import').get('selected_sha256')==wanted and self.section('native_import').get('accept_sensitive')=='1')
            self.host.key('Return')
            self.host.wait(lambda v:v['generation']>before and v['reader_visible']==1 and not v['saving'])
            self.wait(lambda:not self.nodes('Import book',{'file chooser'}))
        else:
            shelf=self.element('Bookshelf')
            rows=[n for n in bus.children(shelf) if bus.role(n)=='list item' and path.stem in bus.name(n)]
            assert len(rows)==1,[(bus.name(n),bus.role(n)) for n in bus.children(shelf)]
            self.click_node(rows[0]);self.host.key('Return');self.host.wait(lambda v:v['reader_visible']==1 and not v['saving'])
        assert self.host.read()['error']==0 and self.host.read()['frame_generation']>0
    def forward(self):
        self.before_page=self.position();generation=self.host.read()['generation'];self.click('Next page')
        self.host.wait(lambda v:v['generation']>generation and not v['saving']);assert self.position()!=self.before_page and self.host.read()['error']==0
    def backward(self):
        generation=self.host.read()['generation'];self.click('Previous page');self.host.wait(lambda v:v['generation']>generation and not v['saving']);assert self.position()==self.before_page and self.host.read()['error']==0
    def library(self):self.before_page=self.position();self.click('Back to library');self.host.wait(lambda v:v['reader_visible']==0)
    def resume(self):self.click('Continue reading');self.host.wait(lambda v:v['reader_visible']==1 and not v['saving']);assert self.position()==self.before_page
    def modal(self,name):
        title,caption={'search':('Search within book…','Search within book'),'directory':('Directory / page entries…','Directory and page entries'),'records':('Reading records…','Reading records'),'settings':('Reading settings…','Reading settings')}[name]
        self.menu(title);dialog=self.element(caption)
        self.wait(lambda:any(bus.is_ancestor(dialog,n) and bus.states(n).get('showing') and bus.states(n).get('sensitive') for n in bus.focused_all(self.app)))
        self.host.key('Escape');self.wait(lambda:not self.nodes(caption));self.idle()
    def import_cancel(self):
        before=self.position();count=self.host.read()['books'];command('xdotool','windowactivate','--sync',self.host.window);self.host.key('F1');self.element('Import book',{'file chooser'})
        self.host.key('Escape');self.wait(lambda:not self.nodes('Import book',{'file chooser'}));self.idle()
        assert self.position()==before and self.host.read()['books']==count and self.section('native_import').get('active')=='0'
    def close_processing(self,path):
        self.open(path,True);self.menu('Search within book…');self.element('Search within book',{'dialog'})
        self.click('In-book query',{'text'});self.host.paste('ABSENT_QUERY_FOR_FULL_CHAPTER_SCAN')
        # Launch native input asynchronously, so helper sleeps cannot hide the processing interval.
        sender=subprocess.Popen(['xdotool','key','--clearmodifiers','--delay','0','alt+s'])
        observed=self.wait(lambda:self.section('inbook_search') if self.section('inbook_search').get('phase')=='2' and int(self.section('inbook_search').get('polls','0'))>0 else None,10)
        sender.wait(timeout=5)
        command('wmctrl','-ic',hex(int(self.host.window)))
        self.host.process.wait(timeout=30);self.host.log.close();assert self.host.process.returncode==0
        return observed
    def no_replay(self):
        assert self.section('inbook_search').get('visible')=='0' and self.section('inbook_search').get('count')=='0'
        assert self.section('native_import').get('active')=='0' and not self.host.read()['busy']
        return self.state()
    def close(self):self.host.close();return dict(exit_code=self.host.process.returncode)
    def snapshot(self,label):
        command('import','-window',self.host.window,self.out/(label+'.png'))
        return dict(state=self.state(),windows=command('xwininfo','-root','-tree'),nodes=[dict(name=bus.name(n),role=bus.role(n),states=bus.states(n)) for n in bus.walk(self.app)])
