#include <reader_original_export.h>
#include <stdio.h>
static int enter(void *p){(void)p;return 0;}
static void leave(void *p){(void)p;}
int main(void){
  exr_library *lib=NULL;exr_error error={0};roe_exporter *e=NULL,*other=NULL;
  roe_owner owner={enter,leave,NULL};
  if(exr_library_open(":memory:",&lib,&error)!=EXR_OK)return 1;
  if(roe_create(lib,&owner,&e)!=ROE_OK)return 2;
  if(roe_create(lib,&owner,&other)!=ROE_OWNER||other)return 3;
  if(roe_destroy(&e)!=ROE_OK||e)return 4;
  exr_library_close(lib);puts("installed_c_abi");return 0;
}
