#!/usr/bin/env python3
"""Exact first-catalog Window-frame association, separate from visibility and F08 acceptance."""
import argparse
import json
from pathlib import Path

MAX_NS=(1<<63)-1


def audit_window(binding,window):
    errors=[]
    result={'binding_complete':False,'f08_accepted':False,'errors':errors,
            'name':'Window-frame completion upper bound','tti_upper_ms':None,
            'tti_upper_budget_passed':None,'original_tti_budget_ms':2000,
            'physical_presentation_proven':False}
    def need(ok,message):
        if not ok:errors.append(message)
        return ok
    def ns(row,key):
        value=row.get(key)
        if type(value) is not int or value<0 or value>MAX_NS:
            raise ValueError('unavailable/invalid ns: '+key)
        return value
    try:
        if not need(bool(binding) and bool(window),'missing trace'):return result
        header=binding[0];native_header=window[0]
        if not need(header.get('kind')=='start' and header.get('schema')==1,'binding header'):return result
        if not need(native_header.get('kind')=='start' and native_header.get('schema')==1,'Window header'):return result
        identity=(header.get('pid'),header.get('window_id'))
        need(all(type(x) is int and x>0 for x in identity),'invalid Window identity')
        need(identity==(native_header.get('pid'),native_header.get('window_id')),'wrong Window header')
        start=ns(header,'activity_started_elapsed_ns')
        need(start==ns(native_header,'activity_started_elapsed_ns'),'activity start differs')
        events={}
        allowed={'apply','latch','ready_pre_draw','tree_draw_begin','clear','stop'}
        for row in binding[1:]:
            kind=row.get('kind');need(kind in allowed,'unknown binding event')
            need((row.get('pid'),row.get('window_id'))==identity,'wrong event Window')
            need(type(row.get('latch_id')) is int and row.get('latch_id')==1,'wrong latch identity')
            events.setdefault(kind,[]).append(row)
        for kind in ['apply','latch','ready_pre_draw','tree_draw_begin','clear']:
            need(len(events.get(kind,[]))==1,'missing/duplicate '+kind)
        need(len(events.get('stop',[]))<=1,'duplicate binding stop')
        if errors:return result
        apply,latch,ready,draw,clear=(events[k][0] for k in ['apply','latch','ready_pre_draw','tree_draw_begin','clear'])
        for row,status in [(apply,'armed'),(latch,'latched'),(ready,'candidate'),(draw,'candidate'),(clear,'cleared')]:
            need(row.get('status')==status,'binding status '+str(row.get('status')))
        revision=(apply.get('generation'),apply.get('revision'))
        need(all(type(x) is int and x>=0 for x in revision),'invalid revision')
        for row in [latch,ready,draw,clear]:
            need((row.get('generation'),row.get('revision'))==revision,'wrong revision')
        time=ns(latch,'frame_time_ns')
        need(time>0,'invalid frame time')
        for row in [ready,draw,clear]:need(ns(row,'frame_time_ns')==time,'cross-frame timestamp')
        need(all(row.get('active') is True for row in [latch,ready,draw]),'cross-frame inactive latch')
        need(clear.get('active') is False,'latch not cleared')
        mono=[ns(row,'mono_ns') for row in [apply,latch,ready,draw,clear]]
        need(mono==sorted(mono) and mono[3]>time,'UI frame witness order')
        elapsed=[ns(row,'elapsed_ns') for row in [apply,latch,ready,draw,clear]]
        need(elapsed==sorted(elapsed) and elapsed[2]>=start,'elapsed witness order')
        need(all(row.get('kind') in ('frame','stop') for row in window[1:]),'native capture error/unknown row')
        frames=[row for row in window[1:] if row.get('kind')=='frame']
        need(bool(frames),'missing native callbacks')
        for sequence,row in enumerate(frames,1):
            need((row.get('pid'),row.get('window_id'))==identity,'wrong callback Window')
            need(type(row.get('sequence')) is int and row.get('sequence')==sequence,'callback sequence missing/duplicate')
            need(type(row.get('drop_count')) is int and row.get('drop_count')==0,'callback drop/unavailable')
        matches=[row for row in frames if row.get('vsync_ns')==time]
        result['exact_vsync_matches']=len(matches)
        if not need(len(matches)==1,'missing/duplicate exact native VSYNC'):return result
        frame=matches[0]
        intended=ns(frame,'intended_vsync_ns');vsync=ns(frame,'vsync_ns');total=ns(frame,'total_ns')
        # API34 public metric intervals telescope exactly to FrameInfo.DrawStart.
        stages=[ns(frame,key) for key in ['unknown_ns','input_ns','animation_ns','layout_measure_ns']]
        draw_start=intended+sum(stages);completed=intended+total
        need(draw_start<=MAX_NS and completed<=MAX_NS,'native timestamp overflow')
        need(intended<=vsync,'native intended/actual order')
        need(draw_start>=mono[3]>time,'RT-only/unproven native DrawStart before tree_draw_begin')
        need(completed>=draw_start,'native completion before UI draw')
        callback_mono=ns(frame,'callback_mono_ns');callback_elapsed=ns(frame,'callback_elapsed_ns')
        need(callback_mono>=completed,'callback before native completion')
        need(callback_elapsed>=elapsed[3]>=start,'callback elapsed order')
        if errors:return result
        upper=(callback_elapsed-start)/1e6
        result.update(binding_complete=True,tti_upper_ms=upper,tti_upper_budget_passed=upper<=2000,
                      original_ready_pre_draw_ms=(elapsed[2]-start)/1e6,
                      callback_after_pre_draw_ms=(callback_elapsed-elapsed[2])/1e6,
                      native_draw_start_mono_ns=draw_start,native_frame_completed_mono_ns=completed,
                      matched_sequence=frame['sequence'],vsync_ns=vsync,intended_vsync_ns=intended,
                      closed_cleanly=bool(events.get('stop')))
    except (ValueError,TypeError,KeyError,IndexError) as error:
        errors.append(str(error))
    return result


def audit_directory(windows):
    files=sorted((windows/'catalog-ready').glob('*.jsonl'))
    result={'f08_accepted':False,'binding_complete':False,'windows':[],'errors':[]}
    if not files:result['errors'].append('missing catalog-ready files')
    native=sorted(windows.glob('*.jsonl'))
    if {p.name for p in native}!={p.name for p in files}:result['errors'].append('binding/native Window census differs')
    for path in files:
        try:
            counterpart=windows/path.name
            raw=path.read_bytes();other=counterpart.read_bytes()
            if not raw.endswith(b'\n') or not other.endswith(b'\n'):raise ValueError('truncated trace')
            value=audit_window([json.loads(x) for x in raw.splitlines()],[json.loads(x) for x in other.splitlines()])
        except (OSError,ValueError) as error:
            value={'binding_complete':False,'errors':[str(error)]}
        result['windows'].append({'file':path.name,**value})
    result['binding_complete']=bool(files) and not result['errors'] and all(x['binding_complete'] for x in result['windows'])
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('windows',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();value=audit_directory(args.windows);text=json.dumps(value,indent=2)+'\n'
    if args.output:args.output.write_text(text)
    print(text,end='')
    raise SystemExit(not value['binding_complete'])
