/* SPDX-License-Identifier: MIT */
/* Real host text/undo/save path; table/image commands use its same engine model.
   No window, message loop, input injection, or second editor implementation. */
#define WinMain reader_WinMain
#define EXR_READER_TEST_DRIVERS 1
#include "../reader.c"
#undef WinMain

static const char *e2e_step="setup";
#define E2E_CHECK(expr) do { if(!(expr)) { \
  fprintf(stderr,"%s FAIL line=%d check=%s win32=%lu\n",e2e_step,__LINE__,#expr, \
    (unsigned long)GetLastError());exit(1); } } while(0)
#define E2E_OK(expr) do { exr_status status_=(expr); if(status_!=EXR_OK) { \
  fprintf(stderr,"%s FAIL line=%d status=%d call=%s\n",e2e_step,__LINE__,(int)status_,#expr); \
  exit(1); } } while(0)

/* Compare user content, not session IDs or the paragraph wrapper DOCX adds to
   standalone images. Include every cell paragraph and original image byte. */
static void e2e_content(cv_text *out,const exr_edit_block *b) {
  if(b->kind==EXR_EDIT_TABLE && b->table) {
    const exr_edit_table *t=b->table;
    cv_text_string(out,"[table]");
    for(size_t r=0;r<t->row_count;r++) {
      cv_text_string(out,"[row]");
      for(size_t c=0;c<t->rows[r].cell_count;c++) {
        const exr_edit_cell *cell=&t->rows[r].cells[c];
        cv_text_string(out,"[cell]");
        for(size_t p=0;p<cell->block_count;p++)e2e_content(out,&cell->blocks[p]);
      }
    }
    cv_text_string(out,"[/table]");
  } else if(b->kind==EXR_EDIT_PARAGRAPH) {
    size_t bytes=0;
    for(size_t r=0;r<b->run_count;r++)if(b->runs[r].kind==EXR_EDIT_TEXT)bytes+=b->runs[r].text_size;
    if(!bytes)return;
    cv_text_string(out,"[p]");
    char length[48];snprintf(length,sizeof(length),"%zu:",bytes);cv_text_string(out,length);
    for(size_t r=0;r<b->run_count;r++)if(b->runs[r].kind==EXR_EDIT_TEXT)
      cv_text_append(out,b->runs[r].text,b->runs[r].text_size);
    cv_text_string(out,"[/p]");
  } else if(b->kind==EXR_EDIT_PAGE_BREAK)cv_text_string(out,"[page-break]");
}
static char *e2e_snapshot(exr_edit_doc *doc) {
  cv_text out={0};
  for(size_t i=0;i<exr_edit_block_count(doc);i++)e2e_content(&out,exr_edit_block_at(doc,i));
  /* Images are anchor views, enumerated once at top level by the IO bridge. */
  for(size_t i=0;i<exr_edit_block_count(doc);i++) {
    const exr_edit_block *b=exr_edit_block_at(doc,i);
    if(b->kind!=EXR_EDIT_IMAGE || !b->image)continue;
    const exr_edit_image *im=b->image;char dims[128];
    snprintf(dims,sizeof(dims),"[image %lld %lld %u %zu]",(long long)im->width_emu,
      (long long)im->height_emu,im->format,im->size);cv_text_string(&out,dims);
    const unsigned char *bytes=im->data;
    for(size_t j=0;j<im->size;j++) {
      char hex[3];snprintf(hex,sizeof(hex),"%02x",bytes[j]);cv_text_string(&out,hex);
    }
  }
  cv_text_string(&out,"");E2E_CHECK(out.data);return out.data;
}
static void e2e_same(const char *expected) {
  char *actual=e2e_snapshot(de.doc);
  if(strcmp(expected,actual)) {
    size_t offset=0;while(expected[offset] && expected[offset]==actual[offset])offset++;
    fprintf(stderr,"%s FAIL snapshot_expected=%zu snapshot_actual=%zu first_difference=%zu\n",
      e2e_step,strlen(expected),strlen(actual),offset);
    free(actual);exit(1);
  }
  free(actual);
}
static size_t e2e_images(void) {
  size_t count=0;
  for(size_t i=0;i<exr_edit_block_count(de.doc);i++)
    count+=exr_edit_block_at(de.doc,i)->kind==EXR_EDIT_IMAGE;
  return count;
}
static void e2e_retained_parts(exr_edit_doc *before,exr_edit_doc *after) {
  size_t n=0,m=0,matched=0;
  const exr_edit_part *a=exr_edit_parts(before,&n),*b=exr_edit_parts(after,&m);
  for(size_t i=0;i<n;i++) {
    /* These three parts legitimately gain text/drawing/relationship metadata. */
    if(!strcmp(a[i].name,"word/document.xml") || !strcmp(a[i].name,"[Content_Types].xml") ||
      !strcmp(a[i].name,"word/_rels/document.xml.rels"))continue;
    size_t j=0;while(j<m && strcmp(a[i].name,b[j].name))j++;
    E2E_CHECK(j<m && a[i].size==b[j].size);
    E2E_CHECK(!a[i].size || !memcmp(a[i].data,b[j].data,a[i].size));matched++;
  }
  printf("7 PASS retained_parts=%zu byte_equal=1\n",matched);
}

int main(int argc,char **argv) {
  char directory[MAX_PATH],path[MAX_PATH];
  setvbuf(stdout,NULL,_IONBF,0);setvbuf(stderr,NULL,_IONBF,0);
  E2E_CHECK(argc<=2);
  const char *fixture=argc==2 ? argv[1]:EXR_E2E_FIXTURE;
  SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
  E2E_CHECK(SUCCEEDED(CoInitializeEx(NULL,COINIT_APARTMENTTHREADED)));
  E2E_CHECK(SUCCEEDED(shell_d2d_create(NULL,&host_shell)));
  shell_dpi=96;shell_apply_theme();
  wchar_t temp[MAX_PATH],work[MAX_PATH];
  E2E_CHECK(GetTempPathW(MAX_PATH,temp)>0);
  E2E_CHECK(GetTempFileNameW(temp,L"L12",0,work));
  E2E_CHECK(DeleteFileW(work) && CreateDirectoryW(work,NULL));
  E2E_CHECK(WideCharToMultiByte(CP_UTF8,0,work,-1,directory,sizeof(directory),NULL,NULL)>0);
  E2E_CHECK(snprintf(path,sizeof(path),"%s/edited.docx",directory)<(int)sizeof(path));
  copy_wstring(g.data_dir,HOST_PATH,work);
  wchar_t *source=host_wide(fixture,strlen(fixture)),*dest=host_wide(path,strlen(path));
  E2E_CHECK(source && dest);
  E2E_CHECK(wcscmp(source,dest) && CopyFileW(source,dest,TRUE));free(source);
  printf("work_docx=%s\n",path);

  e2e_step="1 open";E2E_CHECK(de_open(path));
  size_t body=SIZE_MAX,table_index=SIZE_MAX,cell_row=0,cell_col=0,cell_run=0;
  exr_edit_id table_id=0,cell_id=0;exr_error error={0};exr_edit_doc *original=NULL;
  E2E_OK(exr_edit_docx_open(fixture,NULL,&original,&error));
  for(size_t i=0;i<exr_edit_block_count(de.doc);i++) {
    const exr_edit_block *b=exr_edit_block_at(de.doc,i);
    if(body==SIZE_MAX && b->kind==EXR_EDIT_PARAGRAPH && b->run_count && b->runs[0].kind==EXR_EDIT_TEXT)body=i;
    if(cell_id || b->kind!=EXR_EDIT_TABLE || !b->table)continue;
    for(size_t r=0;r<b->table->row_count && !cell_id;r++)
      for(size_t c=0;c<b->table->rows[r].cell_count && !cell_id;c++) {
        const exr_edit_block *p=exr_edit_table_cell_paragraph(de.doc,b->id,r,c,0);
        if(!p)continue;
        for(size_t k=0;k<p->run_count;k++)if(p->runs[k].kind==EXR_EDIT_TEXT) {
          table_index=i;table_id=b->id;cell_id=p->id;cell_row=r;cell_col=c;cell_run=k;break;
        }
      }
  }
  E2E_CHECK(body!=SIZE_MAX && table_index!=SIZE_MAX && cell_id);
  char *opened=e2e_snapshot(de.doc);size_t images=e2e_images();
  printf("1 PASS blocks=%zu images=%zu table_id=%llu cell_paragraph=%llu\n",
    exr_edit_block_count(de.doc),images,(unsigned long long)table_id,(unsigned long long)cell_id);

  e2e_step="2 body typing";
  de_set_caret(de_start(body));de_set_anchor(de_caret());page_procedure(NULL,WM_CHAR,0x4e2d,0);
  E2E_CHECK(de.dirty && de.caret_byte==3);
  E2E_CHECK(!memcmp(exr_edit_block_at(de.doc,body)->runs[0].text,"\xe4\xb8\xad",3));
  char *body_typed=e2e_snapshot(de.doc);E2E_CHECK(strcmp(opened,body_typed));
  printf("2 PASS WM_CHAR=U+4E2D caret_byte=%zu dirty=%d\n",de.caret_byte,de.dirty);

  e2e_step="3 table typing";
  const exr_edit_run *run=&exr_edit_find_block(de.doc,cell_id)->runs[cell_run];
  size_t old_size=run->text_size;
  E2E_OK(de_replace_run(cell_id,cell_run,old_size,old_size,"\xe6\xa0\xbc",3));
  run=&exr_edit_find_block(de.doc,cell_id)->runs[cell_run];
  E2E_CHECK(run->text_size==old_size+3 && !memcmp(run->text+old_size,"\xe6\xa0\xbc",3));
  char *table_typed=e2e_snapshot(de.doc);E2E_CHECK(strcmp(body_typed,table_typed));
  printf("3 PASS table_cell=%zu,%zu UTF8_bytes=%zu->%zu cell_paragraphs=%zu\n",cell_row,cell_col,
    old_size,run->text_size,exr_edit_table_cell_block_count(de.doc,table_id,cell_row,cell_col));

  e2e_step="4 insert image";
  /* Reuse this fixture's real PNG payload; no filesystem image picker required. */
  size_t part_count=0;const exr_edit_part *parts=exr_edit_parts(original,&part_count),*png=NULL;
  for(size_t i=0;i<part_count;i++)if(strstr(parts[i].name,"word/media/") &&
    parts[i].size>=8 && !memcmp(parts[i].data,"\x89PNG\r\n\x1a\n",8)) {png=&parts[i];break;}
  E2E_CHECK(png);exr_edit_id image_id=0;
  E2E_OK(exr_edit_insert_image(de.doc,exr_edit_block_at(de.doc,table_index)->id,
    png->data,png->size,72,48,&image_id));
  const exr_edit_block *image=exr_edit_find_block(de.doc,image_id);
  E2E_CHECK(image && image->image && e2e_images()==images+1);
  E2E_CHECK(image->image->width_emu==914400 && image->image->height_emu==609600);
  E2E_CHECK(image->image->size==png->size && !memcmp(image->image->data,png->data,png->size));
  char *expected=e2e_snapshot(de.doc);
  printf("4 PASS images=%zu->%zu payload_bytes=%zu EMU=914400x609600\n",images,images+1,png->size);

  e2e_step="5 undo/redo";
  E2E_CHECK(de_key('Z',1,0));e2e_same(table_typed);E2E_CHECK(e2e_images()==images);
  E2E_CHECK(de_key('Z',1,0));e2e_same(body_typed);
  E2E_CHECK(de_key('Z',1,0));e2e_same(opened);
  E2E_CHECK(de_key('Y',1,0));e2e_same(body_typed);
  E2E_CHECK(de_key('Y',1,0));e2e_same(table_typed);
  E2E_CHECK(de_key('Y',1,0));e2e_same(expected);
  puts("5 PASS Ctrl+Z=3 restored_original=1 Ctrl+Y=3 restored_all_edits=1");

  e2e_step="6 save";
  E2E_CHECK(de_key('S',1,0) && !de.dirty && de.saved);
  WIN32_FILE_ATTRIBUTE_DATA info;E2E_CHECK(GetFileAttributesExW(dest,GetFileExInfoStandard,&info));
  E2E_CHECK(info.nFileSizeLow || info.nFileSizeHigh);
  printf("6 PASS Ctrl+S dirty=%d docx_bytes=%lu\n",de.dirty,(unsigned long)info.nFileSizeLow);
  de_close();
  e2e_step="7 reopen/compare";E2E_CHECK(de_open(path));e2e_same(expected);
  E2E_CHECK(e2e_images()==images+1 && !de.dirty);
  e2e_retained_parts(original,de.doc);
  printf("7 PASS reopen content_equal=1 snapshot_bytes=%zu images=%zu dirty=%d\n",
    strlen(expected),e2e_images(),de.dirty);
  de_close();exr_edit_doc_free(original);
  free(opened);free(body_typed);free(table_typed);free(expected);
  shell_d2d_destroy(host_shell);host_shell=NULL;CoUninitialize();
  E2E_CHECK(DeleteFileW(dest));free(dest);E2E_CHECK(RemoveDirectoryW(work));
  puts("native-shell-editor-e2e PASS");return 0;
}
