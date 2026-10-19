/* SPDX-License-Identifier: MIT */
#include "pdf_internal.h"
typedef struct { uint16_t name,offset,count; } pdf_name_mapping;
typedef struct { const char *name; const uint16_t *glyphs; } pdf_encoding_vector;
typedef struct { uint16_t name,width; } pdf_width_entry;
typedef struct { const char *name; const pdf_width_entry *entries; size_t count; } pdf_standard_metrics;
#include "pdf_font_data.h"
#define COUNT(a) (sizeof(a)/sizeof(*(a)))

static unsigned name_id(const char *name) {
  size_t low=0,high=COUNT(pdf_glyph_offsets);
  while(low<high) {
    size_t mid=low+(high-low)/2; int cmp=strcmp(name,pdf_glyph_names+pdf_glyph_offsets[mid]);
    if(cmp>0) low=mid+1; else if(cmp<0) high=mid; else return (unsigned)mid;
  }
  return UINT_MAX;
}
const char *exr_pdf_encoding_glyph(const char *encoding,unsigned code) {
  size_t i;
  if(!encoding || code>255) return NULL;
  for(i=0;i<COUNT(pdf_encodings);i++) if(!strcmp(encoding,pdf_encodings[i].name)) {
    const char *name=pdf_glyph_names+pdf_glyph_offsets[pdf_encodings[i].glyphs[code]];
    return *name ? name : NULL;
  }
  return NULL;
}
int exr_pdf_standard_font(const char *name) {
  size_t i;
  if(!name) return 0;
  if(!strcmp(name,"Courier") || !strcmp(name,"Courier-Bold") || !strcmp(name,"Courier-Oblique") || !strcmp(name,"Courier-BoldOblique")) return 1;
  for(i=0;i<COUNT(pdf_metrics);i++) if(!strcmp(name,pdf_metrics[i].name)) return 1;
  return 0;
}
int exr_pdf_standard_width(const char *font,const char *glyph,double *width) {
  size_t i; unsigned id;
  if(!font || !glyph || !width) return 0;
  if(!strcmp(font,"Courier") || !strcmp(font,"Courier-Bold") || !strcmp(font,"Courier-Oblique") || !strcmp(font,"Courier-BoldOblique")) { *width=600; return 1; }
  id=name_id(glyph); if(id==UINT_MAX) return 0;
  for(i=0;i<COUNT(pdf_metrics);i++) if(!strcmp(font,pdf_metrics[i].name)) {
    const pdf_standard_metrics *m=&pdf_metrics[i]; size_t low=0,high=m->count;
    while(low<high) {
      size_t mid=low+(high-low)/2;
      if(m->entries[mid].name<id) low=mid+1; else if(m->entries[mid].name>id) high=mid;
      else { *width=m->entries[mid].width; return 1; }
    }
    break;
  }
  return 0;
}
static const pdf_name_mapping *mapping(const pdf_name_mapping *rows,size_t count,unsigned id) {
  size_t low=0,high=count;
  while(low<high) {
    size_t mid=low+(high-low)/2;
    if(rows[mid].name<id) low=mid+1; else if(rows[mid].name>id) high=mid; else return rows+mid;
  }
  return NULL;
}
static int append_scalar(uint32_t cp,char out[256],size_t *used) {
  unsigned n=cp<0x80 ? 1 : cp<0x800 ? 2 : cp<0x10000 ? 3 : 4;
  if(cp>0x10ffff || (cp>=0xd800 && cp<=0xdfff) || *used+n>=256) return 0;
  if(n==1) out[(*used)++]=(char)cp;
  else {
    unsigned i; out[(*used)++]=(char)((n==2 ? 0xc0 : n==3 ? 0xe0 : 0xf0)|(cp>>(6*(n-1))));
    for(i=n-1;i;i--) out[(*used)++]=(char)(0x80|((cp>>(6*(i-1)))&63));
  }
  return 1;
}
static int hex_scalar(const char *s,size_t n,uint32_t *out) {
  size_t i; uint32_t cp=0;
  for(i=0;i<n;i++) {
    unsigned v=(unsigned char)s[i];
    if(v>='0' && v<='9') v-='0'; else if(v>='A' && v<='F') v=v-'A'+10; else return 0;
    cp=(cp<<4)|v;
  }
  if(cp>0x10ffff || (cp>=0xd800 && cp<=0xdfff)) return 0;
  *out=cp; return 1;
}
size_t exr_pdf_glyph_unicode(const char *name,int dingbats,char out[256]) {
  char copy[128],*part,*end; size_t n,used=0;
  if(!out) return 0;
  out[0]=0; if(!name || (n=strlen(name))>=sizeof(copy)) return 0;
  memcpy(copy,name,n+1); end=strchr(copy,'.'); if(end) *end=0;
  for(part=copy;part;part=end) {
    const pdf_name_mapping *m; unsigned id; size_t i,len;
    end=strchr(part,'_'); if(end) *end++=0;
    id=name_id(part); m=mapping(pdf_agl,COUNT(pdf_agl),id);
    if(!m && dingbats) m=mapping(pdf_dingbats,COUNT(pdf_dingbats),id);
    if(m) {
      for(i=0;i<m->count;i++) if(!append_scalar(pdf_name_scalars[m->offset+i],out,&used)) goto invalid;
      continue;
    }
    len=strlen(part);
    if(len>3 && !memcmp(part,"uni",3) && (len-3)%4==0) {
      /* Validate the entire component before appending any of it. */
      uint32_t cp=0;
      for(i=3;i<len;i+=4) if(!hex_scalar(part+i,4,&cp)) break;
      if(i<len) continue;
      for(i=3;i<len;i+=4) { hex_scalar(part+i,4,&cp); if(!append_scalar(cp,out,&used)) goto invalid; }
    } else if(len>=5 && len<=7 && part[0]=='u') {
      uint32_t cp; if(hex_scalar(part+1,len-1,&cp) && !append_scalar(cp,out,&used)) goto invalid;
    }
    /* AGL specifies an empty sequence for an unrecognized component. */
  }
  out[used]=0; return used;
invalid:
  out[0]=0; return 0;
}
