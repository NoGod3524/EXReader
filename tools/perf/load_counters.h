/* SPDX-License-Identifier: MIT
 * Windows x64 measurement only. TSC is elapsed ticks, NOT retired instructions
 * or unhalted core cycles. Thread cycles exclude descheduling; never convert
 * them to milliseconds. Hardware PMCs need a separately configured driver.
 */
#ifndef LOAD_COUNTERS_H
#define LOAD_COUNTERS_H
#include <windows.h>
#include <x86intrin.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
  uint64_t cycles, tsc, cpu_100ns;
  uint32_t switches;
  double wall_ms;
} load_stamp;
typedef struct { double wall_ms; load_stamp work; } load_measure;
typedef struct {
  load_measure before, after;
  load_stamp start, layout_end, end, transition;
  int started;
} load_sample;
static HANDLE load_profile;
static LARGE_INTEGER load_frequency;
static int load_sandwich;
double perf_reference_ms(void);
uint64_t perf_reference_steps(void);

static void load_close(void) { if(load_profile) DisableThreadProfiling(load_profile); }
static void load_init(void) {
  if(EnableThreadProfiling(GetCurrentThread(), THREAD_PROFILING_FLAG_DISPATCH, 0,
                           &load_profile)) { fputs("thread profiling unavailable\n",stderr); exit(4); }
  atexit(load_close);
  if(!QueryPerformanceFrequency(&load_frequency)) exit(4);
  load_sandwich=getenv("LOAD_SANDWICH") && !strcmp(getenv("LOAD_SANDWICH"),"1");
}
static load_stamp load_read(void) {
  for(unsigned retry=0;retry<64;retry++) {
    PERFORMANCE_DATA p={0},after={0}; ULONG64 cycles;
    FILETIME created,exited,kernel,user;LARGE_INTEGER wall;
    p.Size=after.Size=sizeof(p);p.Version=after.Version=PERFORMANCE_DATA_VERSION;
    if(ReadThreadProfilingData(load_profile,READ_THREAD_PROFILING_FLAG_DISPATCHING,&p) ||
       !QueryThreadCycleTime(GetCurrentThread(),&cycles) ||
       !GetThreadTimes(GetCurrentThread(),&created,&exited,&kernel,&user)) exit(4);
    _mm_lfence();uint64_t tsc=__rdtsc();_mm_lfence();
    if(!QueryPerformanceCounter(&wall) ||
       ReadThreadProfilingData(load_profile,READ_THREAD_PROFILING_FLAG_DISPATCHING,&after)) exit(4);
    /* Retry only a torn clock snapshot, never a target operation/sample. A
       preemption inside the snapshot must not separate QPC and TSC by a quantum. */
    if(p.ContextSwitchCount!=after.ContextSwitchCount) continue;
    load_stamp s={cycles,tsc,
      (((uint64_t)kernel.dwHighDateTime<<32)|kernel.dwLowDateTime)+
      (((uint64_t)user.dwHighDateTime<<32)|user.dwLowDateTime),p.ContextSwitchCount,
      (double)wall.QuadPart*1000.0/(double)load_frequency.QuadPart};
    return s;
  }
  fputs("could not read coherent counter snapshot\n",stderr);exit(4);
}
static load_stamp load_delta(load_stamp a,load_stamp b) {
  load_stamp d={b.cycles-a.cycles,b.tsc-a.tsc,b.cpu_100ns-a.cpu_100ns,b.switches-a.switches,b.wall_ms-a.wall_ms};
  return d;
}
static load_stamp load_add(load_stamp a,load_stamp b) {
  load_stamp s={a.cycles+b.cycles,a.tsc+b.tsc,a.cpu_100ns+b.cpu_100ns,a.switches+b.switches,a.wall_ms+b.wall_ms};
  return s;
}
static load_measure load_reference(void) {
  load_stamp a=load_read();(void)perf_reference_ms();load_stamp b=load_read();
  load_measure m={b.wall_ms-a.wall_ms,load_delta(a,b)};return m;
}
static double load_begin(load_sample *s) {
  if(!s->started || !load_sandwich) { s->before=load_reference();s->started=1; }
  s->start=load_read();s->layout_end=s->start;
  return s->before.wall_ms;
}
static void load_end(load_sample *s) {
  s->end=load_read();
  if(load_sandwich) s->after=load_reference();
}
static void load_print_stamp(const char *name,load_stamp s) {
  printf("\"%s\":{\"cycles\":%" PRIu64 ",\"tsc\":%" PRIu64
         ",\"cpu_100ns\":%" PRIu64 ",\"switches\":%u,\"wall_ms\":%.6f}",
         name,s.cycles,s.tsc,s.cpu_100ns,s.switches,s.wall_ms);
}
static void load_print_measure(const char *name,load_measure m) {
  printf("\"%s\":{\"wall_ms\":%.6f,",name,m.wall_ms);
  load_print_stamp("work",m.work);putchar('}');
}
static void load_print_sample(load_sample *s) {
  printf(",\"load\":{");load_print_measure("before",s->before);putchar(',');
  load_print_measure("after",s->after);putchar(',');
  load_print_stamp("target",load_add(s->transition,load_delta(s->start,s->end)));putchar(',');
  load_print_stamp("layout",load_add(s->transition,load_delta(s->start,s->layout_end)));putchar(',');
  load_print_stamp("render",load_delta(s->layout_end,s->end));printf("}}");
}
#endif
