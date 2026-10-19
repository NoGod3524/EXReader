/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include "../src/pdf_internal.h"
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
#define NEAR(a,b) CHECK(fabs((a)-(b))<1e-8)
typedef struct { exr_pdf_text_glyph glyphs[32]; size_t count; } capture;
static exr_status collect(void *context,const exr_pdf_text_glyph *glyph,exr_error *e) {
  capture *out=context; (void)e; CHECK(out->count<32 && glyph->sequence==out->count && glyph->font);
  CHECK(exr_pdf_font_description(glyph->font)->program_size>100); out->glyphs[out->count++]=*glyph; return EXR_OK;
}
static exr_status stop(void *context,const exr_pdf_text_glyph *glyph,exr_error *e) { (void)context; (void)glyph; (void)e; return EXR_CANCELLED; }
static capture run(exr_pdf_file *file,uint32_t resources,const char *content) {
  capture out={0}; OK(exr_pdf_text_ops(file,resources,content,strlen(content),collect,&out,NULL,&error)); return out;
}
static void position(const capture *out,size_t index,double x,double y) { CHECK(index<out->count); NEAR(out->glyphs[index].transform[4],x); NEAR(out->glyphs[index].transform[5],y); }
static void forms(const char *dir) {
  const char *invalid[]={"cycle","pop","open","save","matrix","box","type","resources","depth"}; size_t i;
  for(i=0;i<=sizeof(invalid)/sizeof(*invalid);i++) {
    char path[4096]; FILE *input; unsigned char *data; long length; exr_pdf_file *file=NULL; uint32_t resources; capture out={0};
    if(!i) snprintf(path,sizeof(path),"%s/pdf-text-forms.pdf",dir);
    else snprintf(path,sizeof(path),"%s/pdf-form-bad-%s.pdf",dir,invalid[i-1]);
    input=fopen(path,"rb"); CHECK(input && !fseek(input,0,SEEK_END)); length=ftell(input); CHECK(length>0); rewind(input); data=malloc((size_t)length);
    CHECK(data && fread(data,1,(size_t)length,input)==(size_t)length); fclose(input); OK(exr_pdf_open(data,(size_t)length,&file,&error));
    OK(exr_pdf_resolve(file,exr_pdf_get(file,exr_pdf_root(file),"Resources"),&resources,&error));
    if(!i) {
      out=run(file,resources,"q 2 0 0 2 100 200 cm /Outer Do Q /Inner Do /Inherit Do /Local Do BT /Simple 10 Tf (C) Tj ET");
      CHECK(out.count==5); position(&out,0,130,254); NEAR(out.glyphs[0].transform[0],.04); NEAR(out.glyphs[0].transform[3],.06);
      position(&out,1,5,7); position(&out,2,0,0); CHECK(out.glyphs[2].character.text.size==2);
      position(&out,3,0,0); NEAR(out.glyphs[3].transform[1],.01); NEAR(out.glyphs[3].transform[2],-.01);
      position(&out,4,0,0); CHECK(out.glyphs[4].character.text.code==67);
      out=run(file,resources,"/G gs /Inherit Do BT <0001> Tj ET"); CHECK(out.count==2 && out.glyphs[1].character.glyph==3); NEAR(out.glyphs[1].transform[0],.02);
      out=run(file,resources,"/Inner Do /Inner Do"); CHECK(out.count==2); position(&out,0,5,7); position(&out,1,5,7);
      out=run(file,resources,"/Form Do"); CHECK(!out.count);
    } else {
      const char content[]="q /Outer Do Q"; exr_status expected=!strcmp(invalid[i-1],"depth") ? EXR_LIMIT : EXR_FORMAT;
      CHECK(exr_pdf_text_ops(file,resources,content,sizeof(content)-1,collect,&out,NULL,&error)==expected);
    }
    exr_pdf_close(file); free(data);
  }
}
int main(int argc,char **argv) {
  char path[4096]; FILE *input; long length; unsigned char *data; exr_pdf_file *file=NULL; uint32_t resources; capture out; size_t i;
  const char *bad[]={"Q","q","BT","ET","BT BT ET ET","BT (A) Tj ET","BT /Missing 10 Tf (A) Tj ET","BT /Simple /Size Tf ET","BT /Simple 10 Tf 2 3 Td 1 Tm ET","BT 8 Tr ET","BT /Simple 10 Tf [true] TJ ET","/MissingForm Do","BI ID x EI","Unknown","BX","EX","1 cm","BT /Composite 10 Tf <00> Tj ET"};
  CHECK(argc==2); forms(argv[1]); snprintf(path,sizeof(path),"%s/pdf-fonts.pdf",argv[1]); input=fopen(path,"rb"); CHECK(input);
  CHECK(!fseek(input,0,SEEK_END)); length=ftell(input); CHECK(length>0); rewind(input); data=malloc((size_t)length);
  CHECK(data && fread(data,1,(size_t)length,input)==(size_t)length); fclose(input); OK(exr_pdf_open(data,(size_t)length,&file,&error));
  OK(exr_pdf_resolve(file,exr_pdf_get(file,exr_pdf_root(file),"Resources"),&resources,&error)); CHECK(resources!=EXR_PDF_NONE);
  out=run(file,resources,"q 2 0 0 3 10 20 cm BT /Simple 10 Tf 1 Tc 2 Tw 50 Tz 4 Ts 1 0 0 1 100 200 Tm (AB) Tj [(C) 100 (A)] TJ ET Q");
  CHECK(out.count==4); position(&out,0,210,632); position(&out,1,216,632); position(&out,2,223,632); position(&out,3,230,632);
  NEAR(out.glyphs[0].transform[0],.01); NEAR(out.glyphs[0].transform[3],.03); CHECK(out.glyphs[1].character.text.size==2 && !memcmp(out.glyphs[1].character.text.utf8,"fi",2));
  out=run(file,resources,"BT /Simple 10 Tf 12 TL 10 100 Td (A) Tj (B) ' 3 2 (A A) \" ET");
  CHECK(out.count==5); position(&out,0,10,100); position(&out,1,10,88); position(&out,2,10,76); position(&out,3,17,76); position(&out,4,24.5,76);
  out=run(file,resources,"BT /Simple 10 Tf (A) Tj q /Simple 20 Tf (A) Tj Q (A) Tj ET");
  CHECK(out.count==3); position(&out,0,0,0); position(&out,1,5,0); position(&out,2,15,0); NEAR(out.glyphs[2].transform[0],.01);
  out=run(file,resources,"BT /Simple 10 Tf 0 1 -1 0 10 20 Tm (AA) Tj ET");
  position(&out,0,10,20); position(&out,1,10,25); NEAR(out.glyphs[0].transform[1],.01); NEAR(out.glyphs[0].transform[2],-.01);
  out=run(file,resources,"BT /Vertical 20 Tf 1 Tc 2 Tw 80 Tz 1 0 0 1 100 200 Tm <00010002000a> Tj ET");
  CHECK(out.count==3); position(&out,0,96,182.8); position(&out,1,95.84,163.76); position(&out,2,94.4,144.94);
  out=run(file,resources,"/G gs BT 3 Tr <0001> Tj ET /Image Do BX 42 Unknown EX");
  CHECK(out.count==1 && out.glyphs[0].rendering_mode==3 && out.glyphs[0].character.glyph==3); NEAR(out.glyphs[0].transform[0],.02);
  out=run(file,resources,"BT /Simple 10 Tf 10 20 TD (A) Tj T* (A) Tj ET"); position(&out,0,10,20); position(&out,1,10,40);
  out=run(file,resources,"BT ET"); CHECK(!out.count);
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) { capture discarded={0}; CHECK(exr_pdf_text_ops(file,resources,bad[i],strlen(bad[i]),collect,&discarded,NULL,&error)==EXR_FORMAT); }
  { const char content[]="BT /Simple 10 Tf (A) Tj ET"; CHECK(exr_pdf_text_ops(file,resources,content,sizeof(content)-1,stop,NULL,NULL,&error)==EXR_CANCELLED); }
  { char content[1024]; capture discarded={0};
    for(i=0;i<129;i++) memcpy(content+2*i,"q ",2);
    CHECK(exr_pdf_text_ops(file,resources,content,258,collect,&discarded,NULL,&error)==EXR_LIMIT);
    snprintf(content,sizeof(content),"10000000 0 0 1 0 0 cm 10000000 0 0 1 0 0 cm");
    CHECK(exr_pdf_text_ops(file,resources,content,strlen(content),collect,&discarded,NULL,&error)==EXR_LIMIT);
  }
  CHECK(exr_pdf_text_ops(NULL,resources,NULL,0,collect,&out,NULL,&error)==EXR_ARGUMENT);
  exr_pdf_close(file); free(data);
  snprintf(path,sizeof(path),"%s/pdf-text-font-budget.pdf",argv[1]); input=fopen(path,"rb"); CHECK(input);
  CHECK(!fseek(input,0,SEEK_END)); length=ftell(input); CHECK(length>0); rewind(input); data=malloc((size_t)length);
  CHECK(data && fread(data,1,(size_t)length,input)==(size_t)length); fclose(input); OK(exr_pdf_open(data,(size_t)length,&file,&error));
  OK(exr_pdf_resolve(file,exr_pdf_get(file,exr_pdf_root(file),"Resources"),&resources,&error));
  { exr_buffer content={0}; capture discarded={0}; char name[64]; CHECK(exr_append(&content,"BT ",3));
    for(i=0;i<129;i++) { int n=snprintf(name,sizeof(name),"/F%u 10 Tf ",(unsigned)i); CHECK(exr_append(&content,name,(size_t)n)); }
    CHECK(exr_append(&content,"ET",2)); CHECK(exr_pdf_text_ops(file,resources,content.data,content.size,collect,&discarded,NULL,&error)==EXR_LIMIT && !discarded.count); free(content.data);
  }
  exr_pdf_close(file); free(data); printf("%u native PDF text geometry checks passed\n",checks); return 0;
}
