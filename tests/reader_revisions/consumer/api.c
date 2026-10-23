/* SPDX-License-Identifier: MIT */
#include <reader_revisions.h>
#include <string.h>
int main(void) {
  reader_revisions *store=0;reader_revision_error error={0};char id[33];
  if(reader_revision_new_id(id,&error)!=READER_REV_OK || strlen(id)!=32) return 1;
  if(reader_revisions_open(":memory:",&store,&error)!=READER_REV_OK) return 2;
  if(reader_revisions_close(&store,&error)!=READER_REV_OK || store) return 3;
  return 0;
}
