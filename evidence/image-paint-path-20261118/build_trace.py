"""Reproduce the instrumented pre-WIP A and WIP B kernels (Windows QPC)."""
from pathlib import Path
import subprocess,shutil,time,json,hashlib
src=Path('src/affine_image.c');saved=src.read_bytes();meta={}
wrapper='static exr_status blend_inks_impl(exr_bitmap *target,const exr_vector_texture *source,const exr_bitmap *inks,const double m[6],double alpha,\n                                     const exr_bitmap *clip,exr_blend_mode mode,exr_composite_state *state,size_t *work,const exr_control *control,exr_error *e,int *path);\nexr_status exr_vector_texture_blend_inks(exr_bitmap *target,const exr_vector_texture *source,const exr_bitmap *inks,const double m[6],double alpha,\n                                     const exr_bitmap *clip,exr_blend_mode mode,exr_composite_state *state,size_t *work,const exr_control *control,exr_error *e) {\n  static int trace=-1; int path=0; double t0; exr_status status;\n  if(trace<0) trace=getenv("EXR_IMAGE_TRACE")!=NULL;\n  if(!trace) return blend_inks_impl(target,source,inks,m,alpha,clip,mode,state,work,control,e,&path);\n  t0=trace_ms(); status=blend_inks_impl(target,source,inks,m,alpha,clip,mode,state,work,control,e,&path);\n  fprintf(stderr,"IMGPATH path=%d ms=%.3f src=%ux%u dst=%ux%u m=%.1f,%.1f,%.1f,%.1f interp=%u mask=%d mm=%d matte=%d state=%d knock=%d shape=%d smask=%d depth=%u flags=%u clip=%d mode=%d inks=%d alpha=%.3f\\n",\n    path,trace_ms()-t0,source->bitmap.width,source->bitmap.height,target->width,target->height,m[0],m[1],m[2],m[3],source->interpolate,source->mask!=NULL,source->mask_mode,source->has_matte,\n    state!=NULL,state ? (int)state->knockout : 0,state ? state->shape!=NULL : 0,state ? state->soft_mask!=NULL : 0,state ? (unsigned)state->depth : 0,state ? state->alpha_flags : 0,clip!=NULL,(int)mode,inks!=NULL,alpha);\n  return status;\n}\nstatic exr_status blend_inks_impl(exr_bitmap *target,const exr_vector_texture *source,const exr_bitmap *inks,const double m[6],double alpha,\n                                     const exr_bitmap *clip,exr_blend_mode mode,exr_composite_state *state,size_t *work,const exr_control *control,exr_error *e,int *path) {\n'
clock='#include <stdio.h>\n#include <windows.h>\n/* Diagnostic: EXR_IMAGE_TRACE=1 prints one IMGPATH line per image paint. */\nstatic double trace_ms(void) { LARGE_INTEGER t,f; QueryPerformanceCounter(&t);QueryPerformanceFrequency(&f); return (double)t.QuadPart*1000/(double)f.QuadPart; }\n'
try:
 for tag in ['A','B']:
  s=subprocess.check_output(['git','show',('809b3743d' if tag=='A' else '4a025e0c0')+':src/affine_image.c']).decode()
  s=s.replace('#ifdef EXR_PROFILE_IMAGE',clock+'#ifdef EXR_PROFILE_IMAGE',1)
  a=s.index('exr_status exr_vector_texture_blend_inks(');b=s.index('  size_t local_work=0,i;',a)
  s=s[:a]+wrapper+s[b:]
  s=s.replace('if(nearest_axis(target,source,','*path=1; if(nearest_axis(target,source,',1)
  s=s.replace('    if(source->interpolate && !source->mask','    *path=2;\n    if(source->interpolate && !source->mask',1)
  if tag=='B':s=s.replace('    if(source->interpolate && source->mask','    *path=4;\n    if(source->interpolate && source->mask',1)
  s=s.replace('exr_status status=solid_mask_blend','*path=3; exr_status status=solid_mask_blend',1)
  s=s.replace('  size_t local_work=0,i;','  *path=9;\n  size_t local_work=0,i;',1)
  s=s.replace('#ifdef EXR_PROFILE_IMAGE\n  memset', '*path=9;\n#ifdef EXR_PROFILE_IMAGE\n  memset',1)
  src.write_text(s)
  dll=Path('build/perf/libexreader.dll');dll.unlink(missing_ok=True);t=time.time()
  subprocess.run(['cmake','--build','build/perf','--target','exreader','-j','4'],check=True)
  assert dll.stat().st_mtime>=t-2
  dest=Path('out/continue/trace-'+tag);dest.mkdir(parents=True,exist_ok=True);shutil.copy2(dll,dest/dll.name)
  meta[tag]={'dll_sha256':hashlib.sha256(dll.read_bytes()).hexdigest()}
finally:src.write_bytes(saved)
Path('evidence/image-paint-path-20261118/trace-builds.json').write_text(json.dumps(meta,indent=2))
