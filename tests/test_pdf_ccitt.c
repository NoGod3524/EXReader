/* SPDX-License-Identifier: MIT */
/* WP4a image filters: CCITT Group 4 decoding against a Pillow-produced strip. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks; static exr_error error;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static const char *directory;

static void path_of(char *out,size_t size,const char *name) { snprintf(out,size,"%s/pdf-color/%s",directory,name); }
typedef struct { unsigned char *data; size_t size,cap; } buf;
static void buf_add(buf *b,const void *p,size_t n) {
  if(n>b->cap-b->size) { size_t c=b->cap ? b->cap : 1024; while(c-b->size<n) c*=2; b->data=realloc(b->data,c); CHECK(b->data); b->cap=c; }
  if(n) memcpy(b->data+b->size,p,n); b->size+=n;
}
static void buf_str(buf *b,const char *s) { buf_add(b,s,strlen(s)); }
static buf make_ccitt_pdf(unsigned w,unsigned h,const char *parms,const unsigned char *stream_data,size_t stream_len) {
  buf b={0}; size_t off[6],xref; char row[512],cs[64]; unsigned i;
  snprintf(cs,sizeof(cs),"q %u 0 0 %u 0 0 cm /Im Do Q",w,h);
  buf_str(&b,"%PDF-1.7\n");
  off[1]=b.size; buf_str(&b,"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n");
  off[2]=b.size; buf_str(&b,"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n");
  off[3]=b.size; snprintf(row,sizeof(row),"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %u %u] /Contents 4 0 R /Resources << /XObject << /Im 5 0 R >> >> >>\nendobj\n",w,h); buf_str(&b,row);
  off[4]=b.size; snprintf(row,sizeof(row),"4 0 obj\n<< /Length %zu >>\nstream\n%s\nendstream\nendobj\n",strlen(cs),cs); buf_str(&b,row);
  off[5]=b.size; snprintf(row,sizeof(row),"5 0 obj\n<< /Type /XObject /Subtype /Image /Width %u /Height %u /BitsPerComponent 1 /ColorSpace /DeviceGray /Filter /CCITTFaxDecode /DecodeParms << %s >> /Length %zu >>\nstream\n",w,h,parms,stream_len); buf_str(&b,row);
  buf_add(&b,stream_data,stream_len); buf_str(&b,"\nendstream\nendobj\n");
  xref=b.size; buf_str(&b,"xref\n0 6\n0000000000 65535 f \n");
  for(i=1;i<6;i++) { snprintf(row,sizeof(row),"%010zu 00000 n \n",off[i]); buf_str(&b,row); }
  snprintf(row,sizeof(row),"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%zu\n%%%%EOF\n",xref); buf_str(&b,row);
  return b;
}
static void extra_ccitt_cases(const exr_fixed_render_options *render) {
  exr_fixed_open_options options={0}; exr_fixed_document *d=NULL; exr_bitmap page={0};
  options.struct_size=sizeof(options);
  /* 1. Boolean /BlackIs1 true & false and /EncodedByteAlign true on a 1-row G4 stream (all-white via V(0)=bit 1). */
  { const unsigned char g4_white[1]={0x80}; unsigned black_is_1;
    for(black_is_1=0;black_is_1<2;black_is_1++) {
      buf b=make_ccitt_pdf(8,1,black_is_1 ? "/K -1 /Columns 8 /Rows 1 /BlackIs1 true /EncodedByteAlign true" : "/K -1 /Columns 8 /Rows 1 /BlackIs1 false /EncodedByteAlign false",g4_white,sizeof(g4_white));
      OK(exr_fixed_open_memory(EXR_PDF,b.data,b.size,&options,&d,&error));
      OK(exr_fixed_render(d,0,1,render,&page,&error));
      CHECK(page.width==8 && page.height==1);
      /* All-white fax pixels: BlackIs1=false -> sample 1 (white 255), BlackIs1=true -> sample 0 (black 0). */
      CHECK(page.pixels[0]==(black_is_1 ? 0 : 255));
      exr_bitmap_free(&page); exr_fixed_free(d); free(b.data);
    }
  }
  /* 2. Group 3 1D (/K 0) without EOLs (/EndOfLine false): white-15 (110101) + black-23 (00000101000)
     is 17 bits/row; two packed rows = 34 bits (5 bytes) with no EOLs between rows. */
  { const unsigned char g3_noeol[5]={0xd4,0x14,0x6a,0x0a,0x00};
    buf b=make_ccitt_pdf(38,2,"/K 0 /Columns 38 /Rows 2 /EndOfLine false",g3_noeol,sizeof(g3_noeol));
    unsigned y,x;
    OK(exr_fixed_open_memory(EXR_PDF,b.data,b.size,&options,&d,&error));
    OK(exr_fixed_render(d,0,1,render,&page,&error));
    CHECK(page.width==38 && page.height==2);
    for(y=0;y<2;y++) for(x=0;x<38;x++) {
      const unsigned char *p=page.pixels+(size_t)y*page.stride+x*4;
      int expected=x<15 ? 255 : 0; /* white-15 then black-23, BlackIs1=false */
      CHECK(p[0]==expected && p[1]==expected && p[2]==expected);
    }
    exr_bitmap_free(&page); exr_fixed_free(d); free(b.data);
    /* Same stream must be rejected when /EndOfLine true requires EOL markers. */
    b=make_ccitt_pdf(38,2,"/K 0 /Columns 38 /Rows 2 /EndOfLine true",g3_noeol,sizeof(g3_noeol));
    OK(exr_fixed_open_memory(EXR_PDF,b.data,b.size,&options,&d,&error));
    CHECK(exr_fixed_render(d,0,1,render,&page,&error)==EXR_FORMAT && !page.pixels);
    exr_fixed_free(d); free(b.data);
  }
  /* 2b. Group 3 1D with /EndOfLine true and explicit 12-bit EOL (000000000001) before each row. */
  { const unsigned char g3_eol[8]={0x00,0x1d,0x41,0x40,0x00,0xea,0x0a,0x00};
    buf b=make_ccitt_pdf(38,2,"/K 0 /Columns 38 /Rows 2 /EndOfLine true",g3_eol,sizeof(g3_eol));
    unsigned y,x;
    OK(exr_fixed_open_memory(EXR_PDF,b.data,b.size,&options,&d,&error));
    OK(exr_fixed_render(d,0,1,render,&page,&error));
    CHECK(page.width==38 && page.height==2);
    for(y=0;y<2;y++) for(x=0;x<38;x++) {
      const unsigned char *p=page.pixels+(size_t)y*page.stride+x*4;
      int expected=x<15 ? 255 : 0;
      CHECK(p[0]==expected);
    }
    exr_bitmap_free(&page); exr_fixed_free(d); free(b.data);
  }
  /* 3. Group 3 1D with /EncodedByteAlign true (2 rows, each 17 bits padded to 3 bytes = 6 bytes). */
  { const unsigned char g3_aligned[6]={0xd4,0x14,0x00,0xd4,0x14,0x00};
    buf b=make_ccitt_pdf(38,2,"/K 0 /Columns 38 /Rows 2 /EndOfLine false /EncodedByteAlign true",g3_aligned,sizeof(g3_aligned));
    unsigned y,x;
    OK(exr_fixed_open_memory(EXR_PDF,b.data,b.size,&options,&d,&error));
    OK(exr_fixed_render(d,0,1,render,&page,&error));
    CHECK(page.width==38 && page.height==2);
    for(y=0;y<2;y++) for(x=0;x<38;x++) {
      const unsigned char *p=page.pixels+(size_t)y*page.stride+x*4;
      int expected=x<15 ? 255 : 0;
      CHECK(p[0]==expected);
    }
    exr_bitmap_free(&page); exr_fixed_free(d); free(b.data);
  }
  /* 4. 512 MiB OOM bomb (/Columns 65535 /Rows 65535 with 8 KiB of 0xFF) must hit EXR_LIMIT before allocating. */
  { unsigned char *ones=malloc(8192); CHECK(ones); memset(ones,0xff,8192);
    buf b=make_ccitt_pdf(8,8,"/K -1 /Columns 65535 /Rows 65535",ones,8192);
    free(ones);
    OK(exr_fixed_open_memory(EXR_PDF,b.data,b.size,&options,&d,&error));
    CHECK(exr_fixed_render(d,0,1,render,&page,&error)==EXR_LIMIT && !page.pixels);
    exr_fixed_free(d); free(b.data);
  }
  /* 5. Real /K (out-of-range float) and int64 /K (> INT_MAX) must fail with EXR_FORMAT without UB. */
  { const unsigned char g4_white[1]={0x80};
    const char *bad_k[]={"/K 99999999999999999999999.0 /Columns 8 /Rows 1","/K 3000000000 /Columns 8 /Rows 1"};
    size_t i;
    for(i=0;i<sizeof(bad_k)/sizeof(*bad_k);i++) {
      buf b=make_ccitt_pdf(8,1,bad_k[i],g4_white,sizeof(g4_white));
      OK(exr_fixed_open_memory(EXR_PDF,b.data,b.size,&options,&d,&error));
      CHECK(exr_fixed_render(d,0,1,render,&page,&error)==EXR_FORMAT && !page.pixels);
      exr_fixed_free(d); free(b.data);
    }
  }
  /* 6. Inline /CCF image must fail cleanly instead of rewinding stream cursor to offset 0. */
  { buf b={0}; size_t off[5],xref; char row[256]; unsigned i;
    const char *cs="BI /W 8 /H 1 /BPC 1 /CS /G /F /CCF /DP << /K -1 /Columns 8 /Rows 1 >> ID \x80 EI";
    buf_str(&b,"%PDF-1.7\n");
    off[1]=b.size; buf_str(&b,"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n");
    off[2]=b.size; buf_str(&b,"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n");
    off[3]=b.size; buf_str(&b,"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 8 8] /Contents 4 0 R >>\nendobj\n");
    off[4]=b.size; snprintf(row,sizeof(row),"4 0 obj\n<< /Length %zu >>\nstream\n%s\nendstream\nendobj\n",strlen(cs),cs); buf_str(&b,row);
    xref=b.size; buf_str(&b,"xref\n0 5\n0000000000 65535 f \n");
    for(i=1;i<5;i++) { snprintf(row,sizeof(row),"%010zu 00000 n \n",off[i]); buf_str(&b,row); }
    snprintf(row,sizeof(row),"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n%zu\n%%%%EOF\n",xref); buf_str(&b,row);
    OK(exr_fixed_open_memory(EXR_PDF,b.data,b.size,&options,&d,&error));
    CHECK(exr_fixed_render(d,0,1,render,&page,&error)==EXR_FORMAT && !page.pixels);
    exr_fixed_free(d); free(b.data);
  }
}
int main(int argc,char **argv) {
  char path[4096]; exr_fixed_document *d=NULL; exr_fixed_open_options options={0};
  exr_fixed_render_options render={0}; exr_bitmap page={0}; unsigned x,y;
  CHECK(argc==2); directory=argv[1];
  options.struct_size=sizeof(options); render.channels=4; render.background=0xffffffff;
  /* The same picture is encoded once as Group 4 and once as Group 3; both must
     decode to the reference polarity. */
  { const char *names[]={"ccitt-g4.pdf","ccitt-g3.pdf"}; size_t n;
    for(n=0;n<sizeof(names)/sizeof(*names);n++) {
      path_of(path,sizeof(path),names[n]);
      OK(exr_fixed_open(path,&options,&d,&error));
      OK(exr_fixed_render(d,0,1,&render,&page,&error));
      CHECK(page.width==32 && page.height==8);
      /* A white page with a black rectangle in rows 2..5, columns 4..19. Polarity
         follows the reference renderer: the rectangle is white, the rest black. */
      for(y=0;y<8;y++) for(x=0;x<32;x++) {
        int inside=y>=2 && y<=5 && x>=4 && x<=19;
        const unsigned char *p=page.pixels+(size_t)y*page.stride+x*4;
        int white=p[0]==255 && p[1]==255 && p[2]==255;
        CHECK(white==inside);
      }
      exr_bitmap_free(&page); exr_fixed_free(d);
    }
  }
  /* Rows may be omitted; the image height then bounds the decode. */
  path_of(path,sizeof(path),"ccitt-g4-norows.pdf");
  OK(exr_fixed_open(path,&options,&d,&error));
  OK(exr_fixed_render(d,0,1,&render,&page,&error));
  CHECK(page.width==32 && page.height==8);
  { const unsigned char *p=page.pixels+(size_t)3*page.stride+8*4;
    CHECK(p[0]==255 && p[1]==255 && p[2]==255);
    p=page.pixels+(size_t)3*page.stride+0*4;
    CHECK(p[0]==0 && p[1]==0 && p[2]==0); }
  exr_bitmap_free(&page); exr_fixed_free(d);
  /* A truncated Group 4 stream is rejected, not silently drawn. */
  path_of(path,sizeof(path),"ccitt-g4-truncated.pdf");
  OK(exr_fixed_open(path,&options,&d,&error)); CHECK(d);
  CHECK(exr_fixed_render(d,0,1,&render,&page,&error)==EXR_FORMAT && !page.pixels);
  exr_fixed_free(d);
  extra_ccitt_cases(&render);
  printf("%u native PDF CCITT checks passed\n",checks);
  return 0;
}
