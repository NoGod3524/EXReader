/* SPDX-License-Identifier: MIT */
#include "exr/library.h"
#include <stdio.h>
#include <string.h>
#ifdef EXR_AUDIO_H
#error Library storage must not require the audio playback API
#endif
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"line %d: %s (%s)\n",__LINE__,#x,e.message);return 1; } } while(0)
int main(int argc,char **argv) {
  exr_error e={0};exr_library *lib=NULL,*backup=NULL;int64_t id=0,again=0;int created=0,found=0;
  exr_book *books=NULL;size_t count=0;char path[4096];
  exr_audio_checkpoint position={"track",1234,1.25},loaded={0};
  CHECK(argc==2);snprintf(path,sizeof(path),"%s/component-backup.sqlite",argv[1]);remove(path);
  CHECK(exr_library_open(":memory:",&lib,&e)==EXR_OK);
  { exr_fixed_document *doc=NULL;
    CHECK(exr_library_import_source(lib,EXR_CBZ,NULL,NULL,&again,&e)==EXR_ARGUMENT && !again);
    CHECK(exr_library_import_source_unique(lib,EXR_CBZ,NULL,NULL,&again,&created,&e)==EXR_ARGUMENT && !again && !created);
    CHECK(exr_library_import_file(lib,EXR_CBZ,NULL,NULL,&again,&e)==EXR_ARGUMENT && !again);
    CHECK(exr_library_import_file_unique(lib,EXR_PDF,NULL,NULL,&again,&created,&e)==EXR_ARGUMENT && !again && !created);
    CHECK(exr_library_fixed_source(lib,0,NULL,&doc,&e)==EXR_ARGUMENT && !doc);
  }
  CHECK(exr_library_import(lib,EXR_TXT,"abc",3,"Title",&id,&e)==EXR_OK && id>0);
  CHECK(exr_library_import_unique(lib,EXR_TXT,"abc",3,NULL,&again,&created,&e)==EXR_OK && !created && again==id);
  CHECK(exr_library_audio_resume(lib,"audio",&position,&e)==EXR_OK);
  CHECK(exr_library_audio_resume_get(lib,"audio",&loaded,&found,&e)==EXR_OK && found && loaded.offset_ms==1234);
  exr_audio_checkpoint_free(&loaded);
#ifndef EXR_TEST_PDF
  { exr_fixed_document *doc=NULL;CHECK(exr_library_fixed(lib,id,NULL,&doc,&e)!=EXR_OK && !doc); }
  CHECK(exr_library_import(lib,EXR_PDF,"%PDF",4,NULL,&again,&e)==EXR_UNSUPPORTED && !again);
#endif
  CHECK(exr_library_backup(lib,path,&e)==EXR_OK);
  CHECK(exr_library_backup(lib,path,&e)==EXR_DATABASE);
  CHECK(exr_library_open(path,&backup,&e)==EXR_OK);
  CHECK(exr_library_books(backup,NULL,&books,&count,&e)==EXR_OK && count==1 && !strcmp(books[0].title,"Title"));
  exr_books_free(books,count);exr_library_close(backup);exr_library_close(lib);remove(path);
  puts("Independent library component passed");return 0;
}
