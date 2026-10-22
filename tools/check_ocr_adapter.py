#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import hashlib,json,math,pathlib,statistics,subprocess,sys,time,unicodedata
def normal(s):return ''.join(c for c in unicodedata.normalize('NFC',s) if not c.isspace())
def alignment(a,b):
 prev=list(range(len(b)+1));rows=[prev]
 for i,x in enumerate(a,1):
  row=[i]
  for j,y in enumerate(b,1):row.append(min(row[-1]+1,prev[j]+1,prev[j-1]+(x!=y)))
  rows.append(row);prev=row
 i,j=len(a),len(b);pairs=[]
 while i or j:
  if i and j and rows[i][j]==rows[i-1][j-1]+(a[i-1]!=b[j-1]):
   if a[i-1]==b[j-1]:pairs.append((i-1,j-1))
   i-=1;j-=1
  elif i and rows[i][j]==rows[i-1][j]+1:i-=1
  else:j-=1
 return rows[-1][-1],pairs
def restored(q,rot):
 # Input rotated clockwise from original 1600x900; undo to original ink coordinates.
 pts=[]
 for x,y in zip(q[::2],q[1::2]):
  if rot==90:x,y=y,900-x
  elif rot==180:x,y=1600-x,900-y
  elif rot==270:x,y=1600-y,x
  pts.append((x,y))
 return [min(x for x,y in pts),min(y for x,y in pts),max(x for x,y in pts),max(y for x,y in pts)]
def main():
 exe,models,corpus,out=map(pathlib.Path,sys.argv[1:]);out.mkdir(parents=True,exist_ok=True)
 manifest=json.loads((corpus/'manifest.json').read_text(encoding='utf8'));records=[];checks=0
 for page in manifest['pages']:
  image=corpus/page['path'];assert hashlib.sha256(image.read_bytes()).hexdigest()==page['sha256']
  dest=out/(page['id']+'.tsv');start=time.monotonic()
  args=[str(exe.resolve()),str(models.resolve()),'eng' if page['language']=='en' else 'chi_sim+eng',str(image),str(dest),str(page['correction']), 'contracts' if not records else 'normal']
  process=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90)
  (out/(page['id']+'.log')).write_bytes(process.stdout+process.stderr)
  assert process.returncode==0,(page['id'],process.returncode)
  items=[];contracts=0
  for line in dest.read_text().splitlines():
   columns=line.split('\t')
   if columns[0]=='backend':backend=columns[1];continue
   if columns[0]=='contracts':contracts=int(columns[1]);continue
   values=list(map(float,columns[1:18]));level=int(columns[0]);conf=values[0];pixel=values[1:9];mapped=values[9:17]
   assert 0<=conf<=100 and all(map(math.isfinite,values))
   for k in range(4):
    assert abs(mapped[2*k]-(pixel[2*k]*.24+13))<1e-8
    assert abs(mapped[2*k+1]-(-pixel[2*k+1]*.24+29+page['input_size'][1]*.24))<1e-8
    assert -.01<=pixel[2*k]<=page['input_size'][0]+.01 and -.01<=pixel[2*k+1]<=page['input_size'][1]+.01
    checks+=1
   items.append((level,bytes.fromhex(columns[18]).decode('utf8'),restored(pixel,page['rotation'])))
  prediction=''.join(t for level,t,b in items if level==1)
  expected=normal(''.join(page['lines']));actual=normal(prediction);error,_=alignment(expected,actual)
  ew=' '.join(page['lines']).split();aw=prediction.split();we,_=alignment(ew,aw)
  symbols=[]
  for level,text,box in items:
   if level!=3:continue
   for c in normal(text):symbols.append((c,box))
  _,pairs=alignment(''.join(x['char'] for x in page['characters']),''.join(c for c,b in symbols))
  offsets=[]
  for a,b in pairs:offsets.append(max(abs(x-y) for x,y in zip(page['characters'][a]['box'],symbols[b][1])))
  records.append({"id":page['id'],"language":page['language'],"rotation":page['rotation'],"input_sha256":page['sha256'],
     "cer_errors":error,"cer_characters":len(expected),"cer":error/len(expected),"wer_errors":we,"wer_words":len(ew),"wer":we/len(ew),
     "matched_character_boxes":len(offsets),"box_edge_error_px_mean":statistics.mean(offsets) if offsets else None,
     "box_edge_error_px_max":max(offsets,default=None),"wall_seconds":time.monotonic()-start,"backend":backend,"contracts":contracts,
     "prediction":prediction,"items":len(items),"raw_sha256":hashlib.sha256(dest.read_bytes()).hexdigest()})
 assert len(records)==30 and sum(r['contracts'] for r in records)==11
 aggregate={}
 for lang in ('en','zh','mixed'):
  group=[r for r in records if r['language']==lang]
  aggregate[lang]={"pages":len(group),"cer":sum(r['cer_errors'] for r in group)/sum(r['cer_characters'] for r in group),
                   "wer":sum(r['wer_errors'] for r in group)/sum(r['wer_words'] for r in group)}
 accepted=aggregate['en']['cer']<=.03 and aggregate['zh']['cer']<=.05
 report={"schema":1,"source":__import__('os').environ['GITHUB_SHA'],"accepted":accepted,"complete_wp11":False,
   "corpus_kind":manifest['kind'],"dpi":300,"pages":records,"aggregate":aggregate,"coordinate_roundtrip_checks":checks,
   "limits":{"english_cer":.03,"chinese_cer":.05},"model_identity":json.loads((models/'identity.json').read_text()),
   "fonts":manifest['fonts'],"unmet":["PDF text-layer writing, search, selection and annotation integration", "real scanned pages and handwriting", "automatic orientation detection"]}
 (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({"accepted":accepted,"pages":30,"aggregate":aggregate,"coordinate_roundtrip_checks":checks,"contracts":11}))
 if not accepted:sys.exit(1)
if __name__=='__main__':main()
