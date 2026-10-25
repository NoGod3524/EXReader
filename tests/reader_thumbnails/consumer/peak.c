/* SPDX-License-Identifier: MIT */
/* Raw process memory for the measurement record only; never a pass gate. */
#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <psapi.h>
unsigned long long thumb_peak_rss(void) {
  PROCESS_MEMORY_COUNTERS c;
  c.cb = sizeof(c);
  if (!GetProcessMemoryInfo(GetCurrentProcess(), &c, sizeof(c))) return 0;
  return (unsigned long long)c.PeakWorkingSetSize;
}
unsigned long long thumb_current_rss(void) {
  PROCESS_MEMORY_COUNTERS c;
  c.cb = sizeof(c);
  if (!GetProcessMemoryInfo(GetCurrentProcess(), &c, sizeof(c))) return 0;
  return (unsigned long long)c.WorkingSetSize;
}
int thumb_thread_count(void) { return -1; }
#elif defined(__APPLE__)
#include <mach/mach.h>
#include <sys/resource.h>
unsigned long long thumb_peak_rss(void) {
  struct rusage u;
  if (getrusage(RUSAGE_SELF, &u) != 0) return 0;
  return (unsigned long long)u.ru_maxrss; /* bytes on macOS */
}
unsigned long long thumb_current_rss(void) {
  mach_task_basic_info_data_t info;
  mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
  if (task_info(mach_task_self(), MACH_TASK_BASIC_INFO, (task_info_t)&info, &count) != KERN_SUCCESS) return 0;
  return (unsigned long long)info.resident_size;
}
int thumb_thread_count(void) {
  thread_array_t threads;
  mach_msg_type_number_t count = 0;
  if (task_threads(mach_task_self(), &threads, &count) != KERN_SUCCESS) return -1;
  vm_deallocate(mach_task_self(), (vm_address_t)threads, count * sizeof(*threads));
  return (int)count;
}
#else
#include <stdio.h>
#include <sys/resource.h>
#include <unistd.h>
unsigned long long thumb_peak_rss(void) {
  struct rusage u;
  if (getrusage(RUSAGE_SELF, &u) != 0) return 0;
  return (unsigned long long)u.ru_maxrss * 1024ull; /* KiB on Linux */
}
unsigned long long thumb_current_rss(void) {
  unsigned long long size = 0, resident = 0;
  FILE *f = fopen("/proc/self/statm", "r");
  if (!f) return 0;
  if (fscanf(f, "%llu %llu", &size, &resident) != 2) resident = 0;
  fclose(f);
  return resident * (unsigned long long)sysconf(_SC_PAGESIZE);
}
int thumb_thread_count(void) {
  char line[256];
  int n = -1;
  FILE *f = fopen("/proc/self/status", "r");
  if (!f) return -1;
  while (fgets(line, sizeof(line), f))
    if (sscanf(line, "Threads: %d", &n) == 1) break;
  fclose(f);
  return n;
}
#endif
