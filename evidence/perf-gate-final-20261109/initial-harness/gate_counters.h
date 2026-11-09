/* SPDX-License-Identifier: MIT
 * Per-thread executed cycles, never TSC or CPU time relabelled as cycles.
 * Linux requires an exposed PMU; permission/virtualization failures are fatal.
 */
#ifndef GATE_COUNTERS_H
#define GATE_COUNTERS_H
#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
static uint64_t gate_cycles(void) {
  ULONG64 value;
  if(!QueryThreadCycleTime(GetCurrentThread(), &value)) exit(4);
  return value;
}
static void gate_init(void) { (void)gate_cycles(); }
#else
#include <linux/perf_event.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <time.h>
static int gate_fd=-1;
static void gate_close(void) { if(gate_fd>=0) close(gate_fd); }
static void gate_init(void) {
  struct perf_event_attr attr={0};
  attr.type=PERF_TYPE_HARDWARE;attr.size=sizeof(attr);
  attr.config=PERF_COUNT_HW_CPU_CYCLES;
  attr.exclude_kernel=1;attr.exclude_hv=1;attr.pinned=1;
  attr.read_format=PERF_FORMAT_TOTAL_TIME_ENABLED|PERF_FORMAT_TOTAL_TIME_RUNNING;
  gate_fd=(int)syscall(SYS_perf_event_open,&attr,0,-1,-1,PERF_FLAG_FD_CLOEXEC);
  if(gate_fd<0) { perror("thread cycles unavailable: perf_event_open");exit(4); }
  atexit(gate_close);
}
static uint64_t gate_cycles(void) {
  struct { uint64_t cycles,enabled,running; } value;
  if(read(gate_fd,&value,sizeof(value))!=sizeof(value) || !value.running ||
     value.enabled!=value.running) {
    fputs("thread cycles unavailable or multiplexed; no time fallback\n",stderr);exit(4);
  }
  return value.cycles;
}
#endif
typedef struct { uint64_t cycles; double wall_ms; } gate_stamp;
typedef struct { gate_stamp start,layout_end,end,transition; uint64_t injected; } gate_sample;
static double gate_wall(void) {
#ifdef _WIN32
  LARGE_INTEGER value,frequency;
  if(!QueryPerformanceCounter(&value) || !QueryPerformanceFrequency(&frequency)) exit(4);
  return (double)value.QuadPart*1000.0/(double)frequency.QuadPart;
#else
  struct timespec t;
  if(clock_gettime(CLOCK_MONOTONIC,&t)) exit(4);
  return t.tv_sec*1000.0+t.tv_nsec/1000000.0;
#endif
}
static gate_stamp gate_read(void) {
  gate_stamp s={gate_cycles(),gate_wall()};return s;
}
static gate_stamp gate_delta(gate_stamp a,gate_stamp b) {
  gate_stamp s={b.cycles-a.cycles,b.wall_ms-a.wall_ms};return s;
}
static gate_stamp gate_add(gate_stamp a,gate_stamp b) {
  gate_stamp s={a.cycles+b.cycles,a.wall_ms+b.wall_ms};return s;
}
static double gate_begin(gate_sample *s) {
  s->start=gate_read();s->layout_end=s->start;return 1.0;
}
static void gate_end(gate_sample *s) {
  s->end=gate_read();
  const char *fault=getenv("PERF_GATE_FAULT_PERCENT");
  if(fault && !strcmp(fault,"25")) {
    /* Real executed work inside the measured rendering window. No JSON scaling.
       Only the selected book's child process gets this environment variable. */
    uint64_t original=s->end.cycles-s->start.cycles+s->transition.cycles;
    uint64_t begin=s->end.cycles;
    volatile uint64_t mix=1;
    while(gate_cycles()-begin < original/4) {
      for(unsigned i=0;i<256;i++) mix=(mix^i)*UINT64_C(1099511628211);
    }
    s->end=gate_read();s->injected=s->end.cycles-begin;
  } else if(fault && strcmp(fault,"0")) {
    fputs("only the declared +25% fault is supported\n",stderr);exit(4);
  }
}
static void gate_print(gate_sample *s) {
  gate_stamp total=gate_add(s->transition,gate_delta(s->start,s->end));
  printf(",\"thread_cycles\":%" PRIu64 ",\"cycle_wall_ms\":%.6f,"
         "\"injected_cycles\":%" PRIu64 "}",total.cycles,total.wall_ms,s->injected);
}
#endif
