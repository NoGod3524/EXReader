"""Exact current native crops plus immutable original failed pixels."""
import configparser
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/reader_gtk_navigation'))
from frame_proof import validate as validate_navigation
sys.path.insert(0, str(ROOT / 'tests/reader_hosts_integration'))
from final import Bundle, fetch, identity, require
MERGED = '58eda15d886268e054f2211a837b4032e946e165'
COMMON = '07ebe8786434ef384c97ccdb451242d3c6aee6cb'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
MODULES = 'f680aeaddfb1ecc67ead353554f5b91a5703f72f'


def authenticate(raw, source, run, attempt, program):
    guard=json.loads(raw('gtk-341-source-guard.json'));identity(guard,source,run,attempt)
    require(guard['accepted'] is True and guard['ordinary_merge_source']==MERGED and guard['common_source']==COMMON and
            guard['sdk']==SDK and guard['shared_version_support']==MODULES and guard['original_failed_run_retained']==40177143143,
            'wrong merged production guard')
    for path,value in guard['production_trees'].items():
        actual=subprocess.check_output(['git','rev-parse',source+':'+path],text=True).strip()
        expected=subprocess.check_output(['git','rev-parse',MERGED+':'+path],text=True).strip()
        require(value==actual==expected,'merged production differs: '+path)
    navigation=json.loads(raw('gtk-navigation-ui/result.json'));validate_navigation(navigation,source,run,attempt)
    require(navigation['program_sha256']==program,'navigation used another actual GTK host')
    hashes={}
    for item in navigation['image_observations']:
        png=raw('gtk-navigation-ui/'+item['name']+'.png',16*1024**2)
        picture=Image.open(io.BytesIO(png)).convert('RGB');x,y,width,height=item['crop']
        require(0<=x<x+width<=picture.width and 0<=y<y+height<=picture.height,'new page crop clipped')
        require(hashlib.sha256(picture.crop((x,y,x+width,y+height)).tobytes()).hexdigest()==item['sha256'],
                'new actual PNG contradicts exact page report')
        hashes[item['name']]=hashlib.sha256(png).hexdigest()
    f2=json.loads(raw('gtk-navigation-installed/result.json'));identity(f2,source,run,attempt)
    require(f2['accepted'] is True and f2['checks']==130,'original F2 installed scope missing')
    f2_probe=json.loads(raw('gtk-navigation-installed/probe.json'))
    require(len(f2_probe['checks'])==130 and all(row['pass'] is True for row in f2_probe['checks']), 'original F2 raw checks failed')
    mutations=[('source_sha','foreign'),('run_id','0'),('attempt','0'),('diagnostic_only',True),
               ('navigation_scope_passed',False),('count',28),('checks',[]),('program_sha256',''),
               ('complete_product',True),('performance_accepted',True)]
    for key,value in mutations:
        changed=copy.deepcopy(navigation);changed[key]=value
        try:validate_navigation(changed,source,run,attempt)
        except (ValueError,AssertionError,KeyError):continue
        raise ValueError('accepted navigation mutation '+key)
    for key in ('serial','generation','pixels'):
        changed=copy.deepcopy(navigation);after=changed['image_observations'][1]
        if key=='serial':after['draw_barrier']['painted_serial']=after['draw_barrier']['after_draw']
        elif key=='generation':after['host']['painted_generation']=-1
        else:after['sha256']='0'*64
        try:validate_navigation(changed,source,run,attempt)
        except (ValueError,AssertionError,KeyError):continue
        raise ValueError('accepted navigation mutation '+key)
    old_meta=fetch('actions/artifacts/12593244189')
    require(old_meta['workflow_run']['id']==40177143143 and
            old_meta['workflow_run']['head_sha']=='6f7c14e9eea98b60d92c5b4d7796e66576bae4eb' and
            old_meta['size_in_bytes']==60517704 and
            old_meta['digest']=='sha256:a39ff47a0de4d0b74c76eafbe32451405eecda27ade922525a9929085c43174b', 'original failed artifact replaced')
    old=Bundle(old_meta)
    try:
        failed=old.report('gtk-navigation-ui/result.json');identity(failed,old_meta['workflow_run']['head_sha'],40177143143,1)
        require(failed['navigation_scope_passed'] is False and any(row['name']=='read_only_browsing_close_preserves_pixels_notes_progress_and_product' and row['pass'] is False for row in failed['checks']),
                'original navigation failure hidden')
        state_raw=old.bytes('gtk-navigation-ui/state.ini',1024**2)
        require(hashlib.sha256(state_raw).hexdigest()=='482859b10be41c334200f563de8bf1b43638bbb5cb4137ebdf226d0f2e069abf','original failure state differs')
        state=configparser.ConfigParser(interpolation=None);state.read_string(state_raw.decode());host=state['host'];prefs=state['preferences']
        width,height=int(prefs['bitmap_width']),int(prefs['bitmap_height'])
        x=int(host['page_x'])+(int(host['page_width'])-width)//2;y=int(host['page_y'])+(int(host['page_height'])-height)//2
        pictures=[Image.open(io.BytesIO(old.bytes('gtk-navigation-ui/'+name+'.png',16*1024**2))).convert('RGB').crop((x,y,x+width,y+height))
                  for name in ('before-directory','after-directory')]
        original_hashes=[hashlib.sha256(picture.tobytes()).hexdigest() for picture in pictures]
        changed=sum(a!=b for a,b in zip(pictures[0].getdata(),pictures[1].getdata()))
        require(original_hashes==['380360e5714fba0ed52cc24ec68d53b10081d189ca6d5924896f6ea2953a9218',
                                 'a221a8489c90b0be2c3766df4c33c1571375516bd457663a60e3954ef26f4084'] and changed==52033,
                'original failed pixels were replaced')
    finally:old.close()
    return dict(accepted=True,navigation_checks=29,installed_f2_checks=130,protocol_rejections=len(mutations)+3,
                screenshot_sha256=hashes,bitmap_rgb_sha256=navigation['image_observations'][0]['sha256'],
                draw_barrier=navigation['image_observations'][1]['draw_barrier'],
                original_failure_run=40177143143,original_failed_bitmap_pixels=changed,original_source_reaccepted=False,
                original_artifact={key:old_meta[key] for key in ('id','name','size_in_bytes','digest','expires_at')})
