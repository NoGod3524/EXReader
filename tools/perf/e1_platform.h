/* SPDX-License-Identifier: MIT */
#ifndef E1_PLATFORM_H
#define E1_PLATFORM_H
#include <stdlib.h>
#ifdef _WIN32
#include <windows.h>
#include <psapi.h>
/* R3 reports Linux ru_maxrss in KiB; preserve the byte result on Windows. */
struct rusage { long long ru_maxrss; };
#define RUSAGE_SELF 0
static int getrusage(int who, struct rusage *usage) {
  PROCESS_MEMORY_COUNTERS counters;
  (void)who;
  if(!GetProcessMemoryInfo(GetCurrentProcess(), &counters, sizeof(counters))) return -1;
  usage->ru_maxrss=(long long)(counters.PeakWorkingSetSize/1024);
  return 0;
}
static int e1_pin(void) {
  const char *cpu=getenv("E1_CPU");
  const char *priority=getenv("E1_PRIORITY");
  unsigned index=cpu?(unsigned)strtoul(cpu,NULL,10):0;
  if(priority && !strcmp(priority,"high") && !SetPriorityClass(GetCurrentProcess(),HIGH_PRIORITY_CLASS)) return 0;
  return index<sizeof(DWORD_PTR)*8 && SetProcessAffinityMask(GetCurrentProcess(),(DWORD_PTR)1<<index);
}
#else
#include <sys/resource.h>
/* Non-Windows callers must set affinity externally (e.g. taskset). */
static int e1_pin(void) { return 1; }
#endif
static float e1_dimension(const char *name, float fallback) {
  const char *value=getenv(name);
  return value?(float)atoi(value):fallback;
}
#endif
