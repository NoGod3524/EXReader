/* SPDX-License-Identifier: MIT */
/* CCITT Group 3/4 fax decoding (ISO 32000-1 7.4.6). Row decoding follows the
   structure of the BSD-licensed Go x/image/ccitt reader: each row is decoded as
   changing elements against the previous row, then packed to one bit per pixel. */
#include "pdf_internal.h"
#include "pdf_ccitt_tables.h"

typedef struct { const unsigned char *data; size_t size,bits; } fax_bits;

static int fax_bit(fax_bits *r) {
  int value;
  if(r->bits>=r->size*8) return -1;
  value=(r->data[r->bits>>3]>>(7-(r->bits&7)))&1;
  r->bits++;
  return value;
}
static int fax_code(fax_bits *r,const short table[][2],unsigned *value) {
  int node=1;
  while(node>0) {
    int b=fax_bit(r);
    if(b<0) return 0;
    node=table[node][b];
  }
  if(!node) return 0;
  *value=(unsigned)~node;
  return 1;
}
/* b1 or b2 on the reference row, relative to the current pen colour. */
static int fax_find_b(const unsigned char *prev,size_t width,size_t wi,int at_start,int pen_white,int want_b2) {
  size_t i=wi;
  unsigned char pen=pen_white ? 0xFF : 0x00;
  unsigned char opposite=(unsigned char)~pen;
  if(at_start) {
    while(i<width && prev[i]==0xFF) i++;
    if(want_b2) while(i<width && prev[i]==0x00) i++;
    return (int)i;
  }
  while(i<width && prev[i]==opposite) i++;
  while(i<width && prev[i]==pen) i++;
  if(want_b2) while(i<width && prev[i]==opposite) i++;
  return (int)i;
}
static int fax_run(fax_bits *r,int pen_white,size_t room,size_t *run) {
  size_t total=0;
  for(;;) {
    unsigned n;
    if(!fax_code(r,pen_white ? exr_ccitt_white_table : exr_ccitt_black_table,&n)) return 0;
    total+=n;
    if(n<=63) break;   /* makeup codes already carry their full length */
    if(total>room) return 0;
  }
  if(total>room) return 0;
  *run=total;
  return 1;
}
static int fax_row(fax_bits *r,unsigned char *curr,const unsigned char *prev,size_t width,int align) {
  size_t wi=0;
  int pen_white=1,at_start=1;
  if(align) r->bits=(r->bits+7)&~(size_t)7;
  while(wi<width) {
    unsigned mode,fill=(unsigned)(pen_white ? 0xFF : 0x00);
    if(!fax_code(r,exr_ccitt_mode_table,&mode)) return 0;
    if(mode==0) {                       /* pass */
      int b2=fax_find_b(prev,width,wi,at_start,pen_white,1);
      if(b2<(int)wi || b2>(int)width) return 0;
      memset(curr+wi,fill,(size_t)b2-wi); wi=(size_t)b2;
    } else if(mode==1) {                /* horizontal: two runs */
      size_t run;int k;
      for(k=0;k<2;k++) {
        if(!fax_run(r,pen_white,width-wi,&run) || wi+run>width) return 0;
        memset(curr+wi,fill,run); wi+=run; pen_white=!pen_white;
        fill=(unsigned)(pen_white ? 0xFF : 0x00);
      }
    } else if(mode>=2 && mode<=8) {     /* V0, VR1..3, VL1..3 */
      int delta=mode==2 ? 0 : (mode<=5 ? (int)(mode-2) : -(int)(mode-5));
      int b1=fax_find_b(prev,width,wi,at_start,pen_white,0);
      int a1=b1+delta;
      if(a1<(int)wi || a1>(int)width) return 0;
      memset(curr+wi,fill,(size_t)(a1-(int)wi)); wi=(size_t)a1; pen_white=!pen_white;
    } else return 0;                    /* extension or unknown */
    at_start=0;
  }
  return 1;
}
/* Group 3 lines are separated by an end-of-line code: at least 11 zeros then a 1. */
static int fax_eol(fax_bits *r) {
  size_t zeros=0;
  for(;;) {
    int b=fax_bit(r);
    if(b<0) return 0;
    if(b) { if(zeros>=11) return 1; zeros=0; }
    else { if(++zeros>64) return 0; }
  }
}
static int fax_row_1d(fax_bits *r,unsigned char *curr,size_t width) {
  size_t wi=0;
  int pen_white=1;
  while(wi<width) {
    size_t run;
    if(!fax_run(r,pen_white,width-wi,&run) || wi+run>width) return 0;
    memset(curr+wi,(unsigned)(pen_white ? 0xFF : 0x00),run);
    wi+=run; pen_white=!pen_white;
  }
  return 1;
}
exr_status exr_pdf_ccitt_decode(const unsigned char *data,size_t size,long k,unsigned columns,unsigned rows,
                                int black_is_1,int byte_align,unsigned char **out,size_t *out_size,exr_error *e) {
  fax_bits r={(const unsigned char *)data,size,0};
  size_t stride,y;
  unsigned char *image,*prev=NULL,*curr=NULL;
  if(!out || !out_size) return exr_fail(e,EXR_ARGUMENT,"Missing CCITT output");
  *out=NULL;*out_size=0;
  if(!columns || columns>65536 || !rows || rows>65536) return exr_fail(e,EXR_FORMAT,"Invalid CCITT image dimensions");
  if(!rows) return exr_fail(e,EXR_UNSUPPORTED,"CCITT needs an explicit row count");
  stride=((size_t)columns+7)/8;
  image=calloc(stride*rows,1);
  prev=malloc(columns);curr=malloc(columns);
  if(!image || !prev || !curr) { free(image);free(prev);free(curr);return exr_fail(e,EXR_MEMORY,"CCITT image allocation failed"); }
  memset(prev,0xFF,columns); /* the row above the first is white */
  for(y=0;y<rows;y++) {
    size_t x;
    memset(curr,0xFF,columns);
    if(k<0) {
      if(!fax_row(&r,curr,prev,columns,byte_align)) { free(image);free(prev);free(curr);return exr_fail(e,EXR_FORMAT,"Invalid CCITT Group 4 data"); }
    } else {
      /* Group 3: an EOL separates lines; with K > 0 each line carries a tag bit
         selecting one- or two-dimensional coding. */
      { size_t saved=r.bits;
        if(!fax_eol(&r)) {
          r.bits=saved; /* the first line may start without an EOL */
          if(y) { free(image);free(prev);free(curr);return exr_fail(e,EXR_FORMAT,"Invalid CCITT Group 3 data"); }
        }
      }
      if(k>0) {
        int tag=fax_bit(&r);
        if(tag<0) { free(image);free(prev);free(curr);return exr_fail(e,EXR_FORMAT,"Invalid CCITT Group 3 data"); }
        if(!tag && !fax_row(&r,curr,prev,columns,0)) { free(image);free(prev);free(curr);return exr_fail(e,EXR_FORMAT,"Invalid CCITT Group 3 data"); }
        else if(tag && !fax_row_1d(&r,curr,columns)) { free(image);free(prev);free(curr);return exr_fail(e,EXR_FORMAT,"Invalid CCITT Group 3 data"); }
      } else if(!fax_row_1d(&r,curr,columns)) { free(image);free(prev);free(curr);return exr_fail(e,EXR_FORMAT,"Invalid CCITT Group 3 data"); }
    }
    for(x=0;x<columns;x++) {
      int black=curr[x]==0x00;
      /* Sample polarity matches the reference implementation: with BlackIs1 false a
         black fax pixel carries sample 0, so Decode [0 1] paints it black. */
      int sample=black ? (black_is_1 ? 1 : 0) : (black_is_1 ? 0 : 1);
      if(sample) image[y*stride+(x>>3)]|=(unsigned char)(1u<<(7-(x&7)));
    }
    memcpy(prev,curr,columns);
  }
  free(prev);free(curr);
  *out=image;*out_size=stride*rows;
  return EXR_OK;
}
