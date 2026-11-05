/* SPDX-License-Identifier: MIT
 * Isolated fake-provider contract checks, NOT actual-host/provider acceptance.
 * Assertions remain active in Release. No fixture enters the library archive.
 */
#include "windows_migration_host.h"
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while(0)
typedef struct {
  int acquire, exclusive, start, terminal, cancel, reopen, release_count;
  int reopen_count, start_count, partial_lease, reenter;
  rmh_worker_outcome outcome;
  reader_migration_host *h;
} fake;
static int acquire(void *v, void **lease) {
  fake *f = v;
  if (f->acquire || f->partial_lease) *lease = f;
  return f->acquire;
}
static int exclusive(void *v, void *lease) {
  fake *f=v; CHECK(lease==f); return f->exclusive;
}
static int start(void *v, void *lease, uint64_t epoch) {
  fake *f=v; CHECK(lease==f && epoch!=0); ++f->start_count;
  if (f->reenter) CHECK(rmh_cancel(f->h,epoch)==RMH_REFUSED);
  return f->start;
}
static rmh_worker_outcome observe(void *v, void *lease, uint64_t epoch, int *terminal) {
  fake *f=v; CHECK(lease==f && epoch!=0); *terminal=f->terminal; return f->outcome;
}
static int cancel(void *v, void *lease, uint64_t epoch) {
  fake *f=v; CHECK(lease==f && epoch!=0); return f->cancel;
}
static int reopen(void *v, void *lease, rmh_worker_outcome outcome) {
  fake *f=v; CHECK(lease==f && outcome==f->outcome); ++f->reopen_count; return f->reopen;
}
static void release(void *v, void *lease) {
  fake *f=v; CHECK(lease==f); ++f->release_count;
}
static rmh_provider provider(fake *f) {
  rmh_provider p={1,f,acquire,exclusive,start,observe,cancel,reopen,release}; return p;
}
static reader_migration_host *create(fake *f) {
  rmh_provider p;
  *f=(fake){0};
  f->acquire=f->exclusive=f->start=f->cancel=f->reopen=1;
  p=provider(f);
  f->h=rmh_create(&p); CHECK(f->h); return f->h;
}
static uint64_t running(fake *f) {
  uint64_t epoch=0;
  CHECK(rmh_acquire(f->h)==RMH_OK);
  CHECK(!rmh_commands_allowed(f->h));
  CHECK(rmh_destroy(f->h)==RMH_REFUSED);
  CHECK(rmh_opened(f->h,1)==RMH_OK);
  CHECK(rmh_commands_allowed(f->h));
  CHECK(rmh_request(f->h,&epoch)==RMH_OK && epoch==1);
  CHECK(!rmh_commands_allowed(f->h));
  return epoch;
}
static void close_destroy(fake *f) {
  CHECK(rmh_host_closed(f->h)==RMH_OK);
  CHECK(rmh_destroy(f->h)==RMH_OK);
  CHECK(f->release_count==1);
}
static DWORD WINAPI wrong_thread(void *v) {
  fake *f=v;
  CHECK(!rmh_commands_allowed(f->h));
  CHECK(rmh_get_state(f->h)==RMH_RECOVERY_REQUIRED);
  CHECK(rmh_cancel(f->h,1)==RMH_REFUSED);
  CHECK(rmh_host_closed(f->h)==RMH_REFUSED);
  CHECK(rmh_destroy(f->h)==RMH_REFUSED);
  return 0;
}
int main(void) {
  fake f; rmh_provider p; uint64_t e, second; HANDLE thread;
  int groups=0;
  CHECK(!rmh_create(NULL));
  p=(rmh_provider){0}; CHECK(!rmh_create(&p));
  create(&f); p=provider(&f); p.version=2; CHECK(!rmh_create(&p));
  CHECK(rmh_destroy(f.h)==RMH_OK); ++groups;

  create(&f); f.acquire=0;
  CHECK(rmh_acquire(f.h)==RMH_REFUSED);
  CHECK(rmh_get_state(f.h)==RMH_RECOVERY_REQUIRED);
  CHECK(rmh_opened(f.h,1)==RMH_REFUSED);
  CHECK(rmh_destroy(f.h)==RMH_OK && f.release_count==0); ++groups;

  create(&f); f.acquire=0; f.partial_lease=1;
  CHECK(rmh_acquire(f.h)==RMH_REFUSED);
  CHECK(rmh_destroy(f.h)==RMH_OK && f.release_count==1); ++groups;

  create(&f); CHECK(rmh_acquire(f.h)==RMH_OK);
  CHECK(rmh_opened(f.h,0)==RMH_REFUSED);
  CHECK(!rmh_commands_allowed(f.h)); close_destroy(&f); ++groups;

  create(&f); e=running(&f);
  CHECK(rmh_request(f.h,&second)==RMH_REFUSED);
  CHECK(rmh_drained(f.h,e+1,1)==RMH_REFUSED);
  CHECK(rmh_drained(f.h,e,0)==RMH_PENDING && f.start_count==0);
  CHECK(rmh_destroy(f.h)==RMH_REFUSED);
  close_destroy(&f); ++groups;

  create(&f); e=running(&f); f.exclusive=0;
  CHECK(rmh_drained(f.h,e,1)==RMH_REFUSED && f.start_count==0);
  CHECK(rmh_get_state(f.h)==RMH_RECOVERY_REQUIRED);
  close_destroy(&f); ++groups;

  create(&f); e=running(&f); f.start=0;
  CHECK(rmh_drained(f.h,e,1)==RMH_REFUSED);
  CHECK(rmh_destroy(f.h)==RMH_REFUSED);
  CHECK(rmh_host_closed(f.h)==RMH_REFUSED);
  CHECK(rmh_observe(f.h,e)==RMH_PENDING);
  f.terminal=1; f.outcome=RMH_WORKER_COMMITTED_ACKNOWLEDGED;
  CHECK(rmh_observe(f.h,e)==RMH_REFUSED && f.reopen_count==0);
  close_destroy(&f); ++groups;

  create(&f); e=running(&f); f.reenter=1;
  CHECK(rmh_drained(f.h,e,1)==RMH_OK);
  CHECK(rmh_observe(f.h,e+1)==RMH_REFUSED);
  f.outcome=RMH_WORKER_COMMITTED_ACKNOWLEDGED;
  CHECK(rmh_observe(f.h,e)==RMH_PENDING && f.reopen_count==0);
  CHECK(rmh_destroy(f.h)==RMH_REFUSED);
  CHECK(rmh_host_closed(f.h)==RMH_REFUSED);
  f.cancel=0; CHECK(rmh_cancel(f.h,e)==RMH_REFUSED);
  f.cancel=1; CHECK(rmh_cancel(f.h,e)==RMH_OK);
  CHECK(rmh_get_state(f.h)==RMH_MIGRATING); ++groups;

  thread=CreateThread(NULL,0,wrong_thread,&f,0,NULL); CHECK(thread);
  CHECK(WaitForSingleObject(thread,10000)==WAIT_OBJECT_0); CloseHandle(thread);
  CHECK(rmh_get_state(f.h)==RMH_MIGRATING); ++groups;

  f.terminal=1; CHECK(rmh_observe(f.h,e)==RMH_OK && f.reopen_count==1);
  CHECK(!rmh_commands_allowed(f.h));
  CHECK(rmh_destroy(f.h)==RMH_REFUSED);
  CHECK(rmh_opened(f.h,1)==RMH_OK);
  CHECK(rmh_commands_allowed(f.h));
  CHECK(rmh_request(f.h,&second)==RMH_OK && second==2);
  CHECK(rmh_observe(f.h,e)==RMH_REFUSED);
  close_destroy(&f); ++groups;

  create(&f); e=running(&f); CHECK(rmh_drained(f.h,e,1)==RMH_OK);
  f.terminal=1; f.outcome=RMH_WORKER_ABORTED_CLEAN; f.reopen=0;
  CHECK(rmh_observe(f.h,e)==RMH_REFUSED && f.reopen_count==1);
  CHECK(rmh_opened(f.h,1)==RMH_REFUSED); close_destroy(&f); ++groups;

  create(&f); e=running(&f); CHECK(rmh_drained(f.h,e,1)==RMH_OK);
  f.terminal=1; f.outcome=RMH_WORKER_ABORTED_CLEAN;
  CHECK(rmh_observe(f.h,e)==RMH_OK && f.reopen_count==1);
  CHECK(rmh_opened(f.h,0)==RMH_REFUSED);
  CHECK(!rmh_commands_allowed(f.h)); close_destroy(&f); ++groups;

  create(&f); e=running(&f); CHECK(rmh_drained(f.h,e,1)==RMH_OK);
  f.terminal=1; f.outcome=RMH_WORKER_RECOVERY_REQUIRED;
  CHECK(rmh_observe(f.h,e)==RMH_REFUSED && f.reopen_count==0);
  close_destroy(&f); ++groups;

  create(&f); e=running(&f); CHECK(rmh_drained(f.h,e,1)==RMH_OK);
  f.terminal=1; f.outcome=RMH_WORKER_PENDING;
  CHECK(rmh_observe(f.h,e)==RMH_REFUSED && f.reopen_count==0);
  close_destroy(&f); ++groups;

  create(&f); e=running(&f); CHECK(rmh_drained(f.h,e,1)==RMH_OK);
  f.terminal=1; f.outcome=(rmh_worker_outcome)99;
  CHECK(rmh_observe(f.h,e)==RMH_REFUSED && f.reopen_count==0);
  close_destroy(&f); ++groups;
  create(&f); e=running(&f); CHECK(rmh_drained(f.h,e,1)==RMH_OK);
  f.outcome=RMH_WORKER_RECOVERY_REQUIRED;
  CHECK(rmh_observe(f.h,e)==RMH_PENDING);
  CHECK(rmh_get_state(f.h)==RMH_RECOVERY_REQUIRED);
  CHECK(rmh_cancel(f.h,e)==RMH_REFUSED);
  CHECK(rmh_destroy(f.h)==RMH_REFUSED);
  f.terminal=1; f.outcome=RMH_WORKER_COMMITTED_ACKNOWLEDGED;
  CHECK(rmh_observe(f.h,e)==RMH_REFUSED && f.reopen_count==0);
  close_destroy(&f); ++groups;
  CHECK(groups==16);
  printf("controller_contract_groups=%d actual_host_acceptance=false full_p0=false\n",groups);
  return 0;
}
