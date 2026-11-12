/* SPDX-License-Identifier: MIT */
#include "base_internal.h"
#include <ctype.h>
exr_status exr_number_text(exr_buffer *out,int value,const char *format,exr_error *e) {
  char text[100]; int n=value;
  if(!out || !format) return exr_fail(e,EXR_ARGUMENT,"Missing numbering format/output");
  if(!strcmp(format,"none")) return EXR_OK;
  if(!strcmp(format,"bullet")) {
    if(!exr_append(out,"\xe2\x80\xa2",3)) goto limit;
    return EXR_OK;
  }
  if(!strcmp(format,"decimal") || !strcmp(format,"decimalZero") || !strcmp(format,"decimalFullWidth") ||
     (n<=0 && (!strcmp(format,"lowerLetter") || !strcmp(format,"upperLetter") || !strcmp(format,"lowerRoman") || !strcmp(format,"upperRoman")))) {
    int size=snprintf(text,sizeof(text),!strcmp(format,"decimalZero") ? "%02d" : "%d",n);
    if(!exr_append(out,text,(size_t)size)) goto limit;
    return EXR_OK;
  }
  if(!strcmp(format,"ordinal")) {
    int m=n%100,size=snprintf(text,sizeof(text),"%d%s",n,(m>=11 && m<=13) ? "th" : (n%10)==1 ? "st" : (n%10)==2 ? "nd" : (n%10)==3 ? "rd" : "th");
    if(!exr_append(out,text,(size_t)size)) goto limit;
    return EXR_OK;
  }
  if(!strcmp(format,"chineseCounting") || !strcmp(format,"chineseCountingThousand") ||
     !strcmp(format,"taiwaneseCounting") || !strcmp(format,"japaneseCounting") ||
     !strcmp(format,"chineseLegalSimplified") || !strcmp(format,"ideographLegalTraditional")) {
    static const char *const std_d[]={"\xe3\x80\x87","\xe4\xb8\x80","\xe4\xba\x8c","\xe4\xb8\x89","\xe5\x9b\x9b","\xe4\xba\x94","\xe5\x85\xad","\xe4\xb8\x83","\xe5\x85\xab","\xe4\xb9\x9d","\xe5\x8d\x81"};
    static const char *const lgl_d[]={"\xe9\x9b\xb6","\xe5\xa3\xb9","\xe8\xb4\xb0","\xe5\x8f\x81","\xe8\x82\x86","\xe4\xbc\x8d","\xe9\x99\x86","\xe6\x9f\x92","\xe6\x8d\x8c","\xe7\x8e\x96","\xe6\x8b\xbe"};
    int legal=!strcmp(format,"chineseLegalSimplified") || !strcmp(format,"ideographLegalTraditional");
    const char *const *d=legal ? lgl_d : std_d;
    if(n>=1 && n<=9) {
      if(!exr_append(out,d[n],strlen(d[n]))) goto limit;
    } else if(n>=10 && n<=99) {
      if((n>=20 || legal) && !exr_append(out,d[n/10],strlen(d[n/10]))) goto limit;
      if(!exr_append(out,d[10],strlen(d[10]))) goto limit;
      if((n%10) && !exr_append(out,d[n%10],strlen(d[n%10]))) goto limit;
    } else {
      int size=snprintf(text,sizeof(text),"%d",n);
      if(!exr_append(out,text,(size_t)size)) goto limit;
    }
    return EXR_OK;
  }
  if(!strcmp(format,"ideographTraditional") || !strcmp(format,"ideographZodiac")) {
    static const char *const stems[]={"\xe7\x94\xb2","\xe4\xb9\x99","\xe4\xb8\x99","\xe4\xb8\x81","\xe6\x88\x8a","\xe5\xb7\xb1","\xe5\xba\x9a","\xe8\xbe\x9b","\xe5\xa3\xac","\xe7\x99\xb8"};
    static const char *const branch[]={"\xe5\xad\x90","\xe4\xb8\x91","\xe5\xaf\x85","\xe5\x8d\xaf","\xe8\xbe\xb0","\xe5\xb7\xb3","\xe5\x8d\x88","\xe6\x9c\xaa","\xe7\x94\xb3","\xe9\x85\x89","\xe6\x88\x8c","\xe4\xba\xa5"};
    int z=!strcmp(format,"ideographZodiac"),lim=z ? 12 : 10;
    const char *const *tbl=z ? branch : stems;
    if(n>=1 && n<=lim) {
      if(!exr_append(out,tbl[n-1],strlen(tbl[n-1]))) goto limit;
    } else {
      int size=snprintf(text,sizeof(text),"%d",n);
      if(!exr_append(out,text,(size_t)size)) goto limit;
    }
    return EXR_OK;
  }
  if(!strcmp(format,"decimalEnclosedCircle") || !strcmp(format,"decimalEnclosedCircleChinese") ||
     !strcmp(format,"ideographEnclosedCircle") || !strcmp(format,"decimalEnclosedParen") ||
     !strcmp(format,"decimalEnclosedFullstop")) {
    if(n>=1 && n<=20 && (!strcmp(format,"decimalEnclosedCircle") || !strcmp(format,"decimalEnclosedCircleChinese") || !strcmp(format,"ideographEnclosedCircle"))) {
      unsigned char u[3]={0xe2,0x91,(unsigned char)(0xa0+n-1)};
      if(!exr_append(out,(const char *)u,3)) goto limit;
    } else {
      int size=snprintf(text,sizeof(text),"%d",n);
      if(!exr_append(out,text,(size_t)size)) goto limit;
    }
    return EXR_OK;
  }
  if(!strcmp(format,"lowerLetter") || !strcmp(format,"upperLetter")) {
    size_t used=0; int upper=!strcmp(format,"upperLetter");
    while(n>0) { text[used++]=(char)((upper ? 'A' : 'a')+(n-1)%26); n=(n-1)/26; }
    while(used) if(!exr_append(out,&text[--used],1)) goto limit;
    return EXR_OK;
  }
  if(!strcmp(format,"lowerRoman") || !strcmp(format,"upperRoman")) {
    const int values[]={1000,900,500,400,100,90,50,40,10,9,5,4,1};
    const char *labels[]={"M","CM","D","CD","C","XC","L","XL","X","IX","V","IV","I"}; size_t i;
    if(n>3999) { int size=snprintf(text,sizeof(text),"%d",n); if(!exr_append(out,text,(size_t)size)) goto limit; return EXR_OK; }
    for(i=0;i<13;i++) while(n>=values[i]) {
      const char *p=labels[i]; n-=values[i];
      while(*p) { char c=!strcmp(format,"lowerRoman") ? (char)tolower((unsigned char)*p) : *p; if(!exr_append(out,&c,1)) goto limit; p++; }
    }
    return EXR_OK;
  }
  return exr_fail(e,EXR_FORMAT,"Unsupported numbering format: %.80s",format);
limit:
  return exr_fail(e,EXR_LIMIT,"Numbering text exceeds allocation budget");
}
