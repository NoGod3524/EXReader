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
  if(!e){
    return;
  }
  *e={};
  e->status=s;
  e->session_status=session;
  e->revision_code=revision;
  size_t n=0;
  while(text[n]&&n<sizeof(e->message)-1){
    e->message[n]=text[n];
    n++;
  }
  e->message[n]=0;
}

/* One capability per handle: a store opened through
 * reader_revisions_open_raw_v3 refuses the legacy entry point (READER_REV_ARGUMENT)
 * and vice versa. The compiled profile selects the entry point that matches the
 * handle its host opened. No private handle field is read, and a handle from the
 * other family fails closed instead of being guessed. */
reader_revision_status read_outbox(reader_revisions *store,size_t limit,reader_revision_outbox_fn visit,
    void *context,reader_revision_error *error){
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  return reader_revision_outbox_raw_v3(store,limit,visit,context,error);
#else
  return reader_revision_outbox(store,limit,visit,context,error);
#endif
}

reader_revision_status read_heads(reader_revisions *store,const char *entity_kind,const char *entity_key,
    reader_revision_head_fn visit,void *context,reader_revision_state *state,reader_revision_error *error){
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  return reader_revision_heads_raw_v3(store,entity_kind,entity_key,visit,context,state,error);
#else
  return reader_revision_heads(store,entity_kind,entity_key,visit,context,state,error);
#endif
}

reason from_revision(int code){
  switch(code){
    case READER_REV_OK:
      return READER_SYNC_VIEW_REASON_NONE;
    case READER_REV_COLLISION:
    case READER_REV_MISSING_PARENT:
    case READER_REV_CYCLE:
      return READER_SYNC_VIEW_REASON_CONFLICT;
    case READER_REV_DATABASE:
    case READER_REV_MEMORY:
      return READER_SYNC_VIEW_REASON_STORAGE;
    case READER_REV_HASH:
    case READER_REV_FORMAT:
    case READER_REV_UNSAFE:
      return READER_SYNC_VIEW_REASON_INTEGRITY;
    case READER_REV_LIMIT:
      return READER_SYNC_VIEW_REASON_LIMIT;
    default:
      return READER_SYNC_VIEW_REASON_INTERNAL;
  }
}

reason from_dav(int dav,int http){
  if(http==401||http==403){
    return READER_SYNC_VIEW_REASON_NEEDS_CREDENTIALS;
  }
  switch(dav){
    case EXR_DAV_OK:
    case EXR_DAV_CANCELLED:
      return READER_SYNC_VIEW_REASON_NONE;
    case EXR_DAV_AUTH:
      return READER_SYNC_VIEW_REASON_NEEDS_CREDENTIALS;
    case EXR_DAV_TLS:
      return READER_SYNC_VIEW_REASON_TLS;
    case EXR_DAV_IO:
      return READER_SYNC_VIEW_REASON_OFFLINE;
    case EXR_DAV_LIMIT:
      return READER_SYNC_VIEW_REASON_LIMIT;
    case EXR_DAV_MEMORY:
      return READER_SYNC_VIEW_REASON_STORAGE;
    case EXR_DAV_ARGUMENT:
      return READER_SYNC_VIEW_REASON_INTERNAL;
    default:
      return READER_SYNC_VIEW_REASON_SERVER;
  }
}

reason classify(const reader_session_snapshot &s){
  const reader_sync_error &e=s.error;
  switch(s.status){
    case READER_SESSION_OK:
      return READER_SYNC_VIEW_REASON_NONE;
    case READER_SESSION_ACCOUNT:
      return READER_SYNC_VIEW_REASON_ACCOUNT;
    case READER_SESSION_IO:
      return READER_SYNC_VIEW_REASON_STORAGE;
    case READER_SESSION_SYNC:
      break;
    default:
      return READER_SYNC_VIEW_REASON_INTERNAL;
  }
  if(e.http_status==401||e.http_status==403){
    return READER_SYNC_VIEW_REASON_NEEDS_CREDENTIALS;
  }
  if(e.dav_code){
    return from_dav(e.dav_code,e.http_status);
  }
  if(e.revision_code){
    return from_revision(e.revision_code);
  }
  switch(e.code){
    case READER_SYNC_OK:
    case READER_SYNC_CANCELLED:
      return READER_SYNC_VIEW_REASON_NONE;
    case READER_SYNC_HASH:
      return READER_SYNC_VIEW_REASON_INTEGRITY;
    case READER_SYNC_LIMIT:
      return READER_SYNC_VIEW_REASON_LIMIT;
    case READER_SYNC_IO:
      return READER_SYNC_VIEW_REASON_STORAGE;
    case READER_SYNC_DAV:
      return READER_SYNC_VIEW_REASON_SERVER;
    case READER_SYNC_REVISION:
      return READER_SYNC_VIEW_REASON_INTERNAL;
    default:
      return READER_SYNC_VIEW_REASON_INTERNAL;
  }
}

reader_sync_view_phase phase_of(reader_session_state s){
  switch(s){
    case READER_SESSION_IDLE:
      return READER_SYNC_VIEW_IDLE;
    case READER_SESSION_RUNNING:
      return READER_SYNC_VIEW_SYNCING;
    case READER_SESSION_CANCELLING:
      return READER_SYNC_VIEW_CANCELLING;
    case READER_SESSION_CANCELLED:
      return READER_SYNC_VIEW_CANCELLED;
    case READER_SESSION_FINISHED:
      return READER_SYNC_VIEW_SWEEP_COMPLETE;
    case READER_SESSION_FAILED:
      return READER_SYNC_VIEW_FAILED;
    case READER_SESSION_CLOSING:
      return READER_SYNC_VIEW_CLOSING;
    case READER_SESSION_CLOSED:
      return READER_SYNC_VIEW_CLOSED;
  }
  return READER_SYNC_VIEW_UNKNOWN;
}

struct copied_row {
  reader_sync_view_row row{};
  std::string kind;
  std::string key;
};

struct collector {
  std::vector<copied_row> rows;
  size_t limit=0;
  bool memory=false;
};

// Runs inside reader_revision_outbox: copy only, never call back into the store.
int visit(void *opaque,const reader_revision_outbox_row *r){
  collector &c=*static_cast<collector *>(opaque);
  try{
    copied_row value;
    size_t n=0;
    while(n<sizeof(value.row.revision_id)-1&&r->info.revision_id[n]){
      value.row.revision_id[n]=r->info.revision_id[n];
      n++;
    }
    value.row.revision_id[n]=0;
    n=0;
    while(n<sizeof(value.row.entity_kind)-1&&r->info.entity_kind[n]){
      value.row.entity_kind[n]=r->info.entity_kind[n];
      n++;
    }
    value.row.entity_kind[n]=0;
    n=0;
    while(n<sizeof(value.row.operation)-1&&r->info.operation[n]){
      value.row.operation[n]=r->info.operation[n];
      n++;
    }
    value.row.operation[n]=0;
    value.row.bytes=(uint64_t)r->info.bytes;
    value.row.attempts=r->attempts;
    // Retry stores "revision_error_<decimal code>"; anything else stays "none".
    static const char token[]="revision_error_";
    const char *last=r->last_error;
    if(last&&std::strlen(last)>sizeof(token)-1&&std::strncmp(last,token,sizeof(token)-1)==0){
      const char *digits=last+sizeof(token)-1;
      int code=0;
      size_t used=0;
      while(digits[used]>='0'&&digits[used]<='9'&&used<3){
        code=code*10+(digits[used]-'0');
        used++;
      }
      if(used&&!digits[used]&&code>=(int)READER_REV_ARGUMENT&&code<=(int)READER_REV_NOT_FOUND){
        value.row.last_revision_code=code;
        value.row.last_reason=from_revision(code);
      }
    }
    value.kind=r->info.entity_kind;
    value.key=r->info.entity_key;
    c.rows.push_back(std::move(value));
  }catch(...){
    c.memory=true;
    return 1;
  }
  return c.rows.size()>=c.limit?1:0;
}

int heads_visit(void *,const reader_revision_head *){
  return 0;
}
}

extern "C" reader_sync_view_status reader_sync_view_capture(reader_session *session,reader_revisions *revisions,
    const reader_sync_view_options *options,reader_sync_view_snapshot **out,reader_sync_view_error *error){
  if(error){
    *error={};
  }
  if(out){
    *out=nullptr;
  }
  if(!out||!session){
    fail(error,READER_SYNC_VIEW_ARGUMENT,0,0,"Session and output are required");
    return READER_SYNC_VIEW_ARGUMENT;
  }
  size_t limit=READER_SYNC_VIEW_DEFAULT_ROWS;
  bool conflicts=false;
  if(options){
    if(options->row_limit>READER_SYNC_VIEW_MAX_ROWS){
      fail(error,READER_SYNC_VIEW_ARGUMENT,0,0,"Row limit must be 0..100");
      return READER_SYNC_VIEW_ARGUMENT;
    }
    if(options->row_limit){
      limit=options->row_limit;
    }
    conflicts=options->detect_conflicts!=0;
  }
  try{
    std::unique_ptr<reader_sync_view_snapshot> snapshot(new reader_sync_view_snapshot);
    reader_session_snapshot observed{};
    int observed_status=(int)reader_session_observe(session,&observed);
    if(observed_status!=(int)READER_SESSION_OK){
      fail(error,READER_SYNC_VIEW_SESSION,observed_status,0,"Session observation failed");
      return READER_SYNC_VIEW_SESSION;
    }
    reader_sync_view_summary &v=snapshot->summary;
    v.phase=phase_of(observed.state);
    v.reason=classify(observed);
    v.session_status=(int)observed.status;
    v.http_status=observed.error.http_status;
    v.dav_code=observed.error.dav_code;
    v.revision_code=observed.error.revision_code;
    v.attempt=observed.attempt;
    v.completed_sweeps=observed.completed_sweeps;
    v.operations=observed.steps;
    v.pushed_operations=observed.pushed;
    v.pulled_operations=observed.pulled;
    v.originals_verified_operations=observed.originals_verified;
    v.metadata_wait_observations=observed.pending_metadata_observations;
    v.original_wait_observations=observed.pending_original_observations;
    v.transfer_bytes=observed.transfer_bytes;
    v.shard=observed.shard;
    v.completed_shards=observed.completed_shards;
    v.shard_count=READER_SYNC_VIEW_SHARD_COUNT;
    for(size_t n=0;n<sizeof(v.cursor)-1&&observed.after[n];n++){
      v.cursor[n]=observed.after[n];
    }
    v.sweep_complete=observed.state==READER_SESSION_FINISHED?1:0;
    v.library_complete=observed.full_library_complete?1:0;
    v.resumable=(observed.state==READER_SESSION_CANCELLED||observed.state==READER_SESSION_FAILED)?1:0;
    if(revisions){
      collector gathered;
      gathered.limit=limit;
      reader_revision_error revision_error{};
      reader_revision_status status=read_outbox(revisions,limit,visit,&gathered,&revision_error);
      if(gathered.memory){
        throw std::bad_alloc();
      }
      if(status!=READER_REV_OK){
        fail(error,READER_SYNC_VIEW_REVISIONS,0,(int)status,
          status==READER_REV_OWNER?"Pending list needs its owning worker":"Pending list could not be read");
        return READER_SYNC_VIEW_REVISIONS;
      }
      std::set<std::pair<std::string,std::string>> concurrent;
      if(conflicts){
        std::set<std::pair<std::string,std::string>> checked;
        for(const copied_row &row:gathered.rows){
          std::pair<std::string,std::string> identity(row.kind,row.key);
          if(!checked.insert(identity).second){
            continue;
          }
          reader_revision_state state{};
          status=read_heads(revisions,row.kind.c_str(),row.key.c_str(),heads_visit,nullptr,&state,&revision_error);
          if(status!=READER_REV_OK){
            fail(error,READER_SYNC_VIEW_REVISIONS,0,(int)status,"Conflict check could not be read");
            return READER_SYNC_VIEW_REVISIONS;
          }
          if(state.heads>1){
            concurrent.insert(identity);
          }
        }
      }
      snapshot->rows.reserve(gathered.rows.size());
      for(copied_row &row:gathered.rows){
        row.row.conflict=concurrent.count(std::make_pair(row.kind,row.key))?1:0;
        if(row.row.conflict){
          v.conflict_records++;
        }
        if(row.row.attempts>0||row.row.last_revision_code){
          v.retried_records++;
        }
        snapshot->rows.push_back(row.row);
      }
      v.outbox_included=1;
      v.pending_records=snapshot->rows.size();
      v.more_may_exist=snapshot->rows.size()>=limit?1:0;
      v.conflicts_checked=conflicts?1:0;
    }
    *out=snapshot.release();
    return READER_SYNC_VIEW_OK;
  }catch(const std::bad_alloc &){
    fail(error,READER_SYNC_VIEW_MEMORY,0,0,"Out of memory");
    return READER_SYNC_VIEW_MEMORY;
  }catch(...){
    fail(error,READER_SYNC_VIEW_MEMORY,0,0,"Unexpected failure");
    return READER_SYNC_VIEW_MEMORY;
  }
}

extern "C" reader_sync_view_status reader_sync_view_summary_get(const reader_sync_view_snapshot *snapshot,
    reader_sync_view_summary *out){
  if(out){
    *out={};
  }
  if(!snapshot||!out){
    return READER_SYNC_VIEW_ARGUMENT;
  }
  *out=snapshot->summary;
  return READER_SYNC_VIEW_OK;
}

extern "C" reader_sync_view_status reader_sync_view_rows(const reader_sync_view_snapshot *snapshot,size_t offset,
    reader_sync_view_row *rows,size_t capacity,size_t *copied){
  if(copied){
    *copied=0;
  }
  if(!snapshot||!copied||!rows||!capacity||offset>snapshot->rows.size()){
    return READER_SYNC_VIEW_ARGUMENT;
  }
  size_t count=snapshot->rows.size()-offset;
  if(count>capacity){
    count=capacity;
  }
  for(size_t n=0;n<count;n++){
    rows[n]=snapshot->rows[offset+n];
  }
  *copied=count;
  return READER_SYNC_VIEW_OK;
}

extern "C" reader_sync_view_status reader_sync_view_release(reader_sync_view_snapshot **pointer){
  if(!pointer){
    return READER_SYNC_VIEW_ARGUMENT;
  }
  delete *pointer;
  *pointer=nullptr;
  return READER_SYNC_VIEW_OK;
}

extern "C" const char *reader_sync_view_phase_text(reader_sync_view_phase phase){
  switch(phase){
    case READER_SYNC_VIEW_IDLE:
      return "idle";
    case READER_SYNC_VIEW_SYNCING:
      return "syncing";
    case READER_SYNC_VIEW_CANCELLING:
      return "cancelling";
    case READER_SYNC_VIEW_CANCELLED:
      return "cancelled";
    case READER_SYNC_VIEW_SWEEP_COMPLETE:
      return "sweep-complete";
    case READER_SYNC_VIEW_FAILED:
      return "failed";
    case READER_SYNC_VIEW_CLOSING:
      return "closing";
    case READER_SYNC_VIEW_CLOSED:
      return "closed";
    default:
      return "unknown";
  }
}

extern "C" const char *reader_sync_view_reason_text(reader_sync_view_reason reason){
  switch(reason){
    case READER_SYNC_VIEW_REASON_NONE:
      return "none";
    case READER_SYNC_VIEW_REASON_NEEDS_CREDENTIALS:
      return "needs-credentials";
    case READER_SYNC_VIEW_REASON_OFFLINE:
      return "offline";
    case READER_SYNC_VIEW_REASON_TLS:
      return "tls";
    case READER_SYNC_VIEW_REASON_SERVER:
      return "server";
    case READER_SYNC_VIEW_REASON_ACCOUNT:
      return "account";
    case READER_SYNC_VIEW_REASON_STORAGE:
      return "storage";
    case READER_SYNC_VIEW_REASON_CONFLICT:
      return "conflict";
    case READER_SYNC_VIEW_REASON_INTEGRITY:
      return "integrity";
    case READER_SYNC_VIEW_REASON_LIMIT:
      return "limit";
    case READER_SYNC_VIEW_REASON_INTERNAL:
      return "internal";
    default:
      return "unknown";
  }
}
