"""Time source copies of vector/canvas in a separate DLL using Ninja's link inputs."""
import json
import re
import shlex
import subprocess
from pathlib import Path

root = next(path for path in Path(__file__).resolve().parents
            if (path / 'src/vector.c').is_file() and (path / 'CMakeLists.txt').is_file())
build = root / 'build/perf'
out = root / 'build/pdf-fast-rect-profile'
out.mkdir(exist_ok=True)
source = (root / 'src/vector.c').read_text()
source = source.replace('static exr_status fill_blend(', 'static exr_status profiled_fill_blend(', 1)
wrapper = r'''
#include <windows.h>
#include <stdio.h>
static struct { size_t calls; double ms; } rect_profile[5];
static double rect_frequency;
static double rect_now(void) {
  LARGE_INTEGER tick; QueryPerformanceCounter(&tick); return tick.QuadPart*1000.0/rect_frequency;
}
static void rect_dump(void) {
  const char *names[]={"rect_gray","rect_rgba_plain","rect_rgba_state","general_gray","general_rgba"};
  size_t i;
  for(i=0;i<5;i++) fprintf(stderr,"VECTOR_PROFILE %s calls=%zu ms=%.6f\n",names[i],rect_profile[i].calls,rect_profile[i].ms);
}
static exr_status fill_blend(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,
                            exr_vector_rule rule,uint32_t color,const double *cmyk,double cmyk_alpha,
                            const exr_bitmap *clip,exr_blend_mode mode,exr_composite_state *state,
                            size_t *work,const exr_control *control,exr_error *error) {
  double before,elapsed; size_t category,i; int rectangle=0; exr_status result;
  if(!rect_frequency) {
    LARGE_INTEGER frequency; QueryPerformanceFrequency(&frequency); rect_frequency=(double)frequency.QuadPart;
    atexit(rect_dump);
  }
  before=rect_now();
  result=profiled_fill_blend(bitmap,edges,count,rule,color,cmyk,cmyk_alpha,clip,mode,state,work,control,error);
  elapsed=rect_now()-before;
  if(count==4 && edges) {
    double left=DBL_MAX,right=-DBL_MAX,top=DBL_MAX,bottom=-DBL_MAX;
    for(i=0;i<4;i++) {
      left=fmin(left,fmin(edges[i].x0,edges[i].x1)); right=fmax(right,fmax(edges[i].x0,edges[i].x1));
      top=fmin(top,fmin(edges[i].y0,edges[i].y1)); bottom=fmax(bottom,fmax(edges[i].y0,edges[i].y1));
    }
    rectangle=axis_rectangle(edges,left,top,right,bottom);
    if(rectangle && rect_profile[0].calls+rect_profile[1].calls+rect_profile[2].calls<7)
      fprintf(stderr,"RECT_DETAIL channels=%u bounds=%.9f,%.9f,%.9f,%.9f color=%08x clip=%d state=%d cmyk=%d mode=%d ms=%.6f\n",
        bitmap->channels,left,top,right,bottom,color,clip!=NULL,state!=NULL,cmyk!=NULL,(int)mode,elapsed);
  }
  category=rectangle ? (bitmap->channels==1 ? 0 : state ? 2 : 1) : bitmap->channels==1 ? 3 : 4;
  rect_profile[category].calls++;rect_profile[category].ms+=elapsed;
  return result;
}
'''
source = source.replace('\nexr_status exr_vector_fill_blend(', '\n' + wrapper + '\nexr_status exr_vector_fill_blend(', 1)
profile_source = out / 'vector-profile.c'
profile_source.write_text(source)
rows = json.loads(subprocess.check_output(['ninja', '-C', str(build), '-t', 'compdb', '-x'], text=True))
compile_row = next(row for row in rows if row['output'] == 'CMakeFiles/exr_graphics_objects.dir/src/vector.c.obj')
argv = [part.strip('"') for part in shlex.split(compile_row['command'], posix=False)]
argv[-1] = str(profile_source)
argv[argv.index('-o') + 1] = str(out / 'vector-profile.obj')
argv.insert(1, '-I' + str(root / 'src'))
subprocess.run(argv, cwd=build, check=True)
canvas = (root / 'src/canvas.c').read_text()
names = ['exr_canvas_create', 'exr_canvas_clip', 'exr_canvas_path',
         'exr_canvas_begin_group', 'exr_canvas_end_layer']
prelude = r'''
#include <windows.h>
#include <stdio.h>
static struct { size_t calls; double ms; } canvas_profile[5];
static double canvas_frequency;
static void canvas_dump(void) {
  const char *names[]={"create","clip","path","begin_group","end_layer"}; size_t i;
  for(i=0;i<5;i++) fprintf(stderr,"CANVAS_PROFILE %s calls=%zu ms=%.6f\n",names[i],canvas_profile[i].calls,canvas_profile[i].ms);
}
static double canvas_now(void) {
  LARGE_INTEGER tick;
  if(!canvas_frequency) {
    LARGE_INTEGER frequency; QueryPerformanceFrequency(&frequency); canvas_frequency=(double)frequency.QuadPart;
    atexit(canvas_dump);
  }
  QueryPerformanceCounter(&tick); return tick.QuadPart*1000.0/canvas_frequency;
}
'''
wrappers = []
for index, name in enumerate(names):
    match = re.search(r'exr_status\s+' + name + r'\s*\((.*?)\)\s*\{', canvas, re.S)
    params = match.group(1)
    arguments = [re.search(r'(\w+)\s*$', re.sub(r'\[[^\]]*\]', '', param)).group(1)
                 for param in params.split(',')]
    canvas = canvas[:match.start()] + match.group(0).replace(name, 'profile_' + name, 1) + canvas[match.end():]
    wrappers.append(f'''exr_status {name}({params}) {{
  double before=canvas_now(); exr_status result=profile_{name}({','.join(arguments)});
  canvas_profile[{index}].calls++;canvas_profile[{index}].ms+=canvas_now()-before;return result;
}}''')
canvas_source = out / 'canvas-profile.c'
canvas_source.write_text(canvas.split('\n', 1)[0] + '\n' + '#include "canvas_internal.h"\n' + prelude + canvas + '\n' + '\n'.join(wrappers))
compile_row = next(row for row in rows if row['output'] == 'CMakeFiles/exr_graphics_objects.dir/src/canvas.c.obj')
argv = [part.strip('"') for part in shlex.split(compile_row['command'], posix=False)]
argv[-1] = str(canvas_source)
argv[argv.index('-o') + 1] = str(out / 'canvas-profile.obj')
argv.insert(1, '-I' + str(root / 'src'))
subprocess.run(argv, cwd=build, check=True)
line = next(row['command'] for row in rows if row['output'] == 'libexreader.dll')
inner = line.split(' && ', 1)[1].rsplit(' && ', 1)[0]
argv = [part.strip('"') for part in shlex.split(inner, posix=False)]
argv[argv.index('-o') + 1] = str(out / 'libexreader.dll')
argv = [str(out / 'vector-profile.obj') if part == 'CMakeFiles/exr_graphics_objects.dir/src/vector.c.obj' else part for part in argv]
argv = [str(out / 'canvas-profile.obj') if part == 'CMakeFiles/exr_graphics_objects.dir/src/canvas.c.obj' else part for part in argv]
argv = [('-Wl,--out-implib,' + str(out / 'libexreader.dll.a')) if part.startswith('-Wl,--out-implib,') else part for part in argv]
subprocess.run(argv, cwd=build, check=True)
print(out / 'libexreader.dll')
