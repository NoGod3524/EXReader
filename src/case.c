/* SPDX-License-Identifier: MIT */
#include "case_internal.h"
#include "case_unicode_data.h"
#include <string.h>

unsigned exr_case_properties(uint32_t cp) {
  size_t lo=0,hi=sizeof(exr_case_properties_data)/sizeof(*exr_case_properties_data);
  while(lo<hi) {
    size_t mid=lo+(hi-lo)/2;const exr_case_range *r=exr_case_properties_data+mid;
    if(cp<r->first) hi=mid;else if(cp>r->last) lo=mid+1;else return r->properties;
  }
  return 0;
}
static int locale(const char *language,const char *key) {
  return language && language[0]==key[0] && language[1]==key[1] && (!language[2] || language[2]=='-');
}
static int preceded(const uint32_t *text,size_t at,unsigned wanted) {
  while(at) {
    unsigned p=exr_case_properties(text[--at]);
    if(p&EXR_CASE_IGNORABLE) continue;
    return !!(p&wanted);
  }
  return 0;
}
static int followed(const uint32_t *text,size_t count,size_t at,unsigned wanted) {
  while(++at<count) {
    unsigned p=exr_case_properties(text[at]);
    if(p&EXR_CASE_IGNORABLE) continue;
    return !!(p&wanted);
  }
  return 0;
}
static int after(const uint32_t *text,size_t at,int dotted) {
  while(at) {
    uint32_t cp=text[--at];unsigned p=exr_case_properties(cp),ccc=p>>6;
    if(dotted ? !!(p&EXR_CASE_SOFT_DOTTED) : cp==0x49) return 1;
    if(!ccc || ccc==230) break;
  }
  return 0;
}
static int ahead(const uint32_t *text,size_t count,size_t at,int dot) {
  while(++at<count) {
    unsigned ccc=exr_case_properties(text[at])>>6;
    if(dot ? text[at]==0x307 : ccc==230) return 1;
    if(!ccc || (dot && ccc==230)) break;
  }
  return 0;
}
unsigned exr_case_map(const uint32_t *text,size_t count,size_t at,unsigned mode,
                       const char *language,uint32_t output[3]) {
  uint32_t cp=text[at];size_t lo=0,hi=sizeof(exr_case_mappings)/sizeof(*exr_case_mappings);
  int turkic=locale(language,"tr") || locale(language,"az");
  output[0]=cp;
  if(mode==EXR_CASE_LITERAL) return 1;
  if(mode==EXR_CASE_LOWER && cp==0x3a3 && preceded(text,at,EXR_CASE_CASED) && !followed(text,count,at,EXR_CASE_CASED)) { output[0]=0x3c2;return 1; }
  if(turkic) {
    if(mode==EXR_CASE_LOWER) {
      if(cp==0x130) { output[0]=0x69;return 1; }
      if(cp==0x307 && after(text,at,0)) return 0;
      if(cp==0x49 && !ahead(text,count,at,1)) { output[0]=0x131;return 1; }
    } else if(cp==0x69) { output[0]=0x130;return 1; }
  }
  if(locale(language,"lt")) {
    if(mode!=EXR_CASE_LOWER && cp==0x307 && after(text,at,1)) return 0;
    if(mode==EXR_CASE_LOWER) {
      if((cp==0x49 || cp==0x4a || cp==0x12e) && ahead(text,count,at,0)) {
        output[0]=cp==0x12e ? 0x12f : cp+32;output[1]=0x307;return 2;
      }
      if(cp==0xcc || cp==0xcd || cp==0x128) {
        output[0]=0x69;output[1]=0x307;output[2]=cp==0xcc ? 0x300 : cp==0xcd ? 0x301 : 0x303;return 3;
      }
    }
  }
  while(lo<hi) { size_t mid=lo+(hi-lo)/2;if(exr_case_mappings[mid].cp<cp) lo=mid+1;else hi=mid; }
  if(lo<sizeof(exr_case_mappings)/sizeof(*exr_case_mappings) && exr_case_mappings[lo].cp==cp) {
    const exr_case_mapping *m=exr_case_mappings+lo;
    memcpy(output,m->values[mode],m->size[mode]*sizeof(*output));return m->size[mode];
  }
  return 1;
}
unsigned exr_case_word(const uint32_t *text,size_t count,size_t *first_cased) {
  size_t i;int upper=1,lower=1,title=1;*first_cased=SIZE_MAX;
  for(i=0;i<count;i++) {
    unsigned p=exr_case_properties(text[i]);if(!(p&EXR_CASE_CASED)) continue;
    upper&=!!(p&EXR_CASE_UPPERCASE);lower&=!!(p&EXR_CASE_LOWERCASE);
    if(*first_cased==SIZE_MAX) { *first_cased=i;title&=!!(p&(EXR_CASE_UPPERCASE|EXR_CASE_TITLECASE)); }
    else title&=!!(p&EXR_CASE_LOWERCASE);
  }
  return *first_cased==SIZE_MAX ? EXR_CASE_LITERAL : upper ? EXR_CASE_UPPER : lower ? EXR_CASE_LOWER : title ? EXR_CASE_TITLE : EXR_CASE_LITERAL;
}
