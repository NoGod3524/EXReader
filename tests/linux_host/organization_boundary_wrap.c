/* SPDX-License-Identifier: MIT
   Linked only into the explicitly requested, uninstalled GTK boundary probe. */
#include <reader_projection.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

reader_revision_status __real_reader_revision_entities_page(reader_revisions *,const char *,const char *,int,size_t,reader_revision_entity_fn,void *,reader_revision_error *);
reader_revision_status __wrap_reader_revision_entities_page(reader_revisions *s,const char *kind,const char *after,int direction,size_t limit,reader_revision_entity_fn visit,void *context,reader_revision_error *error) {
  reader_revision_status code=__real_reader_revision_entities_page(s,kind,after,direction,limit,visit,context,error);
  const char *path=getenv("EXR_TEST_ORGANIZATION_PROBE");
  static int fired=0;
  if(code==READER_REV_OK && path && *path && !fired && kind && !strcmp(kind,"tag") && !after) {
    char marker[4096],release[4096];
    if(snprintf(marker,sizeof(marker),"%s/selected",path)>=(int)sizeof(marker) || snprintf(release,sizeof(release),"%s/release",path)>=(int)sizeof(release)) return READER_REV_ARGUMENT;
    fired=1;FILE *file=fopen(marker,"w");if(!file)return READER_REV_DATABASE;
    fputs("selected\n",file);fclose(file);
    struct timespec pause={0,10000000};
    for(int i=0;i<9000;i++) { if(access(release,F_OK)==0)return code; nanosleep(&pause,NULL); }
    return READER_REV_DATABASE;
  }
  return code;
}
