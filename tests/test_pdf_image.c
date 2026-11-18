/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include "../src/pdf_raster_internal.h"
#include "cmyk_reference.h"
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static unsigned char *load(const char *dir,const char *name,size_t *size) {
  char path[4096]; FILE *f; long n; unsigned char *data;
  snprintf(path,sizeof(path),"%s/%s",dir,name); f=fopen(path,"rb"); CHECK(f && !fseek(f,0,SEEK_END)); n=ftell(f); CHECK(n>0); rewind(f);
  *size=(size_t)n; data=malloc(*size); CHECK(data && fread(data,1,*size,f)==*size); fclose(f); return data;
}
static uint32_t resources(exr_pdf_file *file) { uint32_t id; OK(exr_pdf_resolve(file,exr_pdf_get(file,exr_pdf_root(file),"Resources"),&id,&error)); return id; }
static uint32_t image(exr_pdf_file *file,const char *name) { uint32_t dict; OK(exr_pdf_resolve(file,exr_pdf_get(file,resources(file),"XObject"),&dict,&error)); return exr_pdf_get(file,dict,name); }
static void pixel(const exr_bitmap *b,unsigned x,unsigned y,unsigned red,unsigned green,unsigned blue,unsigned alpha) {
  const unsigned char *p=b->pixels+(size_t)y*b->stride+x*4; if(p[0]!=red || p[1]!=green || p[2]!=blue || p[3]!=alpha) fprintf(stderr,"image pixel got %u,%u,%u,%u expected %u,%u,%u,%u\n",p[0],p[1],p[2],p[3],red,green,blue,alpha);CHECK(p[0]==red && p[1]==green && p[2]==blue && p[3]==alpha);
}
static exr_bitmap decode(exr_pdf_file *file,const char *name) {
  exr_bitmap b={0}; int interpolate=0; OK(exr_pdf_image_decode(file,image(file,name),resources(file),0x0000ffff,&b,&interpolate,NULL,NULL,&error)); CHECK(!interpolate); return b;
}
static exr_bitmap render(exr_pdf_file *file,const char *content) {
  exr_pdf_raster_config c={0}; exr_bitmap b={0}; c.width=c.height=8; c.channels=4; c.background=0xffffffff;
  OK(exr_pdf_raster_content(file,resources(file),content,strlen(content),NULL,&c,NULL,&b,&error)); return b;
}
static void decoded(exr_pdf_file *file) {
  exr_bitmap b=decode(file,"RGB"); CHECK(b.width==2 && b.height==2); pixel(&b,0,0,255,0,0,255); pixel(&b,1,0,0,255,0,255); pixel(&b,0,1,0,0,255,255); free(b.pixels);
  b=decode(file,"Gray"); pixel(&b,0,0,255,255,255,255); pixel(&b,1,0,0,0,0,255); free(b.pixels);
  b=decode(file,"Gray16"); pixel(&b,0,0,0,0,0,255); pixel(&b,1,0,255,255,255,255); free(b.pixels);
  b=decode(file,"RGB4"); pixel(&b,0,0,255,0,136,255); free(b.pixels);
  b=decode(file,"CMYK2"); { unsigned rgb[3];cmyk_reference((const double[4]){0,1,0,0},rgb);pixel(&b,0,0,rgb[0],rgb[1],rgb[2],255); } free(b.pixels);
  b=decode(file,"Stencil"); pixel(&b,0,0,0,0,255,255); pixel(&b,1,0,0,0,255,0); free(b.pixels);
  b=decode(file,"Rows1"); pixel(&b,0,0,255,255,255,255); pixel(&b,1,0,0,0,0,255); pixel(&b,1,1,255,255,255,255); pixel(&b,0,1,0,0,0,255); free(b.pixels);
  b=decode(file,"Alias"); pixel(&b,0,0,255,0,0,255); free(b.pixels);
  b=decode(file,"Indexed"); pixel(&b,0,0,255,0,0,255); pixel(&b,1,0,0,255,0,255); pixel(&b,2,0,0,0,255,255); pixel(&b,3,0,0,0,255,255); free(b.pixels);
  b=decode(file,"IndexedReverse"); pixel(&b,0,0,0,0,255,255); pixel(&b,2,0,0,255,0,255); pixel(&b,3,0,255,0,0,255); free(b.pixels);
  b=decode(file,"PaletteStream"); pixel(&b,0,0,0,0,0,255); pixel(&b,1,0,255,255,255,255); free(b.pixels);
  b=decode(file,"Key"); pixel(&b,0,0,255,0,0,0); pixel(&b,1,0,0,255,0,255); free(b.pixels);
  b=decode(file,"IndexKey"); pixel(&b,0,0,0,0,255,255); pixel(&b,1,0,0,0,255,0); pixel(&b,3,0,255,0,0,255); free(b.pixels);
  b=decode(file,"Explicit"); pixel(&b,0,0,255,0,0,255); pixel(&b,1,0,0,0,0,0); pixel(&b,0,1,0,0,255,255); free(b.pixels);
  b=decode(file,"Soft"); pixel(&b,0,0,255,0,0,128); pixel(&b,1,0,0,255,0,128); free(b.pixels);
  b=decode(file,"SoftInterp"); pixel(&b,0,0,0,0,0,0); pixel(&b,1,0,255,0,0,64); pixel(&b,2,0,255,0,0,191); pixel(&b,3,0,255,0,0,255); free(b.pixels);
  b=decode(file,"Matte"); pixel(&b,0,0,255,0,0,128); free(b.pixels);
  b=decode(file,"SoftInvert"); pixel(&b,0,0,255,0,0,255); pixel(&b,1,0,0,0,0,0); free(b.pixels);
  b=decode(file,"GrayMatte"); pixel(&b,0,0,255,255,255,128); free(b.pixels);
}
static void rasterized(exr_pdf_file *file) {
  exr_bitmap b=render(file,"4 0 0 4 0 0 cm /RGB Do"); pixel(&b,0,3,255,0,0,255); pixel(&b,3,3,0,255,0,255); pixel(&b,0,0,0,0,255,255); pixel(&b,6,6,255,255,255,255); free(b.pixels);
  b=render(file,"0 0 1 rg 4 0 0 2 0 0 cm /Stencil Do"); pixel(&b,0,0,0,0,255,255); pixel(&b,3,0,255,255,255,255); free(b.pixels);
  b=render(file,"0 0 1 4 re W n 4 0 0 4 0 0 cm /RGB Do"); pixel(&b,0,3,255,0,0,255); pixel(&b,3,3,255,255,255,255); free(b.pixels);
  b=render(file,"/Form Do"); pixel(&b,1,1,0,0,0,255); pixel(&b,5,5,255,255,255,255); free(b.pixels);
  b=render(file,"4 0 0 4 0 0 cm /Soft Do"); pixel(&b,0,3,255,127,127,255); pixel(&b,3,3,127,255,127,255); free(b.pixels);
  b=render(file,"4 0 0 4 0 0 cm /Explicit Do"); pixel(&b,0,3,255,0,0,255); pixel(&b,3,3,255,255,255,255); free(b.pixels);
  b=render(file,"8 0 0 2 0 0 cm /HighMask Do"); pixel(&b,0,0,255,255,255,255); pixel(&b,2,0,255,170,170,255); pixel(&b,4,0,255,85,85,255); pixel(&b,6,0,255,0,0,255); free(b.pixels);
}
static int cancel(void *context) { (void)context; return 1; }
static void affine(void) {
  unsigned char pixels[16]={255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,255},target[256],mask[64];
  exr_bitmap src={0},dst={0},clip={0}; double matrix[6]={4,0,0,4,0,0}; size_t work=0;
  src.width=src.height=2; src.channels=4; src.stride=8; src.pixels=pixels;
  dst.width=dst.height=8; dst.channels=4; dst.stride=32; dst.pixels=target;
  clip.width=clip.height=clip.stride=8; clip.channels=1; clip.pixels=mask; memset(mask,128,64);
  memset(target,255,sizeof(target)); OK(exr_vector_image(&dst,&src,matrix,.5,0,&clip,&work,NULL,&error)); pixel(&dst,0,0,255,191,191,255);
  memset(target,0,sizeof(target)); OK(exr_vector_image(&dst,&src,matrix,1,1,NULL,&work,NULL,&error)); pixel(&dst,0,0,255,0,0,255); CHECK(target[1*32+1*4]>target[1*32+1*4+1]);
  matrix[0]=0; matrix[1]=4; matrix[2]=-4; matrix[3]=0; matrix[4]=4;
  memset(target,255,sizeof(target)); OK(exr_vector_image(&dst,&src,matrix,1,0,NULL,&work,NULL,&error)); pixel(&dst,3,0,255,0,0,255); pixel(&dst,0,0,0,0,255,255);
  CHECK(exr_vector_image(&dst,&dst,matrix,1,0,NULL,NULL,NULL,&error)==EXR_ARGUMENT);
  matrix[0]=NAN; CHECK(exr_vector_image(&dst,&src,matrix,1,0,NULL,NULL,NULL,&error)==EXR_ARGUMENT); matrix[0]=0;
  work=(size_t)256*1024*1024; CHECK(exr_vector_image(&dst,&src,matrix,1,0,NULL,&work,NULL,&error)==EXR_LIMIT);
  { exr_control control={0}; control.cancelled=cancel; CHECK(exr_vector_image(&dst,&src,matrix,1,0,NULL,NULL,&control,&error)==EXR_CANCELLED); }
  /* A transparent red neighbor must not tint bilinear sampling of blue. */
  src.width=2; src.height=1; src.stride=8; pixels[3]=0; pixels[4]=0; pixels[5]=0; pixels[6]=255; pixels[7]=255;
  matrix[0]=4; matrix[1]=matrix[2]=0; matrix[3]=4; matrix[4]=0; memset(target,0,sizeof(target));
  OK(exr_vector_image(&dst,&src,matrix,1,1,NULL,NULL,NULL,&error)); CHECK(target[1*4]==0 && target[1*4+2]==255 && target[1*4+3]>0);
  { unsigned char red[4]={255,0,0,255},alphas[16]={0,0,0,255,85,85,85,255,170,170,170,255,255,255,255,255};
    exr_vector_texture color={0},opacity={0};
    color.bitmap.width=color.bitmap.height=1; color.bitmap.channels=color.bitmap.stride=4; color.bitmap.pixels=red;
    opacity.bitmap.width=4; opacity.bitmap.height=1; opacity.bitmap.channels=4; opacity.bitmap.stride=16; opacity.bitmap.pixels=alphas;
    color.mask=&opacity; color.mask_mode=1; matrix[0]=8; matrix[3]=2; memset(target,255,sizeof(target));
    OK(exr_vector_texture_paint(&dst,&color,matrix,1,NULL,NULL,NULL,&error)); pixel(&dst,2,0,255,170,170,255); pixel(&dst,6,0,255,0,0,255);
    color.has_matte=1; color.matte[0]=NAN; CHECK(exr_vector_texture_paint(&dst,&color,matrix,1,NULL,NULL,NULL,&error)==EXR_ARGUMENT);
    color.has_matte=0; color.mask=&color; CHECK(exr_vector_texture_paint(&dst,&color,matrix,1,NULL,NULL,NULL,&error)==EXR_ARGUMENT);
    color.mask=&opacity; opacity.bitmap=dst; CHECK(exr_vector_texture_paint(&dst,&color,matrix,1,NULL,NULL,NULL,&error)==EXR_ARGUMENT);
  }
  { unsigned char colors[16],masks[16],white[4]={255,255,255,255},reference[256],initial[256];unsigned trial,i;
    exr_vector_texture color={0},opacity={0},unit={0};exr_bitmap other=dst;
    color.bitmap=src;color.bitmap.width=color.bitmap.height=2;color.bitmap.stride=8;color.bitmap.pixels=colors;
    opacity.bitmap=color.bitmap;opacity.bitmap.pixels=masks;color.mask=&opacity;
    unit.bitmap=color.bitmap;unit.bitmap.width=unit.bitmap.height=1;unit.bitmap.stride=4;unit.bitmap.pixels=white;
    other.pixels=reference;matrix[0]=6.5;matrix[1]=.3;matrix[2]=.25;matrix[3]=6.8;matrix[4]=-.2;matrix[5]=.1;
    for(trial=0;trial<64;trial++) {
      double alpha=trial<32 ? .63 : 1;
      for(i=0;i<16;i++) { colors[i]=(unsigned char)(i*29+trial*17);masks[i]=(unsigned char)(i*41+trial*11); }
      for(i=0;i<256;i++) initial[i]=(unsigned char)(i*13+trial);
      color.mask_mode=trial&1 ? 1 : 2;
      if(trial>=32) {
        /* Constant opaque color and a varying soft mask with fractional
           edges, horizontal/vertical reflection and partially covered pixels. */
        matrix[0]=trial&1 ? -6.5 : 6.5; matrix[4]=trial&1 ? 6.3 : -.2;
        matrix[3]=trial&4 ? -6.8 : 6.8; matrix[5]=trial&4 ? 6.9 : .1;
        matrix[1]=matrix[2]=0; colors[3]=255; color.mask_mode=1;
        for(i=4;i<16;i+=4) memcpy(colors+i,colors,4);
        for(i=3;i<16;i+=4) masks[i]=255;
        for(i=0;i<64;i++) mask[i]=(unsigned char)(i*17);
      }
      memcpy(target,initial,256);memcpy(reference,initial,256);
      opacity.mask=NULL;
      OK(exr_vector_texture_paint(&dst,&color,matrix,alpha,trial&2 ? &clip : NULL,NULL,NULL,&error));
      /* An opaque identity child forces the generic sampler without changing
         the mask samples, providing an independent path for comparison. */
      opacity.mask=&unit;opacity.mask_mode=2;
      OK(exr_vector_texture_paint(&other,&color,matrix,alpha,trial&2 ? &clip : NULL,NULL,NULL,&error));
      CHECK(!memcmp(target,reference,256));
    }
  }
  /* Axis-aligned unmasked nearest images take a tabulated fast path. An opaque
     unit mask multiplies every sample by exactly 1 and forces the generic
     sampler, so both renders must match byte for byte: flipped and fractional
     scales, partly off-target placement, transparent texels and destinations,
     varied clip coverage, constant alpha and a separable blend mode. */
  { /* {4,4,-.75,-.75} puts samples exactly on the far image edge, u=v=1. */
    static const double placements[][4]={{4,4,0,0},{-3.5,2.25,7.9,-.3},{1.7,-5.2,.4,7.6},{.6,.45,1.2,2.6},{9,9,-.5,-.5},{4,4,-.75,-.75}};
    unsigned char colors[48],white[4]={255,255,255,255},reference[256],initial[256];unsigned trial,i;
    exr_vector_texture color={0},unit={0};exr_bitmap other=dst;
    color.bitmap.width=4;color.bitmap.height=3;color.bitmap.channels=4;color.bitmap.stride=16;color.bitmap.pixels=colors;
    unit.bitmap.width=unit.bitmap.height=1;unit.bitmap.channels=unit.bitmap.stride=4;unit.bitmap.pixels=white;
    other.pixels=reference;
    for(i=0;i<64;i++) mask[i]=(unsigned char)(i*53);
    for(trial=0;trial<48;trial++) {
      const double *p=placements[trial%6],m[6]={p[0],0,0,p[1],p[2],p[3]};const exr_bitmap *cover=(trial/6)&4 ? NULL : &clip;
      double alpha=(trial/6)&1 ? 1 : .63;exr_blend_mode mode=(trial/6)&2 ? EXR_BLEND_MULTIPLY : EXR_BLEND_NORMAL;
      for(i=0;i<48;i++) colors[i]=(unsigned char)(i*37+trial*23);
      colors[3]=0;colors[7]=255;
      for(i=0;i<256;i++) initial[i]=(unsigned char)(i*13+trial);
      for(i=3;i<256;i+=12) initial[i]=0;
      memcpy(target,initial,256);memcpy(reference,initial,256);
      color.mask=NULL;
      OK(exr_vector_texture_blend(&dst,&color,m,alpha,cover,mode,NULL,NULL,NULL,&error));
      color.mask=&unit;color.mask_mode=2;
      OK(exr_vector_texture_blend(&other,&color,m,alpha,cover,mode,NULL,NULL,NULL,&error));
      CHECK(memcmp(target,initial,256) && !memcmp(target,reference,256));
    }
  }
  /* Axis-aligned interpolated images, unmasked or with an image soft mask,
     take the converted-row axis path. A nested opaque unit mask forces the
     generic sampler and scales by exactly 1, so both renders must match byte
     for byte: up- and downscales, flips, fractional and off-target placement,
     mask grids unlike the image's, nearest and interpolated masks, both mask
     modes, transparent texels and destinations, clip coverage and alpha. */
  { static const double placements[][4]={{24,20,0,0},{-17.5,9.25,20.9,-.3},{6.7,-21.2,3.4,19.6},{30.5,26,-3.1,-2.7},{3.3,2.9,10.2,8.6},{11,13,-.5,6.25}};
    static const unsigned sizes[][4]={{5,4,5,4},{7,3,4,6},{9,8,3,2},{2,2,6,5}};
    unsigned char colors[288],masks[144],white[4]={255,255,255,255},drawn[1920],reference[1920],initial[1920],cover[480];
    exr_vector_texture color={0},opacity={0},unit={0},child={0};exr_bitmap out={0},other,coverage={0};unsigned trial,i;
    out.width=24;out.height=20;out.channels=4;out.stride=96;out.pixels=drawn;other=out;other.pixels=reference;
    coverage.width=24;coverage.height=20;coverage.channels=1;coverage.stride=24;coverage.pixels=cover;
    for(i=0;i<sizeof(cover);i++) cover[i]=(unsigned char)(i*53);
    unit.bitmap.width=unit.bitmap.height=1;unit.bitmap.channels=unit.bitmap.stride=4;unit.bitmap.pixels=white;
    child=unit;child.mask=&unit;child.mask_mode=2;
    color.bitmap.channels=opacity.bitmap.channels=4;color.bitmap.pixels=colors;opacity.bitmap.pixels=masks;color.interpolate=1;
    for(trial=0;trial<384;trial++) {
      const double *p=placements[trial%6],m[6]={p[0],0,0,p[1],p[2],p[3]};const unsigned *z=sizes[(trial/6)%4],variant=trial/24;
      double alpha=variant&1 ? 1 : .63;const exr_bitmap *clip_used=variant&2 ? &coverage : NULL;
      color.bitmap.width=z[0];color.bitmap.height=z[1];color.bitmap.stride=z[0]*4;
      opacity.bitmap.width=z[2];opacity.bitmap.height=z[3];opacity.bitmap.stride=z[2]*4;opacity.interpolate=(variant&4)!=0;
      for(i=0;i<sizeof(colors);i++) colors[i]=(unsigned char)(i*37+trial*23);
      for(i=0;i<sizeof(masks);i++) masks[i]=(unsigned char)(i*41+trial*11);
      colors[3]=0;colors[7]=255;
      for(i=0;i<sizeof(initial);i++) initial[i]=(unsigned char)(i*13+trial);
      for(i=3;i<sizeof(initial);i+=12) initial[i]=0;
      /* Soft-masked. */
      color.mask=&opacity;color.mask_mode=variant&8 ? 2 : 1;
      memcpy(drawn,initial,sizeof(drawn));memcpy(reference,initial,sizeof(reference));
      opacity.mask=NULL;OK(exr_vector_texture_paint(&out,&color,m,alpha,clip_used,NULL,NULL,&error));
      opacity.mask=&unit;opacity.mask_mode=2;OK(exr_vector_texture_paint(&other,&color,m,alpha,clip_used,NULL,NULL,&error));
      CHECK(memcmp(drawn,initial,sizeof(drawn)) && !memcmp(drawn,reference,sizeof(drawn)));
      /* Unmasked. */
      memcpy(drawn,initial,sizeof(drawn));memcpy(reference,initial,sizeof(reference));
      color.mask=NULL;OK(exr_vector_texture_paint(&out,&color,m,alpha,clip_used,NULL,NULL,&error));
      color.mask=&child;color.mask_mode=2;OK(exr_vector_texture_paint(&other,&color,m,alpha,clip_used,NULL,NULL,&error));
      CHECK(memcmp(drawn,initial,sizeof(drawn)) && !memcmp(drawn,reference,sizeof(drawn)));
    }
  }
}
static void jpeg_cases(const char *dir) {
  const char *bad[]={"dimensions","channels","not-jpeg","truncated","color-transform","middle"};
  unsigned char *data; size_t size,i; exr_pdf_file *file=NULL; exr_bitmap b;
  data=load(dir,"pdf-jpeg.pdf",&size); OK(exr_pdf_open(data,size,&file,&error));
  for(i=0;i<3;i++) {
    const char *names[]={"Baseline","Progressive","Wrapped"}; b=decode(file,names[i]); CHECK(b.width==16 && b.height==16);
    CHECK(b.pixels[0]>250 && b.pixels[1]<5 && b.pixels[2]<5 && b.pixels[3]==255);
    CHECK(b.pixels[15*4]<5 && b.pixels[15*4+1]>250); free(b.pixels);
  }
  b=decode(file,"Gray"); CHECK(b.width==8 && b.height==8); pixel(&b,0,0,64,64,64,255); free(b.pixels);
  b=decode(file,"Inverted"); pixel(&b,0,0,191,191,191,255); free(b.pixels);
  b=render(file,"4 0 0 4 0 0 cm /Baseline Do"); CHECK(b.pixels[3*b.stride]>250 && b.pixels[3*b.stride+1]<5 && b.pixels[0]<5 && b.pixels[2]>250); free(b.pixels);
  { const unsigned char *plain,*wrapped,*again; size_t n,m,repeat; exr_pdf_stream_codec codec; uint32_t parameters;
    OK(exr_pdf_image_payload(file,image(file,"Baseline"),&plain,&n,&codec,&parameters,&error)); CHECK(codec==EXR_PDF_STREAM_JPEG);
    OK(exr_pdf_image_payload(file,image(file,"Wrapped"),&wrapped,&m,&codec,&parameters,&error)); CHECK(codec==EXR_PDF_STREAM_JPEG && n==m && !memcmp(plain,wrapped,n));
    OK(exr_pdf_image_payload(file,image(file,"Wrapped"),&again,&repeat,&codec,&parameters,&error)); CHECK(again==wrapped && repeat==m);
    CHECK(exr_pdf_stream_data(file,image(file,"Wrapped"),&again,&repeat,&error)==EXR_FORMAT && !again && !repeat);
  }
  exr_pdf_close(file); free(data);
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) {
    char name[128]; int interp=1; snprintf(name,sizeof(name),"pdf-jpeg-bad-%s.pdf",bad[i]); data=load(dir,name,&size); OK(exr_pdf_open(data,size,&file,&error));
    CHECK(exr_pdf_image_decode(file,image(file,"Baseline"),resources(file),0,&b,&interp,NULL,NULL,&error)==EXR_FORMAT && !b.pixels && !interp); exr_pdf_close(file); free(data);
  }
}
static void cmyk_jpeg_cases(const char *dir) {
  const char *names[]={"CMYK","Progressive","YCCK","YCCKProgressive","NoAdobe","ICC","Wrapped"};
  const char *bad[]={"dimensions","channels","truncated","decode","transform"};
  unsigned char *data; size_t size,i,j; exr_pdf_file *file=NULL; exr_bitmap b;
  unsigned reference[3];cmyk_reference((const double[4]){40/255.,80/255.,120/255.,32/255.},reference);
  data=load(dir,"pdf-jpeg-cmyk.pdf",&size); OK(exr_pdf_open(data,size,&file,&error));
  for(i=0;i<sizeof(names)/sizeof(*names);i++) {
    b=decode(file,names[i]); CHECK(b.width==17 && b.height==9);
    /* Expected inks C=40 M=80 Y=120 K=32, converted by DeviceCMYK.
       YCCK has a lossy YCbCr round trip: allow two byte values. */
    for(j=0;j<(size_t)b.width*b.height;j++) {
      CHECK(abs((int)b.pixels[j*4]-(int)reference[0])<=2);
      CHECK(abs((int)b.pixels[j*4+1]-(int)reference[1])<=2);
      CHECK(abs((int)b.pixels[j*4+2]-(int)reference[2])<=2 && b.pixels[j*4+3]==255);
    }
    free(b.pixels);
  }
  b=decode(file,"Default"); { unsigned black[3];cmyk_reference((const double[4]){215/255.,175/255.,135/255.,223/255.},black);pixel(&b,0,0,black[0],black[1],black[2],255); } free(b.pixels);
  b=decode(file,"Key"); pixel(&b,0,0,reference[0],reference[1],reference[2],0); free(b.pixels);
  b=decode(file,"Soft"); pixel(&b,0,0,reference[0],reference[1],reference[2],128); free(b.pixels);
  for(i=0;i<2;i++) {
    const double inks[4][4]={{0,1,1,0},{1,0,1,0},{1,1,0,0},{0,0,0,128/255.}};unsigned expected[4][3];
    for(j=0;j<4;j++) cmyk_reference(inks[j],expected[j]);
    if(i) { /* Independent libjpeg/Pillow decoded inks of this lossy YCCK fixture. */
      cmyk_reference((const double[4]){0,1,254/255.,0},expected[0]);
      cmyk_reference((const double[4]){254/255.,0,254/255.,0},expected[1]);
      cmyk_reference((const double[4]){253/255.,1,0,0},expected[2]);
    }
    b=decode(file,i ? "YQuad" : "Quad"); CHECK(b.width==32 && b.height==32);
    for(j=0;j<4;j++) {
      const unsigned char *p=b.pixels+(8+(j/2)*16)*b.stride+(8+(j%2)*16)*4; unsigned k;
      for(k=0;k<3;k++) { if(abs((int)p[k]-(int)expected[j][k])>2) fprintf(stderr,"quad %zu/%zu channel %u got %u expected %u\n",i,j,k,p[k],expected[j][k]);CHECK(abs((int)p[k]-(int)expected[j][k])<=2); }
      CHECK(p[3]==255);
    }
    free(b.pixels);
  }
  b=render(file,"8 0 0 8 0 0 cm /CMYK Do"); pixel(&b,4,4,reference[0],reference[1],reference[2],255); free(b.pixels);
  { exr_control control={0}; int interpolate=1; control.cancelled=cancel;
    CHECK(exr_pdf_image_decode(file,image(file,"CMYK"),resources(file),0,&b,&interpolate,NULL,&control,&error)==EXR_CANCELLED && !b.pixels && !interpolate);
  }
  exr_pdf_close(file); free(data);
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) {
    char name[128]; int interpolate=1; snprintf(name,sizeof(name),"pdf-jpeg-cmyk-bad-%s.pdf",bad[i]);
    data=load(dir,name,&size); OK(exr_pdf_open(data,size,&file,&error));
    CHECK(exr_pdf_image_decode(file,image(file,"CMYK"),resources(file),0,&b,&interpolate,NULL,NULL,&error)==EXR_FORMAT && !b.pixels && !interpolate);
    exr_pdf_close(file); free(data);
  }
}
static void cache_cases(const char *dir) {
  unsigned char *data;size_t size,work=0,cost;exr_pdf_file *file=NULL,*other=NULL;
  exr_vector_texture *a=NULL,*b=NULL,*c=NULL;exr_pdf_image_cache_stats stats,before;
  data=load(dir,"pdf-images.pdf",&size);OK(exr_pdf_open(data,size,&file,&error));
  OK(exr_pdf_open(data,size,&other,&error));
  OK(exr_pdf_image_load(file,image(file,"Soft"),resources(file),0,&a,&work,NULL,&error));cost=work;
  exr_pdf_operation_end(file);
  OK(exr_pdf_image_load(file,image(file,"Soft"),resources(file),0,&b,&work,NULL,&error));
  CHECK(a==b && a->mask && work==2*cost);exr_pdf_image_release(b);
  exr_pdf_image_cache_report(file,&stats);CHECK(stats.hits==1 && stats.misses==1 && stats.entries==1 && stats.bytes>0);
  OK(exr_pdf_image_load(other,image(other,"Soft"),resources(other),0,&b,NULL,NULL,&error));CHECK(b!=a);
  exr_pdf_image_release(b);exr_pdf_close(other);
  /* Eviction must not invalidate a layer still held by a caller. */
  exr_pdf_image_cache_limits(file,1024,1);
  OK(exr_pdf_image_load(file,image(file,"RGB"),resources(file),0,&b,NULL,NULL,&error));
  OK(exr_pdf_image_load(file,image(file,"Gray"),resources(file),0,&c,NULL,NULL,&error));
  pixel(&a->bitmap,0,0,255,0,0,255);pixel(&b->bitmap,0,0,255,0,0,255);
  exr_pdf_image_release(a);exr_pdf_image_release(b);exr_pdf_image_release(c);
  exr_pdf_image_cache_report(file,&stats);CHECK(stats.entries==1 && stats.bytes<=1024 && stats.evictions==1);
  exr_pdf_image_cache_limits(file,0,0);before=stats;
  OK(exr_pdf_image_load(file,image(file,"RGB"),resources(file),0,&a,NULL,NULL,&error));
  OK(exr_pdf_image_load(file,image(file,"RGB"),resources(file),0,&b,NULL,NULL,&error));CHECK(a!=b);
  exr_pdf_image_release(a);exr_pdf_image_release(b);
  exr_pdf_image_cache_report(file,&stats);CHECK(!stats.bytes && !stats.entries && stats.hits==before.hits);
  exr_pdf_image_cache_limits(file,1,128);
  a=NULL;OK(exr_pdf_image_load(file,image(file,"RGB"),resources(file),0,&a,NULL,NULL,&error));exr_pdf_image_release(a);
  exr_pdf_image_cache_report(file,&stats);CHECK(!stats.bytes);
  exr_pdf_image_cache_limits(file,1024*1024,2);
  OK(exr_pdf_image_load(file,image(file,"RGB"),resources(file),0,&a,NULL,NULL,&error));
  OK(exr_pdf_image_load(file,image(file,"Gray"),resources(file),0,&b,NULL,NULL,&error));
  OK(exr_pdf_image_load(file,image(file,"RGB"),resources(file),0,&c,NULL,NULL,&error));CHECK(c==a);exr_pdf_image_release(c);
  OK(exr_pdf_image_load(file,image(file,"Rows1"),resources(file),0,&c,NULL,NULL,&error));exr_pdf_image_release(c);
  /* The intervening RGB hit makes Gray the least recently used entry. */
  OK(exr_pdf_image_load(file,image(file,"RGB"),resources(file),0,&c,NULL,NULL,&error));CHECK(c==a);exr_pdf_image_release(c);
  OK(exr_pdf_image_load(file,image(file,"Gray"),resources(file),0,&c,NULL,NULL,&error));CHECK(c!=b);
  exr_pdf_image_release(a);exr_pdf_image_release(b);exr_pdf_image_release(c);
  exr_pdf_image_cache_limits(file,1024*1024,128);
  OK(exr_pdf_image_load(file,image(file,"Matte"),resources(file),0,&a,NULL,NULL,&error));
  exr_pdf_operation_end(file);
  OK(exr_pdf_image_load_from(file,image(file,"Matte"),file,EXR_PDF_NONE,0xff00ffff,3,&b,NULL,NULL,&error));CHECK(a==b && a->mask && !a->has_matte);
  exr_pdf_image_release(a);exr_pdf_image_release(b);exr_pdf_image_cache_report(file,&stats);CHECK(stats.entries==1 && !stats.matte_bypasses);
  OK(exr_pdf_image_load(file,image(file,"Stencil"),resources(file),0xff0000ff,&a,NULL,NULL,&error));
  OK(exr_pdf_image_load(file,image(file,"Stencil"),resources(file),0x00ff00ff,&b,NULL,NULL,&error));
  pixel(&a->bitmap,0,0,255,0,0,255);pixel(&b->bitmap,0,0,0,255,0,255);
  exr_pdf_image_release(a);exr_pdf_image_release(b);
  /* Resource aliases must be resolved again in the caller's resource scope. */
  OK(exr_pdf_image_load(file,image(file,"Alias"),resources(file),0,&a,NULL,NULL,&error));
  OK(exr_pdf_image_load(file,image(file,"Alias"),resources(file),0,&b,NULL,NULL,&error));CHECK(a!=b);
  exr_pdf_image_release(a);exr_pdf_image_release(b);b=NULL;
  CHECK(exr_pdf_image_load_from(file,image(file,"Alias"),file,EXR_PDF_NONE,0,1,&b,NULL,NULL,&error)==EXR_FORMAT && !b);
  { exr_bitmap ink_a={0},ink_b={0};uint32_t id=image(file,"CMYK2"),res=resources(file);
    OK(exr_pdf_image_load_inks(file,id,file,res,0,1,&a,&ink_a,NULL,NULL,&error));
    OK(exr_pdf_image_load_inks(file,id,file,res,0,1,&b,&ink_b,NULL,NULL,&error));
    CHECK(a!=b && ink_a.pixels && ink_b.pixels && ink_a.pixels!=ink_b.pixels);
    CHECK(!memcmp(ink_a.pixels,ink_b.pixels,(size_t)ink_a.stride*ink_a.height));
    free(ink_a.pixels);free(ink_b.pixels);exr_pdf_image_release(a);exr_pdf_image_release(b);
    OK(exr_pdf_image_load_from(file,id,file,res,0,0,&a,NULL,NULL,&error));
    OK(exr_pdf_image_load_from(file,id,file,res,0,1,&b,NULL,NULL,&error));CHECK(a!=b);
    OK(exr_pdf_image_load_from(file,id,file,EXR_PDF_NONE,0,1,&c,NULL,NULL,&error));CHECK(c!=b);
    exr_pdf_image_release(a);exr_pdf_image_release(b);exr_pdf_image_release(c);
  }
  { const char *content="q 4 0 0 4 0 0 cm /RGB Do Q q 4 0 0 4 4 4 cm /Soft Do Q q 0 1 0 rg 4 0 0 2 0 4 cm /Stencil Do Q q 2 0 0 2 4 0 cm /Matte Do Q";
    exr_bitmap baseline,warm,hit;
    exr_pdf_image_cache_limits(file,0,0);baseline=render(file,content);
    exr_pdf_image_cache_limits(file,1024*1024,128);warm=render(file,content);exr_pdf_image_cache_report(file,&before);
    exr_pdf_operation_end(file);hit=render(file,content);exr_pdf_image_cache_report(file,&stats);CHECK(stats.hits==before.hits+3);
    CHECK(!memcmp(baseline.pixels,warm.pixels,(size_t)baseline.stride*baseline.height));
    CHECK(!memcmp(baseline.pixels,hit.pixels,(size_t)baseline.stride*baseline.height));
    free(baseline.pixels);free(warm.pixels);free(hit.pixels);
  }
  exr_pdf_close(file);free(data);
}
int main(int argc,char **argv) {
  const char *bad[]={"soft-color","explicit-type","matte-short","palette-short","palette-high","key-range","short","extra","bits","decode-short","decode-extra","space","mask","soft","stencil-space","stencil-bits","stencil-decode","interpolate","zero"};
  size_t size,i; unsigned char *data; exr_pdf_file *file=NULL;
  CHECK(argc==2); cache_cases(argv[1]); jpeg_cases(argv[1]); cmyk_jpeg_cases(argv[1]); data=load(argv[1],"pdf-images.pdf",&size); OK(exr_pdf_open(data,size,&file,&error)); decoded(file); rasterized(file); affine();
  { exr_vector_texture *texture=NULL; OK(exr_pdf_image_load(file,image(file,"HighMask"),resources(file),0,&texture,NULL,NULL,&error));
    CHECK(texture && texture->bitmap.width==1 && texture->mask && texture->mask->bitmap.width==4); exr_pdf_image_release(texture); exr_pdf_image_release(NULL);
  }
  { exr_control control={0}; exr_bitmap b; int interp=1; size_t work=(size_t)256*1024*1024; control.cancelled=cancel;
    CHECK(exr_pdf_image_decode(file,image(file,"RGB"),resources(file),0,&b,&interp,NULL,&control,&error)==EXR_CANCELLED && !b.pixels && !interp);
    CHECK(exr_pdf_image_decode(file,image(file,"RGB"),resources(file),0,&b,&interp,&work,NULL,&error)==EXR_LIMIT && !b.pixels);
  }
  exr_pdf_close(file); free(data);
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) {
    char name[128]; exr_bitmap b; int interp=1; snprintf(name,sizeof(name),"pdf-image-bad-%s.pdf",bad[i]); data=load(argv[1],name,&size); OK(exr_pdf_open(data,size,&file,&error));
    CHECK(exr_pdf_image_decode(file,image(file,"RGB"),resources(file),0,&b,&interp,NULL,NULL,&error)==EXR_FORMAT && !b.pixels && !b.width && !interp); exr_pdf_close(file); free(data);
  }
  for(i=0;i<2;i++) {
    exr_bitmap b; int interp=1; data=load(argv[1],i ? "pdf-image-mask-bytes.pdf" : "pdf-image-mask-depth.pdf",&size); OK(exr_pdf_open(data,size,&file,&error));
    CHECK(exr_pdf_image_decode(file,image(file,"RGB"),resources(file),0,&b,&interp,NULL,NULL,&error)==EXR_LIMIT && !b.pixels && !b.width && !interp); exr_pdf_close(file); free(data);
  }
  printf("%u native PDF image checks passed\n",checks); return 0;
}
