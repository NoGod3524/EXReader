/* SPDX-License-Identifier: MIT */
#include "layout_internal.h"
#include "vector_internal.h"
#include FT_TRUETYPE_TABLES_H
#include FT_OUTLINE_H
#define CBLC FT_MAKE_TAG('C','B','L','C')
#define CBDT FT_MAKE_TAG('C','B','D','T')
#define SBIX FT_MAKE_TAG('s','b','i','x')
typedef struct { uint32_t at,end,order; unsigned ppem,ppi; } bitmap_strike;
struct exr_sbix { FT_ULong size; unsigned flags,count; bitmap_strike strikes[]; };
static unsigned be16(const unsigned char *p) { return (unsigned)p[0]<<8|p[1]; }
static uint32_t be32(const unsigned char *p) { return (uint32_t)be16(p)<<16|be16(p+2); }
static int signed16(const unsigned char *p) { unsigned n=be16(p); return n<32768 ? (int)n : (int)n-65536; }
static exr_status field(exr_face *face,FT_ULong tag,FT_ULong size,FT_ULong offset,void *out,size_t n,size_t *work,const exr_control *control,exr_error *error) {
  FT_ULong length=(FT_ULong)n;
  if(offset>size || n>size-offset) return exr_fail(error,EXR_FONT,"Font bitmap field exceeds table");
  if(!exr_vector_work(work,n)) return exr_fail(error,EXR_LIMIT,"Font bitmap read/work budget exceeded");
  if(exr_control_cancel(control,error)!=EXR_OK) return EXR_CANCELLED;
  if(!n) return EXR_OK;
  if(FT_Load_Sfnt_Table(face->face,tag,(FT_Long)offset,out,&length) || length!=n) return exr_fail(error,EXR_FONT,"Cannot read font bitmap field");
  return EXR_OK;
}
static int strike_order(const void *a,const void *b) {
  const bitmap_strike *x=a,*y=b; return x->at<y->at ? -1 : x->at>y->at ? 1 : x->order<y->order ? -1 : x->order>y->order;
}
void exr_font_bitmaps_free(exr_face *face) { free(face->sbix); free(face->cblc); face->sbix=NULL; face->cblc=NULL; face->sbix_checked=face->cblc_checked=0; }
static exr_status directory(exr_face *face,size_t *work,const exr_control *control,exr_error *error) {
  FT_ULong size=0; FT_Error code; struct exr_sbix *table=NULL; unsigned char header[8],offsets[1024];
  unsigned count,i,j; uint64_t minimum; exr_status status;
  if(face->sbix_checked) return EXR_OK;
  code=FT_Load_Sfnt_Table(face->face,SBIX,0,NULL,&size);
  if(code==FT_Err_Table_Missing || code==FT_Err_Invalid_Face_Handle || code==FT_Err_Invalid_Argument) { face->sbix_checked=1; return EXR_OK; }
  if(code || size>UINT32_MAX) return exr_fail(error,EXR_FONT,"Cannot locate sbix table");
  status=field(face,SBIX,size,0,header,8,work,control,error); if(status!=EXR_OK) return status;
  if(be16(header)!=1 || !(be16(header+2)&1) || (be16(header+2)&~3u)) return exr_fail(error,EXR_FONT,"Unsupported sbix version/flags");
  count=be32(header+4); if(count>256) return exr_fail(error,EXR_LIMIT,"sbix exceeds 256 strikes");
  status=field(face,SBIX,size,8,offsets,4*count,work,control,error); if(status!=EXR_OK) return status;
  table=calloc(1,sizeof(*table)+count*sizeof(*table->strikes)); if(!table) return exr_fail(error,EXR_MEMORY,"sbix strike allocation failed");
  table->size=size; table->flags=be16(header+2); table->count=count;
  minimum=4+((uint64_t)face->face->num_glyphs+1)*4;
  for(i=0;i<count;i++) table->strikes[i]=(bitmap_strike){be32(offsets+4*i),(uint32_t)size,i,0,0};
  qsort(table->strikes,count,sizeof(*table->strikes),strike_order);
  for(i=0;i<count;i++) {
    bitmap_strike *strike=table->strikes+i;
    for(j=i+1;j<count;j++) if(table->strikes[j].at>strike->at) { strike->end=table->strikes[j].at; break; }
    if(strike->at<8+4*count || strike->at>strike->end || minimum>strike->end-strike->at) { status=exr_fail(error,EXR_FONT,"Invalid sbix strike boundaries"); goto done; }
    status=field(face,SBIX,size,strike->at,header,4,work,control,error); if(status!=EXR_OK) goto done;
    strike->ppem=be16(header); strike->ppi=be16(header+2);
    if(!strike->ppem) { status=exr_fail(error,EXR_FONT,"Zero sbix strike size"); goto done; }
  }
  face->sbix=table; face->sbix_checked=1; return EXR_OK;
done:
  free(table); return status;
}
static exr_status span(exr_face *face,const bitmap_strike *strike,uint32_t glyph,uint32_t *begin,uint32_t *end,size_t *work,const exr_control *control,exr_error *error) {
  unsigned char bytes[8]; uint64_t minimum=4+((uint64_t)face->face->num_glyphs+1)*4;
  exr_status status=field(face,SBIX,face->sbix->size,strike->at+4+(FT_ULong)glyph*4,bytes,8,work,control,error);
  if(status!=EXR_OK) return status;
  *begin=be32(bytes); *end=be32(bytes+4);
  if(*begin>*end || *end>strike->end-strike->at || (*begin!=*end && (*begin<minimum || *end-*begin<8))) return exr_fail(error,EXR_FONT,"Invalid sbix glyph boundaries");
  return EXR_OK;
}
static exr_status sbix_image(exr_face *face,uint32_t glyph,float pixels,exr_glyph_image *out,size_t *work,const exr_control *control,exr_error *error) {
  const bitmap_strike *selected=NULL; uint32_t begin=0,end=0,chosen_begin=0,chosen_end=0,active[16]; unsigned i,depth=0;
  unsigned char header[8],*encoded=NULL; int x,y; uint32_t original=glyph; exr_status status; double left=0,bottom=0,scale;
  memset(out,0,sizeof(*out));
  status=directory(face,work,control,error); if(status!=EXR_OK || !face->sbix) return status;
  for(i=0;i<face->sbix->count;i++) {
    const bitmap_strike *strike=face->sbix->strikes+i;
    status=span(face,strike,glyph,&begin,&end,work,control,error); if(status!=EXR_OK) return status;
    if(begin==end) continue;
    if(!selected || (strike->ppem>=pixels && (selected->ppem<pixels || strike->ppem<selected->ppem)) ||
       (strike->ppem<pixels && selected->ppem<pixels && strike->ppem>selected->ppem) ||
       (strike->ppem==selected->ppem && strike->order<selected->order)) { selected=strike; chosen_begin=begin; chosen_end=end; }
  }
  if(!selected) return EXR_OK;
  begin=chosen_begin; end=chosen_end;
  for(;;) {
    uint32_t type;
    if(depth==16) return exr_fail(error,EXR_LIMIT,"sbix duplicate depth exceeds 16");
    for(i=0;i<depth;i++) if(active[i]==glyph) return exr_fail(error,EXR_FONT,"Cyclic sbix duplicate glyph");
    active[depth++]=glyph;
    status=field(face,SBIX,face->sbix->size,selected->at+begin,header,8,work,control,error); if(status!=EXR_OK) return status;
    x=signed16(header); y=signed16(header+2); type=be32(header+4);
    if(type!=FT_MAKE_TAG('d','u','p','e')) break;
    if(end-begin!=10) return exr_fail(error,EXR_FONT,"Invalid sbix duplicate record");
    status=field(face,SBIX,face->sbix->size,selected->at+begin+8,header,2,work,control,error); if(status!=EXR_OK) return status;
    glyph=be16(header); if(glyph>=(uint64_t)face->face->num_glyphs) return exr_fail(error,EXR_FONT,"Invalid sbix duplicate glyph ID");
    status=span(face,selected,glyph,&begin,&end,work,control,error); if(status!=EXR_OK) return status;
    if(begin==end) return exr_fail(error,EXR_FONT,"sbix duplicate references an absent image");
  }
  if(be32(header+4)!=FT_MAKE_TAG('p','n','g',' ') && be32(header+4)!=FT_MAKE_TAG('j','p','g',' ')) return exr_fail(error,EXR_FORMAT,"Unsupported sbix image encoding");
  if(end-begin-8>32*1024*1024) return exr_fail(error,EXR_LIMIT,"sbix encoded image exceeds 32 MiB");
  encoded=malloc(end-begin-8 ? end-begin-8 : 1); if(!encoded) return exr_fail(error,EXR_MEMORY,"sbix image allocation failed");
  status=field(face,SBIX,face->sbix->size,selected->at+begin+8,encoded,end-begin-8,work,control,error); if(status!=EXR_OK) goto done;
  if((be32(header+4)==FT_MAKE_TAG('p','n','g',' ') && (end-begin-8<8 || memcmp(encoded,"\x89PNG\r\n\x1a\n",8))) ||
     (be32(header+4)==FT_MAKE_TAG('j','p','g',' ') && (end-begin-8<3 || memcmp(encoded,"\xff\xd8\xff",3)))) { status=exr_fail(error,EXR_FORMAT,"sbix image signature differs from its encoding"); goto done; }
  status=exr_image_decode(encoded,end-begin-8,&out->bitmap,error); if(status!=EXR_OK) goto done;
  if(!exr_vector_work(work,(size_t)out->bitmap.width*out->bitmap.height)) { status=exr_fail(error,EXR_LIMIT,"Font bitmap decode work exceeds budget"); goto done; }
  if(FT_Load_Glyph(face->face,original,FT_LOAD_NO_SCALE|FT_LOAD_NO_HINTING|FT_LOAD_NO_BITMAP)) { status=exr_fail(error,EXR_FONT,"Cannot read bitmap glyph design origin"); goto done; }
  if(face->face->glyph->format==FT_GLYPH_FORMAT_OUTLINE && face->face->glyph->outline.n_contours>0) {
    FT_BBox bounds; FT_Outline_Get_CBox(&face->face->glyph->outline,&bounds);
    left=(double)bounds.xMin*pixels/face->face->units_per_EM; bottom=(double)bounds.yMin*pixels/face->face->units_per_EM;
  }
  scale=(double)pixels/selected->ppem;
  out->scale=(float)scale; out->left=(float)(left+x*scale); out->top=(float)(-bottom-(y+(double)out->bitmap.height)*scale);
  out->flags=(face->sbix->flags&2) ? EXR_GLYPH_IMAGE_OUTLINE_OVERLAY : 0;
  if(out->bitmap.width*scale>8192 || out->bitmap.height*scale>8192 || out->bitmap.width*scale*out->bitmap.height*scale>16*1024*1024 || fabs(out->left)>1e7 || fabs(out->top)>1e7) { status=exr_fail(error,EXR_LIMIT,"Scaled font bitmap exceeds raster limits"); goto done; }
  status=exr_control_cancel(control,error);
done:
  free(encoded); if(status!=EXR_OK) { exr_bitmap_free(&out->bitmap); memset(out,0,sizeof(*out)); } return status;
}
typedef struct { uint32_t at,end,count; unsigned first,last,ppem,flags,depth; } cblc_strike;
struct exr_cblc { FT_ULong size,data_size; unsigned count; cblc_strike strikes[]; };
typedef struct {
  uint32_t png,size; unsigned width,height,advance,vadvance,vertical,ppem;
  int hx,hy,vx,vy;
} bitmap_record;
static int signed8(unsigned char value) { return value<128 ? value : (int)value-256; }
/* Validate arrays once, in bounded reads, before any binary search uses them. */
static exr_status cblc_index(exr_face *face,const struct exr_cblc *table,const cblc_strike *strike,
                            uint32_t at,unsigned first,unsigned last,size_t *work,const exr_control *control,exr_error *error) {
  unsigned char b[1024]; unsigned format,width=0,codes=0; uint32_t base,count,previous=0,previous_code=0,i=0;
  uint64_t array=0,total=0; exr_status status;
#define READ_INDEX(offset,n) do { if((uint64_t)(offset)>strike->end || (n)>strike->end-(uint64_t)(offset)) goto bad; status=field(face,CBLC,strike->end,(FT_ULong)(offset),b,(n),work,control,error); if(status!=EXR_OK) return status; } while(0)
  READ_INDEX(at,8); format=be16(b); base=be32(b+4); count=last-first+1;
  if(base<4 || base>table->data_size) goto bad;
  if(format==1 || format==3) { width=format==1 ? 4 : 2; total=(uint64_t)count+1; array=(uint64_t)at+8; }
  else if(format==2 || format==5) {
    uint32_t image_size;
    READ_INDEX((uint64_t)at+8,12); image_size=be32(b); if(!image_size) goto bad;
    if(format==5) { READ_INDEX((uint64_t)at+20,4); count=be32(b); width=2; codes=1; total=count; array=(uint64_t)at+24; }
    if(count>last-first+1 || (uint64_t)image_size*count>table->data_size-base) goto bad;
  } else if(format==4) {
    READ_INDEX((uint64_t)at+8,4); count=be32(b); if(count>last-first+1) goto bad;
    width=4; codes=2; total=(uint64_t)count+1; array=(uint64_t)at+12;
  } else return exr_fail(error,EXR_FORMAT,"Unsupported CBLC index format");
  if(array>strike->end || total*width>strike->end-array) goto bad;
  while(i<total) {
    unsigned j,n=(unsigned)(total-i); if(n>sizeof(b)/width) n=(unsigned)(sizeof(b)/width);
    READ_INDEX(array+(uint64_t)i*width,(size_t)n*width);
    for(j=0;j<n;j++,i++) {
      const unsigned char *p=b+j*width; uint32_t value=width==2 ? be16(p) : be32(p);
      if(codes && i<count) {
        unsigned code=be16(p);
        if(code<first || code>last || (i && code<=previous_code)) goto bad;
        previous_code=code;
      }
      if(codes!=1) {
        if(codes==2) value=be16(p+2);
        if((i && value<previous) || value>table->data_size-base) goto bad;
        previous=value;
      }
    }
  }
#undef READ_INDEX
  return EXR_OK;
bad:
  return exr_fail(error,EXR_FONT,"Invalid CBLC index data");
}
static exr_status cblc_directory(exr_face *face,size_t *work,const exr_control *control,exr_error *error) {
  FT_ULong size=0,data_size=0; FT_Error code; unsigned char b[48]; unsigned count,i,j; struct exr_cblc *table; exr_status status;
  if(face->cblc_checked) return EXR_OK;
  code=FT_Load_Sfnt_Table(face->face,CBLC,0,NULL,&size);
  if(code==FT_Err_Table_Missing || code==FT_Err_Invalid_Face_Handle || code==FT_Err_Invalid_Argument) { face->cblc_checked=1; return EXR_OK; }
  if(code || size>UINT32_MAX || FT_Load_Sfnt_Table(face->face,CBDT,0,NULL,&data_size) || data_size>UINT32_MAX) return exr_fail(error,EXR_FONT,"Missing CBDT data or invalid bitmap table size");
  status=field(face,CBLC,size,0,b,8,work,control,error); if(status!=EXR_OK) return status;
  if(be32(b)!=UINT32_C(0x00030000)) return exr_fail(error,EXR_FONT,"Unsupported CBLC version");
  count=be32(b+4); if(count>256) return exr_fail(error,EXR_LIMIT,"CBLC exceeds 256 strikes");
  if((uint64_t)count*48>size-8) return exr_fail(error,EXR_FONT,"Truncated CBLC strike list");
  status=field(face,CBDT,data_size,0,b,4,work,control,error); if(status!=EXR_OK) return status;
  if(be32(b)!=UINT32_C(0x00030000)) return exr_fail(error,EXR_FONT,"Unsupported CBDT version");
  table=calloc(1,sizeof(*table)+count*sizeof(*table->strikes)); if(!table) return exr_fail(error,EXR_MEMORY,"CBLC directory allocation failed");
  table->size=size; table->data_size=data_size; table->count=count;
  for(i=0;i<count;i++) {
    cblc_strike *strike=table->strikes+i; uint32_t bytes; unsigned previous=0;
    status=field(face,CBLC,size,8+(FT_ULong)i*48,b,48,work,control,error); if(status!=EXR_OK) goto done;
    strike->at=be32(b); bytes=be32(b+4); strike->count=be32(b+8);
    strike->first=be16(b+40); strike->last=be16(b+42); strike->ppem=b[45]; strike->depth=b[46]; strike->flags=b[47];
    if(strike->count>65536) { status=exr_fail(error,EXR_LIMIT,"CBLC index list exceeds 65536 ranges"); goto done; }
    if(!b[44] || !b[45] || b[44]!=b[45]) { status=exr_fail(error,EXR_FORMAT,"Non-square or zero CBLC ppem is unsupported"); goto done; }
    if(strike->first>strike->last || strike->last>=(uint64_t)face->face->num_glyphs || (strike->flags&~3u) || !strike->flags ||
       strike->at>size || bytes>size-strike->at || (uint64_t)strike->count*8>bytes || (strike->count && strike->at<8+48*count)) goto bad;
    strike->end=strike->at+bytes;
    for(j=0;j<strike->count;j++) {
      uint32_t offset; unsigned first,last;
      status=field(face,CBLC,strike->end,strike->at+(FT_ULong)j*8,b,8,work,control,error); if(status!=EXR_OK) goto done;
      first=be16(b); last=be16(b+2); offset=be32(b+4);
      if(first>last || first<strike->first || last>strike->last || (j && first<=previous) || offset<(uint64_t)strike->count*8 || offset>bytes || bytes-offset<8) goto bad;
      previous=last;
      status=cblc_index(face,table,strike,strike->at+offset,first,last,work,control,error); if(status!=EXR_OK) goto done;
    }
  }
  face->cblc=table; face->cblc_checked=1; return EXR_OK;
bad:
  status=exr_fail(error,EXR_FONT,"Invalid CBLC strike/index boundaries");
done:
  free(table); return status;
}
static void record_metrics(bitmap_record *record,const unsigned char *bytes,int big) {
  record->height=bytes[0]; record->width=bytes[1]; record->hx=signed8(bytes[2]); record->hy=signed8(bytes[3]); record->advance=bytes[4];
  if(big) { record->vertical=1; record->vx=signed8(bytes[5]); record->vy=signed8(bytes[6]); record->vadvance=bytes[7]; }
}
static exr_status cblc_record(exr_face *face,const cblc_strike *strike,uint32_t glyph,bitmap_record *record,
                              size_t *work,const exr_control *control,exr_error *error) {
  uint32_t lo=0,hi=strike->count,at,base,image_size=0,count=0,index=0; unsigned char b[20]; unsigned first,last,format,image_format;
  uint64_t start=0,end=0; exr_status status; int constant_metrics=0;
  memset(record,0,sizeof(*record));
  if(glyph<strike->first || glyph>strike->last) return EXR_OK;
#define READ(offset,output,n) do { status=field(face,CBLC,strike->end,(offset),(output),(n),work,control,error); if(status!=EXR_OK) return status; } while(0)
  while(lo<hi) { uint32_t mid=lo+(hi-lo)/2; READ(strike->at+(FT_ULong)mid*8,b,8); if(be16(b+2)<glyph) lo=mid+1; else hi=mid; }
  if(lo==strike->count) return EXR_OK;
  READ(strike->at+(FT_ULong)lo*8,b,8); first=be16(b); last=be16(b+2);
  if(glyph<first || glyph>last) return EXR_OK;
  at=strike->at+be32(b+4); READ(at,b,8); format=be16(b); image_format=be16(b+2); base=be32(b+4);
  if(format==1 || format==3) {
    unsigned width=format==1 ? 4 : 2;
    if((uint64_t)at+8+((uint64_t)last-first+2)*width>strike->end) goto bad;
    READ(at+8+(FT_ULong)(glyph-first)*width,b,2*width); start=width==4 ? be32(b) : be16(b); end=width==4 ? be32(b+4) : be16(b+2);
  } else if(format==2 || format==5) {
    READ(at+8,b,12); image_size=be32(b); record_metrics(record,b+4,1); constant_metrics=1;
    if(!image_size) goto bad;
    if(format==2) { index=glyph-first; count=last-first+1; }
    else {
      READ(at+20,b,4); count=be32(b); if(count>65536) return exr_fail(error,EXR_LIMIT,"CBLC sparse list exceeds 65536 glyphs");
      if((uint64_t)at+24+(uint64_t)count*2>strike->end) goto bad;
      lo=0; hi=count;
      while(lo<hi) { uint32_t mid=lo+(hi-lo)/2; READ(at+24+(FT_ULong)mid*2,b,2); if(be16(b)<glyph) lo=mid+1; else hi=mid; }
      if(lo==count) return EXR_OK;
      READ(at+24+(FT_ULong)lo*2,b,2); if(be16(b)!=glyph) return EXR_OK; index=lo;
    }
    start=(uint64_t)image_size*index; end=start+image_size;
    if((uint64_t)base+(uint64_t)image_size*count>face->cblc->data_size) goto bad;
  } else if(format==4) {
    READ(at+8,b,4); count=be32(b); if(count>65536) return exr_fail(error,EXR_LIMIT,"CBLC sparse list exceeds 65536 glyphs");
    if((uint64_t)at+12+((uint64_t)count+1)*4>strike->end) goto bad;
    lo=0; hi=count;
    while(lo<hi) { uint32_t mid=lo+(hi-lo)/2; READ(at+12+(FT_ULong)mid*4,b,4); if(be16(b)<glyph) lo=mid+1; else hi=mid; }
    if(lo==count) return EXR_OK;
    READ(at+12+(FT_ULong)lo*4,b,8); if(be16(b)!=glyph) return EXR_OK;
    start=be16(b+2); end=be16(b+6);
  } else return exr_fail(error,EXR_FORMAT,"Unsupported CBLC index format");
#undef READ
  if(start>end || (uint64_t)base+end>face->cblc->data_size || base<4) goto bad;
  if(start==end) { memset(record,0,sizeof(*record)); return EXR_OK; }
  if(strike->depth!=32 || (image_format!=17 && image_format!=18 && image_format!=19)) return exr_fail(error,EXR_FORMAT,"Unsupported CBDT bitmap encoding/depth");
  at=(uint32_t)(base+start);
  if(image_format!=19) {
    unsigned size=image_format==17 ? 5 : 8;
    if(image_format==17 && strike->flags!=1) return exr_fail(error,EXR_FORMAT,"Vertical-only CBDT small metrics are unsupported");
    status=field(face,CBDT,(FT_ULong)(base+end),at,b,size,work,control,error); if(status!=EXR_OK) return status;
    record_metrics(record,b,image_format==18); at+=size;
  } else if(!constant_metrics) goto bad;
  status=field(face,CBDT,(FT_ULong)(base+end),at,b,4,work,control,error); if(status!=EXR_OK) return status;
  record->png=at+4; record->size=be32(b); record->ppem=strike->ppem;
  if(!record->width && !record->height && !record->size) { memset(record,0,sizeof(*record)); return EXR_OK; }
  if(!record->width || !record->height || !record->size || record->size>(uint64_t)base+end-record->png) goto bad;
  if(record->size>32*1024*1024) return exr_fail(error,EXR_LIMIT,"CBDT PNG exceeds 32 MiB");
  return EXR_OK;
bad:
  return exr_fail(error,EXR_FONT,"Invalid CBLC/CBDT glyph record");
}
static exr_status cblc_find(exr_face *face,uint32_t glyph,float pixels,bitmap_record *out,size_t *work,const exr_control *control,exr_error *error) {
  unsigned i; exr_status status=cblc_directory(face,work,control,error); memset(out,0,sizeof(*out));
  if(status!=EXR_OK || !face->cblc) return status;
  for(i=0;i<face->cblc->count;i++) {
    bitmap_record record={0};
    status=cblc_record(face,face->cblc->strikes+i,glyph,&record,work,control,error); if(status!=EXR_OK) return status;
    if(!record.size) continue;
    if(!out->size || (record.ppem>=pixels && (out->ppem<pixels || record.ppem<out->ppem)) || (record.ppem<pixels && out->ppem<pixels && record.ppem>out->ppem)) *out=record;
  }
  return EXR_OK;
}
exr_status exr_font_image(exr_face *face,uint32_t glyph,float pixels,exr_glyph_image *out,size_t *work,const exr_control *control,exr_error *error) {
  bitmap_record record={0}; unsigned char *png=NULL; double scale; exr_status status=sbix_image(face,glyph,pixels,out,work,control,error);
  if(status!=EXR_OK || out->bitmap.pixels) return status;
  status=cblc_find(face,glyph,pixels,&record,work,control,error); if(status!=EXR_OK || !record.size) return status;
  png=malloc(record.size); if(!png) return exr_fail(error,EXR_MEMORY,"CBDT PNG allocation failed");
  status=field(face,CBDT,face->cblc->data_size,record.png,png,record.size,work,control,error); if(status!=EXR_OK) goto done;
  if(record.size<8 || memcmp(png,"\x89PNG\r\n\x1a\n",8)) { status=exr_fail(error,EXR_FORMAT,"Invalid CBDT PNG signature"); goto done; }
  status=exr_image_decode(png,record.size,&out->bitmap,error); if(status!=EXR_OK) goto done;
  if(out->bitmap.width!=record.width || out->bitmap.height!=record.height) { status=exr_fail(error,EXR_FONT,"CBDT metrics differ from PNG dimensions"); goto done; }
  if(!exr_vector_work(work,(size_t)out->bitmap.width*out->bitmap.height)) { status=exr_fail(error,EXR_LIMIT,"Font bitmap decode work exceeds budget"); goto done; }
  scale=(double)pixels/record.ppem; out->scale=(float)scale; out->left=(float)(record.hx*scale); out->top=(float)(-record.hy*scale);
  if(out->bitmap.width*scale>8192 || out->bitmap.height*scale>8192 || out->bitmap.width*scale*out->bitmap.height*scale>16*1024*1024) { status=exr_fail(error,EXR_LIMIT,"Scaled font bitmap exceeds raster limits"); goto done; }
  status=exr_control_cancel(control,error);
done:
  free(png); if(status!=EXR_OK) { exr_bitmap_free(&out->bitmap); memset(out,0,sizeof(*out)); } return status;
}
exr_status exr_font_bitmap_vertical(exr_face *face,uint32_t glyph,float pixels,float *x,float *y,const exr_control *control,exr_error *error) {
  bitmap_record record={0}; size_t work=0; float advance; exr_status status=cblc_find(face,glyph,pixels,&record,&work,control,error);
  *x=*y=0; if(status!=EXR_OK) return status;
  if(record.size) {
    float scale=pixels/record.ppem;
    if(record.vertical) { *x=(record.vx-record.hx)*scale; *y=-(record.vy+record.hy)*scale; }
    else {
      if(exr_measure_vertical(face,glyph,0,&advance)) return exr_fail(error,EXR_FONT,"Cannot measure vertical bitmap glyph");
      *x=-(record.hx+record.width/2.0f)*scale; *y=-record.hy*scale-(advance-record.height*scale)/2;
    }
  }
  return EXR_OK;
}
exr_status exr_font_glyph_image(exr_font *font,size_t index,uint32_t glyph,float pixels,exr_glyph_image *out,const exr_control *control,exr_error *error) {
  size_t work=0; exr_status status;
  if(out) memset(out,0,sizeof(*out));
  if(!font || index>=font->count || !out || glyph>=(uint64_t)font->faces[index].face->num_glyphs || !isfinite(pixels) || pixels<1.0f/64 || pixels>4096) return exr_fail(error,EXR_ARGUMENT,"Invalid font glyph-image query");
  if(exr_control_cancel(control,error)!=EXR_OK) return EXR_CANCELLED;
  status=exr_font_image(font->faces+index,glyph,pixels,out,&work,control,error);
  if(status==EXR_OK && exr_control_cancel(control,error)!=EXR_OK) { exr_bitmap_free(&out->bitmap); memset(out,0,sizeof(*out)); return EXR_CANCELLED; }
  return status==EXR_OK ? exr_fail(error,EXR_OK,"") : status;
}
