/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <miniz.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks; static const char *scenario;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"%s line %d: %s (%d: %s)\n",scenario,__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
typedef struct { unsigned char *data; size_t size,capacity; } buffer;
static void bytes(buffer *b,const void *data,size_t n) {
  if(n>b->capacity-b->size) { size_t cap=b->capacity ? b->capacity : 4096; while(cap-b->size<n) cap*=2; b->data=realloc(b->data,cap); CHECK(b->data); b->capacity=cap; }
  if(n) memcpy(b->data+b->size,data,n);
  b->size+=n;
}
static void add(buffer *b,const char *s) { bytes(b,s,strlen(s)); }
static void object(buffer *b,size_t *offset,unsigned id,const char *s) {
  char row[64]; offset[id]=b->size; snprintf(row,sizeof(row),"%u 0 obj\n",id); add(b,row); add(b,s); add(b,"\nendobj\n");
}
static void stream(buffer *b,size_t *offset,unsigned id,const char *dict,const void *data,size_t n) {
  char row[2048]; offset[id]=b->size; snprintf(row,sizeof(row),"%u 0 obj\n<< %s /Length %zu >>\nstream\n",id,dict,n); add(b,row); bytes(b,data,n); add(b,"\nendstream\nendobj\n");
}
static buffer build(const buffer *content,const buffer *form,const buffer *glyph,int own_glyph_resources) {
  buffer b={0}; size_t offset[10],xref; unsigned i; char row[2048];
  add(&b,"%PDF-1.7\n"); object(&b,offset,1,"<< /Type /Catalog /Pages 2 0 R >>");
  object(&b,offset,2,"<< /Type /Pages /Count 1 /Kids [3 0 R] >>");
  object(&b,offset,3,"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 32 32] /Contents 4 0 R /Resources << /Font << /F1 5 0 R /T3 7 0 R >> /XObject << /Fm 6 0 R >> /ColorSpace << /Local /DeviceRGB /Gray /DeviceGray /Palette [/Indexed /DeviceRGB 1 9 0 R] /Alias /Palette /Cycle /Cycle >> >> >>");
  stream(&b,offset,4,"",content->data,content->size); object(&b,offset,5,"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  stream(&b,offset,6,"/Type /XObject /Subtype /Form /BBox [0 0 32 32] /Resources << /ColorSpace << /Local /DeviceGray >> >>",form ? form->data : NULL,form ? form->size : 0);
  snprintf(row,sizeof(row),"<< /Type /Font /Subtype /Type3 /FontBBox [0 0 1000 1000] /FontMatrix [.001 0 0 .001 0 0] /FirstChar 65 /LastChar 65 /Widths [1000] /Encoding << /Differences [65 /A] >> /CharProcs << /A 8 0 R >> %s >>",own_glyph_resources ? "/Resources << /ColorSpace << /Local /DeviceGray >> >>" : ""); object(&b,offset,7,row);
  stream(&b,offset,8,"",glyph ? glyph->data : NULL,glyph ? glyph->size : 0);
  stream(&b,offset,9,"","\xff\x00\x00\x00\xff\x00",6);
  xref=b.size; add(&b,"xref\n0 10\n0000000000 65535 f \n"); for(i=1;i<10;i++) { snprintf(row,sizeof(row),"%010zu 00000 n \n",offset[i]); add(&b,row); }
  snprintf(row,sizeof(row),"trailer\n<< /Size 10 /Root 1 0 R >>\nstartxref\n%zu\n%%%%EOF\n",xref); add(&b,row); return b;
}
static exr_fixed_document *open_pdf(const buffer *b) { exr_fixed_document *d=NULL; OK(exr_fixed_open_memory(EXR_PDF,b->data,b->size,NULL,&d,&error)); return d; }
static void text(exr_fixed_document *d,const char *expected) {
  exr_fixed_text *t=NULL; size_t n; OK(exr_fixed_load_text(d,0,NULL,&t,&error)); CHECK(!strcmp(exr_fixed_text_string(t,&n),expected) && n==strlen(expected)); exr_fixed_text_free(t);
}
static exr_bitmap render(exr_fixed_document *d) { exr_bitmap b={0}; OK(exr_fixed_render(d,0,1,NULL,&b,&error)); CHECK(b.width==32 && b.height==32); return b; }
static unsigned color(const exr_bitmap *b,unsigned x,unsigned y) { const unsigned char *p=b->pixels+(b->height-y-1)*b->stride+x*4; return ((unsigned)p[0]<<16)|((unsigned)p[1]<<8)|p[2]; }
static void inline_data(buffer *b,const char *dict,const void *data,size_t size,const char *separator) {
  add(b,"BI "); add(b,dict); add(b," ID"); add(b,separator ? separator : " "); bytes(b,data,size); add(b,"\nEI ");
}
static void label(buffer *b) { add(b,"BT /F1 8 Tf 3 Tr 1 0 0 1 20 20 Tm (Z) Tj ET"); }
static void save(const buffer *b,const char *dir,const char *name) { char path[4096]; FILE *f; if(!dir) return; snprintf(path,sizeof(path),"%s/%s",dir,name); f=fopen(path,"wb"); CHECK(f); CHECK(fwrite(b->data,1,b->size,f)==b->size); CHECK(!fclose(f)); }
static void raw_cases(const char *dir) {
  static const unsigned char rgb[]={255,0,0,0,255,0},gray[]={32,69,73,32,255,10},packed[]={0x18,0xe4};
  buffer c={0},b; exr_fixed_document *d; exr_bitmap image; size_t i;
  scenario="raw RGB and text following image"; add(&c,"q 16 0 0 8 0 0 cm "); inline_data(&c,"/W 2 /H 1 /BPC 8 /CS /RGB",rgb,6,NULL); add(&c,"Q "); label(&c); b=build(&c,NULL,NULL,0); d=open_pdf(&b); image=render(d); CHECK(color(&image,4,4)==0xff0000 && color(&image,12,4)==0x00ff00); text(d,"Z"); save(&b,dir,"pdf-inline-rgb.pdf"); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); c.size=0;
  scenario="raw embedded EI and trailing pixel newline"; add(&c,"q 24 0 0 4 0 0 cm "); inline_data(&c,"/Width 6 /Height 1 /BitsPerComponent 8 /ColorSpace /Gray",gray,6,NULL); add(&c,"Q "); label(&c); b=build(&c,NULL,NULL,0); d=open_pdf(&b); image=render(d); for(i=0;i<6;i++) CHECK(color(&image,(unsigned)(i*4+1),1)==gray[i]*0x010101u); text(d,"Z"); save(&b,dir,"pdf-inline-ei.pdf"); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); c.size=0;
  scenario="CRLF ID and leading whitespace pixel"; add(&c,"q 8 0 0 4 0 0 cm "); inline_data(&c,"/W 1 /H 1 /BPC 8 /CS /G",gray+5,1,"\r\n"); add(&c,"Q "); label(&c); b=build(&c,NULL,NULL,0); d=open_pdf(&b); image=render(d); CHECK(color(&image,1,1)==0x0a0a0a); text(d,"Z"); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); c.size=0;
  scenario="packed samples reset at each padded row"; add(&c,"q 12 0 0 8 0 0 cm "); inline_data(&c,"/W 3 /H 2 /BPC 2 /CS /G",packed,2,NULL); add(&c,"Q "); b=build(&c,NULL,NULL,0); d=open_pdf(&b); image=render(d); CHECK(color(&image,1,6)==0 && color(&image,5,6)==0x555555 && color(&image,9,6)==0xaaaaaa); CHECK(color(&image,1,1)==0xffffff && color(&image,5,1)==0xaaaaaa && color(&image,9,1)==0x555555); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); c.size=0;
  scenario="stencil inherited fill and reversed Decode"; add(&c,"0 0 1 rg q 16 0 0 4 0 0 cm "); inline_data(&c,"/W 8 /H 1 /IM true /D [1 0]","\xa0",1,NULL); add(&c,"Q "); b=build(&c,NULL,NULL,0); d=open_pdf(&b); image=render(d); CHECK(color(&image,0,1)==0x0000ff && color(&image,2,1)==0xffffff && color(&image,4,1)==0x0000ff); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); c.size=0;
  scenario="sixteen bit big endian samples"; add(&c,"q 16 0 0 8 0 0 cm "); inline_data(&c,"/W 2 /H 1 /BPC 16 /CS /G","\x00\x00\xff\xff",4,NULL); add(&c,"Q "); b=build(&c,NULL,NULL,0); d=open_pdf(&b); image=render(d); CHECK(color(&image,4,4)==0 && color(&image,12,4)==0xffffff); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); c.size=0;
  for(i=0;i<3;i++) {
    const char *spaces[]={"[/I /RGB 1 <FF000000FF00>]","/Palette","/Alias"}; char dict[192]; scenario="Indexed direct and cross arena named aliases"; add(&c,"q 16 0 0 8 0 0 cm "); snprintf(dict,sizeof(dict),"/W 2 /H 1 /BPC 1 /CS %s",spaces[i]); inline_data(&c,dict,"\x40",1,NULL); add(&c,"Q "); label(&c); b=build(&c,NULL,NULL,0); d=open_pdf(&b); image=render(d); CHECK(color(&image,4,4)==0xff0000 && color(&image,12,4)==0x00ff00); text(d,"Z"); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); c.size=0;
  }
  scenario="JPEG entropy stuffed FF, restart and fake EI do not terminate the image";
  { const unsigned char encoded[]={255,216,255,218,0,2,32,69,73,32,255,0,217,255,208,32,255,217};
    inline_data(&c,"/W 1 /H 1 /BPC 8 /CS /RGB /F /DCT",encoded,sizeof(encoded),NULL); label(&c); b=build(&c,NULL,NULL,0); d=open_pdf(&b); text(d,"Z"); exr_fixed_free(d); free(b.data); }
  free(c.data);
}
static buffer hexed(const void *data,size_t n) { const unsigned char *p=data; const char *hex="0123456789ABCDEF"; size_t i; buffer b={0}; for(i=0;i<n;i++) { char row[2]={hex[p[i]>>4],hex[p[i]&15]}; bytes(&b,row,2); } add(&b,">"); return b; }
static buffer ascii85(const void *data,size_t n) {
  const unsigned char *p=data; buffer b={0}; size_t at; for(at=0;at<n;at+=4) { uint32_t v=0; unsigned i,k=(unsigned)(n-at<4 ? n-at : 4); char row[5]; for(i=0;i<4;i++) v=(v<<8)|(i<k ? p[at+i] : 0); for(i=5;i;i--) { row[i-1]=(char)(v%85+33); v/=85; } bytes(&b,row,k+1); } add(&b,"~>"); return b;
}
static buffer deflated(const void *data,size_t n,int level) { buffer b={0}; mz_ulong size=mz_compressBound((mz_ulong)n); b.data=malloc(size); CHECK(b.data); b.capacity=size; CHECK(mz_compress2(b.data,&size,data,(mz_ulong)n,level)==MZ_OK); b.size=size; return b; }
static buffer lzw(const unsigned char *data,size_t n) {
  buffer b={0}; size_t bit=0,i; unsigned char zero=0; for(i=0;i<n+2;i++) { unsigned code=i==0 ? 256 : i==n+1 ? 257 : data[i-1],k; for(k=0;k<9;k++,bit++) { if(!(bit&7)) bytes(&b,&zero,1); b.data[bit/8]|=(unsigned char)(((code>>(8-k))&1)<<(7-bit%8)); } } return b;
}
static void filtered_cases(const char *dir) {
  const unsigned char samples[]={255,0,0,0,255,0}; buffer payload[6],c={0},b; size_t i; exr_fixed_document *d; exr_bitmap image;
  scenario="filter generation"; payload[0]=hexed(samples,6); payload[1]=ascii85(samples,6); payload[2]=deflated(samples,6,6); payload[3]=(buffer){0}; bytes(&payload[3],"\x05",1); bytes(&payload[3],samples,6); bytes(&payload[3],"\x80",1); payload[4]=lzw(samples,6); payload[5]=ascii85(payload[2].data,payload[2].size);
  for(i=0;i<6;i++) {
    const char *filters[]={"/AHx","/A85","/Fl","/RL","/LZW","[/A85 /Fl]"}; char dict[256]; scenario="existing lossless filters and real stream terminators"; snprintf(dict,sizeof(dict),"/W 2 /H 1 /BPC 8 /CS /RGB /F %s",filters[i]); add(&c,"q 16 0 0 8 0 0 cm "); inline_data(&c,dict,payload[i].data,payload[i].size,NULL); add(&c,"Q "); label(&c); b=build(&c,NULL,NULL,0); d=open_pdf(&b); image=render(d); CHECK(color(&image,4,4)==0xff0000 && color(&image,12,4)==0x00ff00); text(d,"Z"); if(i==5) save(&b,dir,"pdf-inline-filter-chain.pdf"); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); c.size=0; free(payload[i].data);
  }
  scenario="Flate stored data contains fake EI token";
  { const char pixels[]=" EI \xff\x0a"; buffer p=deflated(pixels,6,0); add(&c,"q 24 0 0 4 0 0 cm "); inline_data(&c,"/W 6 /H 1 /BPC 8 /CS /G /F /Fl",p.data,p.size,NULL); add(&c,"Q "); label(&c); b=build(&c,NULL,NULL,0); d=open_pdf(&b); image=render(d); CHECK(color(&image,5,1)==0x454545 && color(&image,21,1)==0x0a0a0a); text(d,"Z"); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); free(p.data); c.size=0; }
  scenario="Flate PNG predictor reused";
  { const unsigned char predicted[]={0,255,0,0,0,255,0}; buffer p=deflated(predicted,7,6); add(&c,"q 16 0 0 8 0 0 cm "); inline_data(&c,"/W 2 /H 1 /BPC 8 /CS /RGB /F /Fl /DP << /Predictor 15 /Colors 3 /Columns 2 >>",p.data,p.size,NULL); add(&c,"Q "); b=build(&c,NULL,NULL,0); d=open_pdf(&b); image=render(d); CHECK(color(&image,4,4)==0xff0000 && color(&image,12,4)==0x00ff00); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); free(p.data); }
  free(c.data);
}
static buffer load(const char *dir,const char *name) { buffer b={0}; char path[4096]; FILE *f; long n; snprintf(path,sizeof(path),"%s/%s",dir,name); f=fopen(path,"rb"); CHECK(f); CHECK(!fseek(f,0,SEEK_END)); n=ftell(f); CHECK(n>0); rewind(f); b.data=malloc((size_t)n); CHECK(b.data); b.size=b.capacity=(size_t)n; CHECK(fread(b.data,1,b.size,f)==b.size); CHECK(!fclose(f)); return b; }
static void jpeg_cases(const char *fixtures,const char *dir) {
  buffer c={0},b,p,j; exr_fixed_document *d; exr_bitmap image; size_t i;
  for(i=0;i<3;i++) {
    const char *files[]={"pdf-images/baseline.jpg","pdf-images/progressive.jpg","pdf-images/gray.jpg"}; char dict[128]; scenario="JPEG real EOI, progressive multiple scans and embedded APP bytes"; j=load(fixtures,files[i]); p=(buffer){0}; bytes(&p,j.data,2); bytes(&p,"\xff\xe1\x00\x0a" " EI " "\xff\xd9" " x",12); bytes(&p,j.data+2,j.size-2); snprintf(dict,sizeof(dict),"/W %u /H %u /BPC 8 /CS /%s /F /DCT",i==2 ? 8 : 16,i==2 ? 8 : 16,i==2 ? "G" : "RGB"); add(&c,"q 16 0 0 16 0 0 cm "); inline_data(&c,dict,p.data,p.size,NULL); add(&c,"Q "); label(&c); b=build(&c,NULL,NULL,0); d=open_pdf(&b); image=render(d); if(i==2) CHECK(color(&image,4,4)==0x404040); else CHECK(color(&image,2,13)>0xf00000 && (color(&image,13,13)&0xff0000)<0x050000); text(d,"Z"); if(!i) save(&b,dir,"pdf-inline-jpeg.pdf"); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); free(j.data); free(p.data); c.size=0;
  }
  free(c.data);
}
static void cmyk_inline_cases(const char *fixtures) {
  const char *files[]={"cmyk.jpg","cmyk-progressive.jpg","ycck.jpg","ycck-progressive.jpg"}; size_t i;
  for(i=0;i<4;i++) {
    char path[128]; buffer c={0},b,j; exr_fixed_document *d; exr_bitmap image; const unsigned char *p;
    scenario="CMYK/YCCK inline JPEG preserves Decode and following text";
    snprintf(path,sizeof(path),"pdf-images/%s",files[i]); j=load(fixtures,path);
    add(&c,"q 16 0 0 16 0 0 cm "); inline_data(&c,"/W 17 /H 9 /BPC 8 /CS /CMYK /F /DCT /D [1 0 1 0 1 0 1 0]",j.data,j.size,NULL);
    add(&c,"Q "); label(&c); b=build(&c,NULL,NULL,0); d=open_pdf(&b); image=render(d);
    p=image.pixels+(image.height-5)*image.stride+4*4;
    CHECK(abs((int)p[0]-183)<=2 && abs((int)p[1]-143)<=2 && abs((int)p[2]-103)<=2 && p[3]==255); text(d,"Z");
    exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); free(c.data); free(j.data);
  }
}
static void scoped_cases(const char *dir) {
  buffer c={0},f={0},g={0},b; exr_fixed_document *d; exr_bitmap image;
  scenario="Form resources determine raw cardinality and image ColorSpace"; add(&f,"q 16 0 0 8 0 0 cm "); inline_data(&f,"/W 2 /H 1 /BPC 8 /CS /Local","\x40\xc0",2,NULL); add(&f,"Q "); add(&c,"/Fm Do "); label(&c); b=build(&c,&f,NULL,0); d=open_pdf(&b); image=render(d); CHECK(color(&image,4,4)==0x404040 && color(&image,12,4)==0xc0c0c0); text(d,"Z"); save(&b,dir,"pdf-inline-form.pdf"); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); c.size=f.size=0;
  scenario="Type3 inherited page resources"; add(&g,"1000 0 d0 1000 0 0 1000 0 0 cm "); inline_data(&g,"/W 1 /H 1 /BPC 8 /CS /Local","\xff\x00\x00",3,NULL); add(&c,"BT /T3 16 Tf 1 0 0 1 0 0 Tm (A) Tj ET"); b=build(&c,NULL,&g,0); d=open_pdf(&b); image=render(d); CHECK(color(&image,4,4)==0xff0000); text(d,"A"); save(&b,dir,"pdf-inline-type3.pdf"); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); g.size=0;
  scenario="Type3 own resources"; add(&g,"1000 0 d0 1000 0 0 1000 0 0 cm "); inline_data(&g,"/W 1 /H 1 /BPC 8 /CS /Local","\x40",1,NULL); b=build(&c,NULL,&g,1); d=open_pdf(&b); image=render(d); CHECK(color(&image,4,4)==0x404040); text(d,"A"); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); c.size=g.size=0;
  scenario="uncolored Type3 inline stencil"; add(&g,"1000 0 0 0 1000 1000 d1 1000 0 0 1000 0 0 cm "); inline_data(&g,"/W 1 /H 1 /IM true /D [1 0]","\x80",1,NULL); add(&c,"0 0 1 rg BT /T3 16 Tf 1 0 0 1 0 0 Tm (A) Tj ET"); b=build(&c,NULL,&g,0); d=open_pdf(&b); image=render(d); CHECK(color(&image,4,4)==0x0000ff); text(d,"A"); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data);
  free(c.data); free(f.data); free(g.data);
}
static int cancelled(void *context) { unsigned *calls=context; return ++*calls>=3; }
static void bad_cases(void) {
  const char *bad[]={"BI ID x EI","1 BI /W 1 /H 1 /BPC 8 /CS /G ID x EI","BI /W 1 /W 2 /H 1 /BPC 8 /CS /G ID x EI","BI /W 1 /Width 2 /H 1 /BPC 8 /CS /G ID x EI","BI /W 0 /H 1 /BPC 8 /CS /G ID x EI","BI /W 1 /H 1 /BPC 3 /CS /G ID x EI","BI /W 1 /H 1 /BPC 8 /CS /G ID/x EI","BI /W 1 /H 1 /BPC 8 /CS /G ID xEI","BI /W 1 /H 1 /BPC 8 /CS /G ID x EIfoo","BI /W 1 /H 1 /BPC 8 /CS /G ID x","BI /W 1 /H 1 /BPC 8 /CS /G /F [] ID x EI","BI /W 1 /H 1 /BPC 8 /CS /Cycle ID x EI","BI /W 1 /H 1 /BPC 8 /CS /G /F /AHx ID 00 EI","BI /W 1 /H 1 /BPC 8 /CS /G /F /A85 ID !~> EI","BI /W 1 /H 1 /BPC 8 /CS /G /F /Fl ID junk EI","BI /W 1 /H 1 /BPC 8 /CS /G /F /DCT ID junk EI","BT BI /W 1 /H 1 /BPC 8 /CS /G ID x EI ET","BI /W 1 /H 1 /BPC 8 /CS /G /Unknown [1 0 R] ID x EI"};
  buffer c={0},b,g={0}; size_t i; exr_fixed_document *d;
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) { exr_bitmap image={0}; exr_fixed_text *t=NULL; scenario=bad[i]; add(&c,bad[i]); b=build(&c,NULL,NULL,0); d=open_pdf(&b); CHECK(exr_fixed_render(d,0,1,NULL,&image,&error)==EXR_FORMAT && !image.pixels); CHECK(exr_fixed_load_text(d,0,NULL,&t,&error)==EXR_FORMAT && !t); exr_fixed_free(d); free(b.data); c.size=0; }
  scenario="d1 rejects colored inline images"; add(&g,"1000 0 0 0 1000 1000 d1 "); inline_data(&g,"/W 1 /H 1 /BPC 8 /CS /RGB","\xff\x00\x00",3,NULL); add(&c,"BT /T3 16 Tf (A) Tj ET"); b=build(&c,NULL,&g,0); d=open_pdf(&b); { exr_bitmap image={0}; CHECK(exr_fixed_render(d,0,1,NULL,&image,&error)==EXR_FORMAT && !image.pixels); text(d,"A"); } exr_fixed_free(d); free(b.data); c.size=0;
  scenario="cancel during inline decompression";
  { unsigned calls=0; exr_control control={0}; exr_fixed_text *t=NULL; unsigned char *pixels=calloc(1024*1024,1); buffer p; CHECK(pixels); p=deflated(pixels,1024*1024,6); inline_data(&c,"/W 1024 /H 1024 /BPC 8 /CS /G /F /Fl",p.data,p.size,NULL); b=build(&c,NULL,NULL,0); d=open_pdf(&b); control.context=&calls; control.cancelled=cancelled; CHECK(exr_fixed_load_text(d,0,&control,&t,&error)==EXR_CANCELLED && !t); exr_fixed_free(d); free(b.data); c.size=0;
    scenario="inline decode budget persists across released images"; for(i=0;i<200;i++) inline_data(&c,"/W 1024 /H 1024 /BPC 8 /CS /G /F /Fl",p.data,p.size,NULL); b=build(&c,NULL,NULL,0); d=open_pdf(&b); CHECK(exr_fixed_load_text(d,0,NULL,&t,&error)==EXR_LIMIT && !t); exr_fixed_free(d); free(b.data); c.size=0;
    scenario="nested Form inline images share the page decode budget";
    { buffer form={0}; inline_data(&form,"/W 1024 /H 1024 /BPC 8 /CS /G /F /Fl",p.data,p.size,NULL); for(i=0;i<200;i++) add(&c,"/Fm Do "); b=build(&c,&form,NULL,0); d=open_pdf(&b); CHECK(exr_fixed_load_text(d,0,NULL,&t,&error)==EXR_LIMIT && !t); exr_fixed_free(d); free(b.data); free(form.data); }
    free(p.data); free(pixels); }
  free(c.data); free(g.data);
}
int main(int argc,char **argv) { const char *dir=argc>2 ? argv[2] : NULL; scenario="arguments"; CHECK(argc>=2); raw_cases(dir); filtered_cases(dir); jpeg_cases(argv[1],dir); cmyk_inline_cases(argv[1]); scoped_cases(dir); bad_cases(); printf("%u native PDF inline image checks passed\n",checks); return 0; }
