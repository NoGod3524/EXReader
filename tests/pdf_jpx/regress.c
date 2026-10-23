/* SPDX-License-Identifier: MIT */
#include "base_internal.h"
#include "pdf_jpx_internal.h"
#include <openjpeg.h>
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>

#ifdef EXR_JPX_STANDALONE
exr_status exr_fail(exr_error *e,exr_status code,const char *fmt,...) {
  va_list ap;if(e) { e->code=code;va_start(ap,fmt);vsnprintf(e->message,sizeof(e->message),fmt,ap);va_end(ap); }return code;
}
exr_status exr_control_cancel(const exr_control *c,exr_error *e) {
  return c && c->cancelled && c->cancelled(c->context) ? exr_fail(e,EXR_CANCELLED,"cancelled") : EXR_OK;
}
#endif
static int cancel(void *p) { int *n=(int *)p;return --*n<=0; }
static unsigned sample(unsigned i,unsigned c,unsigned bits) { return (i*37+c*19)&((1u<<bits)-1); }
static unsigned char *load(const char *path,size_t *size) {
  FILE *f=fopen(path,"rb");long n;unsigned char *p;
  assert(f && !fseek(f,0,SEEK_END));n=ftell(f);assert(n>0 && !fseek(f,0,SEEK_SET));
  p=(unsigned char *)malloc((size_t)n);assert(p && fread(p,1,(size_t)n,f)==(size_t)n);fclose(f);*size=(size_t)n;return p;
}
static unsigned char *encode_size(const char *path,unsigned width,unsigned height,unsigned bits,unsigned count,int raw,int signed_sample,int subsample,size_t *size) {
  opj_image_cmptparm_t comp[4];opj_cparameters_t params;
  opj_codec_t *codec;opj_stream_t *stream;opj_image_t *image;unsigned c,i;
  memset(comp,0,sizeof(comp));
  for(c=0;c<count;c++) { comp[c].dx=subsample ? 2 : 1;comp[c].dy=1;comp[c].w=subsample ? (width+1)/2 : width;comp[c].h=height;comp[c].prec=bits;comp[c].sgnd=signed_sample; }
  image=opj_image_create(count,comp,count==1 ? OPJ_CLRSPC_GRAY : OPJ_CLRSPC_SRGB);assert(image);image->x1=width;image->y1=height;
  for(c=0;c<count;c++) {
    uint32_t noise=1234567+c;
    for(i=0;i<comp[c].w*height;i++) {
      noise^=noise<<13;noise^=noise>>17;noise^=noise<<5;
      image->comps[c].data[i]=(OPJ_INT32)((width>7 ? noise&((1u<<bits)-1) : sample(i,c,bits))>>(signed_sample ? 1 : 0));
    }
  }
  opj_set_default_encoder_parameters(&params);params.tcp_numlayers=1;params.cp_disto_alloc=1;params.tcp_rates[0]=0;params.numresolution=1;params.tcp_mct=0;
  codec=opj_create_compress(raw ? OPJ_CODEC_J2K : OPJ_CODEC_JP2);assert(codec && opj_setup_encoder(codec,&params,image));
  stream=opj_stream_create_default_file_stream(path,OPJ_FALSE);assert(stream);
  assert(opj_start_compress(codec,image,stream) && opj_encode(codec,stream) && opj_end_compress(codec,stream));
  opj_stream_destroy(stream);opj_destroy_codec(codec);opj_image_destroy(image);return load(path,size);
}
static unsigned char *encode(const char *path,unsigned bits,unsigned count,int raw,int signed_sample,int subsample,size_t *size) {
  return encode_size(path,7,3,bits,count,raw,signed_sample,subsample,size);
}
static void rejected(const unsigned char *p,size_t n,unsigned w,unsigned h,unsigned c,unsigned b,int indexed,const exr_control *control,exr_status expected) {
  unsigned char *out=(unsigned char *)1;size_t size=123;exr_error e={0};
  exr_status s=exr_pdf_jpx_decode(p,n,w,h,c,b,indexed,control,&out,&size,&e);
  assert(s!=EXR_OK && !out && !size);if(expected!=EXR_OK) assert(s==expected);
}
int main(int argc,char **argv) {
  unsigned bits_list[]={1,2,4,8,16};unsigned b,c,raw;
  if(argc==8) {
    size_t n,size;unsigned char *p=load(argv[1],&n),*out=NULL;exr_error e={0};FILE *f;
    exr_status s=exr_pdf_jpx_decode(p,n,(unsigned)atoi(argv[2]),(unsigned)atoi(argv[3]),(unsigned)atoi(argv[4]),(unsigned)atoi(argv[5]),atoi(argv[6]),NULL,&out,&size,&e);
    if(s!=EXR_OK) { fprintf(stderr,"decode %d: %s\n",s,e.message);free(p);return 1; }
    f=fopen(argv[7],"wb");assert(f && fwrite(out,1,size,f)==size);fclose(f);free(out);free(p);return 0;
  }
  for(b=0;b<5;b++) for(c=1;c<=3;c+=2) for(raw=0;raw<2;raw++) {
    unsigned bits=bits_list[b];char path[80];size_t n,size,row=((size_t)7*c*bits+7)/8;unsigned char *p,*out=NULL;exr_error e={0};unsigned x,y,k;
    snprintf(path,sizeof(path),"jpx-%u-%u.%s",bits,c,raw ? "j2k" : "jp2");p=encode(path,bits,c,raw,0,0,&n);
    assert(exr_pdf_jpx_decode(p,n,7,3,c,bits,c==1,NULL,&out,&size,&e)==EXR_OK && size==row*3);
    for(y=0;y<3;y++) {
      size_t at=y*row*8;
      for(x=0;x<7;x++) for(k=0;k<c;k++) { unsigned v=0,z;for(z=0;z<bits;z++,at++) v=v*2+((out[at>>3]>>(7-(at&7)))&1);assert(v==sample(y*7+x,k,bits)); }
      while(at<(y+1)*row*8) { assert(!(out[at>>3]&(1u<<(7-(at&7)))));at++; }
    }
    free(out);
    rejected(p,n,8,3,c,bits,c==1,NULL,EXR_FORMAT);
    rejected(p,n/2,7,3,c,bits,c==1,NULL,EXR_FORMAT);
    rejected(p,n-2,7,3,c,bits,c==1,NULL,EXR_FORMAT);
    rejected(p,n,8192,8192,32,16,0,NULL,EXR_LIMIT);
    { int remaining=1;exr_control control={cancel,NULL,&remaining};rejected(p,n,7,3,c,bits,c==1,&control,EXR_CANCELLED); }
    free(p);
  }
  { size_t n;unsigned char *p=encode("signed.jp2",8,1,0,1,0,&n);rejected(p,n,7,3,1,8,0,NULL,EXR_UNSUPPORTED);free(p); }
  { size_t n;unsigned char *p=encode("subsample.jp2",8,1,0,0,1,&n);rejected(p,n,7,3,1,8,0,NULL,EXR_UNSUPPORTED);free(p); }
  { unsigned char p[]={1,2,3,4};rejected(p,sizeof(p),7,3,1,8,0,NULL,EXR_FORMAT); }
  {
    static const unsigned char cdef[]={0,0,0,8,'c','d','e','f'};
    size_t n;unsigned char *p=encode("metadata.jp2",8,1,0,0,0,&n),*extended=(unsigned char *)malloc(n+sizeof(cdef));
    assert(extended);memcpy(extended,p,n);memcpy(extended+n,cdef,sizeof(cdef));
    rejected(extended,n+sizeof(cdef),7,3,1,8,0,NULL,EXR_UNSUPPORTED);
    extended[n+4]='p';extended[n+5]='c';extended[n+6]='l';extended[n+7]='r';
    rejected(extended,n+sizeof(cdef),7,3,1,8,0,NULL,EXR_UNSUPPORTED);free(extended);free(p);
  }
  {
    size_t n;int remaining=3;exr_control control={cancel,NULL,&remaining};
    unsigned char *p=encode_size("cancel.j2k",257,257,8,1,1,0,0,&n);
    assert(n>4096);rejected(p,n,257,257,1,8,0,&control,EXR_CANCELLED);assert(remaining<=0);free(p);
  }
  puts("JPX packed samples: JP2/J2K 1/2/4/8/16-bit Gray/RGB; malformed, truncated, dimensions, budget, cancellation, signed and subsampling passed");return 0;
}
