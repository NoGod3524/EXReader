#include "bounded_txt.h"
#include <stdlib.h>
#include <string.h>
#define WINDOW_BYTES 65536u
#define WINDOW_LINES 512u
static exr_status fail(exr_error *e, exr_status s, const char *message) {
  if (e) { e->code=s; strncpy(e->message,message,sizeof(e->message)-1); e->message[sizeof(e->message)-1]=0; }
  return s;
}
exr_status bounded_txt_next(const exr_source *source, uint64_t *cursor,
                            exr_document **out, exr_error *e) {
  unsigned char *data; size_t available, used=0, end=0, lines=0, i; exr_status s;
  if (!out) return fail(e,EXR_ARGUMENT,"Missing output");
  *out=NULL;
  if (!source || !source->read_at || !cursor || *cursor>source->size)
    return fail(e,EXR_ARGUMENT,"Invalid source or cursor");
  if (source->size>128u*1024u*1024u) return fail(e,EXR_LIMIT,"Source exceeds frozen input limit");
  if (source->control.cancelled && source->control.cancelled(source->control.context))
    return fail(e,EXR_CANCELLED,"Cancelled before read");
  if (*cursor==source->size) return EXR_OK;
  available=(size_t)((source->size-*cursor)<WINDOW_BYTES ? source->size-*cursor : WINDOW_BYTES);
  data=(unsigned char *)malloc(available);
  if (!data) return fail(e,EXR_MEMORY,"Window allocation failed");
  while (used<available) {
    size_t n;
    if (source->control.cancelled && source->control.cancelled(source->control.context)) { free(data); return fail(e,EXR_CANCELLED,"Cancelled during read"); }
    n=source->read_at(source->context,*cursor+used,data+used,available-used);
    if (!n || n>available-used) { free(data); return fail(e,EXR_IO,"Source read failed"); }
    used+=n;
  }
  if (available>=2 && !*cursor && ((data[0]==0xff && data[1]==0xfe) || (data[0]==0xfe && data[1]==0xff))) {
    free(data); return fail(e,EXR_UNSUPPORTED,"UTF-16 is not yet supported by this candidate");
  }
  if (*cursor && available>=3 && data[0]==0xef && data[1]==0xbb && data[2]==0xbf) {
    free(data); return fail(e,EXR_UNSUPPORTED,"BOM at a window boundary");
  }
  for (i=0;i<available;i++) {
    if (data[i]=='\r') { free(data); return fail(e,EXR_UNSUPPORTED,"CR line endings are not yet supported"); }
    if (data[i]=='\n') { end=i+1; if (++lines==WINDOW_LINES) break; }
  }
  if (i==available && *cursor+available==source->size) end=available;
  if (!end) { free(data); return fail(e,EXR_LIMIT,"Line exceeds candidate window"); }
  s=exr_document_open_memory(EXR_TXT,data,end,out,e);
  free(data);
  if (s!=EXR_OK) return s;
  if (source->control.cancelled && source->control.cancelled(source->control.context)) {
    exr_document_free(*out); *out=NULL; return fail(e,EXR_CANCELLED,"Cancelled before commit");
  }
  *cursor+=end;
  return EXR_OK;
}
