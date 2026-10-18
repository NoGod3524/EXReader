/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
typedef struct { size_t struct_size; exr_font *fallback_font; exr_control control; } original_fixed_options;
_Static_assert(sizeof(original_fixed_options)==offsetof(exr_fixed_open_options,pdf_password),"Original fixed open options retain their prefix");
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
typedef struct {
  size_t struct_size; const char *title; const exr_fixed_page *pages; size_t page_count;
  exr_fixed_draw_fn draw; void *context; exr_context_release_fn release;
} old_fixed_input;
typedef struct {
  size_t struct_size; const char *title; const exr_fixed_page *pages; size_t page_count;
  exr_fixed_draw_fn draw; void *context; exr_context_release_fn release; exr_fixed_text_fn text;
} text_fixed_input;
typedef struct {
  size_t struct_size; const char *title; const exr_fixed_page *pages; size_t page_count;
  exr_fixed_draw_fn draw; void *context; exr_context_release_fn release; exr_fixed_text_fn text; exr_fixed_metadata_fn metadata;
} metadata_fixed_input;
_Static_assert(sizeof(metadata_fixed_input)==offsetof(exr_fixed_input,annotations),"Metadata-capable input prefix must retain its layout");
_Static_assert(sizeof(text_fixed_input)==offsetof(exr_fixed_input,metadata),"Text-capable input prefix must retain its layout");
_Static_assert(sizeof(old_fixed_input)==offsetof(exr_fixed_input,text),"Original input prefix must retain its layout");
static exr_status draw(void *context,size_t page,const double matrix[6],const exr_draw_sink *sink,const exr_control *control,exr_error *e) {
  (void)context; (void)page; (void)matrix; (void)sink; (void)control; (void)e; return EXR_OK;
}
int main(void) {
  old_fixed_input input={0}; exr_fixed_page page={0}; exr_fixed_document *d=NULL; const exr_fixed_page *pages; size_t count;
  CHECK(exr_abi_version()==EXR_ABI_VERSION && EXR_ABI_VERSION==1); CHECK(!strcmp(exr_version(),EXR_VERSION));
  CHECK(EXR_CANCELLED==9 && EXR_PASSWORD==10 && EXR_UNSUPPORTED==11);
  { original_fixed_options options={0}; options.struct_size=sizeof(options);
    CHECK(exr_fixed_open_memory(EXR_PDF,"%PDF-1.7",8,(const exr_fixed_open_options *)&options,&d,&error)==EXR_FORMAT && !d);
  }
  page.id="original"; page.geometry.bounds[2]=100; page.geometry.bounds[3]=80; page.geometry.unit_scale=1;
  input.struct_size=sizeof(input); input.title="Prefix consumer"; input.pages=&page; input.page_count=1; input.draw=draw;
  CHECK(exr_fixed_create((const exr_fixed_input *)&input,&d,&error)==EXR_OK);
  pages=exr_fixed_pages(d,&count); CHECK(count==1 && !strcmp(pages[0].id,"original") && !strcmp(exr_fixed_title(d),input.title));
  { exr_fixed_text *text=(exr_fixed_text *)(uintptr_t)1; CHECK(exr_fixed_load_text(d,0,NULL,&text,&error)==EXR_FORMAT && !text); }
  exr_fixed_free(d);
  { text_fixed_input older={0}; exr_metadata_entry *entries=NULL; size_t n;
    older.struct_size=sizeof(older); older.pages=&page; older.page_count=1; older.draw=draw;
    CHECK(exr_fixed_create((const exr_fixed_input *)&older,&d,&error)==EXR_OK);
    CHECK(exr_fixed_load_metadata(d,NULL,&entries,&n,&error)==EXR_FORMAT && !entries && !n);
    exr_fixed_free(d);
  }
  printf("%u ABI compatibility checks passed\n",checks); return 0;
}
