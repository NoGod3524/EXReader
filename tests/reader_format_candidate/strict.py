"""Recompute the dual-OS acceptance from same-attempt original ZIPs and actual program bytes."""
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from common import (ROOT, WORK, HERE, SDK, PATCHES, guard, identity, artifact, api_helpers, git,
                    file_hash, strict_json, write, verify_program, manifest_contract, original_manifest, load_module, combined_tree)
from test_argv import VECTORS


def native(path):
    rows = ET.parse(path).getroot().findall('.//testcase')
    names=[row.attrib['name'] for row in rows]
    assert len(names)==len(set(names))==169
    assert all(not any(child.tag in ('failure','error','skipped') for child in row) for row in rows)
    return sorted(names)


def main():
    provenance=guard(); own=identity(); fetch,_=api_helpers()
    jobs=fetch(f"actions/runs/{own['run_id']}/attempts/{own['attempt']}/jobs?per_page=100")['jobs']
    names={'preflight','corpus','producer-windows','producer-linux'}
    upstream=[row for row in jobs if row['name'] in names]
    assert len(upstream)==4 and {row['name'] for row in upstream}==names
    assert all(row['head_sha']==own['source_sha'] and row['status']=='completed' and row['conclusion']=='success' and row['run_attempt']==own['attempt'] for row in upstream), upstream
    metadata=fetch(f"actions/runs/{own['run_id']}/attempts/{own['attempt']}")
    assert metadata['head_sha']==own['source_sha'] and metadata['path'].split('@')[0]=='.github/workflows/reader-format-combination.yml'
    records=[row for row in fetch(f"actions/runs/{own['run_id']}/artifacts?per_page=100")['artifacts']
             if row['name'].endswith(f"-{own['run_id']}-{own['attempt']}")]
    expected_artifacts={f"{label}-{own['run_id']}-{own['attempt']}" for label in ('format-guard','format-corpus','format-windows','format-linux')}
    assert len(records)==4 and {row['name'] for row in records}==expected_artifacts
    verified=[]
    for label in ('guard','corpus','windows','linux'):
        verified.append(artifact('format-'+label,WORK/'strict'/label))
    original, v1=original_manifest(); v2=manifest_contract(strict_json((HERE/'manifest-v2.json').read_bytes()))
    corpus=WORK/'strict/corpus'; pin=strict_json((corpus/'pin.json').read_bytes())
    assert all(pin[key]==value for key,value in own.items())
    assert (corpus/'manifest-v1.json').read_bytes()==original
    assert file_hash(corpus/'manifest-v2.json')==provenance['manifest_v2_sha256']==pin['manifest_v2_sha256']
    expected_inputs={row['id']:row for row in v2['files']}
    assert {row['id'] for row in pin['files']}==set(expected_inputs) and len(pin['files'])==18
    for entry in v2['files']:
        path=corpus/entry['path']; assert path.stat().st_size==entry['source']['bytes'] and file_hash(path)==entry['source']['sha256']
        record=next(row for row in pin['files'] if row['id']==entry['id'])
        assert record['license']==entry['source']['license'] and record['sha256']==entry['source']['sha256']
    guard_record=strict_json((WORK/'strict/guard/guard.json').read_bytes())
    protocol=strict_json((WORK/'strict/guard/protocol.json').read_bytes())
    assert all(guard_record[key]==value for key,value in own.items())
    assert protocol['ok'] and protocol['rejected']==len(protocol['cases'])==122 and len(set(protocol['cases']))==122
    expected=combined_tree(); assert expected==strict_json((WORK/'strict/guard/trees.json').read_bytes())
    platforms={}; named_sets=[]; cbz_observations={}; f5=load_module(WORK/'vendor/f5/run_acceptance.py','strict_original_f5')
    mandatory_programs={'rtf-base','rtf-candidate','cbz-base','cbz-candidate','adapter-base','adapter-candidate',
                        'sdk-base','sdk-candidate','original-f5','argv-probe','argv-self-test','loaded-sdk-0'}
    for platform in ('windows','linux'):
        root=WORK/'strict'/platform
        summary=strict_json((root/'summary.json').read_bytes())
        assert all(summary[key]==value for key,value in own.items())
        assert summary['platform']==('Windows' if platform=='windows' else 'Linux')
        assert summary['candidate_package_accepted'] and summary['f5_v2_accepted'] and not summary['original_f5_v1_accepted']
        assert not summary['sdk_adopted'] and not summary['complete_product'] and summary['legacy_1710_count']==0
        assert strict_json((root/'trees.json').read_bytes())==summary['trees']==expected
        assert summary['manifest_v2_sha256']==provenance['manifest_v2_sha256']
        producer_guard=strict_json((root/'guard.json').read_bytes())
        assert producer_guard['sources']==provenance['sources'] and producer_guard['patches']==provenance['patches']
        native_sets={name:native(root/'logs'/(name+'-junit.xml')) for name in ('base','candidate')}
        assert native_sets['base']==native_sets['candidate']==summary['native_test_names']['base']==summary['native_test_names']['candidate']
        boundary=strict_json((root/'logs/rtf-candidate-boundary.log').read_bytes())
        assert boundary==summary['rtf_boundary'] and boundary['checks']==100 and boundary['padded']==5 and boundary['rejected']==26
        for variant in ('base','candidate'):
            for ident in ('rtf-crowley-policy','rtf-micro-republics'):
                probe=strict_json((root/'logs'/f'rtf-{variant}-{ident}.log').read_bytes())
                assert probe['status']==probe['expected']==(5 if variant=='base' else 0)
                assert probe['document']==(variant=='candidate')
        parts=strict_json((root/'s13-parts.json').read_bytes()); assert set(parts)=={'workspace','fixtures','real','suite'}
        checks=[(part['scope'],row['name']) for part in parts.values() for row in part['checks']]
        assert len(checks)==len(set(checks))==summary['s13_named_count']==103
        assert all(part['check_count']==len(part['checks']) and part['accepted'] and not part['failed'] and all(row['ok'] for row in part['checks']) for part in parts.values())
        assert parts['suite']['base_results']==parts['suite']['candidate_results']=={name:'passed' for name in native_sets['base']}
        named_sets.append(sorted(checks))
        for ident in ('cbz-pepper-01','cbz-pepper-02'):
            declared=expected_inputs[ident]['source']; raw_cbz=root/'s13/inputs'/(ident+'.cbz')
            assert raw_cbz.stat().st_size==declared['bytes'] and file_hash(raw_cbz)==declared['sha256']
            observation=strict_json((root/'s13/real-reports'/('candidate-'+ident+'-run1.json')).read_bytes())
            assert str(observation['input']).replace('\\','/').rsplit('/',1)[-1]==ident+'.cbz'
            # Only the declared runner-specific absolute prefix is excluded;
            # every native CBZ observation remains in the cross-platform comparison.
            observation['input']=ident+'.cbz'
            cbz_observations.setdefault(ident,{})[platform]=observation
        programs=strict_json((root/'programs.json').read_bytes())['programs']
        by_name={row['name']:row for row in programs}
        assert len(programs)==len(by_name)==summary['program_count']==12 and set(by_name)==mandatory_programs
        for program in programs:
            path=Path(program['path'])
            assert not path.is_absolute() and '..' not in path.parts
            verify_program(root/path,program)
        for variant in ('base','candidate'):
            library=root/'prefixes'/variant/('bin/exreader.dll' if platform=='windows' else 'lib/libexreader.so')
            assert file_hash(library)==by_name['sdk-'+variant]['sha256']
        args=strict_json((root/'argv/report.json').read_bytes())
        assert args['ok'] and len(args['vectors'])==len(VECTORS)
        assert all(row['case']==index and row['ok'] and row['argv_hex']==[value.encode('utf-8').hex() for value in VECTORS[index]] for index,row in enumerate(args['vectors']))
        assert args['probe_sha256']==by_name['argv-probe']['sha256'] and args['native_test_sha256']==by_name['argv-self-test']['sha256']
        if platform=='windows': assert args['native_utf16']['windows_utf16_checks']==5 and args['native_utf16']['invalid_rejected_without_fallback']
        panels={}
        for label,entries in (('v1-base-original',v1['files']),('v1-candidate-utf8',v1['files']),('v2-candidate-utf8',v2['files'])):
            panel=strict_json((root/'panels'/label/'summary.json').read_bytes())
            assert all(panel[key]==value for key,value in own.items())
            assert [row['id'] for row in panel['files']]==[row['id'] for row in entries]
            accepted=[]
            for entry,row in zip(entries,panel['files']):
                assert row['manifest_path']==entry['path'] and row['input_sha256']==entry['source']['sha256']
                output_lines=[line for line in row['stdout'].splitlines() if line.strip()]
                assert output_lines and strict_json(output_lines[-1])==row['result']
                mismatches=f5.compare_expectations(entry['expect'],row['result'])
                assert mismatches==row['mismatches']
                readback=root/'panels'/label/'results'/entry['id']/'readback.bin'
                readback_ok=readback.is_file() and readback.stat().st_size==entry['source']['bytes'] and file_hash(readback)==entry['source']['sha256']
                good=row['exit_code']==0 and not mismatches and readback_ok
                assert row['readback_verified']==readback_ok and (row['status']=='accepted')==good
                if label!='v1-base-original':
                    query=entry.get('query','').encode('utf-8').hex()
                    assert row['actual_query_utf8_hex']==query and re.findall(r'^FORMAT_QUERY_UTF8_HEX ([0-9a-f]*)$',row['stderr'],re.M)==[query]
                    assert row['loaded_sdk']['sha256']==by_name['sdk-candidate']['sha256']==by_name['loaded-sdk-0']['sha256']
                    assert row['loaded_sdk']['path']==by_name['loaded-sdk-0']['runtime_path']
                accepted.append(good)
            assert panel['accepted']==all(accepted)
            if label=='v2-candidate-utf8': assert all(accepted)
            elif label=='v1-candidate-utf8': assert [entry['id'] for entry,ok in zip(entries,accepted) if not ok]==['rtf-crowley-policy']
            else:
                assert not all(accepted)
                for row in panel['files']:
                    if row['id'].startswith('rtf-'): assert row['result']['detail']['import_error']=='Invalid or unsupported RTF stream'
                    if row['id'].startswith('cbz-'): assert row['result']['detail']['import_error']=='Unsafe CBZ member path'
            panels[label]={'accepted':panel['accepted'],'files':len(accepted),'accepted_files':sum(accepted)}
        platforms[platform]={'native_each':169,'rtf_boundary':100,'cbz_named':103,'argv_vectors':len(VECTORS),'programs':12,'panels':panels}
    assert named_sets[0]==named_sets[1]
    assert all(rows['windows']==rows['linux'] for rows in cbz_observations.values())
    result={**own,'candidate_package_accepted':True,'f5_v2_accepted':True,'original_f5_v1_accepted':False,
            'sdk_adopted':False,'host_integration_accepted':False,'complete_product':False,'legacy_1710_count':0,
            'scope':'isolated RTF+CBZ patch candidate and separately versioned 18-file F5 corpus on Windows/Linux',
            'jobs':[{key:row[key] for key in ('id','name','head_sha','conclusion')} for row in upstream],
            'artifacts':verified,'trees':expected,'manifest_v2_sha256':provenance['manifest_v2_sha256'],'platforms':platforms,
            'cbz_cross_platform_observations_identical':True,'failed':[],'pending':[]}
    write(WORK/'strict-result/summary.json',result); print(json.dumps(result),flush=True)


if __name__=='__main__':
    try: main()
    except Exception as error:
        write(WORK/'strict-result/failure.json',{**identity(),'candidate_package_accepted':False,'sdk_adopted':False,'error':repr(error)})
        raise
