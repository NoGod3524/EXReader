"""Native 100/150/200 x normal/high x default/small capability-gated matrix."""
import json
import os
from pathlib import Path
import sys
import time
import traceback
from contract import BASE,SDK,D08,TARGET,CONFIGS,REQUIRED,actual_scale,validate
from reuse import driver,OUT,ROOT
old=driver()
from prior_driver import U,W,C,P,w32,hc_read
import display


def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def contained(inner,outer):
    return bool(inner and outer and inner[0]<inner[2] and inner[1]<inner[3] and outer[0]<=inner[0]<inner[2]<=outer[2] and outer[1]<=inner[1]<inner[3]<=outer[3])


class Driver(old.Driver):
    def key(self,key,mods=()):
        # Reuse existing keyboard transport and trace, but require each actual
        # SendInput call to succeed rather than silently ignoring its return.
        assert self.kb.transport=='sendinput'
        self.kb.ready()
        vk=old.keyboard.KEYS.get(key,key)
        self.trace.event('d20-sendinput',dict(key=key,modifiers=list(mods)))
        pressed=[]
        try:
            for mod in mods:
                value=old.keyboard.MODIFIERS[mod]
                assert w32.send_key(value),('modifier injection failed',mod)
                pressed.append(value)
            assert w32.send_key(vk),('key injection failed',key)
            time.sleep(.03)
            assert w32.send_key(vk,up=True)
        finally:
            for value in reversed(pressed):assert w32.send_key(value,up=True)
        time.sleep(.18)

    def traversal(self):
        orders=[]
        for reverse in (False,True):
            samples=[]
            for _ in range(60):
                self.key('tab',('shift',) if reverse else ())
                value=self.focus(self.app.window);samples.append(value)
                if len(samples)>1 and value['hwnd'] in [s['hwnd'] for s in samples[:-1]]:break
            orders.append(samples)
        self.shot('keyboard-traversal')
        result=dict(forward=orders[0],reverse=orders[1],transport=self.kb.transport)
        self.config.setdefault('traversal_observations',[]).append(result)
        assert all(len({x['hwnd'] for x in order})>1 for order in orders),result
        assert all(x['descendant'] and x['visible'] and x['enabled'] for order in orders for x in order),result
        return result

    def status(self,scene):
        hwnd=self.app.control('status');text=w32.window_text(hwnd)
        bounds=w32.window_rect(hwnd);main=w32.window_rect(self.app.window)
        area=W.RECT();assert U.SystemParametersInfoW(0x30,0,C.byref(area),0)
        work=[area.left,area.top,area.right,area.bottom]
        image=P.shot(hwnd,self.out/(f'status-{self.config["configuration"]}-{scene}.bmp'))
        name=f'status-{self.config["configuration"]}-{scene}.bmp';self.config['screenshots'].append(name)
        node=self.uia.describe(self.uia.control(hwnd),patterns=True)
        count=len(set(image[2][i:i+3] for i in range(0,len(image[2]),4)))
        result=dict(hwnd=hwnd,text=text,uia_name=(node or {}).get('name'),uia=node,
                    visible=bool(U.IsWindowVisible(hwnd)),bounds=bounds,work_pixels=work,
                    contained=contained(bounds,main) and contained(bounds,work),paint_colors=count,
                    scope='nonempty native/UIA status text, exposed physical bounds and nonuniform actual client paint; not semantic glyph contrast or speech')
        self.config.setdefault('status_observations',{})[scene]=result
        assert result['visible'] and result['contained'] and text and result['uia_name'] and count>1,result
        return result

    def turn(self):
        assert self.goto(123),'reading page not keyboard-reachable'
        before=self.app.label();self.key('right');self.app.wait_idle()
        after=self.app.label();self.shot('page-turn')
        assert before!=after,{'before':before,'after':after}
        self.key('left');self.app.wait_idle();returned=self.app.label()
        assert returned==before,{'before':before,'returned':returned}
        return dict(before=before,after=after,returned=returned,transport='sendinput')

    def more(self):
        self.key(ord('V'),('alt',));self.key(ord('M'))
        self.app.wait(lambda:U.IsWindowVisible(U.GetDlgItem(self.app.window,122)),timeout=10)
        self.shot('more-expanded');self.contrast_pixels(self.app.window,'more')
        targets=[101,119,121,122,123,107,109]
        area=W.RECT();assert U.SystemParametersInfoW(0x30,0,C.byref(area),0)
        work=[area.left,area.top,area.right,area.bottom];main=w32.window_rect(self.app.window)
        controls=[dict(id=i,hwnd=int(U.GetDlgItem(self.app.window,i)),visible=bool(U.IsWindowVisible(U.GetDlgItem(self.app.window,i))),
            rect=w32.window_rect(U.GetDlgItem(self.app.window,i))) for i in targets]
        reached=self.goto(122);focus=self.focus(self.app.window)
        result=dict(work_pixels=work,window_pixels=main,controls=controls,note_editor_keyboard_reached=reached,focus=focus,
                    exposed_bounds_contained=contained(main,work) and all(contained(x['rect'],main) and contained(x['rect'],work) for x in controls))
        self.config['more_observation']=result
        self.attempt('status-more',lambda:self.status('more'))
        self.key(ord('V'),('alt',));self.key(ord('M'))
        self.app.wait(lambda:not U.IsWindowVisible(U.GetDlgItem(self.app.window,122)),timeout=10)
        result['collapse_focus']=self.focus(self.app.window);self.shot('more-collapsed')
        assert all(x['visible'] for x in controls) and reached and all(focus[k] for k in ('descendant','visible','enabled')) and result['exposed_bounds_contained'],result
        assert all(result['collapse_focus'][k] for k in ('descendant','visible','enabled')),result
        return result

    def run_matrix(self):
        original_hc=hc_read();initial=display.readback();configs=[];requests=[];restoration={}
        primary=[m for m in initial['monitors'] if m['primary']]
        assert len(primary)==1
        original_scale=primary[0]['scale_percent']
        try:
            for scale in (100,150,200):
                request=display.request_scale(scale,'scale-'+str(scale));requests.append(request)
                for contrast in ('normal','high'):
                    for size in ('default','small'):
                        self.config=dict(configuration=f'{scale}-{contrast}-{size}',requested_scale=scale,requested_contrast=contrast,requested_window=size,checks={},screenshots=[],execution='not-run-capability-pending',capability=dict(request=request,available=False))
                        configs.append(self.config)
                        if not request['available']:
                            self.config['capability']['reason']=request['reason']
                            for key in REQUIRED:self.check(key,'pending',{'reason':'actual requested display scale not available; no substitute 100% product observation'})
                            continue
                        h=hc_read();h.dwFlags=(h.dwFlags|1) if contrast=='high' else (h.dwFlags&~1)
                        C.set_last_error(0);hc_ok=bool(U.SystemParametersInfoW(0x43,h.cbSize,C.byref(h),2));error=C.get_last_error();time.sleep(.5)
                        actual=hc_read();readback=display.readback()
                        self.config['contrast_readback']=dict(set_return=hc_ok,winerror=error,flags=actual.dwFlags)
                        available=actual_scale(readback,scale) and bool(actual.dwFlags&1)==(contrast=='high')
                        self.config['capability'].update(available=available,readback=readback)
                        if not available:
                            for key in REQUIRED:self.check(key,'pending',{'reason':'requested high contrast or scale did not survive actual readback'})
                            continue
                        self.config['execution']='executed'
                        try:
                            self.launch(self.config['configuration'])
                            self.config['loaded_modules']=old.loaded_modules(self.app.process.pid)
                            self.config['actual_transport']=self.kb.transport
                            if size=='small':self.app.settle((700,480))
                            snap=self.shot('launch')
                            good=snap['monitor_scale']['scale_percent']==scale and snap['window_dpi']==scale*96//100
                            self.check('dpi','pass' if good else 'fail',snap)
                            self.geometry_pixels()
                            self.attempt('status-shelf',lambda:self.status('shelf'))
                            self.attempt('keyboard-shelf',self.traversal)
                            self.attempt('import-open',lambda:self.import_open('txt'))
                            if self.config['checks']['import-open']['status']=='pass':
                                self.attempt('status-reading',lambda:self.status('reading'))
                                self.attempt('keyboard-reading',self.traversal)
                                self.attempt('page-turn',self.turn)
                                for name,key in [('search',ord('F')),('directory',ord('G')),('records',ord('L')),('settings',0xBC)]:
                                    try:self.modal(name,key)
                                    except Exception:
                                        self.check(name,'fail',{'traceback':traceback.format_exc()})
                                        if self.dialog():self.key('escape')
                                self.attempt('more',self.more)
                                self.attempt('return-focus',self.returning)
                                try:self.modal('shelf-search',ord('F'))
                                except Exception:self.check('shelf-search','fail',{'traceback':traceback.format_exc()})
                        except Exception:self.config['driver_exception']=traceback.format_exc()
                        finally:
                            self.close()
                            for key in REQUIRED:
                                if key not in self.config['checks']:self.check(key,'error',{'reason':'not executed after recorded prerequisite failure'})
        finally:
            self.close();self.trace.close()
            hc_restore=bool(U.SystemParametersInfoW(0x43,original_hc.cbSize,C.byref(original_hc),2))
            restored_hc=hc_read();restoration.update(high_contrast_set_return=hc_restore,high_contrast_original_flags=original_hc.dwFlags,
                 high_contrast_final_flags=restored_hc.dwFlags,high_contrast_restored=bool(restored_hc.dwFlags&1)==bool(original_hc.dwFlags&1))
            final_display=display.readback()
            if not actual_scale(final_display,original_scale):
                restored=display.request_scale(original_scale,'restore-scale');restoration['scale_restore_request']=restored
                final_display=restored['readback']
            restoration.update(original_display=initial,final_display=final_display,scale_restored=actual_scale(final_display,original_scale))
            r=dict(accepted=False,screen_reader_accepted=False,source_sha=TARGET,target_sha=TARGET,seed=BASE,sdk_source=SDK,
                historical_source=D08,historical_results_reused=False,run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                program_sha256=old.digest(self.exe),configurations=configs,display_requests=requests,restoration=restoration,
                coverage={str(s):sum(c['execution']=='executed' for c in configs if c['requested_scale']==s) for s in (100,150,200)},
                limitations=['No Narrator/NVDA/physical-keyboard acceptance','Target DPI unawareness is recorded separately from actual monitor scale',
                    'Original D08 contrast pixel judgment remains pending unless it measured a failing enabled pair; no semantic glyph/focus/ICC grant',
                    'More/status native bounds and pixel samples do not prove all glyph clipping absent',
                    'Legacy selector host compact ON/raw3 OFF, current seed; no other source results combined'])
            r['files']=[dict(path=p.relative_to(OUT).as_posix(),bytes=p.stat().st_size,sha256=old.digest(p)) for p in sorted(OUT.rglob('*'))
                         if p.is_file() and 'profile-' not in p.as_posix() and p.name!='report.json']
            save(OUT/'report.json',r)
            print('D20_RESULT',json.dumps({k:r[k] for k in ('source_sha','program_sha256','coverage','restoration')},ensure_ascii=True),flush=True)
            validate(r,TARGET,os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_RUN_ATTEMPT'])
            assert restoration['scale_restored']
            assert not any(c.get('driver_exception') for c in configs)
            assert not any(v['status']=='error' for c in configs for v in c['checks'].values())


if __name__=='__main__':
    display.allowed();w32.make_dpi_aware();Driver().run_matrix()
