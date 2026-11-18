"""Build image-call timers against base and candidate, then restore/relink production.
Run only while no benchmark is active. Both builds use the same compiler/options.
"""
from pathlib import Path
import json,re,subprocess
ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'src/affine_image.c'
HERE=Path(__file__).resolve().parent
TIMER='''
#include <windows.h>
#include <stdio.h>
static unsigned probe_stable,probe_crossing;
static double probe_ms(void) { LARGE_INTEGER t,f;QueryPerformanceCounter(&t);QueryPerformanceFrequency(&f);return t.QuadPart*1000.0/f.QuadPart; }
'''
WRAPPER='''
exr_status exr_vector_texture_blend_inks(exr_bitmap *target,const exr_vector_texture *source,const exr_bitmap *inks,const double m[6],double alpha,
 const exr_bitmap *clip,exr_blend_mode mode,exr_composite_state *state,size_t *work,const exr_control *control,exr_error *e) {
 probe_stable=probe_crossing=0;double t=probe_ms();
 exr_status status=probe_texture(target,source,inks,m,alpha,clip,mode,state,work,control,e);
 if(getenv("EXR_IMAGE_TRACE")) fprintf(stderr,"IMAGE %u %u %u %u %u %u %u %u %u %u %.9g %.9g %.9g %.9g %.9g %.9g %.6f %u %u\\n",source->bitmap.width,source->bitmap.height,source->interpolate,!!source->mask,source->mask && source->mask->interpolate,source->has_matte,mode,!!state,state && !!state->pixels,state && !!state->soft_mask,m[0],m[1],m[2],m[3],m[4],m[5],probe_ms()-t,probe_stable,probe_crossing);
 return status;
}
'''
def build():
    p=subprocess.run(['cmake','--build','build/perf','--parallel','6'],cwd=ROOT,text=True,capture_output=True)
    assert p.returncode==0,p.stdout+p.stderr
    return p.stdout+p.stderr

def main():
    final=SRC.read_bytes();logs={}
    try:
        for tag in 'AB':
            s=subprocess.check_output(['git','show','6e11e8c95:src/affine_image.c'],cwd=ROOT).decode() if tag=='A' else final.decode()
            s=s.replace('#include <fenv.h>','#include <fenv.h>\n'+TIMER)
            s=s.replace('exr_status exr_vector_texture_blend_inks(', 'static exr_status probe_texture(')
            s=s.replace('    if(stable) for(unsigned sy=0;sy<2;sy++) for(unsigned k=0;k<2;k++)', '    if(stable) probe_stable++;else probe_crossing++;\n    if(stable) for(unsigned sy=0;sy<2;sy++) for(unsigned k=0;k<2;k++)')
            SRC.write_text(s+WRAPPER,newline='\n');logs[tag]=build()
            d=ROOT/'out'/('shading-image-'+tag);d.mkdir(exist_ok=True)
            (d/'libexreader.dll').write_bytes((ROOT/'build/perf/libexreader.dll').read_bytes())
    finally:
        SRC.write_bytes(final)
        dll=ROOT/'build/perf/libexreader.dll';dll.unlink(missing_ok=True)
        logs['production']=build()
        d=ROOT/'out/shading-final';d.mkdir(exist_ok=True)
        (d/'libexreader.dll').write_bytes(dll.read_bytes())
        (HERE/'build-logs.json').write_text(json.dumps(logs,indent=2)+'\n')
    print('Restored and forcibly relinked production DLL.')
if __name__=='__main__':main()
