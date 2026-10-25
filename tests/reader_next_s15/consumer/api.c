/* SPDX-License-Identifier: MIT */
#include <reader_original_export.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int enter(void *p){(void)p;return 0;}
static void leave(void *p){(void)p;}

static int self_check(void){
  exr_library *lib=NULL;exr_error error={0};roe_exporter *e=NULL,*other=NULL;
  roe_owner owner={enter,leave,NULL};
  if(EXR_ABI_VERSION!=1u)return 11;
  if(exr_library_open(":memory:",&lib,&error)!=EXR_OK)return 1;
  if(roe_create(lib,&owner,&e)!=ROE_OK)return 2;
  if(roe_create(lib,&owner,&other)!=ROE_OWNER||other)return 3;
  if(roe_destroy(&e)!=ROE_OK||e)return 4;
  exr_library_close(lib);
  printf("{\"c_abi\":1,\"version\":\"%s\",\"abi\":%u,\"call\":\"self\"}\n",EXR_VERSION,EXR_ABI_VERSION);
  return 0;
}

static int export_one(const char *db,const char *dir){
  exr_library *lib=NULL;exr_error error={0};roe_exporter *e=NULL;roe_owner owner={enter,leave,NULL};
  roe_selection selected={1,"C_Consumer"};
  roe_options options={0};roe_result *result=NULL;roe_status status;
  if(exr_library_open(db,&lib,&error)!=EXR_OK)return 20;
  if(roe_create(lib,&owner,&e)!=ROE_OK)return 21;
  options.directory=dir;options.naming=ROE_HASH_NAME;
  status=roe_run(e,&selected,1,&options,&result);
  if(status!=ROE_OK||!result||result->count!=1||result->items[0].status!=ROE_OK||
     result->items[0].committed!=1)return 22;
  printf("{\"c_abi\":1,\"version\":\"%s\",\"abi\":%u,\"call\":\"export\",\"hash\":\"%s\",\"path\":\"%s\",\"bytes\":%llu,\"created\":%d}\n",
    EXR_VERSION,EXR_ABI_VERSION,result->items[0].original_sha256,result->items[0].output_path,
    (unsigned long long)result->items[0].bytes,result->items[0].created);
  roe_result_free(result);
  if(roe_destroy(&e)!=ROE_OK)return 23;
  exr_library_close(lib);
  return 0;
}

/* Seed one TXT original from a frozen fixture through the public SDK, then export it. */
static int seed_export(const char *db,const char *dir,const char *source){
  FILE *f=fopen(source,"rb");long size;char *data;int64_t id=0;
  exr_library *lib=NULL;exr_error error={0};
  if(!f)return 40;
  if(fseek(f,0,SEEK_END)!=0)return 41;
  size=ftell(f);if(size<=0)return 42;
  rewind(f);data=(char *)malloc((size_t)size);if(!data)return 43;
  if(fread(data,1,(size_t)size,f)!=(size_t)size){free(data);fclose(f);return 44;}
  fclose(f);
  if(exr_library_open(db,&lib,&error)!=EXR_OK){free(data);return 45;}
  if(exr_library_import(lib,EXR_TXT,data,(size_t)size,"c consumer seed",&id,&error)!=EXR_OK){free(data);exr_library_close(lib);return 46;}
  free(data);exr_library_close(lib);
  return export_one(db,dir);
}

int main(int argc,char **argv){
  if(argc==1)return self_check();
  if(argc==3)return export_one(argv[1],argv[2]);
  if(argc==5&&strcmp(argv[1],"seed")==0)return seed_export(argv[2],argv[3],argv[4]);
  return 30;
}
