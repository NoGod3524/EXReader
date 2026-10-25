"""Side-channel traces around the unchanged GTK sampler and its original watch."""
import importlib.util
import json
import os
from pathlib import Path
import select
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('frozen_c02_gtk',ROOT/'tests/reader_final_c02/gtk_perf.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
S=B.S
import observe as O

WATCHES={}
OriginalWatch=S.Watch
OriginalHost=S.Host


def stamp():return time.monotonic()


class FileEvents:
    """Independent inotify descriptor; its observations never feed the sampler."""
    def __init__(self,folder):
        self.folder=Path(folder);self.events=[];self.failure=None;self.running=False
        self.fd=O._libc.inotify_init1(O.IN_NONBLOCK|O.IN_CLOEXEC)
        if self.fd<0:self.failure='diagnostic inotify_init1 failed';return
        self.wd=O._libc.inotify_add_watch(self.fd,str(self.folder).encode(),O.WATCH_MASK)
        if self.wd<0:self.failure='diagnostic inotify_add_watch failed';os.close(self.fd);self.fd=-1;return
        self.running=True;self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()

    def loop(self):
        try:
            while self.running:
                ready,_,_=select.select([self.fd],[],[],0.1)
                if not ready:continue
                try:data=os.read(self.fd,65536)
                except BlockingIOError:continue
                delivered=stamp();position=0;batch=[]
                while position+O.EVENT.size<=len(data):
                    wd,mask,cookie,length=O.EVENT.unpack_from(data,position);position+=O.EVENT.size
                    name=data[position:position+length].rstrip(b'\0').decode(errors='replace');position+=length
                    batch.append(dict(at=delivered,mask=mask,cookie=cookie,name=name,watch=wd))
                # A latest snapshot, not a promise to reconstruct each overwritten write.
                state=O.read_state(self.folder/'state.ini');read_at=stamp()
                for item in batch:item.update(snapshot_read_at=read_at,latest_state=state)
                self.events.extend(batch)
        except Exception as error:self.failure=type(error).__name__+': '+str(error)

    def close(self):
        self.running=False
        if self.fd>=0:
            self.thread.join(timeout=2)
            if self.thread.is_alive():self.failure='diagnostic thread failed to join'
            os.close(self.fd);self.fd=-1


class TraceWatch(OriginalWatch):
    def __init__(self,folder,name='state.ini'):
        super().__init__(folder,name);self.operations=[];self.file_events=FileEvents(folder)
        WATCHES[str(self.folder.resolve())]=self

    def close(self):
        super().close();self.file_events.close()
        value=dict(schema=1,source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],
          attempt=os.environ['GITHUB_RUN_ATTEMPT'],operations=self.operations,original_observations=self.events,
          original_failure=self.failure,independent_file_events=self.file_events.events,
          independent_failure=self.file_events.failure,
          scope='diagnostic side channel only; no event or snapshot feeds original wait/predicate; latest snapshots can miss overwritten states')
        B.K.write_json(self.folder/'diagnostic-timeline.json',value)
        WATCHES.pop(str(self.folder.resolve()),None)


def watch_for(host):return WATCHES.get(str(host.folder.resolve()))


def snapshot(watch):
    return None if watch is None else dict(at=stamp(),mark=watch.mark(),latest=watch.latest())


class TraceHost(OriginalHost):
    def traced(self,name,function,*args,**kwargs):
        watch=watch_for(self);item=dict(operation=name,entered_at=stamp(),before=snapshot(watch))
        if name=='press':item['key']=str(args[0])
        if name=='open_import_dialog':
            path=Path(args[0]);item['path']=str(path)
            try:item['bytes']=path.stat().st_size
            except OSError as error:item['stat_fault']=str(error)
        try:
            result=function(*args,**kwargs);item.update(status='ok',result=result);return result
        except Exception as error:
            item.update(status='failed',fault_class=type(error).__name__,fault=str(error));raise
        finally:
            item.update(returned_at=stamp(),after=snapshot(watch),pid=self.pid)
            if watch is not None:watch.operations.append(item)

    def launch(self):return self.traced('launch',super().launch)
    def press(self,*args,**kwargs):return self.traced('press',super().press,*args,**kwargs)
    def open_import_dialog(self,*args,**kwargs):
        return self.traced('open_import_dialog',super().open_import_dialog,*args,**kwargs)


class DiagnosticSampler(B.CompactSampler):
    def await_state(self,host,watch,predicate,timeout,since=0,what='host state'):
        item=dict(operation='await_state',what=what,timeout=timeout,since=since,
                  entered_at=stamp(),before=snapshot(watch))
        try:
            result=super().await_state(host,watch,predicate,timeout,since,what)
            item.update(status='ok',result_index=result[0],result_event=result[1]);return result
        except Exception as error:
            item.update(status='failed',fault_class=type(error).__name__,fault=str(error));raise
        finally:
            item.update(returned_at=stamp(),after=snapshot(watch));watch.operations.append(item)


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true','Actions only'
    assert DiagnosticSampler.scenario_import is S.Sampler.scenario_import
    assert DiagnosticSampler.turns is S.Sampler.turns
    assert TraceWatch._loop is OriginalWatch._loop and TraceWatch.wait is OriginalWatch.wait
    S.Host=TraceHost;S.Watch=TraceWatch;B.CompactSampler=DiagnosticSampler
    B.main()


if __name__=='__main__':main()
