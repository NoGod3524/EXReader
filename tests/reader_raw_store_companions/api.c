#include <reader_commands.h>
#include <reader_session.h>
#include <string.h>
#define c_contract original_c_contract
#define reader_session_create reader_session_create_raw_v3
#include "../reader_session/consumer/api.c"
#undef c_contract
int c_contract(void){
  return original_c_contract()||READER_REVISION_ANCHOR_MAX_VERSION!=2||strcmp(READER_REVISIONS_VERSION,"0.4.0")||
    strcmp(READER_COMMANDS_VERSION,"0.2.0")||strcmp(READER_SYNC_VERSION,"0.2.0")||strcmp(READER_SESSION_VERSION,"0.2.0");
}
