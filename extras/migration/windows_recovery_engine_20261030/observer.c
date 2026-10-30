/* SPDX-License-Identifier: MIT
 * Actual isolated observer. Reads only inherited target handle, never opens
 * target paths or calls SDK target-open. Does not grant semantic recovery. */
#include "protocol.h"
#include <stdlib.h>
#include <string.h>
#include <errno.h>
int main(int argc,char **argv){
 lm_we_request request;lm_we_response response;wr_error e={0};
 wr_identity a,b;HANDLE target;DWORD got=0,wrote=0;char second[65],id[49];
 char *end=NULL;unsigned long long raw;
 if(argc!=2)return 2;
 errno=0;raw=strtoull(argv[1],&end,10);
 if(errno||!raw||!end||*end||raw>(unsigned long long)UINTPTR_MAX)return 2;
 target=(HANDLE)(uintptr_t)raw;
 memset(&request,0,sizeof(request));memset(&response,0,sizeof(response));
 if(!ReadFile(GetStdHandle(STD_INPUT_HANDLE),&request,sizeof(request),&got,NULL)||
 got!=sizeof(request)||!lm_we_request_valid(&request))return 3;
 if(!lm_we_hash(target,response.target_sha,&a,&e)||
 !lm_we_hash(target,second,&b,&e)||strcmp(second,response.target_sha)||
 !wr_identity_equal(&a,&b)||a.size!=b.size)return 4;
 wr_identity_text(&a,id);if(strcmp(id,request.target))return 5;
 response.request=request;response.bytes=a.size;response.observed=1;
 if(!WriteFile(GetStdHandle(STD_OUTPUT_HANDLE),&response,sizeof(response),&wrote,NULL)||
 wrote!=sizeof(response)||!FlushFileBuffers(GetStdHandle(STD_OUTPUT_HANDLE)))return 6;
 return 0;
}
