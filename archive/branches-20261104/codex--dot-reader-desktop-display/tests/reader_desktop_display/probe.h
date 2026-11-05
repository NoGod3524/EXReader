/* SPDX-License-Identifier: MIT */
#include <exr_desktop_display.h>
#include <stdio.h>
#include <string.h>
static int failures;
static void result(const char *name,int pass) {
  printf("{\"case\":\"%s\",\"result\":\"%s\",\"module\":\"%s\"}\n",name,pass?"PASS":"FAIL",exr_display_build_id());
  fflush(stdout); if(!pass) ++failures;
}
static void unavailable(const char *name,const char *detail) {
  printf("{\"case\":\"%s\",\"result\":\"UNAVAILABLE\",\"detail\":\"%s\",\"module\":\"%s\"}\n",name,detail,exr_display_build_id()); fflush(stdout);
}
static exr_display_observation snapshot(exr_display_lease *l) {
  exr_display_observation o; memset(&o,0,sizeof(o)); o.struct_size=sizeof(o);
  if(exr_display_observe(l,&o)!=EXR_DISPLAY_OK) ++failures;
  return o;
}
static void boundaries(void *window) {
  exr_display_options o={sizeof(o),window,"Reading",1000}; exr_display_lease *l=NULL;
  exr_display_lease *many[EXR_DISPLAY_MAX_LEASES]={0}; unsigned i; int ok=1;
  result("null_options",exr_display_create(NULL,&l)==EXR_DISPLAY_ARGUMENT && !l);
  o.struct_size=0; result("bad_options_size",exr_display_create(&o,&l)==EXR_DISPLAY_ARGUMENT && !l); o.struct_size=sizeof(o);
  o.reason="\xc0\xaf"; result("bad_utf8",exr_display_create(&o,&l)==EXR_DISPLAY_ARGUMENT && !l);
  o.reason="\xed\xa0\x80"; result("surrogate_utf8",exr_display_create(&o,&l)==EXR_DISPLAY_ARGUMENT && !l);
  o.reason="bad\nreason"; result("control_reason",exr_display_create(&o,&l)==EXR_DISPLAY_ARGUMENT && !l);
  o.reason="Reading"; o.lease_ms=99; result("lease_lower_bound",exr_display_create(&o,&l)==EXR_DISPLAY_ARGUMENT);
  o.lease_ms=600001; result("lease_upper_bound",exr_display_create(&o,&l)==EXR_DISPLAY_ARGUMENT); o.lease_ms=1000;
  { char s[258]; memset(s,'a',257); s[257]=0; o.reason=s;
    result("reason_upper_bound",exr_display_create(&o,&l)==EXR_DISPLAY_ARGUMENT);
    s[256]=0; result("reason_exact_bound",exr_display_create(&o,&l)==EXR_DISPLAY_OK); exr_display_close(l); }
  o.reason="Reading \xe4\xb9\xa6";
  for(i=0;i<EXR_DISPLAY_MAX_LEASES;i++) if(exr_display_create(&o,&many[i])!=EXR_DISPLAY_OK) ok=0;
  result("lease_count_bound",ok && exr_display_create(&o,&l)==EXR_DISPLAY_LIMIT && !l);
  for(i=0;i<EXR_DISPLAY_MAX_LEASES;i++) exr_display_close(many[i]);
  result("lease_count_recovered",exr_display_create(&o,&l)==EXR_DISPLAY_OK);
  if(l) {
    exr_display_observation before,after; memset(&before,0xa5,sizeof(before)); before.struct_size=0; after=before;
    result("observe_failure_atomic",exr_display_observe(l,&after)==EXR_DISPLAY_ARGUMENT && !memcmp(&before,&after,sizeof(after)));
    result("invalid_active_atomic",exr_display_set_active(l,2)==EXR_DISPLAY_ARGUMENT && snapshot(l).state==EXR_DISPLAY_INACTIVE);
    exr_display_close(l);
  }
  result("close_null",exr_display_close(NULL)==EXR_DISPLAY_OK);
}
