/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include "../../../examples/linux/reading.h"
#include <exr_pc02_sdk.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>
static int control(const char *mode,const char *path) {
 char authority[PATH_MAX];pc02_lease *lease=NULL;pc02_cap *cap=NULL;
 if(!pc02_user_authority(authority,sizeof(authority))||
    !pc02_open(authority,path,PC02_OWNER,NULL,NULL,&lease))return 2;
 if(!strcmp(mode,"owner"))return pc02_check(lease)&&pc02_close(lease)?0:2;
 const char *manifest="1111111111111111111111111111111111111111111111111111111111111111";
 const char *input="2222222222222222222222222222222222222222222222222222222222222222";
 if(!pc02_begin(lease,manifest,input,&cap))return 2;
 pc02_pending_record descriptor;
 if(!pc02_pending(lease,&descriptor))return 2;
 printf("{\"pending\":true,\"generation\":%llu,\"seal\":\"%s\",\"manifest\":\"%s\",\"input\":\"%s\"}\n",
  (unsigned long long)descriptor.generation,descriptor.seal,descriptor.manifest,descriptor.input);
 fflush(stdout);_exit(0);
}
static int execute(linux_reader *reader,reader_command *command,reader_result *result) {
 reader_result_free(result);linux_reader_execute(reader,command,result);
 if(result->status!=EXR_OK){fprintf(stderr,"actual GTK operation failed: %d %s\n",(int)result->status,result->message);return 0;}
 return 1;
}
int main(int argc,char **argv) {
 if(argc==3&&(!strcmp(argv[1],"owner")||!strcmp(argv[1],"pending")))return control(argv[1],argv[2]);
 if(argc<4)return 64;
 linux_reader *reader=NULL;exr_error error={0};reader_result result={0};reader_command command={0};
 int code=2;exr_status status=linux_reader_open(argv[2],argv[3],NULL,&reader,&error);
 if(status!=EXR_OK){fprintf(stderr,"actual GTK open refused: %s\n",error.message);return 2;}
 command.action=READER_SHELF;command.font=24;command.zoom=100;
 if(!execute(reader,&command,&result)||!result.has_shelf)goto done;
 if(!strcmp(argv[1],"probe")){
  printf("{\"admitted\":true,\"books\":%zu}\n",result.book_count);code=0;goto done;
 }
 if(argc!=5||strcmp(argv[1],"hold"))goto done;
 command.action=READER_IMPORT;command.path=argv[4];
 if(!execute(reader,&command,&result)||!result.has_frame||result.width==0||result.height==0)goto done;
 command.book=result.book;command.part=result.part;command.start=result.start;
 command.action=READER_COMMIT;if(!execute(reader,&command,&result))goto done;
 command.action=READER_SEARCH_BEGIN;command.search_token=1;command.search_query="silver";
 if(!execute(reader,&command,&result)||!result.has_search||result.search_count==0)goto done;
 printf("{\"holding\":true,\"book\":%lld,\"search_results\":%zu,\"search_complete\":%s}\n",
  (long long)command.book,result.search_count,result.search_complete?"true":"false");
 fflush(stdout);
 if(getchar()!='\n')goto done;
 code=0;
done:
 reader_result_free(&result);linux_reader_close(reader);
 if(!code&&!strcmp(argv[1],"hold"))puts("{\"closed\":true}");
 return code;
}
