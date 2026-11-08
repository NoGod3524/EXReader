/* SPDX-License-Identifier: MIT */
/* Public API acceptance probe: index timing and full real-book pagination. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void quoted(const char *s) {
  putchar('"');
  for(;*s;s++) {
    unsigned char c=(unsigned char)*s;
    if(c=='"' || c=='\\') putchar('\\');
    if(c<32) printf("\\u%04x",c); else putchar(c);
  }
  putchar('"');
}
int main(int argc,char **argv) {
  exr_font_manager *manager=NULL; exr_font_manager_summary summary={0};
  exr_font *font=NULL; exr_publication *publication=NULL; exr_document *doc=NULL;
  exr_pager *pager=NULL; exr_layout *page=NULL; exr_error error={0}; exr_status status;
  size_t parts=0,total=0,missing=0,used[32]={0},i,*map=NULL,count=0;
  exr_layout_config config=exr_layout_config_defaults();
  if(argc!=2 && argc!=5) return 2;
  status=exr_font_manager_open(argv[1],&manager,&error); if(status) goto done;
  summary.struct_size=sizeof(summary);
  status=exr_font_manager_summary_get(manager,&summary,&error); if(status) goto done;
  printf("{\"kind\":\"index\",\"families\":%zu,\"files\":%zu,\"faces\":%zu,\"skipped\":%zu,\"parsed\":%zu,\"cached\":%zu,\"cache\":%u,\"written\":%u,\"ms\":%.3f}\n",
    summary.families,summary.files,summary.faces,summary.skipped,summary.parsed_files,
    summary.cached_files,summary.cache,summary.cache_written,summary.elapsed_ms);
  if(argc==2) goto done;
  if(!strcmp(argv[3],"-")) {
    status=exr_font_manager_create_font(manager,"serif",0,&font,&map,&count,&error);
    if(status) goto done;
    for(i=0;i<count;i++) {
      exr_font_face_info f={0}; f.struct_size=sizeof(f);
      status=exr_font_manager_face(manager,map[i],&f,&error); if(status) goto done;
      printf("{\"kind\":\"face\",\"font_index\":%zu,\"manager_index\":%zu,\"family\":",i,map[i]);
      quoted(f.family); puts("}");
    }
  } else { status=exr_font_open(argv[3],&font,&error); if(status) goto done; }
  status=exr_publication_open(argv[2],&publication,&error); if(status) goto done;
  exr_publication_parts(publication,&parts);
  config.page=(exr_layout_options){612,624,0,18,1.6f,14.4f};
  config.user_css="html,body{writing-mode:horizontal-tb!important} *{font-family:serif!important}";
  config.embedded_fonts=0;
  for(i=0;i<parts;i++) {
    size_t local=0;
    status=exr_publication_load(publication,i,&doc,&error); if(status) goto done;
    status=exr_pager_create(doc,font,&config,&pager,&error); if(status) goto done;
    for(;;local++) {
      const exr_glyph *glyphs; const exr_line *lines; size_t n,j,line_count;
      status=exr_pager_next(pager,&page,&error); if(status) goto done;
      if(!page) break;
      glyphs=exr_layout_glyphs(page,&n); lines=exr_layout_lines(page,&line_count);
      for(j=0;j<n;j++) {
        if(glyphs[j].flags&EXR_GLYPH_HIDDEN) continue;
        missing+=(glyphs[j].flags&EXR_GLYPH_MISSING)!=0;
        if(glyphs[j].font_index<32) used[glyphs[j].font_index]++;
      }
      if(!local && line_count) {
        const exr_line *line=&lines[0];
        printf("{\"kind\":\"first_line\",\"part\":%zu,\"start\":%zu,\"end\":%zu,\"box\":[%.3f,%.3f,%.3f,%.3f],\"codepoints\":[",
          i,line->start,line->end,line->x,line->y,line->width,line->height);
        for(j=0;j<line->glyph_count;j++) printf("%s%u",j?",":"",glyphs[line->glyph_start+j].codepoint);
        puts("]}");
      }
      if(i==15 && !local && strcmp(argv[4],"-")) {
        exr_bitmap bitmap={0};
        status=exr_render_page_color(page,NULL,0,&bitmap,&error); if(status) goto done;
        status=exr_bitmap_write_png(&bitmap,argv[4],&error); exr_bitmap_free(&bitmap); if(status) goto done;
      }
      total++; exr_layout_free(page); page=NULL;
    }
    exr_pager_free(pager); pager=NULL; exr_document_free(doc); doc=NULL;
  }
  printf("{\"kind\":\"book\",\"parts\":%zu,\"pages\":%zu,\"missing\":%zu,\"font_usage\":[",parts,total,missing);
  for(i=0;i<exr_font_count(font);i++) printf("%s%zu",i?",":"",used[i]);
  puts("]}");
done:
  if(status) fprintf(stderr,"%d: %s\n",(int)status,error.message);
  exr_layout_free(page); exr_pager_free(pager); exr_document_free(doc);
  exr_publication_free(publication); exr_font_free(font); exr_free(map); exr_font_manager_free(manager);
  return status ? 1 : 0;
}
