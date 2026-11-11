/* SPDX-License-Identifier: MIT */
/* Console-only check of the real JOB_LAYOUT branches; creates no HWND. */
#define WinMain reader_WinMain
#define EXR_READER_TEST_DRIVERS 1
#include "../reader.c"
#undef WinMain
#include <assert.h>

static void require_ok(exr_status status, exr_error *error) {
  if (status != EXR_OK) { fprintf(stderr, "%d: %s\n", status, error->message); exit(1); }
}

int main(int argc, char **argv) {
  exr_error error = {0};
  SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
  setvbuf(stdout,NULL,_IONBF,0);
  assert(argc == 3);
  require_ok(exr_font_open(argv[1], &g.font, &error), &error);
  FILE *file = fopen(argv[2], "wb"); assert(file);
  for (int i=0; i<1000; i++) fprintf(file, "Record %06d: Reading a portable book keeps its content point while letters change size and pages are measured again.\n", i);
  fclose(file);
  for (int mode=0; mode<3; mode++) {
    host_job initial = {0};
    initial.shell_geometry = shell_geometry_for(1280,800,96,17,mode==2);
    initial.font_percent = 150;
    g.session.active = 1; g.session.book_id = 1;
    g.session.txt = mode == 1;
    session_configure(&g.session, &initial);
    if (mode == 1) {
      wchar_t *path = host_wide(argv[2], strlen(argv[2])); WIN32_FILE_ATTRIBUTE_DATA attr;
      assert(GetFileAttributesExW(path, GetFileExInfoStandard, &attr));
      g.session.txt = 1;
      g.session.txt_source = (exr_source){((uint64_t)attr.nFileSizeHigh<<32)|attr.nFileSizeLow, txt_read, txt_release,
        CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL),{0}};
      free(path);
      require_ok(exr_txt_pager_create(&g.session.txt_source,g.font,&g.session.config,&g.session.pager,&error),&error);
    } else {
      if (mode == 2) {
        char *html = malloc(200000); assert(html);
        size_t n = (size_t)sprintf(html,"<html><head><style>html{writing-mode:vertical-rl}</style></head><body><p>");
        for(int i=0;i<1000;i++) n+=(size_t)sprintf(html+n,"Record %06d: Reading a portable book keeps its content point while letters change size. ",i);
        n+=(size_t)sprintf(html+n,"</p></body></html>");
        require_ok(exr_document_open_memory(EXR_HTML,html,n,&g.session.document,&error),&error); free(html);
      } else require_ok(exr_document_open(argv[2],&g.session.document,&error),&error);
      require_ok(exr_pager_create(g.session.document,g.font,&g.session.config,&g.session.pager,&error),&error);
    }
    require_ok(exr_pager_set_cache(g.session.pager,2,0,&error),&error);
    if (g.session.txt) {
      const exr_layout *layout = NULL;
      require_ok(exr_pager_get(g.session.pager,9,&layout,&error),&error);
      require_ok(txt_frame(&g.session,&g.session.txt_source,layout,9,&g.frame,&error),&error);
      g.frame.book_id=1;
    } else require_ok(render_reflow(&g.session,9,&g.frame,NULL,&error),&error);
    size_t head = g.frame.shell_lines[0].start; assert(head>0);
    int sizes[]={18,20,22,24,28,32,17};
    for(size_t i=0;i<sizeof(sizes)/sizeof(*sizes);i++) {
      host_job job = {0}; job.kind=JOB_LAYOUT; job.book_id=1; job.font_percent=150;
      job.shell_geometry=shell_geometry_for(1280,800,96,(float)sizes[i],mode==2);
      if (g.session.txt) job.txt_offset=head;
      else {
        require_ok(exr_anchor_create(g.session.document,head,head,&job.anchor,&error),&error);
        job.has_anchor=1;
      }
      require_ok(job_layout(&job),&job.error);
      assert(job.have_frame && job.frame.shell_lines[0].start==head);
      size_t first=job.frame.shell_lines[0].glyph_start;
      assert(job.frame.glyphs[first].start==head && job.frame.text_bytes>0);
      printf("%s,%d,%zu,%zu,%zu\n",mode==1?"TXT":mode==2?"document-vertical":"document",sizes[i],head,
             job.frame.shell_lines[0].start,job.frame.page+1);
      exr_pager_free(g.session.pager); g.session.pager=job.candidate_pager;
      g.session.config=job.candidate_config; g.session.shell_geometry=job.shell_geometry;
      if(g.session.txt) g.session.txt_source=job.candidate.txt_source;
      frame_move(&g.frame,&job.frame); exr_anchor_free(&job.anchor);
      if(sizes[i]==32) {
        host_job go={0}; go.book_id=1; go.direction=go.batch_delta=1; go.target_page=g.frame.page+1;
        size_t end=g.frame.range_end;
        require_ok(job_go(&go),&go.error);
        assert(go.have_frame && go.frame.shell_lines[0].start==end);
        frame_clear(&go.frame);
      }
    }
    frame_clear(&g.frame); session_clear(&g.session);
  }
  exr_font_free(g.font);
  return 0;
}
