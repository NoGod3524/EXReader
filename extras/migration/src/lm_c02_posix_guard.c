/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include "lm_c02_guard.h"
#include <exr_pc02_sdk.h>
#include <string.h>
/* One command per process. Keep the checked shared lease through every SDK
   owner/source close and early return, until the process itself terminates. */
static pc02_lease *admission;
static char physical_library[4096];
static int entered;
int lm_c02_guard_command(const char *command,lm_err *error){
 if(command&&(!strcmp(command,"inspect")||!strcmp(command,"dump")||
    !strcmp(command,"verify")||!strcmp(command,"export-ledger")))return 1;
 lm_err_set(error,"c02-owner-required",
  "Use exreader-c02-migrate migrate/recover after explicit exreader-c02-admission enrollment; legacy mutation commands are disabled before SDK, lock, or break-lock access.");
 return 0;
}
int lm_c02_guard_read(const char *command,const char *target,const char *report,
 const char **physical_target,lm_err *error){
 const char *physical;
 if(physical_target)*physical_target=NULL;
 if(!physical_target||!lm_c02_guard_command(command,error))return 0;
 if(report){
  lm_err_set(error,"c02-stdout-only","Use stdout for command reports; --report cannot overwrite a library or recovery file.");return 0;
 }
 if(!strcmp(command,"inspect"))return 1;
 if(entered){lm_err_set(error,"c02-already-entered","A command already holds shared custody until process exit.");return 0;}
 if(!target||target[0]!='/'||!pc02_sdk_open_user(target,&admission)||
    !(physical=pc02_library_path(admission))||strlen(physical)>=sizeof(physical_library)||
    !pc02_check(admission))goto refuse;
 strcpy(physical_library,physical);entered=1;*physical_target=physical_library;return 1;
refuse:
 (void)pc02_close(admission);admission=NULL;
 lm_err_set(error,"c02-admission-refused","Library admission refused before SDK open; complete explicit C02 enrollment or recovery first.");
 return 0;
}
