/* SPDX-License-Identifier: MIT */
#include "base_internal.h"
#include "pdf_jpx_internal.h"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
exr_status exr_fail(exr_error *e,exr_status code,const char *fmt,...) {
  (void)fmt;if(e) e->code=code;return code;
}
exr_status exr_control_cancel(const exr_control *c,exr_error *e) {
  return c && c->cancelled && c->cancelled(c->context) ? exr_fail(e,EXR_CANCELLED,"cancelled") : EXR_OK;
}
static int cancel(void *context) { (void)context;return 1; }
int main(void) {
  const unsigned char data[]={255,0x4f,255,0x51};
  unsigned char *samples=(unsigned char *)1;size_t size=123;exr_error e={0};
  exr_control control={cancel,NULL,NULL};
  assert(exr_pdf_jpx_decode(data,sizeof(data),1,1,1,8,0,NULL,&samples,&size,&e)==EXR_UNSUPPORTED);
  assert(!samples && !size);
  samples=(unsigned char *)1;size=123;
  assert(exr_pdf_jpx_decode(data,sizeof(data),1,1,1,8,0,&control,&samples,&size,&e)==EXR_CANCELLED);
  assert(!samples && !size);return 0;
}
