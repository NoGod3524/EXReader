/* SPDX-License-Identifier: MIT */
#include "lm_c02_guard.h"
#include <exr_wh3_win.h>
#include <string.h>
#include <wchar.h>
/* A CLI has one command. Retain shared custody through process termination,
   including every early return and allocation failure in the original reader.
   No other source/SDK owner can execute after this process has terminated.
   There is deliberately no early-release API or exit callback ordering hazard. */
static wh3wr_registration *admission;
static char physical_library[4*(MAX_PATH+128)];
static int entered;
int lm_c02_guard_command(const char *command,lm_err *error) {
 if(command&&(!strcmp(command,"inspect")||!strcmp(command,"dump")||
    !strcmp(command,"verify")||!strcmp(command,"export-ledger")))return 1;
 lm_err_set(error,"c02-owner-required",
   "Use exreader-c02-migrate migrate/recover after explicit exreader-c02-admission enrollment; legacy Windows mutation commands are disabled before SDK or lock access.");
 return 0;
}
int lm_c02_guard_read(const char *command,const char *target,const char *report,
 const char **physical_target,lm_err *error) {
 wchar_t input[MAX_PATH],absolute[MAX_PATH],physical[MAX_PATH+128];DWORD n;
 if(physical_target)*physical_target=NULL;
 if(!physical_target||!lm_c02_guard_command(command,error))return 0;
 if(report){
  lm_err_set(error,"c02-stdout-only","Use stdout for command reports; --report is disabled so a read command cannot overwrite a library or recovery file.");
  return 0;
 }
 if(!strcmp(command,"inspect"))return 1;
 if(entered){lm_err_set(error,"c02-already-entered","A command already holds shared custody until process exit.");return 0;}
 if(!target||!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,target,-1,input,MAX_PATH))goto refuse;
 n=GetFullPathNameW(input,MAX_PATH,absolute,NULL);
 if(!n||n>=MAX_PATH||!wh3wr_open(absolute,WH3WG_SHARED,NULL,&admission)||
    !wh3wr_library_path(admission,physical,MAX_PATH+128)||
    !WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,physical,-1,physical_library,sizeof(physical_library),NULL,NULL)||
    !wh3wr_check(admission))goto refuse;
 entered=1;*physical_target=physical_library;return 1;
refuse:
 (void)wh3wr_close(admission);admission=NULL;
 lm_err_set(error,"c02-admission-refused",
   "Library admission refused before SDK open; complete explicit C02 enrollment or recovery first.");
 return 0;
}
