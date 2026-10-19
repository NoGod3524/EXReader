#!/usr/bin/env python3
"""Original RGB blend PDFs; raw MuPDF/PDFium and explicit ISO page-group references."""
# SPDX-License-Identifier: MIT
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'tests/fixtures/pdf-blend'
MODES='Normal Multiply Screen Overlay Darken Lighten ColorDodge ColorBurn HardLight SoftLight Difference Exclusion Hue Saturation Color Luminosity'.split()
CASES=[((51,102,153),255,(204,77,26),255),((128,32,220),255,(40,220,150),128),
 ((255,255,255),255,(255,0,0),64),((0,0,0),255,(255,255,255),255),
 ((255,255,255),255,(0,0,0),255),((17,255,127),128,(240,31,0),192),
 ((255,0,128),0,(80,127,250),128),((255,0,255),128,(0,0,0),0),
 ((128,128,128),255,(210,20,160),255),((128,128,128),64,(200,200,200),192),
 ((255,0,0),192,(0,255,0),64),((0,0,255),128,(0,255,255),128),((0,0,0),0,(0,0,0),0)]
def number(n):return f'{n/255:.9f}'
def color(rgb,stroke=False):return ' '.join(map(number,rgb))+(' RG' if stroke else ' rg')
def stream(data,extra=b''):
 if isinstance(data,str):data=data.encode()
 return b'<< /Length '+str(len(data)).encode()+b' '+extra+b' >>\nstream\n'+data+b'\nendstream'
class PDF:
 def __init__(self,w,h):
  self.w=w;self.h=h;self.objects=[b'',b'',b'',b''];self.gs={};self.xo={};self.fonts={};self.annotations=[]
 def add(self,value):self.objects.append(value);return len(self.objects)
 def state(self,name,mode,alpha=255):
  mode=('/'+mode) if isinstance(mode,str) and not mode.startswith(('[','null')) else mode
  self.gs[name]=self.add(f'<< /BM {mode} /ca {number(alpha)} /CA {number(alpha)} >>'.encode())
 def resources(self):
  def refs(items):return ' '.join(f'/{k} {v} 0 R' for k,v in items.items())
  return f'<< /ExtGState << {refs(self.gs)} >> /XObject << {refs(self.xo)} >> /Font << {refs(self.fonts)} >> >>'
 def finish(self,name,content):
  self.objects[0]=b'<< /Type /Catalog /Pages 2 0 R >>';self.objects[1]=b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>'
  annots=(' /Annots ['+' '.join(f'{a} 0 R' for a in self.annotations)+']') if self.annotations else ''
  self.objects[2]=f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.w} {self.h}] /Contents 4 0 R /Group << /S /Transparency /CS /DeviceRGB /I true >> /Resources {self.resources()}{annots} >>'.encode();self.objects[3]=stream(content)
  data=bytearray(b'%PDF-1.7\n%\x80\x81\x82\x83\n');offsets=[0]
  for i,obj in enumerate(self.objects,1):offsets.append(len(data));data+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
  xref=len(data);data+=f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
  for off in offsets[1:]:data+=f'{off:010d} 00000 n \n'.encode()
  data+=f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
  (ROOT/(name+'.pdf')).write_bytes(data)
def make_flat():
 p=PDF(256,len(CASES)*16);ops=[]
 for row,(bg,ba,fg,fa) in enumerate(CASES):
  p.state(f'B{row}','Normal',ba)
  for col,mode in enumerate(MODES):
   key=f'F{row}_{col}';p.state(key,mode,fa);x=col*16;y=row*16
   ops.append(f'q /B{row} gs {color(bg)} {x} {y} 16 16 re f /{key} gs {color(fg)} {x} {y} 16 16 re f Q')
 p.finish('flat','\n'.join(ops));return p

def make_primitives():
 p=PDF(256,144);p.state('N','Normal');p.state('B','Normal',192)
 fg=(204,77,26);bg=(51,102,153)
 image=p.add(stream(bytes(fg),b'/Type /XObject /Subtype /Image /Width 1 /Height 1 /BitsPerComponent 8 /ColorSpace /DeviceRGB'));p.xo['Im']=image
 p.xo['Fm']=p.add(stream('0 0 12 12 re f',b'/Type /XObject /Subtype /Form /BBox [0 0 12 12] /Resources << >>'))
 font_data=(ROOT.parent/'shaping/shaping.ttf').read_bytes();font_file=p.add(stream(font_data,b'/Length1 '+str(len(font_data)).encode()))
 desc=p.add(f'<< /Type /FontDescriptor /FontName /EXRShapingOracle /Flags 32 /FontBBox [0 -200 1000 800] /ItalicAngle 0 /Ascent 800 /Descent -200 /CapHeight 800 /StemV 80 /FontFile2 {font_file} 0 R >>'.encode())
 p.fonts['F']=p.add(f'<< /Type /Font /Subtype /TrueType /BaseFont /EXRShapingOracle /Encoding /WinAnsiEncoding /FirstChar 65 /LastChar 65 /Widths [600] /FontDescriptor {desc} 0 R >>'.encode())
 ops=[]
 for col,mode in enumerate(MODES):
  p.state(f'G{col}',mode,192)
  for row in range(6):
   x=col*16;y=row*24;ops.append(f'q /B gs {color(bg)} {x} {y} 16 24 re f /G{col} gs {color(fg)} {color(fg,True)}')
   if row==0:ops.append(f'{x+2} {y+2} 12 12 re f')
   elif row==1:ops.append(f'8 w {x+2} {y+8} m {x+14} {y+8} l S')
   elif row==2:ops.append(f'q 12 0 0 12 {x+2} {y+2} cm /Im Do Q')
   elif row==3:ops.append(f'q 1 0 0 1 {x+2} {y+2} cm /Fm Do Q')
   elif row==4:ops.append(f'BT /F 20 Tf 1 0 0 1 {x+2} {y+4} Tm (A) Tj ET')
   else:
    appearance=p.add(stream(f'/G{col} gs {color(fg)} 0 0 12 12 re f',f'/Type /XObject /Subtype /Form /BBox [0 0 12 12] /Resources {p.resources()}'.encode()))
    p.annotations.append(p.add(f'<< /Type /Annot /Subtype /Square /Rect [{x+2} {y+2} {x+14} {y+14}] /AP << /N {appearance} 0 R >> >>'.encode()))
   ops.append('Q')
 p.finish('primitives','\n'.join(ops));return p

def make_state():
 p=PDF(96,16);p.state('N','Normal');p.state('M','Multiply');p.state('A','[/Missing /Multiply /Screen]');p.state('U','[/Missing /Other]');p.state('C','Compatible');p.state('X','Unregistered');p.state('Z','null')
 ops=[]
 for col,command in enumerate(('/A gs','/U gs','/C gs','/X gs','/M gs q /N gs Q /Z gs','q /M gs Q')):
  x=16*col;ops.append(f'q /N gs {color((51,102,153))} {x} 0 16 16 re f {command} {color((204,77,26))} {x} 0 16 16 re f Q')
 p.finish('state','\n'.join(ops));return p

def make_groups():
 p=PDF(256,64);p.state('B','Normal',192)
 group=b'/Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << /S /Transparency /CS /DeviceRGB /I true >>'
 # Child state is independent of the caller's opacity and blend; overlapping
 # children must be combined before the caller's opacity is applied once.
 p.state('Child','Multiply',128)
 p.xo['Plain']=p.add(stream('1 0 0 rg 0 0 12 16 re f 0 0 1 rg 4 0 12 16 re f',group+b' /Resources << >>'))
 p.xo['Mixed']=p.add(stream('1 0 0 rg 0 0 16 16 re f /Child gs 0 1 0 rg 0 0 16 16 re f',group+f' /Resources {p.resources()}'.encode()))
 p.state('Nested','Screen',192)
 p.xo['Nested']=p.add(stream('/Nested gs /Plain Do',group+f' /Resources {p.resources()}'.encode()))
 p.xo['Clipped']=p.add(stream('0 1 1 rg -8 -8 32 32 re f',group.replace(b'[0 0 16 16]',b'[2 2 14 14]')+b' /Resources << >>'))
 ops=[]
 for col,mode in enumerate(MODES):
  p.state(f'G{col}',mode,128)
  for row,form in enumerate(('Plain','Mixed','Nested','Clipped')):
   x=col*16;y=row*16
   ops.append(f'q /B gs {color((51,102,153))} {x} {y} 16 16 re f /G{col} gs 1 0 0 1 {x} {y} cm /{form} Do Q')
 p.finish('groups','\n'.join(ops));return p

def make_compound():
 p=PDF(256,48);p.state('B','Normal',192);ops=[]
 for col,mode in enumerate(MODES):
  for row,(fa,sa) in enumerate(((128,128),(128,0),(64,192))):
   key=f'G{row}_{col}'
   p.gs[key]=p.add(f'<< /BM /{mode} /ca {number(fa)} /CA {number(sa)} >>'.encode())
   x=col*16;y=row*16
   ops.append(f'q /B gs {color((51,102,153))} {x} {y} 16 16 re f /{key} gs 1 0 0 rg 0 1 0 RG 4 w {x+2} {y+2} 12 12 re B Q')
 p.finish('compound','\n'.join(ops));return p

def make_ap_groups(isolated=True):
 p=PDF(256,16);p.state('B','Normal',192);ops=[]
 for col,mode in enumerate(MODES):
  p.state(f'G{col}',mode,128);x=col*16
  ops.append(f'q /B gs {color((51,102,153))} {x} 0 16 16 re f Q')
  group=' /I true /CS /DeviceRGB' if isolated else ' /I false'
  prefix='' if isolated else '/B gs '
  ap=p.add(stream(prefix+f'1 0 0 rg 0 0 16 16 re f /G{col} gs 0 1 0 rg 0 0 16 16 re f',f'/Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << /S /Transparency{group} >> /Resources {p.resources()}'.encode()))
  p.annotations.append(p.add(f'<< /Type /Annot /Subtype /Square /Rect [{x} 0 {x+16} 16] /AP << /N {ap} 0 R >> >>'.encode()))
 p.finish('ap-groups' if isolated else 'ap-nonisolated','\n'.join(ops));return p

def make_nonisolated():
 p=PDF(256,160);p.state('C','Multiply',128);p.state('Low','ColorDodge',1)
 p.gs['D']=p.add(b'<< /BM /HardLight /ca 0.752941176 /CA 0.250980392 >>')
 sm=p.add(stream(bytes((128,)),b'/Type /XObject /Subtype /Image /Width 1 /Height 1 /BitsPerComponent 8 /ColorSpace /DeviceGray'))
 p.xo['Im']=p.add(stream(bytes((204,77,26)),f'/Type /XObject /Subtype /Image /Width 1 /Height 1 /BitsPerComponent 8 /ColorSpace /DeviceRGB /SMask {sm} 0 R'.encode()))
 font_data=(ROOT.parent/'shaping/shaping.ttf').read_bytes();font_file=p.add(stream(font_data,b'/Length1 '+str(len(font_data)).encode()))
 desc=p.add(f'<< /Type /FontDescriptor /FontName /EXRShapingOracle /Flags 32 /FontBBox [0 -200 1000 800] /ItalicAngle 0 /Ascent 800 /Descent -200 /CapHeight 800 /StemV 80 /FontFile2 {font_file} 0 R >>'.encode())
 p.fonts['F']=p.add(f'<< /Type /Font /Subtype /TrueType /BaseFont /EXRShapingOracle /Encoding /WinAnsiEncoding /FirstChar 65 /LastChar 65 /Widths [600] /FontDescriptor {desc} 0 R >>'.encode())
 def form(content,isolated=False,box='0 0 16 16'):
  return p.add(stream(content,f'/Type /XObject /Subtype /Form /BBox [{box}] /Group << /S /Transparency /I {str(isolated).lower()} >> /Resources {p.resources()}'.encode()))
 p.xo['Iso']=form('/C gs 1 0 0 rg 0 0 16 16 re f 0 1 0 rg 0 0 16 16 re f',True)
 p.xo['Nested']=form('/C gs 0 0 1 rg 0 0 16 16 re f 1 0 0 rg 0 0 16 16 re f')
 bodies=['/C gs 1 0.2 0.5 rg 0 0 16 16 re f',
  '/C gs 0 1 0 RG 4 w 2 2 12 12 re S',
  '/C gs 16 0 0 16 0 0 cm /Im Do',
  '/C gs 1 0.2 0.5 rg BT /F 20 Tf 1 0 0 1 2 4 Tm (A) Tj ET',
  '/D gs 1 0 0 rg 0 1 0 RG 4 w 2 2 12 12 re B',
  '/C gs /Iso Do','/C gs /Nested Do',
  '/Low gs 0.99 1 0 rg 0 0 16 16 re f','',
  '/C gs 1 1 0 rg -8 -8 32 32 re f']
 for row,body in enumerate(bodies):p.xo[f'NI{row}']=form(body,box='2.25 2.25 13.75 13.75' if row==9 else '0 0 16 16')
 ops=[]
 for row,ba in enumerate((255,128,192,0,64,192,255,1,128,255)):
  p.state(f'B{row}','Normal',ba)
  for col,mode in enumerate(MODES):
   p.state(f'G{col}',mode,128);x=col*16;y=row*16
   ops.append(f'q /B{row} gs {color((51,102,153))} {x} {y} 16 16 re f /G{col} gs 1 0 0 1 {x} {y} cm /NI{row} Do Q')
 p.finish('nonisolated','\n'.join(ops));return p

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--oracle-module-dir',type=Path);args=parser.parse_args()
 if args.oracle_module_dir:sys.path.insert(0,str(args.oracle_module_dir))
 import pymupdf, pypdfium2
 ROOT.mkdir(parents=True,exist_ok=True);pages={'flat':make_flat(),'primitives':make_primitives(),'state':make_state(),'groups':make_groups(),'compound':make_compound(),'ap-groups':make_ap_groups(),'nonisolated':make_nonisolated(),'ap-nonisolated':make_ap_groups(False)}
 for name,page in pages.items():
  mask=bytearray([1])*(page.w*page.h)
  if name=='primitives':
   mask=bytearray(page.w*page.h)
   for row in range(6):
    for col in range(16):
     for y in range(row*24+6,row*24+10):
      for x in range(col*16+6,col*16+10):mask[(page.h-1-y)*page.w+x]=1
  if name=='groups':
   mask=bytearray(page.w*page.h)
   for row in range(4):
    for col in range(16):
     for y in range(row*16+4,row*16+12):
      for x in range(col*16+4,col*16+12):mask[(page.h-1-y)*page.w+x]=1
  if name=='nonisolated':
   mask=bytearray(page.w*page.h)
   for row in range(10):
    for col in range(16):
     for y in range(row*16+6,row*16+10):
      for x in range(col*16+(2 if row in (1,4) else 6),col*16+(4 if row in (1,4) else 10)):mask[(page.h-1-y)*page.w+x]=1
  (ROOT/(name+'.mask')).write_bytes(mask)
  with pymupdf.open(ROOT/(name+'.pdf')) as document:
   for alpha in (False,True):
    pix=document[0].get_pixmap(colorspace=pymupdf.csRGB,alpha=alpha);data=pix.samples
    if not alpha:data=b''.join(data[i:i+3]+b'\xff' for i in range(0,len(data),3))
    assert len(data)==page.w*page.h*4
    (ROOT/(name+('-mupdf-alpha' if alpha else '-mupdf-white')+'.rgba')).write_bytes(data)
  with pypdfium2.PdfDocument(ROOT/(name+'.pdf')) as document:
   rendered={}
   for alpha in (False,True):
    bitmap=document[0].render(fill_color=(0,0,0,0) if alpha else (255,255,255,255))
    data=bytearray(bitmap.to_pil().convert('RGBA').tobytes());bitmap.close()
    if alpha:
     for i in range(0,len(data),4):
      for k in range(3):data[i+k]=(data[i+k]*data[i+3]+127)//255
    rendered[alpha]=data
    (ROOT/(name+('-pdfium-alpha' if alpha else '-pdfium-white')+'.rgba')).write_bytes(data)
   # ISO 32000-1 11.4.7: isolate page content, then composite normally onto medium.
   # PDFium's transparent render supplies the blend math; its white render does
   # not isolate content. Annotation APs are painted after the page group.
   alpha_data=bytearray(rendered[True]);white_data=bytearray(alpha_data)
   for i in range(0,len(white_data),4):
    for k in range(3):white_data[i+k]=min(255,white_data[i+k]+255-white_data[i+3])
    white_data[i+3]=255
   if name=='primitives':white_data[:24*page.w*4]=rendered[False][:24*page.w*4]
   if name=='ap-groups':white_data=rendered[False]
   if name=='nonisolated':
    alpha_data=bytearray((ROOT/(name+'-mupdf-alpha.rgba')).read_bytes())
    white_data=bytearray((ROOT/(name+'-mupdf-white.rgba')).read_bytes())
    from pdf_group_reference import probe
    audit=[]
    raw_oracles={oracle:(ROOT/(name+'-'+oracle+'-alpha.rgba')).read_bytes() for oracle in ('mupdf','pdfium')}
    for row in range(10):
     for col,mode in enumerate(MODES):
      expected_alpha,expected_white=probe(row,mode)
      deltas={oracle:0 for oracle in ('mupdf','pdfium')}
      for y in range(row*16+6,row*16+10):
       for x in range(col*16+(2 if row in (1,4) else 6),col*16+(4 if row in (1,4) else 10)):
        i=((page.h-1-y)*page.w+x)*4
        for oracle in deltas:
         raw=raw_oracles[oracle]
         deltas[oracle]=max(deltas[oracle],max(abs(a-b) for a,b in zip(expected_alpha,raw[i:i+4])))
        alpha_data[i:i+4]=expected_alpha;white_data[i:i+4]=expected_white
      # Opaque/separable samples independently agree with MuPDF; its partial
      # nonseparable behavior and PDFium's implicit isolation are retained raw.
      if row!=2 and (row in (0,6,9) or col<12):assert deltas['mupdf']<=3,(row,mode,deltas)
      audit.append({'row':row,'mode':mode,'premultiplied_expected':list(expected_alpha),'white_expected':list(expected_white),'raw_max_difference':deltas})
    (ROOT/'nonisolated-oracle.json').write_text(json.dumps({'reference':'Independent Decimal(40) ISO 32000-1 11.4.4 group arithmetic at full-coverage interior probes; MuPDF checked on opaque or separable samples except its masked image alpha result (204 instead of ISO/PDFium 200 in row 2). PDFium renders these non-isolated Forms as isolated; MuPDF partial-alpha nonseparable differences retained.', 'probes':audit},indent=2)+'\n',encoding='utf-8')
   if name=='ap-nonisolated':
    from pdf_group_reference import ap_probe
    for col,mode in enumerate(MODES):
     ea,ew=ap_probe(mode,False),ap_probe(mode,True)
     for y in range(16):
      for x in range(col*16,(col+1)*16):
       i=(y*page.w+x)*4;alpha_data[i:i+4]=ea;white_data[i:i+4]=ew
   if name=='state':
    # 11.6.3: first recognized BM array name. 7.3.9: null entry is absent.
    for y in range(page.h):
     for x in list(range(16))+list(range(64,80)):
      i=(y*page.w+x)*4;alpha_data[i:i+4]=white_data[i:i+4]=bytes((41,31,16,255))
   (ROOT/(name+'-alpha.rgba')).write_bytes(alpha_data)
   (ROOT/(name+'-white.rgba')).write_bytes(white_data)
 for i,mode in enumerate(('5','[/Normal 5]','[7 /Multiply]')):
  p=PDF(16,16);p.gs['Bad']=p.add(f'<< /BM {mode} >>'.encode());p.finish(f'bad-{i}','/Bad gs 1 0 0 rg 0 0 16 16 re f')
 for i,group in enumerate(('<< /S /Transparency /I false >>','<< /S /Transparency /I true /K true >>','<< /S /Transparency /I true /CS /DeviceCMYK >>','<< /S /Transparency /I 1 >>','<< /S /Missing /I true >>')):
  p=PDF(16,16);p.xo['Fm']=p.add(stream('0 0 16 16 re f',f'/Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group {group} /Resources << >>'.encode()));p.finish(f'group-bad-{i}','/Fm Do')
 p=PDF(16,16);p.xo['Fm']=p.add(stream('0 0 16 16 re f',b'/Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << /S /Transparency /I false /CS /DeviceRGB >> /Resources << >>'));p.finish('group-bad-5','/Fm Do')
 p=PDF(16,16);p.xo['Fm']=p.add(stream('q BT',b'/Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << /S /Transparency /I true >> /Resources << >>'));p.finish('group-malformed','/Fm Do')
 manifest={'pymupdf':pymupdf.VersionBind,'mupdf':pymupdf.VersionFitz,'pypdfium2':str(pypdfium2.PYPDFIUM_INFO),'pdfium':str(pypdfium2.PDFIUM_INFO),'scope':'Original RGB scenes. Raw MuPDF/PDFium renders retained separately. Expected samples use PDFium premultiplied alpha plus ISO 32000-1 11.4.7 page isolation; annotation white region uses PDFium white; BM array/null cells use 11.6.3 and 7.3.9 normative results. Non-isolated interior samples use independent Decimal(40) ISO group formulas, cross-checked against MuPDF on opaque/separable samples; PDFium implicitly isolates these Forms. MuPDF partial-alpha nonseparable blending differs; both engines misselect unknown-first BM array. Font is original MIT fixture.','modes':MODES,'color_cases':CASES,'sizes':{k:[v.w,v.h] for k,v in pages.items()},'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.iterdir()) if p.name!='manifest.json'}}
 (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8');print('Original blend fixtures and MuPDF/PDFium references generated',pymupdf.VersionFitz,pypdfium2.PDFIUM_INFO)
if __name__=='__main__':main()
