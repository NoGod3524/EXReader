/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks; static const char *scenario;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"%s line %d: %s (%d %s)\n",scenario,__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
#define D65 "/WhitePoint [.95047 1 1.08883]"
#define D50 "/WhitePoint [.96422 1 .82521]"
#define CG "[/CalGray << " D65 " >>]"
#define CG2 "[/CalGray << " D65 " /Gamma 2.2 >>]"
#define CR "[/CalRGB << " D65 " /Matrix [.4124564 .2126729 .0193339 .3575761 .7151522 .1191920 .1804375 .0721750 .9503041] >>]"
#define LAB "[/Lab << " D65 " /Range [-128 127 -128 127] >>]"
typedef struct { unsigned char *data; size_t size,capacity; } buffer;
static void bytes(buffer *b,const void *data,size_t n) { if(n>b->capacity-b->size) { size_t cap=b->capacity ? b->capacity : 4096; while(cap-b->size<n) cap*=2; b->data=realloc(b->data,cap); CHECK(b->data); b->capacity=cap; } if(n) memcpy(b->data+b->size,data,n); b->size+=n; }
static void add(buffer *b,const char *text) { bytes(b,text,strlen(text)); }
static void object(buffer *b,size_t *offset,unsigned id,const char *body) { char row[64]; offset[id]=b->size; snprintf(row,sizeof(row),"%u 0 obj\n",id); add(b,row); add(b,body); add(b,"\nendobj\n"); }
static void stream(buffer *b,size_t *offset,unsigned id,const char *dict,const void *data,size_t size) { char row[2048]; offset[id]=b->size; snprintf(row,sizeof(row),"%u 0 obj\n<< %s /Length %zu >>\nstream\n",id,dict,size); add(b,row); bytes(b,data,size); add(b,"\nendstream\nendobj\n"); }
static buffer book(const char *definition,const buffer *content,const char *image_dict,const void *samples,size_t sample_size,const char *icc_dict,const char *form) {
  buffer b={0}; size_t offset[11],xref; char row[8192]; unsigned i;
  add(&b,"%PDF-1.7\n"); object(&b,offset,1,"<< /Type /Catalog /Pages 2 0 R >>"); object(&b,offset,2,"<< /Type /Pages /Count 1 /Kids [3 0 R] >>");
  snprintf(row,sizeof(row),"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 64 32] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> /XObject << /Im 7 0 R /Fm 8 0 R >> /ColorSpace << /S %s /Alias /S /Base " CG " >> >> >>",definition); object(&b,offset,3,row);
  stream(&b,offset,4,"",content->data,content->size); object(&b,offset,5,"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  stream(&b,offset,6,icc_dict ? icc_dict : "/N 3",NULL,0);
  snprintf(row,sizeof(row),"/Type /XObject /Subtype /Image /Width 1 /Height 1 /BitsPerComponent 8 /ColorSpace %s %s",definition,image_dict ? image_dict : ""); stream(&b,offset,7,row,samples,sample_size);
  stream(&b,offset,8,"/Type /XObject /Subtype /Form /BBox [0 0 64 32] /Resources << /ColorSpace << /S 10 0 R /Base " CG2 " >> >>",form,form ? strlen(form) : 0);
  stream(&b,offset,9,"","\x00\x80\xff",3); object(&b,offset,10,"[/Indexed /Base 0 <80>]");
  xref=b.size; add(&b,"xref\n0 11\n0000000000 65535 f \n"); for(i=1;i<11;i++) { snprintf(row,sizeof(row),"%010zu 00000 n \n",offset[i]); add(&b,row); }
  snprintf(row,sizeof(row),"trailer\n<< /Size 11 /Root 1 0 R >>\nstartxref\n%zu\n%%%%EOF\n",xref); add(&b,row); return b;
}
static exr_fixed_document *opened(const buffer *b) { exr_fixed_document *d=NULL; OK(exr_fixed_open_memory(EXR_PDF,b->data,b->size,NULL,&d,&error)); return d; }
static exr_bitmap rendered(exr_fixed_document *d) { exr_bitmap image={0}; OK(exr_fixed_render(d,0,1,NULL,&image,&error)); CHECK(image.width==64 && image.height==32); return image; }
static void label(buffer *b) { add(b," BT /F1 8 Tf 3 Tr (Z) Tj ET "); }
static void text(exr_fixed_document *d) { exr_fixed_text *t=NULL; size_t n; OK(exr_fixed_load_text(d,0,NULL,&t,&error)); CHECK(!strcmp(exr_fixed_text_string(t,&n),"Z") && n==1); exr_fixed_text_free(t); }
static void pixel(const exr_bitmap *image,unsigned x,unsigned y,const unsigned expected[3],unsigned tolerance) { const unsigned char *p=image->pixels+(image->height-y-1)*image->stride+x*4; unsigned i; for(i=0;i<3;i++) CHECK(abs((int)p[i]-(int)expected[i])<=(int)tolerance); CHECK(p[3]==255); }
static void save(const buffer *b,const char *directory,const char *name) { char path[4096]; FILE *f; if(!directory || !name) return; snprintf(path,sizeof(path),"%s/%s",directory,name); f=fopen(path,"wb"); CHECK(f); CHECK(fwrite(b->data,1,b->size,f)==b->size); CHECK(!fclose(f)); }
static void same_color(const char *definition,const char *components,const char *dict,const void *samples,size_t sample_size,const char *icc,const unsigned expected[3],const char *directory,const char *name) {
  buffer content={0},b; exr_fixed_document *d; exr_bitmap image;
  add(&content,"/S cs "); add(&content,components); add(&content," sc 0 0 8 8 re f q 8 0 0 8 10 0 cm /Im Do Q q 8 0 0 8 20 0 cm BI /W 1 /H 1 /BPC 8 /CS /S "); add(&content,dict ? dict : ""); add(&content," ID "); bytes(&content,samples,sample_size); add(&content,"\nEI Q"); label(&content);
  b=book(definition,&content,dict,samples,sample_size,icc,NULL); d=opened(&b); image=rendered(d); pixel(&image,4,4,expected,1); pixel(&image,14,4,expected,1); pixel(&image,24,4,expected,1);
  text(d); save(&b,directory,name); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); free(content.data);
}
static void calibrated(const char *directory) {
  static const unsigned gray188[]={188,188,188},gray129[]={129,129,129},gray119[]={119,119,119},rgb[]={188,137,225},red[]={255,0,0},white[]={255,255,255},black[]={0,0,0};
  scenario="CalGray linear luminance is encoded to sRGB"; same_color(CG,".5019607843137255",NULL,"\x80",1,NULL,gray188,directory,"pdf-color-calgray.pdf");
  scenario="CalGray gamma"; same_color(CG2,".5019607843137255",NULL,"\x80",1,NULL,gray129,NULL,NULL);
  scenario="CalRGB matrix column order and transfer"; same_color(CR,".5019607843137255 .2509803921568627 .7529411764705882",NULL,"\x80\x40\xc0",3,NULL,rgb,directory,"pdf-color-calrgb.pdf");
  scenario="CalRGB primaries"; same_color(CR,"1 0 0",NULL,"\xff\x00\x00",3,NULL,red,NULL,NULL);
  scenario="D50 Bradford white adaptation"; same_color("[/CalRGB << " D50 " /Matrix [.4360747 .2225045 .0139322 .3850649 .7168786 .0971045 .1430804 .0606169 .7141733] >>]",".5019607843137255 .2509803921568627 .7529411764705882",NULL,"\x80\x40\xc0",3,NULL,rgb,NULL,NULL);
  scenario="Lab default Decode uses L/a/b ranges"; same_color(LAB,"50.19607843137255 0 0",NULL,"\x80\x80\x80",3,NULL,gray119,directory,"pdf-color-lab.pdf");
  scenario="Lab D50 neutral and explicit Decode"; same_color("[/Lab << " D50 " /Range [-128 127 -128 127] >>]","50 0 0","/Decode [50 50 0 0 0 0]","\x00\x00\x00",3,NULL,gray119,NULL,NULL);
  scenario="CalGray diffuse black compensation"; same_color("[/CalGray << " D65 " /BlackPoint [.095047 .1 .108883] >>]",".55","/Decode [.55 .55]","\x00",1,NULL,gray188,NULL,NULL);
  scenario="CIE component clamping high"; same_color(CG,"2","/Decode [2 2]","\x00",1,NULL,white,NULL,NULL);
  scenario="CIE component clamping low"; same_color(CG,"-1","/Decode [-1 -1]","\x00",1,NULL,black,NULL,NULL);
}
static void indexed_icc(const char *directory) {
  static const unsigned gray188[]={188,188,188},gray119[]={119,119,119},gray128[]={128,128,128},rgb[]={128,64,192},white[]={255,255,255},black[]={0,0,0};
  scenario="Indexed CalGray palette and rounded vector index"; same_color("[/Indexed " CG " 2 9 0 R]",".7",NULL,"\x01",1,NULL,gray188,directory,"pdf-color-indexed.pdf");
  scenario="Indexed Lab table bytes scale to its ranges"; same_color("[/Indexed " LAB " 0 <808080>]","0",NULL,"\x00",1,NULL,gray119,NULL,NULL);
  scenario="Indexed ICC Alternate table"; same_color("[/Indexed [/ICCBased 6 0 R] 1 <0080>]","1",NULL,"\x01",1,"/N 1 /Alternate " CG,gray188,NULL,NULL);
  scenario="ICCBased absent Alternate chooses DeviceGray"; same_color("[/ICCBased 6 0 R]",".5019607843137255",NULL,"\x80",1,"/N 1",gray128,NULL,NULL);
  scenario="ICCBased absent Alternate chooses DeviceRGB"; same_color("[/ICCBased 6 0 R]",".5019607843137255 .2509803921568627 .7529411764705882",NULL,"\x80\x40\xc0",3,"/N 3",rgb,NULL,NULL);
  scenario="ICCBased explicit CalGray Alternate"; same_color("[/ICCBased 6 0 R]",".5019607843137255",NULL,"\x80",1,"/N 1 /Alternate " CG,gray188,directory,"pdf-color-icc-alternate.pdf");
  scenario="ICC Range is clipped before Alternate without rescaling"; same_color("[/ICCBased 6 0 R]","15",NULL,"\x80",1,"/N 1 /Range [10 20] /Alternate /DeviceGray",white,NULL,NULL);
  scenario="ICC negative Range clips in Alternate without rescaling"; same_color("[/ICCBased 6 0 R]","-1.5",NULL,"\x80",1,"/N 1 /Range [-2 -1] /Alternate /DeviceGray",black,NULL,NULL);
  scenario="ICC Lab Alternate retains its native component ranges"; same_color("[/ICCBased 6 0 R]","50.19607843137255 0 0",NULL,"\x80\x80\x80",3,"/N 3 /Range [0 100 -128 127 -128 127] /Alternate " LAB,gray119,NULL,NULL);
}
static void state_scopes(const char *directory) {
  buffer content={0},b; exr_fixed_document *d; exr_bitmap image; static const unsigned gray188[]={188,188,188},gray129[]={129,129,129},black[]={0,0,0},white[]={255,255,255};
  scenario="q/Q preserves source Indexed state and resets with direct colour"; add(&content,"/S cs 1 sc q 1 0 0 rg Q 2 sc 0 0 8 8 re f /S cs 10 0 8 8 re f "); label(&content); b=book("[/Indexed " CG " 2 9 0 R]",&content,NULL,"\x01",1,NULL,NULL); d=opened(&b); image=rendered(d); pixel(&image,4,4,white,0); pixel(&image,14,4,black,0); text(d); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); content.size=0;
  scenario="same colour space object resolves bases in each Form resource scope"; add(&content,"/S cs 0 sc 0 0 8 8 re f /Fm Do "); label(&content); b=book("10 0 R",&content,NULL,"\x00",1,NULL,"/S cs 0 sc 10 0 8 8 re f"); d=opened(&b); image=rendered(d); pixel(&image,4,4,gray188,1); pixel(&image,14,4,gray129,1); text(d); save(&b,directory,"pdf-color-form-scope.pdf"); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); content.size=0;
  scenario="ICC CMYK initial colour is all-zero white"; add(&content,"/S cs 0 0 8 8 re f /DeviceCMYK cs 10 0 8 8 re f "); label(&content); b=book("[/ICCBased 6 0 R]",&content,NULL,"\x00\x00\x00\x00",4,"/N 4",NULL); d=opened(&b); image=rendered(d); pixel(&image,4,4,white,0); pixel(&image,14,4,black,0); exr_bitmap_free(&image); exr_fixed_free(d); free(b.data); free(content.data);
}
static int cancelled(void *context) { (void)context; return 1; }
static void bad_cases(void) {
  static const char *bad[]={"[/CalGray << >>]","[/CalGray << /WhitePoint [0 1 1] >>]","[/CalGray << /WhitePoint [1 .5 1] >>]","[/CalGray << " D65 " /Gamma 0 >>]","[/CalGray << " D65 " /Gamma -1 >>]","[/CalGray << " D65 " /BlackPoint [-1 0 0] >>]","[/CalGray << " D65 " /BlackPoint [1 1 1] >>]","[/CalRGB << " D65 " /Gamma [1 1] >>]","[/CalRGB << " D65 " /Matrix [1 0 0] >>]","[/Lab << " D65 " /Range [1 -1 -2 2] >>]","[/Lab << " D65 " /Range [1 2 3] >>]","[/Indexed /DeviceRGB 256 <>]","[/Indexed /DeviceRGB 1 <00>]","[/Indexed [/Indexed /DeviceRGB 0 <000000>] 0 <00>]","[/ICCBased << /N 3 >>]","/S","[/Pattern]"};
  buffer c={0},b; exr_fixed_document *d; exr_bitmap image={0}; size_t i;
  add(&c,"/S cs 0 0 8 8 re f "); label(&c);
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) { scenario=bad[i]; b=book(bad[i],&c,NULL,"\x00",1,NULL,NULL); d=opened(&b); CHECK(exr_fixed_render(d,0,1,NULL,&image,&error)==EXR_FORMAT && !image.pixels); text(d); exr_fixed_free(d); free(b.data); }
  { const char *invalid[]={"/N 2","/N 1 /Range [1 0]","/N 3 /Range [0 1]","/N 1 /Alternate /DeviceRGB","/N 3 /Alternate [/ICCBased 6 0 R]"}; for(i=0;i<sizeof(invalid)/sizeof(*invalid);i++) { scenario=invalid[i]; b=book("[/ICCBased 6 0 R]",&c,NULL,"\x00",1,invalid[i],NULL); d=opened(&b); CHECK(exr_fixed_render(d,0,1,NULL,&image,&error)==EXR_FORMAT && !image.pixels); exr_fixed_free(d); free(b.data); } }
  scenario="cancellation before colour work"; b=book(CG,&c,NULL,"\x00",1,NULL,NULL); d=opened(&b); { exr_fixed_render_options options={0}; options.control.cancelled=cancelled; CHECK(exr_fixed_render(d,0,1,&options,&image,&error)==EXR_CANCELLED && !image.pixels); } exr_fixed_free(d); free(b.data);
  free(c.data);
}
int main(int argc,char **argv) { const char *directory=argc>1 ? argv[1] : NULL; scenario="start"; calibrated(directory); indexed_icc(directory); state_scopes(directory); bad_cases(); printf("%u native PDF source colour-space checks passed\n",checks); return 0; }
