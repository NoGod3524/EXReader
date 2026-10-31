/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include <exr_pc02_sdk.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>
int main(int argc,char **argv) {
 pc02_sdk_proof proof={0};pc02_lease *lease=NULL;char library[PATH_MAX];int ok=0,n;
 if(argc!=3)goto usage;
 if(argv[2][0]=='/')n=snprintf(library,sizeof(library),"%s",argv[2]);
 else{
  char current[PATH_MAX];if(!getcwd(current,sizeof(current)))return 2;
  n=snprintf(library,sizeof(library),"%s/%s",current,argv[2]);
 }
 if(n<0||(size_t)n>=sizeof(library))return 2;
 if(!strcmp(argv[1],"create")||!strcmp(argv[1],"enroll"))
  ok=pc02_sdk_enroll_user(library,!strcmp(argv[1],"create"),&proof);
 else if(!strcmp(argv[1],"recover-enrollment"))
  ok=pc02_sdk_recover_enrollment_user(library,&proof);
 else if(!strcmp(argv[1],"check")){
  ok=pc02_sdk_open_user(library,&lease)&&pc02_check(lease);
  if(!pc02_close(lease))ok=0;
 }else goto usage;
 printf("{\"admitted\":%s,\"books\":%zu,\"original_bytes\":%llu}\n",ok?"true":"false",
   proof.books,(unsigned long long)proof.original_bytes);
 if(!ok)fputs("C02 admission refused; retain the library and recovery evidence.\n",stderr);
 return ok?0:2;
usage:
 fputs("Usage: exreader-c02-admission create|enroll|recover-enrollment|check LIBRARY\n",stderr);
 return 64;
}
