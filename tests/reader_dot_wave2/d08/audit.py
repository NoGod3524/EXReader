"""D08 genuine keyboard observations; DPI requests never substitute for readback."""
import os,sys,json,time,hashlib,traceback,copy
from pathlib import Path
from types import SimpleNamespace
from contract import *
from prior_driver import Audit,U,W,C,P,w32,keyboard,evidence,uia_layer,hc_read,monitor_scale,lum,rgb
ROOT=Path.cwd();OUT=ROOT/'build/d08-evidence'
U.IsChild.argtypes=[W.HWND,W.HWND];U.IsChild.restype=W.BOOL
U.IsWindowEnabled.argtypes=[W.HWND];U.IsWindowEnabled.restype=W.BOOL
U.IsWindowVisible.argtypes=[W.HWND];U.IsWindowVisible.restype=W.BOOL

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,r):p.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
class Driver(Audit):
    def __init__(self):
        self.out=OUT/'observations';self.out.mkdir(parents=True,exist_ok=True)
        self.trace=evidence.Trace(self.out/'keyboard.jsonl');self.uia=uia_layer.Uia();assert self.uia.available
        self.exe=OUT/'programs/EXReaderProduct.exe';self.font=OUT/'programs/Reader.otf';self.fixtures=OUT/'fixtures'
        self.args=SimpleNamespace(mode='ON');self.app=None;self.n=0;self.r={'screenshots':[],'snapshots':[]};self.config=None
    def shot(self,label,hwnd=None):
        hwnd=hwnd or self.app.window;name=f'{self.n:04d}-{self.config["configuration"]}-{label}';self.n+=1
        image=P.shot(hwnd,self.out/(name+'.bmp'));point=W.POINT(0,0);U.ClientToScreen(hwnd,C.byref(point))
        rect=W.RECT();U.GetClientRect(hwnd,C.byref(rect))
        s={'tree':self.uia.dump(hwnd,max_depth=5,pattern_depth=3),'native_focus':self.kb.focus(),'uia_focus':self.uia.focused(),
           'window_rect':w32.window_rect(hwnd),'client_rect':[rect.left,rect.top,rect.right,rect.bottom],'client_origin_screen':[point.x,point.y],
           'bitmap_pixels':[image[0],image[1]],'bitmap_coordinates':'client-local top-down BGRA after BMP decode','monitor_scale':monitor_scale(hwnd),
           'window_dpi':int(U.GetDpiForWindow(hwnd)),'system_dpi':int(U.GetDpiForSystem()),'awareness':int(U.GetAwarenessFromDpiAwarenessContext(U.GetWindowDpiAwarenessContext(hwnd)))}
        write(self.out/(name+'.json'),s);self.r['screenshots'].append(name+'.bmp');self.r['snapshots'].append(name+'.json');self.config['screenshots'].append(name+'.bmp');return s
    def focus(self,parent):
        h=self.kb.focus();return {'hwnd':h,'parent':parent,'descendant':bool(h and U.IsChild(parent,h)), 'visible':bool(h and U.IsWindowVisible(h)),'enabled':bool(h and U.IsWindowEnabled(h)),'uia':self.uia.focused()}
    def check(self,key,status,actual):
        self.config['checks'][key]={'status':status,'actual':actual,'snapshots':self.r['snapshots'][-2:]};print(json.dumps({'configuration':self.config['configuration'],'id':key,**self.config['checks'][key]},ensure_ascii=False),flush=True)
    def attempt(self,key,fn):
        try:self.check(key,'pass',fn())
        except Exception as exc:
            self.check(key,'fail',{'exception':str(exc),'traceback':traceback.format_exc()})
            try:self.shot(key+'-failure')
            except Exception:pass
            for _ in range(3):
                if not self.dialog():break
                self.trace.event('recovery_escape',{'failed':key});self.key('escape')
    def modal(self,name,key):
        before=self.focus(self.app.window);self.key(key,('ctrl',));d=self.wait_dialog();self.shot(name,d)
        samples=[self.focus(d)];self.key('tab');samples.append(self.focus(d));self.key('tab',('shift',));samples.append(self.focus(d))
        self.shot(name+'-tab',d);self.key('escape');self.app.wait(lambda:not U.IsWindow(d),timeout=8);after=self.focus(self.app.window);self.shot(name+'-closed')
        actual={'focus':samples,'before':before,'after':after,'dialog':d,'closed':True}
        okay=all(x['descendant'] and x['visible'] and x['enabled'] for x in samples) and all(after[x] for x in ('descendant','visible','enabled'))
        self.check(name,'pass' if okay else 'fail',actual)
        return actual
    def geometry_pixels(self):
        s=self.shot('geometry');r=s['window_rect'];work=W.RECT();U.SystemParametersInfoW(0x30,0,C.byref(work),0);issues=[]
        if r[0]<work.left or r[1]<work.top or r[2]>work.right or r[3]>work.bottom:issues.append({'window_outside_work_area':r})
        bounds=[]
        def walk(n):
            if n.get('native_hwnd') and n.get('rect') and not n.get('offscreen') and n.get('depth',0)>0:
                b=n['rect'];bounds.append(b)
                x,y=s['client_origin_screen'];w,h=s['bitmap_pixels']
                if b[0]<x or b[1]<y or b[2]>x+w or b[3]>y+h:issues.append({'control_outside_client':n})
            for c in n.get('children',[]):walk(c)
        walk(s['tree']);self.check('layout','fail' if issues else 'pass',{'issues':issues,'work_area':[work.left,work.top,work.right,work.bottom],'bounds_count':len(bounds),'scope':'native exposed rectangle containment; glyph clipping unverified'})
        # Capture each native text-bearing button's own client pixels. No screen/client subtraction guesses.
        samples=[]
        for id in (103,):
            h=U.GetDlgItem(self.app.window,id)
            if not h or not U.IsWindowVisible(h):continue
            image=P.shot(h,self.out/f'{self.config["configuration"]}-button-{id}.bmp');name=f'{self.config["configuration"]}-button-{id}.bmp';self.config['screenshots'].append(name)
            fg=rgb(U.GetSysColor(18));bg=rgb(U.GetSysColor(15));counts={'fg':0,'bg':0};coords={'fg':[],'bg':[]}
            for y in range(2,image[1]-2):
                for x in range(2,image[0]-2):
                    pixel=P.at(image,x,y)
                    for label,color in (('fg',fg),('bg',bg)):
                        if list(pixel)==color:
                            counts[label]+=1
                            if len(coords[label])<8:coords[label].append([x,y,list(pixel)])
            lo,hi=sorted((lum(fg),lum(bg)));ratio=(hi+.05)/(lo+.05)
            samples.append({'control':id,'hwnd':h,'screenshot':name,'pixels':image[:2],'foreground':fg,'background':bg,'exact_pixel_counts':counts,'pixel_coordinates':coords,'ratio':ratio,'coordinate_space':'own-control client bitmap','color_space':'8-bit GDI device RGB, sRGB assumed; no ICC measurement'})
        # Sample is useful diagnostic, but no measured ICC or exhaustive glyph/focus/disabled coverage.
        status='fail' if any(x['exact_pixel_counts']['fg'] and x['exact_pixel_counts']['bg'] and x['ratio']<4.5 for x in samples) else 'pending'
        self.check('contrast',status,{'samples':samples,'reason':'actual sampled pixels retained; ICC/sRGB mapping and all text/focus/disabled paints not certified'})
    def returning(self):
        self.key('left',('alt',));self.shot('return-shelf');f=self.focus(self.app.window)
        assert U.IsWindowVisible(self.app.control('books')) and all(f[k] for k in ('descendant','visible','enabled')),f
        return f
    def run_all(self):
        original=hc_read();configs=[]
        try:
            for scale in (100,150,200):
                for contrast in ('normal','high'):
                    for size in ('default','small'):
                        self.config={'configuration':f'{scale}-{contrast}-{size}','requested_scale':scale,'requested_contrast':contrast,'requested_window':size,'checks':{},'screenshots':[]};configs.append(self.config)
                        try:
                            ok=bool(U.SystemParametersInfoW(0x009F,{100:0,150:1,200:2}[scale],None,0));time.sleep(.3)
                            h=hc_read();h.dwFlags=(h.dwFlags|1) if contrast=='high' else (h.dwFlags&~1);hc_ok=bool(U.SystemParametersInfoW(0x43,h.cbSize,C.byref(h),2))
                            self.launch(self.config['configuration'])
                            if size=='small':self.app.settle((700,480))
                            s=self.shot('launch');self.config['contrast_readback']={'set_return':hc_ok,'flags':hc_read().dwFlags};self.config['dpi_request_return']=ok
                            good=s['monitor_scale']['scale_percent']==scale and s['window_dpi']==scale*96/100
                            self.check('dpi','pass' if good else 'fail',s)
                            self.geometry_pixels();self.attempt('import-open',lambda:self.import_open('txt'))
                            if self.config['checks']['import-open']['status']=='pass':
                                for name,key in [('search',ord('F')),('directory',ord('G')),('records',ord('L')),('settings',0xBC)]:
                                    try:self.modal(name,key)
                                    except Exception as exc:
                                        self.check(name,'fail',{'exception':str(exc),'traceback':traceback.format_exc()})
                                        if self.dialog():self.key('escape')
                                self.attempt('return-focus',self.returning)
                                # Preserve shelf-search focus regression independently, not folded into reading search.
                                try:self.modal('shelf-search',ord('F'));self.config['shelf_search']=self.config['checks'].pop('shelf-search')
                                except Exception as exc:self.config['shelf_search']={'status':'fail','actual':str(exc)}
                        except Exception:self.config['exception']=traceback.format_exc()
                        finally:
                            self.close()
                            for key in REQUIRED:
                                if key not in self.config['checks']:self.check(key,'error',{'reason':'not executed after recorded prerequisite failure'})
                            # Unexpected check names are not silently counted as mandatory checks.
                            self.config['checks'].pop('shelf-search',None)
        finally:
            U.SystemParametersInfoW(0x43,original.cbSize,C.byref(original),2);U.SystemParametersInfoW(0x009F,0,None,0);self.close();self.trace.close()
            r={'accepted':False,'screen_reader_accepted':False,'harness_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'target_sha':TARGET,'sdk_source':SDK,'program_sha256':digest(self.exe),'configurations':configs,'limitations':['Narrator and physical keyboard pending','Scale mismatch is failed required coverage, not successful DPI emulation','Contrast has actual pixels but no global compliance grant','Native bounds do not prove glyph clipping']}
            r['files']=[{'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(OUT.rglob('*')) if p.is_file() and 'profile-' not in p.as_posix() and p.name!='report.json']
            write(OUT/'report.json',r);validate(r,os.environ['GITHUB_SHA'],os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_RUN_ATTEMPT'])
if __name__=='__main__':
    assert os.environ.get('GITHUB_ACTIONS')=='true' and os.name=='nt'
    w32.make_dpi_aware();Driver().run_all()
