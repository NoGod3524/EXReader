#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only real production shelf UI, copied Window FrameMetrics and external process PSS."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import threading
import time

APP='org.exreader.host'
HELPER='org.exreader.host.uitest'
IDS=('first_interactive_real_catalog','forward_scroll_visits_all_real_sources',
     'reverse_scroll_preserves_keyset_and_recycles_views','same_title_has_130_stable_source_keys',
     'title_author_literal_and_empty_search','rapid_search_keeps_only_latest_query',
     'refresh_preserves_scrolled_source_anchor','rotation_background_and_process_restore_anchor',
     'offline_read_and_return_to_filtered_shelf','system_picker_import_appears_in_product_search')


def require(value,message):
    if not value:raise ValueError(message)


def save(path,value):
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def summarize(values):
    ordered=sorted(values)
    return {'count':len(ordered),**{f'p{int(q*100)}':ordered[max(0,math.ceil(q*len(ordered))-1)] if ordered else None
                                  for q in (.5,.95,.99)},'max':max(ordered,default=None)}


def analyze(root,identity):
    value=json.loads((root/'ui/validation.json').read_text())
    require(all(value.get(key)==item for key,item in identity.items()),'UI evidence source/run/attempt differs')
    cases=value.get('cases',[])
    require([case.get('id') for case in cases]==list(IDS) and len(cases)==10,'UI cases missing, reordered or duplicated')
    require(value.get('passed')==10 and value.get('failed')==0 and value.get('skipped')==0,'UI failure/skip')
    require(value.get('sdk')==34 and value.get('abi')=='x86_64','UI device differs')
    for case in cases:
        require(case.get('status')=='pass' and all(case.get(key)==item for key,item in identity.items()),'UI case failure or identity differs')
        raw=json.loads((root/'ui'/f'{case["id"]}.json').read_text())
        require(raw==case,'UI per-case report differs')
        require((root/'ui/shots'/f'{case["id"]}.png').stat().st_size>0,'UI screenshot missing/empty')
    frames=[]; pids=set(); windows=[]; drops=0
    for path in sorted((root/'windows').glob('*.jsonl')):
        raw=path.read_bytes();require(raw and raw.endswith(b'\n'),'truncated or empty Window trace')
        rows=[json.loads(line) for line in raw.splitlines()];header=rows[0]
        require(header.get('kind')=='start' and header.get('schema')==1,'Window trace header missing')
        pid,window=header['pid'],header['window_id'];pids.add(pid);sequence=0
        for row in rows[1:]:
            require(row['kind'] in ('frame','stop'),'Window capture failure or unexpected record')
            if row['kind']=='stop':
                require(row['frames']==sequence,'Window stop count differs');continue
            sequence+=1
            require(row.get('pid')==pid and row.get('window_id')==window and row.get('sequence')==sequence,'Window identity/sequence differs')
            require(type(row.get('total_ns')) is int and row['total_ns']>=0 and row.get('first_draw') in (0,1)
                    and type(row.get('drop_count')) is int and row['drop_count']>=0,'invalid completed frame')
            drops+=row['drop_count'];frames.append(row)
        require(sequence>0,'Window has no callbacks')
        windows.append({'file':path.name,'pid':pid,'window_id':window,'callbacks':sequence,
                        'closed_cleanly':rows[-1]['kind']=='stop','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    require(len(windows)>=3 and len(pids)>=2,'rotation and process restart Window identities missing')
    require(drops==0,'callback drops make performance observation incomplete')
    ordinary=[row for row in frames if row['first_draw']==0];require(len(ordinary)>=100,'too few completed ordinary frames')
    memory=json.loads((root/'pss-sampling.json').read_text());valid=[item for item in memory['samples'] if item.get('total_pss_kib') is not None]
    require(not memory['errors'] and len(valid)>=10,'external PSS sampling failed/incomplete')
    require({item['pid'] for item in valid}<=pids,'sampled PID is absent from Window traces')
    segments=[]
    for interval in value['intervals']:
        sample=[row['total_ns']/1e6 for row in ordinary if interval['started_elapsed_ns']<=row['callback_elapsed_ns']<=interval['finished_elapsed_ns']]
        require(len(sample)>=50,'scroll interval lacks completed frames')
        segments.append({**interval,'completed_frame_ms':summarize(sample)})
    first=cases[0]['detail']['observation']
    return {'ui_passed':10,'ui_failed':0,'ui_skipped':0,'real_sdk_sources':2202,'page_limit':50,'cache_limit':150,
            'first_interactive_ms':first['first_interactive_ms'],'completed_window_frame_ms':summarize([row['total_ns']/1e6 for row in ordinary]),
            'callback_drops':drops,'windows':windows,'scroll_segments':segments,
            'total_pss_kib':{'samples':len(valid),'median':statistics.median(item['total_pss_kib'] for item in valid),
                             'sampled_peak':max(item['total_pss_kib'] for item in valid)},
            'performance_budget_accepted':False,'physical_device_execution':False,
            'measurement_limits':['One fixed API34 x86_64 emulator; instrumented candidate only.',
                'FrameMetrics are completed Window callback durations, not display presentation or an isolated ListView cost.',
                'Callback collection/file writes and external PSS polling add overhead.',
                'Force-stop can leave a newline-complete trace without a stop record; undelivered callbacks are not a complete frame census.',
                'TOTAL PSS sampled about once a second; peak is sampled, not continuous, and covers the entire process.',
                'First interactive is the first visible, enabled shelf pre-draw after real catalog rows apply; includes existing SDK mapping repair.',
                'No comparison to the old ABBA run and no new performance/size budget.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    root=parser.parse_args().output;root.mkdir(parents=True,exist_ok=True)
    identity={'source_sha':os.environ.get('GITHUB_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID'),'attempt':os.environ.get('GITHUB_RUN_ATTEMPT')}
    result={**identity,'accepted':False,'problems':[]};samples={'samples':[],'errors':[]};stop=threading.Event();thread=None
    def command(argv,filename=None,timeout=60,checked=True):
        call=subprocess.run(argv,capture_output=True,timeout=timeout);raw=call.stdout+call.stderr
        if filename:(root/filename).write_bytes(raw)
        if checked:require(call.returncode==0,'command failed: '+' '.join(map(str,argv[:5])))
        return raw.decode(errors='replace')
    def adb(*args,**kwargs):return command(['adb',*map(str,args)],**kwargs)
    def sample():
        try:
            while not stop.is_set():
                slot=len(samples['samples']);start=time.monotonic_ns()
                text=adb('shell','pidof',APP,checked=False,timeout=10).strip()
                item={'slot':slot,'pid':int(text) if re.fullmatch(r'[0-9]+',text) else None}
                if item['pid'] is not None:
                    raw=adb('shell','dumpsys','meminfo',str(item['pid']),filename=f'pss/{slot}.txt',timeout=15)
                    match=re.search(r'\*\* MEMINFO in pid (\d+) \[org\.exreader\.host\] \*\*',raw)
                    total=re.search(r'TOTAL PSS:\s*(\d+)',raw)
                    if not total:total=re.search(r'^\s*TOTAL\s+(\d+)\s',raw,re.M)
                    after=adb('shell','pidof',APP,checked=False,timeout=10).strip()
                    if after!=str(item['pid']):item['process_changed_during_sample']=True
                    else:
                        require(match and int(match.group(1))==item['pid'] and total,'PSS PID/total differs')
                        item['total_pss_kib']=int(total.group(1))
                item['collection_elapsed_ms']=(time.monotonic_ns()-start)/1e6;samples['samples'].append(item)
                stop.wait(max(0,1-(time.monotonic_ns()-start)/1e9))
        except Exception as error:samples['errors'].append(type(error).__name__+': '+str(error))
    try:
        require(os.environ.get('GITHUB_ACTIONS')=='true' and identity['source_sha'],'cloud-only shelf execution')
        for name in ('app-debug.apk','uitest-debug.apk','uitest-debug-androidTest.apk'):
            adb('install','-r','-t','build/android-host/artifacts/'+name,filename='install-'+name+'.txt')
        adb('install','-r','-t','examples/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk',filename='install-catalog-runner.txt')
        adb('shell','pm','clear',APP,filename='clear-new-ui-fixture.txt')
        seed=adb('shell','am','instrument','-w','-r','-e','phase','seed-ui','-e','source_sha',identity['source_sha'],
                 '-e','run_id',identity['run_id'],'-e','attempt',identity['attempt'],
                 APP+'.test/org.exreader.host.ShelfCatalogTest',filename='seed-instrumentation.txt',timeout=900)
        require('EXR_SHELF_SEEDED 2202' in seed and 'INSTRUMENTATION_CODE: -1' in seed,'real UI SDK seed failed')
        adb('pull',f'/sdcard/Android/data/{APP}/files/shelf-tests',root/'seed',filename='pull-seed.txt')
        # The seeding instrumentation is not a measured UI process and has no Window.
        adb('shell','am','force-stop',APP,filename='stop-seeding-process.txt')
        adb('shell','mkdir','-p','/sdcard/Download')
        adb('push','build/android-host/fixtures/NewReview.txt','/sdcard/Download/',filename='push-new-fixture.txt')
        (root/'pss').mkdir();thread=threading.Thread(target=sample);thread.start()
        ui=adb('shell','am','instrument','-w','-r','-e','disableAnalytics','true',
               '-e','class','org.exreader.host.uitest.ShelfWalkthroughTest#shelf',
               '-e','exr_source_sha',identity['source_sha'],'-e','exr_run_id',identity['run_id'],'-e','exr_attempt',identity['attempt'],
               HELPER+'.test/androidx.test.runner.AndroidJUnitRunner',filename='ui-instrumentation.txt',timeout=1800)
        require('INSTRUMENTATION_CODE: -1' in ui and 'FAILURES!!!' not in ui,'shelf UI instrumentation failed')
    except Exception as error:result['problems'].append(type(error).__name__+': '+str(error))
    finally:
        stop.set()
        if thread:thread.join(20)
        if thread and thread.is_alive():samples['errors'].append('PSS sampler did not stop')
        save(root/'pss-sampling.json',samples)
        for remote,target in ((f'/sdcard/Android/data/{HELPER}/files/shelf-evidence','ui'),
                              (f'/sdcard/Android/data/{APP}/files/shelf-window-metrics','windows')):
            try:adb('pull',remote,root/target,filename='pull-'+target+'.txt',timeout=120)
            except Exception as error:result['problems'].append('collection: '+str(error))
        adb('logcat','-d','-v','threadtime',filename='logcat.txt',checked=False)
        try:result.update(analyze(root,identity))
        except Exception as error:result['problems'].append('analysis: '+type(error).__name__+': '+str(error))
        result['accepted']=not result['problems'];save(root/'result.json',result)
    print(json.dumps(result),flush=True)
    if not result['accepted']:raise SystemExit(1)


if __name__=='__main__':main()
