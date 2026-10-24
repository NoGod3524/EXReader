/* SPDX-License-Identifier: MIT */
#include <reader_session.h>
int c_contract(void){
  reader_session *s=(reader_session *)1;reader_session_snapshot view;
  if(reader_session_create(NULL,&s)!=READER_SESSION_ARGUMENT||s)return 1;
  if(reader_session_create(NULL,NULL)!=READER_SESSION_ARGUMENT)return 2;
  if(reader_session_start(NULL)!=READER_SESSION_ARGUMENT||reader_session_cancel(NULL)!=READER_SESSION_ARGUMENT)return 3;
  if(reader_session_observe(NULL,&view)!=READER_SESSION_ARGUMENT||view.state)return 4;
  if(reader_session_request_close(NULL)!=READER_SESSION_ARGUMENT||reader_session_destroy(NULL)!=READER_SESSION_ARGUMENT)return 5;
  return 0;
}
