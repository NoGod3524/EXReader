/* SPDX-License-Identifier: MIT */
/* Independent C11 view of the installed public header: constants and the
   argument contract, with no revision store needed. */
#include <reader_annotation_export.h>
#include <stdio.h>
#include <string.h>
int main(void){
  if(strcmp(READER_ANNOTATION_EXPORT_VERSION,"0.1.0")!=0||READER_ANNOTATION_EXPORT_FORMAT_VERSION!=1u){puts("FAIL version");return 1;}
  if(READER_ANNOTATION_EXPORT_PATH_MAX!=4096u||READER_ANNOTATION_EXPORT_TITLE_MAX!=16384u){puts("FAIL limits");return 2;}
  if(READER_ANNOTATION_EXPORT_DEFAULT_MAX_BYTES!=((uint64_t)64u<<20)||READER_ANNOTATION_EXPORT_HARD_MAX_BYTES!=((uint64_t)1u<<30)){puts("FAIL budgets");return 3;}
  reader_annotation_export_stats stats;reader_annotation_export_error error;
  memset(&stats,0xa5,sizeof(stats));memset(&error,0xa5,sizeof(error));
  if(reader_annotation_export_run(NULL,&stats,&error)!=READER_ANNOTATION_EXPORT_ARGUMENT||error.code!=READER_ANNOTATION_EXPORT_ARGUMENT||
     stats.annotations||stats.jsonl_published||stats.markdown_published||!error.message[0]){puts("FAIL null options");return 4;}
  reader_annotation_export_options options;memset(&options,0,sizeof(options));options.struct_size=sizeof(options);
  if(reader_annotation_export_run(&options,NULL,NULL)!=READER_ANNOTATION_EXPORT_ARGUMENT){puts("FAIL missing store");return 5;}
  options.struct_size=1;
  if(reader_annotation_export_run(&options,&stats,&error)!=READER_ANNOTATION_EXPORT_ARGUMENT){puts("FAIL short struct");return 6;}
  puts("OK");return 0;
}
