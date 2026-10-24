/* SPDX-License-Identifier: MIT */
#ifndef READER_READING_INTERNAL_H
#define READER_READING_INTERNAL_H
#include "reader_reading_state.h"
#include <cstdio>
#include <cstring>
namespace {
struct failure { reader_rs_status code; reader_rs_gap gap; int sdk; int revision; const char *message; };
[[noreturn]] void reject(reader_rs_status code,const char *message,reader_rs_gap gap=READER_RS_GAP_NONE,int sdk=0,int revision=0){throw failure{code,gap,sdk,revision,message};}
reader_rs_status report(reader_rs_error *e,const failure &f){
  if(e){e->code=f.code;e->gap=f.gap;e->sdk_code=f.sdk;e->revision_code=f.revision;std::snprintf(e->message,sizeof(e->message),"%s",f.message);}
  return f.code;
}
template<class Function>reader_rs_status call(reader_rs_error *e,Function function){
  if(e)std::memset(e,0,sizeof(*e));
  try{function();return READER_RS_OK;}
  catch(const failure &f){return report(e,f);}
  catch(...){return report(e,{READER_RS_MEMORY,READER_RS_GAP_NONE,0,0,"Cannot allocate reading-state bridge memory"});}
}
}
#endif
