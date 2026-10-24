/* SPDX-License-Identifier: MIT */
#include "reader_sync_view.h"
#include <cstring>
#include <memory>
#include <new>
#include <set>
#include <string>
#include <utility>
#include <vector>
struct reader_sync_view_snapshot {
  reader_sync_view_summary summary{};
  std::vector<reader_sync_view_row> rows;
};
namespace {
using reason=reader_sync_view_reason;
void fail(reader_sync_view_error *e,reader_sync_view_status s,int session,int revision,const char *text){
  if(!e)return;*e={};e->status=s;e->session_status=session;e->revision_code=revision;
  size_t n=0;while(text[n]&&n<sizeof(e->message)-1){e->message[n]=text[n];n++;}e->message[n]=0;
}
reason from_revision(int code){
  switch(code){
    case READER_REV_OK:return READER_SYNC_VIEW_REASON_NONE;
    case READER_REV_COLLISION:case READER_REV_MISSING_PARENT:case READER_REV_CYCLE:return READER_SYNC_VIEW_REASON_CONFLICT;
    case READER_REV_DATABASE:case READER_REV_MEMORY:return READER_SYNC_VIEW_REASON_STORAGE;
    case READER_REV_HASH:case READER_REV_FORMAT:case READER_REV_UNSAFE:return READER_SYNC_VIEW_REASON_INTEGRITY;
    case READER_REV_LIMIT:return READER_SYNC_VIEW_REASON_LIMIT;
    default:return READER_SYNC_VIEW_REASON_INTERNAL;
  }
}
reason from_dav(int dav,int http){
  if(http==401||http==403)return READER_SYNC_VIEW_REASON_NEEDS_CREDENTIALS;
  switch(dav){
    case EXR_DAV_OK:return READER_SYNC_VIEW_REASON_NONE;
    case EXR_DAV_CANCELLED:return READER_SYNC_VIEW_REASON_NONE;
    case EXR_DAV_AUTH:return READER_SYNC_VIEW_REASON_NEEDS_CREDENTIALS;
    case EXR_DAV_TLS:return READER_SYNC_VIEW_REASON_TLS;
    case EXR_DAV_IO:return READER_SYNC_VIEW_REASON_OFFLINE;
    case EXR_DAV_LIMIT:return READER_SYNC_VIEW_REASON_LIMIT;
    case EXR_DAV_MEMORY:return READER_SYNC_VIEW_REASON_STORAGE;
    case EXR_DAV_ARGUMENT:return READER_SYNC_VIEW_REASON_INTERNAL;
    default:return READER_SYNC_VIEW_REASON_SERVER;
  }
}
reason classify(const reader_session_snapshot &s){
  switch(s.status){
    case READER_SESSION_OK:return READER_SYNC_VIEW_REASON_NONE;
    case READER_SESSION_ACCOUNT:return READER_SYNC_VIEW_REASON_ACCOUNT;
    case READER_SESSION_IO:return READER_SYNC_VIEW_REASON_STORAGE;
    case READER_SESSION_SYNC:break;
    default:return READER_SYNC_VIEW_REASON_INTERNAL;
  }
  const reader_sync_error &e=s.error;
  if(e.http_status==401||e.http_status==403)return READER_SYNC_VIEW_REASON_NEEDS_CREDENTIALS;
  if(e.dav_code)return from_dav(e.dav_code,e.http_status);
  if(e.revision_code)return from_revision(e.revision_code);
  switch(e.code){
    case READER_SYNC_OK:return READER_SYNC_VIEW_REASON_NONE;
    case READER_SYNC_CANCELLED:return READER_SYNC_VIEW_REASON_NONE;
    case READER_SYNC_REVISION:return READER_SYNC_VIEW_REASON_INTERNAL;
    case READER_SYNC_HASH:return READER_SYNC_VIEW_REASON_INTEGRITY;
    case READER_SYNC_LIMIT:return READER_SYNC_VIEW_REASON_LIMIT;
    case READER_SYNC_IO:return READER_SYNC_VIEW_REASON_STORAGE;
    case READER_SYNC_DAV:return READER_SYNC_VIEW_REASON_SERVER;
    default:return READER_SYNC_VIEW_REASON_INTERNAL;
  }
}
reader_sync_view_phase phase_of(reader_session_state s){
  switch(s){
    case READER_SESSION_IDLE:return READER_SYNC_VIEW_IDLE;
    case READER_SESSION_RUNNING:return READER_SYNC_VIEW_SYNCING;
    case READER_SESSION_CANCELLING:return READER_SYNC_VIEW_CANCELLING;
    case READER_SESSION_CANCELLED:return READER_SYNC_VIEW_CANCELLED;
    case READER_SESSION_FINISHED:return READER_SYNC_VIEW_SWEEP_COMPLETE;
    case READER_SESSION_FAILED:return READER_SYNC_VIEW_FAILED;
    case READER_SESSION_CLOSING:return READER_SYNC_VIEW_CLOSING;
    case READER_SESSION_CLOSED:return READER_SYNC_VIEW_CLOSED;
  }
  return READER_SYNC_VIEW_UNKNOWN;
}
struct copied_row {reader_sync_view_row row{};std::string kind,key;};
struct collector {std::vector<copied_row> rows;size_t limit=0;bool memory=false;};
// Runs inside reader_revision_outbox: copy only, never call back into the store.
int visit(void *opaque,const reader_revision_outbox_row *r){
  collector &c=*static_cast<collector *>(opaque);
  try{
    copied_row v;
    size_t n=0;
    while(n<sizeof(v.row.revision_id)-1&&r->info.revision_id[n]){v.row.revision_id[n]=r->info.revision_id[n];n++;}
    v.row.revision_id[n]=0;n=0;
    while(n<sizeof(v.row.entity_kind)-1&&r->info.entity_kind[n]){v.row.entity_kind[n]=r->info.entity_kind[n];n++;}
    v.row.entity_kind[n]=0;n=0;
    while(n<sizeof(v.row.operation)-1&&r->info.operation[n]){v.row.operation[n]=r->info.operation[n];n++;}
    v.row.operation[n]=0;
    v.row.bytes=(uint64_t)r->info.bytes;v.row.attempts=r->attempts;
    // Retry stores "revision_error_<decimal code>"; anything else stays "none".
    static const char token[]="revision_error_";
    const char *last=r->last_error;
    if(last&&std::strlen(last)>sizeof(token)-1&&std::strncmp(last,token,sizeof(token)-1)==0){
      const char *digits=last+sizeof(token)-1;int value=0;size_t k=0;
      for(;digits[k]>='0'&&digits[k]<='9'&&k<3;k++)value=value*10+(digits[k]-'0');
      if(k&&!digits[k]&&value>=(int)READER_REV_ARGUMENT&&value<=(int)READER_REV_NOT_FOUND){
        v.row.last_revision_code=value;v.row.last_reason=from_revision(value);
      }
    }
    v.kind=r->info.entity_kind;v.key=r->info.entity_key;
    c.rows.push_back(std::move(v));
  }catch(...){c.memory=true;return 1;}
  return c.rows.size()>=c.limit?1:0;
}
int heads_visit(void *,const reader_revision_head *){return 0;}
}
extern "C" reader_sync_view_status reader_sync_view_capture(reader_session *session,reader_revisions *revisions,
    const reader_sync_view_options *options,reader_sync_view_snapshot **out,reader_sync_view_error *error){
  if(error)*error={};
  if(out)*out=nullptr;
  if(!out||!session){fail(error,READER_SYNC_VIEW_ARGUMENT,0,0,"Session and output are required");return READER_SYNC_VIEW_ARGUMENT;}
  size_t limit=READER_SYNC_VIEW_DEFAULT_ROWS;bool conflicts=false;
  if(options){
    if(options->row_limit>READER_SYNC_VIEW_MAX_ROWS){fail(error,READER_SYNC_VIEW_ARGUMENT,0,0,"Row limit must be 0..100");return READER_SYNC_VIEW_ARGUMENT;}
    if(options->row_limit)limit=options->row_limit;
    conflicts=options->detect_conflicts!=0;
  }
  try{
    std::unique_ptr<reader_sync_view_snapshot> snapshot(new reader_sync_view_snapshot);
    reader_session_snapshot s{};
    int observed=(int)reader_session_observe(session,&s);
    if(observed!=(int)READER_SESSION_OK){fail(error,READER_SYNC_VIEW_SESSION,observed,0,"Session observation failed");return READER_SYNC_VIEW_SESSION;}
    reader_sync_view_summary &v=snapshot->summary;
    v.phase=phase_of(s.state);v.reason=classify(s);v.session_status=(int)s.status;
    v.http_status=s.error.http_status;v.dav_code=s.error.dav_code;v.revision_code=s.error.revision_code;
    v.attempt=s.attempt;v.completed_sweeps=s.completed_sweeps;v.operations=s.steps;v.pushed_operations=s.pushed;
    v.pulled_operations=s.pulled;v.originals_verified_operations=s.originals_verified;
    v.metadata_wait_observations=s.pending_metadata_observations;v.original_wait_observations=s.pending_original_observations;
    v.transfer_bytes=s.transfer_bytes;v.shard=s.shard;v.completed_shards=s.completed_shards;v.shard_count=READER_SYNC_VIEW_SHARD_COUNT;
    for(size_t n=0;n<sizeof(v.cursor)-1&&s.after[n];n++)v.cursor[n]=s.after[n];
    v.sweep_complete=s.state==READER_SESSION_FINISHED?1:0;v.library_complete=s.full_library_complete?1:0;
    v.resumable=(s.state==READER_SESSION_CANCELLED||s.state==READER_SESSION_FAILED)?1:0;
    if(revisions){
      collector c;c.limit=limit;reader_revision_error re{};
      reader_revision_status st=reader_revision_outbox(revisions,limit,visit,&c,&re);
      if(c.memory)throw std::bad_alloc();
      if(st!=READER_REV_OK){
        fail(error,READER_SYNC_VIEW_REVISIONS,0,(int)st,st==READER_REV_OWNER?"Pending list needs its owning worker":"Pending list could not be read");
        return READER_SYNC_VIEW_REVISIONS;
      }
      std::set<std::pair<std::string,std::string>> concurrent;
      if(conflicts){
        std::set<std::pair<std::string,std::string>> checked;
        for(const copied_row &r:c.rows){
          std::pair<std::string,std::string> id(r.kind,r.key);
          if(!checked.insert(id).second)continue;
          reader_revision_state state{};
          st=reader_revision_heads(revisions,r.kind.c_str(),r.key.c_str(),heads_visit,nullptr,&state,&re);
          if(st!=READER_REV_OK){
            fail(error,READER_SYNC_VIEW_REVISIONS,0,(int)st,"Conflict check could not be read");
            return READER_SYNC_VIEW_REVISIONS;
          }
          if(state.heads>1)concurrent.insert(id);
        }
      }
      snapshot->rows.reserve(c.rows.size());
      for(copied_row &r:c.rows){
        r.row.conflict=concurrent.count(std::make_pair(r.kind,r.key))?1:0;
        if(r.row.conflict)v.conflict_records++;
        if(r.row.attempts>0||r.row.last_revision_code)v.retried_records++;
        snapshot->rows.push_back(r.row);
      }
      v.outbox_included=1;v.pending_records=snapshot->rows.size();v.more_may_exist=snapshot->rows.size()>=limit?1:0;
      v.conflicts_checked=conflicts?1:0;
    }
    *out=snapshot.release();return READER_SYNC_VIEW_OK;
  }catch(const std::bad_alloc &){fail(error,READER_SYNC_VIEW_MEMORY,0,0,"Out of memory");return READER_SYNC_VIEW_MEMORY;}
  catch(...){fail(error,READER_SYNC_VIEW_MEMORY,0,0,"Unexpected failure");return READER_SYNC_VIEW_MEMORY;}
}
extern "C" reader_sync_view_status reader_sync_view_summary_get(const reader_sync_view_snapshot *s,reader_sync_view_summary *out){
  if(out)*out={};
  if(!s||!out)return READER_SYNC_VIEW_ARGUMENT;
  *out=s->summary;return READER_SYNC_VIEW_OK;
}
extern "C" reader_sync_view_status reader_sync_view_rows(const reader_sync_view_snapshot *s,size_t offset,
    reader_sync_view_row *rows,size_t capacity,size_t *copied){
  if(copied)*copied=0;
  if(!s||!copied||!rows||!capacity||offset>s->rows.size())return READER_SYNC_VIEW_ARGUMENT;
  size_t n=s->rows.size()-offset;if(n>capacity)n=capacity;
  for(size_t i=0;i<n;i++)rows[i]=s->rows[offset+i];
  *copied=n;return READER_SYNC_VIEW_OK;
}
extern "C" reader_sync_view_status reader_sync_view_release(reader_sync_view_snapshot **p){
  if(!p)return READER_SYNC_VIEW_ARGUMENT;
  delete *p;*p=nullptr;return READER_SYNC_VIEW_OK;
}
extern "C" const char *reader_sync_view_phase_text(reader_sync_view_phase p){
  switch(p){
    case READER_SYNC_VIEW_IDLE:return "idle";case READER_SYNC_VIEW_SYNCING:return "syncing";
    case READER_SYNC_VIEW_CANCELLING:return "cancelling";case READER_SYNC_VIEW_CANCELLED:return "cancelled";
    case READER_SYNC_VIEW_SWEEP_COMPLETE:return "sweep-complete";case READER_SYNC_VIEW_FAILED:return "failed";
    case READER_SYNC_VIEW_CLOSING:return "closing";case READER_SYNC_VIEW_CLOSED:return "closed";
    default:return "unknown";
  }
}
extern "C" const char *reader_sync_view_reason_text(reader_sync_view_reason r){
  switch(r){
    case READER_SYNC_VIEW_REASON_NONE:return "none";case READER_SYNC_VIEW_REASON_NEEDS_CREDENTIALS:return "needs-credentials";
    case READER_SYNC_VIEW_REASON_OFFLINE:return "offline";case READER_SYNC_VIEW_REASON_TLS:return "tls";
    case READER_SYNC_VIEW_REASON_SERVER:return "server";case READER_SYNC_VIEW_REASON_ACCOUNT:return "account";
    case READER_SYNC_VIEW_REASON_STORAGE:return "storage";case READER_SYNC_VIEW_REASON_CONFLICT:return "conflict";
    case READER_SYNC_VIEW_REASON_INTEGRITY:return "integrity";case READER_SYNC_VIEW_REASON_LIMIT:return "limit";
    case READER_SYNC_VIEW_REASON_INTERNAL:return "internal";
    default:return "unknown";
  }
}
