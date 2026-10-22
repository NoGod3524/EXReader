#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Original clean digital print corpus; no claim to scanned-page performance."""
import hashlib,json,pathlib,sys
from PIL import Image,ImageDraw,ImageFont
root=pathlib.Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True)
fonts={"en":pathlib.Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
       "zh":pathlib.Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')}
texts={"en":["The reader keeps every page in order.","Clear words support careful reading.","A quiet library welcomes everyone.","We record results and check them again."],
"zh":["今天我们一起阅读这本新的图书", "清楚的文字帮助大家理解内容", "每一页都有值得学习的重要知识", "认真记录结果然后再次检查"],
"mixed":["阅读图书 Reading books", "清楚文字 Clear words", "学习知识 Study every day", "记录结果 Record results"]}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest={"schema":1,"kind":"original digitally rendered clean print; not scan", "dpi":300,"pages":[],
          "fonts":{k:{"path":str(p),"sha256":sha(p)} for k,p in fonts.items()}}
for lang in ("en","zh","mixed"):
 for n in range(10):
  image=Image.new('L',(1600,900),255);draw=ImageDraw.Draw(image)
  font=ImageFont.truetype(str(fonts['en' if lang=='en' else 'zh']),48)
  truth=[]
  for row,text in enumerate(texts[lang]):
   x,y=100,90+row*170
   draw.text((x,y),text,font=font,fill=0)
   for i,char in enumerate(text):
    if char.isspace():continue
    left=x+draw.textlength(text[:i],font=font)
    box=draw.textbbox((left,y),char,font=font)
    truth.append({"char":char,"box":list(box)})
  rotation=(n%4)*90
  if rotation:image=image.rotate(-rotation,expand=True)
  path=root/f'{lang}-{n:02}.pgm';image.save(path)
  manifest['pages'].append({"id":path.stem,"path":path.name,"sha256":sha(path),"bytes":path.stat().st_size,
     "language":lang,"rotation":rotation,"correction":(-rotation)%360,"original_size":[1600,900],
     "input_size":list(image.size),"lines":texts[lang],"characters":truth})
(root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
