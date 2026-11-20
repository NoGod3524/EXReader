/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;static unsigned checks,maximum;static const char *directory;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_fixed_document *open_scene(const char *name) {
  char path[4096];exr_fixed_document *d=NULL;snprintf(path,sizeof(path),"%s/pdf-blend/%s",directory,name);
  OK(exr_fixed_open(path,NULL,&d,&error));return d;
}
static void scenes(void) {
  const char *kinds[]={"retain","null","clear","restore","ordinary","group","inner-alpha","nested"};
  const unsigned masks[]={64,128,192};unsigned i,j,w,k;char path[4096];unsigned char expected[27][8];FILE *f;
  snprintf(path,sizeof(path),"%s/pdf-blend/mask-scope-oracle.bin",directory);f=fopen(path,"rb");CHECK(f);
  CHECK(fread(expected,1,sizeof(expected),f)==sizeof(expected));CHECK(fgetc(f)==EOF);fclose(f);
  for(i=0;i<8;i++) for(j=0;j<3;j++) {
    exr_fixed_document *d;snprintf(path,sizeof(path),"mask-scope-%s-%u.pdf",kinds[i],masks[j]);d=open_scene(path);
    for(w=0;w<2;w++) {
      exr_bitmap b={0};exr_fixed_render_options options={0};const unsigned char *p;
      options.channels=4;options.background=w ? 0xffffffff : 0;
      OK(exr_fixed_render(d,0,1,&options,&b,&error));p=b.pixels+8*b.stride+8*4;
      for(k=0;k<4;k++) {
        unsigned got=w || k==3 ? p[k] : (p[k]*p[3]+127)/255;
        unsigned diff=(unsigned)abs((int)got-(int)expected[i*3+j][w*4+k]);
        if(diff>maximum) maximum=diff;
        if(diff>2) fprintf(stderr,"%s white %u channel %u got %u want %u\n",path,w,k,got,expected[i*3+j][w*4+k]);
        CHECK(diff<=2);
      }
      exr_bitmap_free(&b);
    }
    exr_fixed_free(d);
  }
  { const char *names[]={"mask-scope-shape-iso.pdf","mask-scope-shape-noniso.pdf","mask-scope-shape-nested.pdf"};
    for(i=0;i<3;i++) {
      exr_fixed_document *d=open_scene(names[i]);
      for(w=0;w<2;w++) {
        exr_bitmap b={0};exr_fixed_render_options options={0};const unsigned char *p;options.channels=4;options.background=w ? 0xffffffff : 0;
        OK(exr_fixed_render(d,0,1,&options,&b,&error));p=b.pixels+8*b.stride+8*4;
        for(k=0;k<4;k++) { unsigned got=w || k==3 ? p[k] : (p[k]*p[3]+127)/255;
          CHECK(abs((int)got-(int)expected[24+i][w*4+k])<=2); }
        exr_bitmap_free(&b);
      }
      exr_fixed_free(d);
    }
  }
  { const char *bad[]={"mask-scope-bad-mask.pdf","mask-scope-bad-content.pdf"};
    for(i=0;i<2;i++) { exr_fixed_document *d=open_scene(bad[i]);exr_bitmap b={0};
      CHECK(exr_fixed_render(d,0,1,NULL,&b,&error)==EXR_FORMAT);CHECK(!b.pixels);exr_fixed_free(d); }
  }
}
static void group_failure(void) {
  exr_fixed_document *d=open_scene("mask-scope-group-128.pdf");exr_canvas_config config={0};exr_canvas *c=NULL;
  exr_draw_sink_ex sink={0};exr_bitmap b={0};config.width=config.height=16;
  OK(exr_canvas_create(&config,&c,&error));OK(exr_canvas_set_layer_budget(c,1024,&error));
  sink.struct_size=sizeof(sink);OK(exr_canvas_get_sink_ex(c,&sink,&error));
  CHECK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error)==EXR_LIMIT);
  CHECK(exr_canvas_take(c,&b,&error)==EXR_LIMIT && !b.pixels);
  exr_canvas_free(c);exr_fixed_free(d);
}
typedef struct { unsigned begins,ends; } inspection;
static exr_status inspect_path(void *ctx,const exr_path_segment *p,size_t n,const double m[6],const exr_draw_style *style,exr_error *e) {
  (void)ctx;(void)p;(void)n;(void)m;(void)style;(void)e;return EXR_OK;
}
static exr_status inspect_begin(void *ctx,double opacity,exr_blend_mode mode,unsigned flags,exr_error *e) {
  inspection *s=ctx;(void)opacity;(void)mode;(void)flags;(void)e;s->begins++;return EXR_OK;
}
static exr_status inspect_end(void *ctx,unsigned commit,exr_error *e) {
  inspection *s=ctx;(void)commit;(void)e;s->ends++;return EXR_OK;
}
static exr_status inspect_mask(void *ctx,const unsigned char *mask,size_t w,size_t h,exr_error *e) {
  (void)ctx;(void)mask;(void)w;(void)h;(void)e;return EXR_OK;
}
static exr_status inspect_extent(void *ctx,unsigned *w,unsigned *h,exr_error *e) {
  (void)ctx;(void)e;*w=*h=2048;return EXR_OK;
}
static void aggregate_budget(void) {
  exr_fixed_document *d=open_scene("mask-scope-budget.pdf");inspection state={0};exr_draw_sink_ex sink={0};
  sink.struct_size=sizeof(sink);sink.base.path=inspect_path;sink.base.context=&state;
  sink.begin_group=inspect_begin;sink.end_layer=inspect_end;sink.soft_mask=inspect_mask;sink.extent=inspect_extent;
  CHECK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error)==EXR_LIMIT);
  CHECK(strstr(error.message,"active soft masks exceed 64 MiB"));CHECK(state.begins==state.ends && state.begins==17);
  exr_fixed_free(d);
}
static size_t build_mask_pdf(char *buf,size_t cap,const char *subtype,const char *bc,const char *tr,
                             const char *grp,const char *bbox,const char *mask_stream,
                             const char *mask_sh,const char *page_sh) {
  size_t off[9]={0},at=0,xref;unsigned i;
  const char *objs[8];char o4[512],o5[512],o6[512],o7[512],o8[512];
  snprintf(o4,sizeof(o4),"<< /Type /ExtGState /SMask << /Type /Mask /S /%s %s %s /G 5 0 R >> >>",subtype,bc,tr);
  snprintf(o5,sizeof(o5),"<< /Type /XObject /Subtype /Form /BBox [%s] /Group << /S /Transparency /CS /DeviceRGB %s >> "
           "/Resources << /Shading << /M 6 0 R >> >> /Length %zu >>\nstream\n%s\nendstream",
           bbox,grp,strlen(mask_stream),mask_stream);
  snprintf(o6,sizeof(o6),"%s",mask_sh);
  snprintf(o7,sizeof(o7),"%s",page_sh);
  const char *page_stream="q /GS1 gs 0.4 3.3 47.2 26.4 re W* n /P sh Q";
  snprintf(o8,sizeof(o8),"<< /Length %zu >>\nstream\n%s\nendstream",strlen(page_stream),page_stream);
  objs[0]="<< /Type /Catalog /Pages 2 0 R >>";
  objs[1]="<< /Type /Pages /Kids [3 0 R] /Count 1 >>";
  objs[2]="<< /Type /Page /Parent 2 0 R /MediaBox [0 0 48 32] /Resources << /ExtGState << /GS1 4 0 R >> /Shading << /P 7 0 R >> >> /Contents 8 0 R >>";
  objs[3]=o4;objs[4]=o5;objs[5]=o6;objs[6]=o7;objs[7]=o8;
  at+=(size_t)snprintf(buf+at,cap-at,"%%PDF-1.4\n");
  for(i=0;i<8;i++) { off[i+1]=at;at+=(size_t)snprintf(buf+at,cap-at,"%u 0 obj\n%s\nendobj\n",i+1,objs[i]); }
  xref=at;at+=(size_t)snprintf(buf+at,cap-at,"xref\n0 9\n0000000000 65535 f \n");
  for(i=1;i<=8;i++) at+=(size_t)snprintf(buf+at,cap-at,"%010zu 00000 n \n",off[i]);
  at+=(size_t)snprintf(buf+at,cap-at,"trailer\n<< /Size 9 /Root 1 0 R >>\nstartxref\n%zu\n%%%%EOF\n",xref);
  return at;
}
static void direct_axial_mask_parity(void) {
  static const struct {
    const char *subtype,*bc,*tr,*grp,*bbox,*stream,*mask_sh,*page_sh;
  } cases[]={
    {"Luminosity","/BC [0 0 0]","","","0.4 3.3 47.6 29.7",
     "q\n0.4 3.3 47.2 26.4 re\nW* n\n/M sh\nQ",
     "<< /ShadingType 2 /ColorSpace /DeviceRGB /Coords [10 35 10 3] /Extend [true true] /Function << /FunctionType 2 /Domain [0 1] /C0 [0 0 0] /C1 [1 1 1] /N 1 >> >>",
     "<< /ShadingType 2 /ColorSpace /DeviceRGB /Coords [10 35 10 3] /Extend [true true] /Function << /FunctionType 2 /Domain [0 1] /C0 [0.87451 0.85882 0.83529] /C1 [0.87451 0.85882 0.83529] /N 1 >> >>"},
    {"Luminosity","/BC [0.2 0.5 0.8]","/TR << /FunctionType 2 /Domain [0 1] /C0 [0.1] /C1 [0.9] /N 2 >>","/I true","0.4 3.3 47.6 29.7",
     "q\n0.4 3.3 47.2 26.4 re\nW* n\n/M sh\nQ",
     "<< /ShadingType 2 /ColorSpace /DeviceRGB /Coords [10 30 10 4] /Extend [false true] /Function << /FunctionType 2 /Domain [0 1] /C0 [0.1 0.3 0.6] /C1 [0.9 0.7 0.2] /N 1 >> >>",
     "<< /ShadingType 2 /ColorSpace /DeviceRGB /Coords [10 20 10 4] /Extend [true true] /Function << /FunctionType 2 /Domain [0 1] /C0 [0.2 0.4 0.8] /C1 [0.8 0.5 0.3] /N 1 >> >>"},
    {"Alpha","","","/I false","1.2 2.5 46.8 30.2",
     "q\n0 3 48 25 re W* n\nq\n2 4 44 22 re W* n\n/M sh\nQ\nQ",
     "<< /ShadingType 2 /ColorSpace /DeviceRGB /Coords [12 24 12 8] /Extend [false false] /Function << /FunctionType 2 /Domain [0 1] /C0 [1 0 0] /C1 [0 0 1] /N 1 >> >>",
     "<< /ShadingType 2 /ColorSpace /DeviceRGB /Coords [12 24 12 8] /Extend [true true] /Function << /FunctionType 2 /Domain [0 1] /C0 [0.1 0.8 0.4] /C1 [0.9 0.2 0.5] /N 1 >> >>"},
  };
  const double scales[]={1.0,5.0/3.0};
  size_t c,s;unsigned w;
  for(c=0;c<sizeof(cases)/sizeof(*cases);c++) {
    char pdf_a[4096],pdf_b[4096],fb_stream[512];
    size_t len_a,len_b;exr_fixed_document *da=NULL,*db=NULL;
    snprintf(fb_stream,sizeof(fb_stream),"q 0 0 0 0 re f Q\n%s",cases[c].stream);
    len_a=build_mask_pdf(pdf_a,sizeof(pdf_a),cases[c].subtype,cases[c].bc,cases[c].tr,cases[c].grp,cases[c].bbox,cases[c].stream,cases[c].mask_sh,cases[c].page_sh);
    len_b=build_mask_pdf(pdf_b,sizeof(pdf_b),cases[c].subtype,cases[c].bc,cases[c].tr,cases[c].grp,cases[c].bbox,fb_stream,cases[c].mask_sh,cases[c].page_sh);
    OK(exr_fixed_open_memory(EXR_PDF,pdf_a,len_a,NULL,&da,&error));
    OK(exr_fixed_open_memory(EXR_PDF,pdf_b,len_b,NULL,&db,&error));
    for(s=0;s<2;s++) for(w=0;w<2;w++) {
      exr_bitmap ba={0},bb={0};exr_fixed_render_options opt={0};
      opt.channels=4;opt.background=w ? 0xffffffffu : 0u;
      OK(exr_fixed_render(da,0,scales[s],&opt,&ba,&error));
      OK(exr_fixed_render(db,0,scales[s],&opt,&bb,&error));
      CHECK(ba.width==bb.width && ba.height==bb.height && ba.stride==bb.stride);
      CHECK(memcmp(ba.pixels,bb.pixels,(size_t)ba.stride*ba.height)==0);
      exr_bitmap_free(&ba);exr_bitmap_free(&bb);
    }
    exr_fixed_free(da);exr_fixed_free(db);
  }
}
int main(int argc,char **argv) {
  CHECK(argc==2);directory=argv[1];scenes();group_failure();aggregate_budget();direct_axial_mask_parity();
  printf("%u mask scope checks; maximum analytic probe difference %u/255\n",checks,maximum);return 0;
}
