/* SPDX-License-Identifier: MIT */
/* Independent C11 view of the installed public headers: constants and the
   argument contract, with no revision store needed. */
#include <reader_annotation_export.h>
#include <reader_annotation_import.h>
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
#include <reader_annotation_export_raw3.h>
#include <reader_annotation_import_raw3.h>
#endif
#include <string.h>
int c06_c_api(void){
  reader_annotation_export_stats stats;reader_annotation_export_error error;
  if(strcmp(READER_ANNOTATION_EXPORT_VERSION,"0.1.0")!=0||READER_ANNOTATION_EXPORT_FORMAT_VERSION!=1u)return 1;
  if(strcmp(READER_ANNOTATION_IMPORT_VERSION,"0.1.0")!=0||READER_ANNOTATION_IMPORT_MAX_ITEMS!=65536u)return 2;
  memset(&stats,0xa5,sizeof(stats));memset(&error,0xa5,sizeof(error));
  if(reader_annotation_export_run(NULL,&stats,&error)!=READER_ANNOTATION_EXPORT_ARGUMENT||!error.message[0])return 3;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  {
    reader_ai3_stats s3;reader_ai3_error e3;reader_ai3_options o3;
    if(strcmp(READER_ANNOTATION_EXPORT_RAW3_VERSION,"0.2.0")!=0||READER_ANNOTATION_EXPORT_RAW3_FORMAT_VERSION!=1u)return 4;
    if(strcmp(READER_ANNOTATION_IMPORT_RAW3_VERSION,"0.2.0")!=0||strcmp(READER_ANNOTATION_IMPORT_RAW3_FORMAT,READER_ANNOTATION_EXPORT_RAW3_FORMAT)!=0)return 5;
    memset(&stats,0xa5,sizeof(stats));memset(&error,0xa5,sizeof(error));
    if(reader_annotation_export_raw3_run(NULL,&stats,&error)!=READER_ANNOTATION_EXPORT_ARGUMENT||!error.message[0])return 6;
    memset(&s3,0xa5,sizeof(s3));memset(&e3,0xa5,sizeof(e3));
    if(reader_annotation_import_raw3_run(NULL,&s3,&e3)!=READER_AI3_ARGUMENT||e3.code!=READER_AI3_ARGUMENT||!e3.message[0])return 7;
    memset(&o3,0,sizeof(o3));o3.struct_size=sizeof(o3);
    if(reader_annotation_import_raw3_run(&o3,NULL,NULL)!=READER_AI3_ARGUMENT)return 8;
    o3.struct_size=1;
    if(reader_annotation_import_raw3_run(&o3,&s3,&e3)!=READER_AI3_ARGUMENT)return 9;
  }
#endif
  return 0;
}
