/* SPDX-License-Identifier: MIT */
#include <reader_revisions.h>
#include <reader_projection.h>
#include <string.h>
static int unused_row(void *context,const reader_revision_entity_row *row){(void)context;(void)row;return 0;}
int main(void) {
  reader_revisions *store=0;reader_revision_error error={0};char id[33];
  if(reader_revision_new_id(id,&error)!=READER_REV_OK || strlen(id)!=32) return 1;
  if(reader_revisions_open(":memory:",&store,&error)!=READER_REV_OK) return 2;
  {reader_revision_selection selection;char *wire=0;size_t bytes=0;
    if(reader_revision_selected(store,"tag","11111111111111111111111111111111",&wire,&bytes,0,&selection,&error)!=READER_REV_NOT_FOUND||selection.kind!=READER_SELECTION_MISSING||wire||bytes)return 4;
  }
  {char *title=0;
    if(reader_revision_entities_page(store,"book",0,1,100,unused_row,0,&error)!=READER_REV_OK)return 5;
    if(reader_revision_book_title(store,"11111111111111111111111111111111",&title,&error)!=READER_REV_NOT_FOUND||title)return 6;
  }
  if(reader_revisions_close(&store,&error)!=READER_REV_OK || store) return 3;
  return 0;
}
