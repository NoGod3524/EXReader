/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
#include <ctype.h>
exr_status exr_number_text(exr_buffer *out,int value,const char *format,exr_error *e) {
  char text[100]; int n=value;
  if(!out || !format) return exr_fail(e,EXR_ARGUMENT,"Missing numbering format/output");
  if(!strcmp(format,"decimal") || !strcmp(format,"decimalZero") ||
     (n<=0 && (!strcmp(format,"lowerLetter") || !strcmp(format,"upperLetter") || !strcmp(format,"lowerRoman") || !strcmp(format,"upperRoman")))) {
    int size=snprintf(text,sizeof(text),!strcmp(format,"decimalZero") ? "%02d" : "%d",n);
    if(!exr_append(out,text,(size_t)size)) goto limit;
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
