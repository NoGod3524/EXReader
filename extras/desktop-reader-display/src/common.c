/* SPDX-License-Identifier: MIT */
#include "common.h"
int exr_display_valid_options(const exr_display_options *o) {
  size_t n=0, i=0;
  const unsigned char *s;
  if (!o || o->struct_size!=sizeof(*o) || !o->native_window || !o->reason ||
      o->lease_ms<EXR_DISPLAY_MIN_LEASE_MS || o->lease_ms>EXR_DISPLAY_MAX_LEASE_MS) return 0;
  s=(const unsigned char *)o->reason;
  while(n<=EXR_DISPLAY_MAX_REASON_BYTES && s[n]) ++n;
  if (!n || n>EXR_DISPLAY_MAX_REASON_BYTES) return 0;
  while(i<n) {
    unsigned c=s[i++], k=0, minimum=0;
    if (c<0x20 || c==0x7f) return 0;
    if(c<0x80) continue;
    if(c>=0xc2 && c<=0xdf) { c &=31; k=1; minimum=0x80; }
    else if(c>=0xe0 && c<=0xef) { c &=15; k=2; minimum=0x800; }
    else if(c>=0xf0 && c<=0xf4) { c &=7; k=3; minimum=0x10000; }
    else return 0;
    if(i+k>n) return 0;
    while(k--) { unsigned b=s[i++]; if((b&0xc0)!=0x80) return 0; c=(c<<6)|(b&63); }
    if(c<minimum || c>0x10ffff || (c>=0xd800 && c<=0xdfff) || (c>=0x80 && c<=0x9f)) return 0;
  }
  return 1;
}
const char *exr_display_status_name(exr_display_status s) {
  static const char *const names[]={"OK","ARGUMENT","NO_MEMORY","LIMIT","WRONG_THREAD","REENTRANT","INACTIVE","PENDING","UNAVAILABLE","CANCELLED","EXPIRED","WINDOW_GONE"};
  return (unsigned)s<sizeof(names)/sizeof(names[0]) ? names[s] : "UNKNOWN";
}
#ifndef EXR_DISPLAY_SOURCE_SHA
#define EXR_DISPLAY_SOURCE_SHA "unversioned"
#endif
const char *exr_display_build_id(void) { return EXR_DISPLAY_SOURCE_SHA; }
