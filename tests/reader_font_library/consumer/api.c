/* SPDX-License-Identifier: MIT */
#include <reader_font_library.h>
#include <exr/core.h>
#include <stdio.h>
#include <string.h>
int main(void){rfl_limits l=rfl_limits_default();rfl_library *p=NULL;rfl_error e={0};
  if(strcmp(exr_version(),"3.40.0")||exr_abi_version()!=1||l.font_bytes!=16777216||l.directory_bytes!=134217728||l.entries!=64)return 1;
  if(rfl_open(NULL,NULL,&p,&e)!=RFL_ARGUMENT||p)return 2;
  puts("installed-c-abi-sdk340");return 0;
}
