BASE='0889f7d1e9a537c6c1b05456547e016b26e1cd85'
TARGET='9321de84eb9c8d3d57cafbeaa8b0a28fe2a26a08'
SDK='edddc463c06ed5731195cdb8f06b2df6dff7699e'
FORMATS={'txt':'Reading sample.txt'}
CONFIGS=[f'{s}-{h}-{w}' for s in (100,150,200) for h in ('normal','high') for w in ('default','small')]
REQUIRED=['dpi','layout','contrast','import-open','search','directory','records','settings','return-focus']
def validate(r,sha,run,attempt):
    assert r['harness_sha']==sha and str(r['run_id'])==str(run) and str(r['attempt'])==str(attempt)
    assert r['target_sha']==TARGET and r['sdk_source']==SDK and r['accepted'] is False
    assert r['screen_reader_accepted'] is False and r['program_sha256']
    assert {x['configuration'] for x in r['configurations']}==set(CONFIGS)
    for config in r['configurations']:
        assert set(config['checks'])==set(REQUIRED)
        assert all(v['status'] in ('pass','fail','error','pending') for v in config['checks'].values())
        assert config['screenshots']
        if config['checks']['dpi']['status']=='pass':
            a=config['checks']['dpi']['actual'];assert a['monitor_scale']['scale_percent']==config['requested_scale'] and a['window_dpi']==96*config['requested_scale']/100
        for key in ('search','directory','records','settings'):
            if config['checks'][key]['status']=='pass':
                assert all(x['descendant'] and x['visible'] and x['enabled'] for x in config['checks'][key]['actual']['focus'])
    assert r['files']
