"""Relink diagnostic-only objects from the Release MinGW baseline; production is untouched."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = '653e44bde'
BUILD = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
header = '''
#include <windows.h>
extern int skip, tile;
extern double counters[16];
static inline double stamp(void) {
  LARGE_INTEGER ticks, hz;
  QueryPerformanceCounter(&ticks);
  QueryPerformanceFrequency(&hz);
  return 1000.0 * ticks.QuadPart / hz.QuadPart;
}
'''
edits = {
    'pdf_content': [('return r->callbacks.image ? r->callbacks.image(r->context,r->file,id,', '''
      size_t len;
      const unsigned char *key=exr_pdf_bytes(arena,values[0],&len);
      tile=key && len==7 && !memcmp(key,"ImTile",6);
      if(skip==1 || ((skip==4 || skip==5) && tile)) return EXR_OK;
      return r->callbacks.image ? r->callbacks.image(r->context,r->file,id,''')],
    'pdf_paint': [('if(paint->smask==EXR_PDF_NONE)', 'if(skip==2 || skip==5 || paint->smask==EXR_PDF_NONE)'),
                  ('if(!r->sink.base.image && !native)', 'if(skip==1 || (!r->sink.base.image && !native))')],
    'pdf_image': [('mask=get(&r,image,"SMask");','mask=(skip==2 || skip==5) ? EXR_PDF_NONE : get(&r,image,"SMask");'),
                  ('status=decode_image(file,image,','counters[8+tile]++; status=decode_image(file,image,')],
    'canvas': [('exr_vector_polyline flat={0}; exr_clip_mask *mask=NULL;', '''
      if(skip==3) return EXR_OK;
      double clip_start=stamp();
      exr_vector_polyline flat={0}; exr_clip_mask *mask=NULL;'''),
               ('unref(c,c->clip); c->clip=NULL; exr_vector_polyline_free(&flat);','counters[2]+=stamp()-clip_start; unref(c,c->clip); c->clip=NULL; exr_vector_polyline_free(&flat);'),
               ('unref(c,mask); exr_vector_polyline_free(&flat);','counters[2]+=stamp()-clip_start; counters[3]++; unref(c,mask); exr_vector_polyline_free(&flat);'),
               ('status=exr_vector_texture_blend(&c->bitmap,image,use,','''
      double start=stamp();
      status=exr_vector_texture_blend(&c->bitmap,image,use,'''),
               ('NULL,c->blend,masked_state(c),&c->work,&c->control,e);','''NULL,c->blend,masked_state(c),&c->work,&c->control,e);
      counters[tile]+=stamp()-start;
      counters[4+tile]++;
      counters[6]+=image->interpolate && use[1]==0 && use[2]==0 && !masked_state(c);
      counters[7]+=image->mask && image->mask->interpolate;
      counters[10]+=c->clip!=NULL;''')],
}
rules = (BUILD/'build.ninja').read_text()
link = re.search(r'^build libexreader.dll .*?Release ([^|\n]+).*?^  LINK_LIBRARIES = ([^\n]+)',rules,re.M|re.S)
objects = link[1].split()
for name, changes in edits.items():
    src = subprocess.check_output(['git','show',f'{BASE}:src/{name}.c'],cwd=ROOT).decode('utf8')
    for old,new in changes:
        assert src.count(old)==1,(name,old,src.count(old))
        src=src.replace(old,new)
    if name=='canvas':
        src += '''
int skip, tile;
double counters[16];
__declspec(dllexport) void probe_begin(int mode) { skip=mode; tile=0; memset(counters,0,sizeof(counters)); }
__declspec(dllexport) void probe_end(double *out) { memcpy(out,counters,sizeof(counters)); }
'''
    path=OUT/(name+'.c')
    path.write_text(header+src)
    original=next(o for o in objects if o.endswith('/'+name+'.c.obj'))
    cmd=subprocess.check_output(['ninja','-t','commands','-s',original],cwd=BUILD,text=True).strip()
    args=[v.replace(chr(92)+chr(34),chr(34)) for v in cmd.split(' -MD ')[0].split()]
    obj=OUT/(name+'.obj')
    subprocess.run([*args,'-I'+str(ROOT/'src'),'-c',str(path),'-o',str(obj)],cwd=BUILD,check=True)
    objects[objects.index(original)]='"'+obj.as_posix()+'"'
rsp=OUT/'probe.rsp'
rsp.write_text(' '.join(objects)+' '+link[2])
dll=OUT/'probe.dll'
subprocess.run([args[0],'-shared','-static','-static-libgcc','exreader.def','-o',str(dll),'@'+str(rsp)],cwd=BUILD,check=True)
print(dll)

