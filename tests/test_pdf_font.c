/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include "../src/pdf_internal.h"
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static unsigned char *read_fixture(const char *dir,const char *name,size_t *size) {
  char path[4096]; FILE *file; long length; unsigned char *data;
  snprintf(path,sizeof(path),"%s/%s",dir,name); file=fopen(path,"rb"); CHECK(file);
  CHECK(!fseek(file,0,SEEK_END)); length=ftell(file); CHECK(length>0); rewind(file);
  *size=(size_t)length; data=malloc(*size); CHECK(data && fread(data,1,*size,file)==*size); fclose(file); return data;
}
static uint32_t font_id(exr_pdf_file *file,const char *name) {
  uint32_t fonts; OK(exr_pdf_resolve(file,exr_pdf_get(file,exr_pdf_root(file),"Fonts"),&fonts,&error));
  return exr_pdf_get(file,fonts,name);
}
static exr_pdf_character character(exr_pdf_font *font,const void *data,size_t size) {
  exr_pdf_character out; size_t at=0; OK(exr_pdf_font_next(font,data,size,&at,&out,&error)); CHECK(at==size && out.text.code_bytes==size); return out;
}
static void basic(const char *dir) {
  unsigned char *data; size_t size; exr_pdf_file *file=NULL; exr_pdf_font *font=NULL; const exr_pdf_font_info *info; exr_pdf_character out;
  data=read_fixture(dir,"pdf-fonts.pdf",&size); OK(exr_pdf_open(data,size,&file,&error));
  OK(exr_pdf_font_open(file,font_id(file,"Simple"),NULL,&font,&error)); info=exr_pdf_font_description(font);
  CHECK(info && info->kind==EXR_PDF_TRUETYPE && !info->composite && !info->vertical);
  CHECK(!strcmp(info->base_name,"ABCDEF+Primary") && !strcmp(info->encoding_name,"WinAnsiEncoding"));
  CHECK(info->program_size>100 && !memcmp(info->program,"\0\1\0\0",4));
  out=character(font,"A",1); CHECK(out.width==500 && !out.glyph_known && !strcmp(out.glyph_name,"A") && out.text.size==1 && out.text.utf8[0]=='A');
  out=character(font,"B",1); CHECK(out.width==600 && !strcmp(out.glyph_name,"B") && out.text.size==2 && !memcmp(out.text.utf8,"fi",2));
  out=character(font,"C",1); CHECK(out.width==700 && !strcmp(out.glyph_name,"uni0043") && out.text.size==3 && !memcmp(out.text.utf8,"\xe4\xb8\x80",3));
  out=character(font,"@",1); CHECK(out.width==250 && !strcmp(out.glyph_name,"at") && out.text.size==3 && !memcmp(out.text.utf8,"\xef\xbf\xbd",3)); exr_pdf_font_close(font);
  OK(exr_pdf_font_open(file,font_id(file,"Composite"),NULL,&font,&error)); info=exr_pdf_font_description(font);
  CHECK(info->kind==EXR_PDF_CID_TYPE2 && info->composite && !info->vertical && info->program_size>100);
  out=character(font,"\0\1",2); CHECK(out.cid==1 && out.glyph_known && out.glyph==3 && out.width==510 && out.vertical_advance==-1001 && out.vertical_x==250 && out.vertical_y==860 && out.text.utf8[0]=='A');
  out=character(font,"\0\2",2); CHECK(out.glyph==7 && out.width==520 && out.vertical_advance==-1002 && out.vertical_x==260 && out.vertical_y==861 && out.text.size==4 && !memcmp(out.text.utf8,"\xf0\x9f\x98\x80",4));
  out=character(font,"\0\3",2); CHECK(out.glyph==0 && out.width==900 && out.vertical_advance==-990 && out.vertical_x==450 && out.vertical_y==870 && out.text.size==3);
  out=character(font,"\0\x0a",2); CHECK(out.width==700 && out.vertical_advance==-900 && out.vertical_x==350 && out.vertical_y==850 && out.text.utf8[0]=='a');
  { size_t at=0; CHECK(exr_pdf_font_next(font,(const unsigned char *)"\0",1,&at,&out,&error)==EXR_FORMAT && !at && !out.text.size); }
  exr_pdf_font_close(font);
  OK(exr_pdf_font_open(file,font_id(file,"Vertical"),NULL,&font,&error)); CHECK(exr_pdf_font_description(font)->vertical);
  out=character(font,"\0\1",2); CHECK(out.width==510 && out.vertical_advance==-1001); exr_pdf_font_close(font);
  OK(exr_pdf_font_open(file,font_id(file,"CFF"),NULL,&font,&error)); info=exr_pdf_font_description(font);
  CHECK(info->kind==EXR_PDF_CID_TYPE0 && !info->program && !info->program_size);
  out=character(font,"\0\1",2); CHECK(out.width==1000 && !out.glyph_known && out.text.size==3); exr_pdf_font_close(font);
  CHECK(!exr_pdf_font_description(NULL)); exr_pdf_font_close(NULL); exr_pdf_close(file); free(data);
}
static void bad(const char *dir,const char *name,const char *key) {
  unsigned char *data; char path[256]; size_t size; exr_pdf_file *file=NULL; exr_pdf_font *font=(exr_pdf_font *)(uintptr_t)1;
  snprintf(path,sizeof(path),"pdf-font-bad-%s.pdf",name); data=read_fixture(dir,path,&size); OK(exr_pdf_open(data,size,&file,&error));
  CHECK(exr_pdf_font_open(file,font_id(file,key),NULL,&font,&error)==EXR_FORMAT && !font && error.code==EXR_FORMAT && error.message[0]);
  exr_pdf_close(file); free(data);
}
static int cancelled(void *context) { (void)context; return 1; }
static void encoding_facts(void) {
  char text[256]; double width=-1;
  CHECK(!strcmp(exr_pdf_encoding_glyph("WinAnsiEncoding",160),"space"));
  CHECK(!strcmp(exr_pdf_encoding_glyph("WinAnsiEncoding",173),"hyphen"));
  CHECK(!strcmp(exr_pdf_encoding_glyph("WinAnsiEncoding",129),"bullet"));
  CHECK(!strcmp(exr_pdf_encoding_glyph("MacRomanEncoding",128),"Adieresis"));
  CHECK(!strcmp(exr_pdf_encoding_glyph("StandardEncoding",174),"fi"));
  CHECK(!strcmp(exr_pdf_encoding_glyph("MacExpertEncoding",33),"exclamsmall"));
  CHECK(!exr_pdf_encoding_glyph("WinAnsiEncoding",0) && !exr_pdf_encoding_glyph("WinAnsiEncoding",256));
  CHECK(!exr_pdf_encoding_glyph(NULL,65) && !exr_pdf_encoding_glyph("Unknown",65));
  CHECK(exr_pdf_glyph_unicode("A.swash",0,text)==1 && !strcmp(text,"A"));
  CHECK(exr_pdf_glyph_unicode("A_B.alt",0,text)==2 && !strcmp(text,"AB"));
  CHECK(exr_pdf_glyph_unicode("f_f_i",0,text)==3 && !strcmp(text,"ffi"));
  CHECK(exr_pdf_glyph_unicode("uni00410042",0,text)==2 && !strcmp(text,"AB"));
  CHECK(exr_pdf_glyph_unicode("u1F600",0,text)==4 && !memcmp(text,"\xf0\x9f\x98\x80",5));
  CHECK(exr_pdf_glyph_unicode("dalethatafpatah",0,text)==4 && !memcmp(text,"\xd7\x93\xd6\xb2",5));
  CHECK(exr_pdf_glyph_unicode("a1",1,text)==3 && !memcmp(text,"\xe2\x9c\x81",4));
  CHECK(!exr_pdf_glyph_unicode("a1",0,text) && !text[0]);
  CHECK(!exr_pdf_glyph_unicode("uniD800",0,text) && !exr_pdf_glyph_unicode("uni0041D800",0,text));
  CHECK(!exr_pdf_glyph_unicode("u110000",0,text) && !exr_pdf_glyph_unicode("u1f600",0,text));
  CHECK(!exr_pdf_glyph_unicode(".notdef",0,text) && !exr_pdf_glyph_unicode(NULL,0,text));
  CHECK(exr_pdf_glyph_unicode("A_unknown_B",0,text)==2 && !strcmp(text,"AB"));
  CHECK(exr_pdf_standard_font("Helvetica") && exr_pdf_standard_font("Courier-BoldOblique"));
  CHECK(!exr_pdf_standard_font("ABCDEF+Helvetica") && !exr_pdf_standard_font(NULL));
  CHECK(exr_pdf_standard_width("Helvetica","A",&width) && width==667);
  CHECK(exr_pdf_standard_width("Times-Roman","A",&width) && width==722);
  CHECK(exr_pdf_standard_width("Courier-Bold","A",&width) && width==600);
  CHECK(exr_pdf_standard_width("Symbol","Alpha",&width) && width==722);
  CHECK(!exr_pdf_standard_width("Helvetica","uni0041",&width) && !exr_pdf_standard_width("Unknown","A",&width));
}
static void fallback_fonts(const char *dir) {
  unsigned char *data; size_t size; exr_pdf_file *file=NULL; exr_pdf_font *font=NULL; exr_pdf_character out;
  const char *names[]={"Helvetica","Helvetica-Bold","Helvetica-Oblique","Helvetica-BoldOblique","Times-Roman","Times-Bold","Times-Italic","Times-BoldItalic","Courier","Courier-Bold","Courier-Oblique","Courier-BoldOblique","Symbol","ZapfDingbats"};
  size_t i; data=read_fixture(dir,"pdf-font-fallback.pdf",&size); OK(exr_pdf_open(data,size,&file,&error));
  for(i=0;i<sizeof(names)/sizeof(*names);i++) {
    OK(exr_pdf_font_open(file,font_id(file,names[i]),NULL,&font,&error));
    out=character(font,"A",1); CHECK(out.width>0 && out.text.size>0 && out.glyph_name); exr_pdf_font_close(font);
  }
  OK(exr_pdf_font_open(file,font_id(file,"WinAnsi"),NULL,&font,&error));
  CHECK(exr_pdf_font_description(font)->flags==32);
  out=character(font,"\xa0",1); CHECK(out.width==278 && out.text.size==1 && out.text.utf8[0]==' ');
  out=character(font,"\xad",1); CHECK(out.width==333 && out.text.size==1 && out.text.utf8[0]=='-');
  out=character(font,"A",1); CHECK(out.width==667 && out.text.size==1 && out.text.utf8[0]=='B' && !strcmp(out.glyph_name,"B")); exr_pdf_font_close(font);
  OK(exr_pdf_font_open(file,font_id(file,"Custom"),NULL,&font,&error));
  out=character(font,"A",1); CHECK(out.width==9 && !out.glyph_name && out.text.size==3); exr_pdf_font_close(font);
  OK(exr_pdf_font_open(file,font_id(file,"Names"),NULL,&font,&error));
  out=character(font,"A",1); CHECK(out.width==10 && out.text.size==3 && !memcmp(out.text.utf8,"\xef\xac\x81",3) && !strcmp(out.glyph_name,"fi"));
  out=character(font,"B",1); CHECK(out.width==20 && out.text.size==2 && !memcmp(out.text.utf8,"AB",2));
  out=character(font,"C",1); CHECK(out.width==30 && out.text.size==4 && !memcmp(out.text.utf8,"\xf0\x9f\x98\x80",4)); exr_pdf_font_close(font);
  exr_pdf_close(file); free(data);
}
int main(int argc,char **argv) {
  const char *simple[]={"unknown-encoding","flags","width-short","width-extra","first-char","differences","subtype","width-missing"};
  const char *composite[]={"encoding","descendants","w-overlap","w-truncated","w-range","w-type","w2-truncated","dw2","cid-map","program-type","program-duplicate"}; size_t i;
  CHECK(argc==2); encoding_facts(); basic(argv[1]); fallback_fonts(argv[1]);
  for(i=0;i<sizeof(simple)/sizeof(*simple);i++) bad(argv[1],simple[i],"Simple");
  for(i=0;i<sizeof(composite)/sizeof(*composite);i++) bad(argv[1],composite[i],"Composite");
  { exr_pdf_font *font=(exr_pdf_font *)(uintptr_t)1; exr_pdf_file *file=NULL; exr_control control={0}; unsigned char *data; size_t size;
    data=read_fixture(argv[1],"pdf-fonts.pdf",&size); OK(exr_pdf_open(data,size,&file,&error)); control.cancelled=cancelled;
    CHECK(exr_pdf_font_open(file,font_id(file,"Simple"),&control,&font,&error)==EXR_CANCELLED && !font);
    CHECK(exr_pdf_font_open(NULL,0,NULL,&font,&error)==EXR_ARGUMENT && !font);
    CHECK(exr_pdf_font_open(file,0,NULL,NULL,&error)==EXR_ARGUMENT); exr_pdf_close(file); free(data);
  }
  printf("%u native PDF font checks passed\n",checks); return 0;
}
