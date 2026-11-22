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
/* Consume an EOL (11+ consecutive zero bits immediately followed by 1) at r->bits.
   Restores r->bits on mismatch so valid 1D data bits are never skipped. */
static int fax_eol_here(fax_bits *r) {
  size_t saved=r->bits,zeros=0;
  for(;;) {
    int b=fax_bit(r);
    if(b<0) { r->bits=saved; return 0; }
    if(b) {
      if(zeros>=11) return 1;
      r->bits=saved; return 0;
    }
    if(++zeros>64) { r->bits=saved; return 0; }
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
exr_status exr_pdf_ccitt_decode(const unsigned char *data,size_t size,int k,unsigned columns,unsigned rows,
                                int black_is_1,int byte_align,int end_of_line,size_t *work,const exr_control *control,
                                unsigned char **out,size_t *out_size,exr_error *e) {
  fax_bits r={(const unsigned char *)data,size,0};
  size_t stride,y;
  unsigned char *image=NULL,*prev=NULL,*curr=NULL;
  exr_status status=EXR_OK;
  int seen_eol=0;
  if(!out || !out_size) return exr_fail(e,EXR_ARGUMENT,"Missing CCITT output");
  *out=NULL;*out_size=0;
  if(!columns || columns>65535 || !rows || rows>65535) return exr_fail(e,EXR_FORMAT,"Invalid CCITT image dimensions");
  stride=((size_t)columns+7)/8;
  image=calloc(stride*rows,1);
  prev=malloc(columns);curr=malloc(columns);
  if(!image || !prev || !curr) { status=exr_fail(e,EXR_MEMORY,"CCITT image allocation failed"); goto fail; }
  memset(prev,0xFF,columns); /* the row above the first is white */
  for(y=0;y<rows;y++) {
    size_t x; unsigned char *tmp;
    if(exr_control_cancel(control,e)!=EXR_OK) { status=EXR_CANCELLED; goto fail; }
    if(work) {
      if((size_t)columns>(size_t)256*1024*1024-*work) { status=exr_fail(e,EXR_LIMIT,"PDF decompression work budget exceeded"); goto fail; }
      *work+=columns;
    }
    memset(curr,0xFF,columns);
    if(k<0) {
      if(!fax_row(&r,curr,prev,columns,byte_align)) { status=exr_fail(e,EXR_FORMAT,"Invalid CCITT Group 4 data"); goto fail; }
    } else {
      /* Group 3: accept optional EOL at current bit position; require it when
         /EndOfLine is true; honor /EncodedByteAlign between non-EOL rows. */
      int has_eol=fax_eol_here(&r);
      if(has_eol) seen_eol=1;
      else {
        if(end_of_line && y) { status=exr_fail(e,EXR_FORMAT,"Invalid CCITT Group 3 data"); goto fail; }
        if(byte_align && y) r.bits=(r.bits+7)&~(size_t)7;
      }
      if(k>0) {
        int tag=fax_bit(&r);
        if(tag<0 || (!tag && !fax_row(&r,curr,prev,columns,0)) || (tag && !fax_row_1d(&r,curr,columns))) {
          status=exr_fail(e,EXR_FORMAT,"Invalid CCITT Group 3 data"); goto fail;
        }
      } else if(!fax_row_1d(&r,curr,columns)) { status=exr_fail(e,EXR_FORMAT,"Invalid CCITT Group 3 data"); goto fail; }
    }
    for(x=0;x<columns;x++) {
      int black=curr[x]==0x00;
      /* Sample polarity matches the reference implementation: with BlackIs1 false a
         black fax pixel carries sample 0, so Decode [0 1] paints it black. */
      int sample=black ? (black_is_1 ? 1 : 0) : (black_is_1 ? 0 : 1);
      if(sample) image[y*stride+(x>>3)]|=(unsigned char)(1u<<(7-(x&7)));
    }
    tmp=prev; prev=curr; curr=tmp;
  }
  if(k>=0 && end_of_line && !seen_eol && !fax_eol_here(&r)) {
    status=exr_fail(e,EXR_FORMAT,"Invalid CCITT Group 3 data"); goto fail;
  }
  free(prev);free(curr);
  *out=image;*out_size=stride*rows;
  return EXR_OK;
fail:
  free(image);free(prev);free(curr);
  return status;
}
