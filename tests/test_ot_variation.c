/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks;
static exr_error error;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while (0)
#define OK(x) CHECK((x)==EXR_OK)
static unsigned read16(const unsigned char *p) { return ((unsigned)p[0]<<8)|p[1]; }
static void put16(unsigned char *p,unsigned value) { p[0]=(unsigned char)(value>>8); p[1]=(unsigned char)value; }
static void put32(unsigned char *p,uint32_t value) { put16(p,value>>16); put16(p+2,value); }
static unsigned char *original;
static size_t original_size;
static void load(const char *directory) {
  char path[4096]; FILE *file; long length;
  snprintf(path,sizeof(path),"%s/variable.ttf",directory); file=fopen(path,"rb"); CHECK(file);
  CHECK(!fseek(file,0,SEEK_END)); length=ftell(file); CHECK(length>0); rewind(file);
  original_size=(size_t)length; original=malloc(original_size); CHECK(original);
  CHECK(fread(original,1,original_size,file)==original_size && !fclose(file));
}
static void replace_table(exr_font_input *input,uint32_t tag,const unsigned char *bytes,size_t size) {
  size_t i,offset=(input->size+3)&~(size_t)3;
  unsigned char *p=realloc((void *)input->data,offset+size); CHECK(p);
  memset(p+input->size,0,offset-input->size); memcpy(p+offset,bytes,size);
  input->data=p; input->size=offset+size;
  for (i=0;i<read16(p+4);i++) {
    unsigned char *record=p+12+i*16;
    if (record[0]==(unsigned char)(tag>>24) && record[1]==(unsigned char)(tag>>16) &&
        record[2]==(unsigned char)(tag>>8) && record[3]==(unsigned char)tag) {
      put32(record+8,(uint32_t)offset); put32(record+12,(uint32_t)size); return;
    }
  }
  CHECK(0);
}
static exr_font *font_with(const unsigned char *gdef,size_t gdef_size,
                           const unsigned char *gpos,size_t gpos_size,
                           const unsigned char *gsub,size_t gsub_size,double weight) {
  exr_font_input input={0}; exr_font_coordinate axis={0,EXR_TAG('w','g','h','t'),weight}; exr_font *font=NULL;
  input.data=malloc(original_size); CHECK(input.data); memcpy((void *)input.data,original,original_size); input.size=original_size;
  if (gdef) replace_table(&input,EXR_TAG('G','D','E','F'),gdef,gdef_size);
  if (gpos) replace_table(&input,EXR_TAG('G','P','O','S'),gpos,gpos_size);
  if (gsub) replace_table(&input,EXR_TAG('G','S','U','B'),gsub,gsub_size);
  OK(exr_font_create_variable(&input,1,&axis,1,&font,&error)); free((void *)input.data); CHECK(font); return font;
}
static void expect(exr_font *font,int rvrn,exr_status status,unsigned glyph,float advance) {
  exr_shape_options options=exr_shape_defaults(); exr_shape_feature feature={EXR_TAG('r','v','r','n'),(uint32_t)rvrn};
  exr_shaped_glyph *out=(exr_shaped_glyph *)(uintptr_t)1; size_t count=99;
  options.font_size=100;
  if (rvrn>=0) { options.features=&feature; options.feature_count=1; }
  CHECK(exr_shape(font,0,"A",1,&options,&out,&count,&error)==status);
  if (status==EXR_OK) { CHECK(count==1 && out && out[0].glyph==glyph); CHECK(isfinite(out[0].advance_x) && fabsf(out[0].advance_x-advance)<.03f); }
  else CHECK(!out && !count && error.code==status);
  exr_free(out); exr_font_free(font);
}
/* A single xAdvance VariationIndex in an otherwise ordinary GPOS table. */
static void positioning(unsigned char p[78],unsigned outer,unsigned inner) {
  memset(p,0,78); put16(p,1); put16(p+4,10); put16(p+6,30); put16(p+8,44);
  put16(p+10,1); put32(p+12,EXR_TAG('D','F','L','T')); put16(p+16,8);
  put16(p+18,4); put16(p+24,0xffff); put16(p+26,1);
  put16(p+30,1); put32(p+32,EXR_TAG('k','e','r','n')); put16(p+36,8); put16(p+40,1);
  put16(p+44,1); put16(p+46,4); put16(p+48,1); put16(p+52,1); put16(p+54,8);
  put16(p+56,1); put16(p+58,10); put16(p+60,0x44); put16(p+64,16);
  put16(p+66,1); put16(p+68,1); put16(p+70,2);
  put16(p+72,outer); put16(p+74,inner); put16(p+76,0x8000);
}
/* Two equal wght support regions, two rows, mixed signed delta widths. */
static size_t store(unsigned char g[100],int long_words) {
  unsigned char *s=g+18,*r=s+12,*d=s+40;
  memset(g,0,100); put16(g,1); put16(g+2,3); put32(g+14,18);
  put16(s,1); put32(s+2,12); put16(s+6,1); put32(s+8,40);
  put16(r,2); put16(r+2,2); put16(r+6,16384); put16(r+8,16384); put16(r+18,16384); put16(r+20,16384);
  put16(d,2); put16(d+2,long_words ? 0x8001 : 1); put16(d+4,2); put16(d+8,1);
  if (long_words) {
    put32(d+10,40000); put16(d+14,(unsigned)-30000);
    put32(d+16,(uint32_t)-70000); put16(d+20,20000); return 80;
  }
  put16(d+10,(unsigned)-200); d[12]=100; put16(d+13,300); d[15]=(unsigned char)-100; return 74;
}
static void stores(void) {
  unsigned char g[100],p[78]; size_t size=store(g,1);
  positioning(p,0,0); expect(font_with(g,size,p,sizeof(p),NULL,0,900),0,EXR_OK,2,1055);
  positioning(p,0,1); expect(font_with(g,size,p,sizeof(p),NULL,0,900),0,EXR_OK,2,-4945);
  /* At the default position every support scalar is zero. */
  expect(font_with(g,size,p,sizeof(p),NULL,0,400),0,EXR_OK,2,50);
  positioning(p,0xffff,0xffff); expect(font_with(g,size,p,sizeof(p),NULL,0,900),0,EXR_OK,2,55);
  size=store(g,0); positioning(p,0,0); expect(font_with(g,size,p,sizeof(p),NULL,0,900),0,EXR_OK,2,45);
  positioning(p,0,1); expect(font_with(g,size,p,sizeof(p),NULL,0,900),0,EXR_OK,2,75);
  positioning(p,1,0); expect(font_with(g,size,p,sizeof(p),NULL,0,900),0,EXR_FONT,0,0);
  positioning(p,0,2); expect(font_with(g,size,p,sizeof(p),NULL,0,900),0,EXR_FONT,0,0);
  positioning(p,0,0); put16(g+64,2); expect(font_with(g,size,p,sizeof(p),NULL,0,900),0,EXR_FONT,0,0);
  store(g,0); put16(g+60,3); expect(font_with(g,size,p,sizeof(p),NULL,0,900),0,EXR_FONT,0,0);
  store(g,0); put32(g+20,1000); expect(font_with(g,size,p,sizeof(p),NULL,0,900),0,EXR_FONT,0,0);
  store(g,1); expect(font_with(g,79,p,sizeof(p),NULL,0,900),0,EXR_FONT,0,0);
}
/* Build two matching variation records. Each replaces one empty feature with
   a different lookup; the first match must win. GSUB lookup zero maps A->alt
   and alt->V so an accidentally repeated rvrn stage is observable. */
static size_t conditional(unsigned char t[256],int position) {
  size_t lookup=46,lookup_size=position ? 22 : 26;
  size_t fv=lookup+6+lookup_size*2,i;
  unsigned char *v=t+fv;
  memset(t,0,256); put16(t,1); put16(t+2,1); put16(t+4,14); put16(t+6,34); put16(t+8,(unsigned)lookup); put32(t+10,(uint32_t)fv);
  put16(t+14,1); put32(t+16,EXR_TAG('D','F','L','T')); put16(t+20,8);
  put16(t+22,4); put16(t+28,0xffff); put16(t+30,1);
  put16(t+34,1); put32(t+36,position ? EXR_TAG('k','e','r','n') : EXR_TAG('r','v','r','n')); put16(t+40,8);
  put16(t+lookup,2); put16(t+lookup+2,6); put16(t+lookup+4,(unsigned)(6+lookup_size));
  for (i=0;i<2;i++) {
    unsigned char *l=t+lookup+6+i*lookup_size,*sub=l+8;
    put16(l,1); put16(l+4,1); put16(l+6,8);
    if (position) {
      put16(sub,1); put16(sub+2,8); put16(sub+4,4); put16(sub+6,(unsigned)(5+i*5));
      put16(sub+8,1); put16(sub+10,1); put16(sub+12,2);
    } else {
      put16(sub,2); put16(sub+2,10); put16(sub+4,2); put16(sub+6,(unsigned)(i ? 3 : 4)); put16(sub+8,3);
      put16(sub+10,1); put16(sub+12,2); put16(sub+14,2); put16(sub+16,4);
    }
  }
  put16(v,1); put32(v+4,2); put32(v+8,24); put32(v+12,52); put32(v+16,38); put32(v+20,70);
  for (i=0;i<2;i++) {
    unsigned char *c=v+24+i*14,*s=v+52+i*18;
    put16(c,1); put32(c+2,6); put16(c+6,1); put16(c+10,8192); put16(c+12,16384);
    put16(s,1); put16(s+4,1); put32(s+8,12); put16(s+14,1); put16(s+16,(unsigned)i);
  }
  return fv+88;
}
static void conditions(void) {
  unsigned char t[256]; size_t size=conditional(t,0),fv=104;
  expect(font_with(NULL,0,NULL,0,t,size,900),-1,EXR_OK,4,55);
  expect(font_with(NULL,0,NULL,0,t,size,900),1,EXR_OK,4,55);
  expect(font_with(NULL,0,NULL,0,t,size,900),0,EXR_OK,2,55);
  expect(font_with(NULL,0,NULL,0,t,size,400),-1,EXR_OK,2,50);
  put16(t+fv+32,2); expect(font_with(NULL,0,NULL,0,t,size,900),-1,EXR_FONT,0,0);
  conditional(t,0); put32(t+fv+60,1000); expect(font_with(NULL,0,NULL,0,t,size,900),-1,EXR_FONT,0,0);
  conditional(t,0); put16(t+fv+58,1); expect(font_with(NULL,0,NULL,0,t,size,900),-1,EXR_FONT,0,0);
  conditional(t,0); put16(t+fv+34,16384); put16(t+fv+36,8192); expect(font_with(NULL,0,NULL,0,t,size,900),-1,EXR_FONT,0,0);
  conditional(t,0); put16(t+fv+30,99); expect(font_with(NULL,0,NULL,0,t,size,900),-1,EXR_OK,3,55);
  /* A NULL condition set matches unconditionally, including default axes. */
  conditional(t,0); put32(t+fv+8,0); expect(font_with(NULL,0,NULL,0,t,size,400),-1,EXR_OK,4,50);
  conditional(t,0); put32(t+fv+12,0); expect(font_with(NULL,0,NULL,0,t,size,900),-1,EXR_OK,2,55);
  /* Required rvrn is still applied exactly once, before the normal stages. */
  conditional(t,0); put16(t+28,0); put16(t+30,0); expect(font_with(NULL,0,NULL,0,t,size,900),0,EXR_OK,4,55);
  /* GPOS uses the same first-match feature selection independently of GSUB. */
  size=conditional(t,1); expect(font_with(NULL,0,t,size,NULL,0,900),0,EXR_OK,2,55.5f);
  expect(font_with(NULL,0,t,size,NULL,0,400),0,EXR_OK,2,50);
  put32(t+10,1000); expect(font_with(NULL,0,t,size,NULL,0,900),0,EXR_FONT,0,0);
}
int main(int argc,char **argv) {
  CHECK(argc==2); load(argv[1]); stores(); conditions(); free(original);
  printf("OpenType variation checks: %u\n",checks); return 0;
}
