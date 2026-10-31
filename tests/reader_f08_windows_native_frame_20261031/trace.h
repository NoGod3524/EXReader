/* SPDX-License-Identifier: MIT
 * Explicit diagnostic build only. Buffer native product work; write once at exit.
 * GdiFlush is GDI execution completion, not compositor/physical presentation.
 */
#ifndef F08_WINDOWS_NATIVE_TRACE_H
#define F08_WINDOWS_NATIVE_TRACE_H
#define F08_CAPACITY 65536
/* Metadata follows the owned frame through frame_move, never a borrowed job. */
typedef struct {
  LONG id,input_id;
  LONGLONG queued_qpc,worker_start_qpc,worker_end_qpc;
} f08_origin;
typedef struct {
  const char *kind;
  LONGLONG qpc,start_qpc,book,v0,v1;
  unsigned long generation;
  UINT message;
  int control,flags;
  DWORD thread;
  f08_origin origin;
} f08_row;
static f08_row f08_rows[F08_CAPACITY];
static volatile LONG f08_count,f08_overflow,f08_jobs,f08_inputs;
static LONG f08_active_input;
static volatile LONG f08_direct_frames;
static f08_origin f08_shelf_pending;
static int f08_shelf_redraw=1;
static int f08_enabled;
static wchar_t f08_path[32768];
static LONGLONG f08_tick(void) { LARGE_INTEGER t;QueryPerformanceCounter(&t);return t.QuadPart; }
static void f08_record(const char *kind,LONGLONG start,const f08_origin *origin,
    unsigned long generation,LONGLONG book,int control,UINT message,int flags,LONGLONG v0,LONGLONG v1) {
  LONG at;f08_row *row;
  if(!f08_enabled) return;
  at=InterlockedIncrement(&f08_count)-1;
  if(at<0 || at>=F08_CAPACITY) { InterlockedExchange(&f08_overflow,1);return; }
  row=&f08_rows[at];row->qpc=f08_tick();row->kind=kind;row->start_qpc=start;
  if(origin) row->origin=*origin;
  row->generation=generation;row->book=book;row->control=control;row->message=message;
  row->flags=flags;row->v0=v0;row->v1=v1;row->thread=GetCurrentThreadId();
}
static LONG f08_input_begin(int control,UINT message) {
  LONG previous=f08_active_input;f08_origin origin={0};
  if(!f08_enabled) return previous;
  f08_active_input=InterlockedIncrement(&f08_inputs);origin.input_id=f08_active_input;
  f08_record("input",0,&origin,0,0,control,message,0,0,0);return previous;
}
static void f08_initialize(void) {
  DWORD size=GetEnvironmentVariableW(L"EXREADER_F08_TRACE",f08_path,32768);
  f08_enabled=size>0 && size<32768;
  if(f08_enabled) f08_record("start",0,NULL,0,0,0,0,0,sizeof(f08_rows),F08_CAPACITY);
}
static int f08_finish(void) {
  FILE *file;LONG i,n;LARGE_INTEGER frequency;
  if(!f08_enabled) return 1;
  f08_record("normal_exit",0,NULL,0,0,0,0,0,0,0);
  QueryPerformanceFrequency(&frequency);file=_wfopen(f08_path,L"wb");if(!file)return 0;
  n=f08_count<F08_CAPACITY ? f08_count:F08_CAPACITY;
  fprintf(file,"{\"schema\":1,\"pid\":%lu,\"frequency\":%lld,\"rows_attempted\":%ld,\"overflow\":%s,\"buffer_bytes\":%llu,\"physical_scanout_proven\":false,\"rows\":[\n",
      GetCurrentProcessId(),frequency.QuadPart,f08_count,f08_overflow?"true":"false",(unsigned long long)sizeof(f08_rows));
  for(i=0;i<n;i++) {
    const f08_row *r=&f08_rows[i];
    fprintf(file,"%s{\"index\":%ld,\"kind\":\"%s\",\"qpc\":%lld,\"start_qpc\":%lld,\"job_id\":%ld,\"input_id\":%ld,\"queued_qpc\":%lld,\"worker_start_qpc\":%lld,\"worker_end_qpc\":%lld,\"generation\":%lu,\"book\":%lld,\"control\":%d,\"message\":%u,\"flags\":%d,\"v0\":%lld,\"v1\":%lld,\"thread\":%lu}\n",
      i?",":"",i,r->kind,r->qpc,r->start_qpc,r->origin.id,r->origin.input_id,r->origin.queued_qpc,
      r->origin.worker_start_qpc,r->origin.worker_end_qpc,r->generation,r->book,r->control,r->message,r->flags,r->v0,r->v1,r->thread);
  }
  fprintf(file,"]}\n");return fclose(file)==0;
}
#endif
