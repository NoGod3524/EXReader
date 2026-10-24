/* SPDX-License-Identifier: MIT */
/* Raw process peak memory for the measurement record only; never a pass gate. */
#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <psapi.h>
unsigned long long search_probe_peak_memory(void) {
  PROCESS_MEMORY_COUNTERS counters;
  counters.cb = sizeof(counters);
  if (!GetProcessMemoryInfo(GetCurrentProcess(), &counters, sizeof(counters))) return 0;
  return (unsigned long long)counters.PeakWorkingSetSize;
}
#else
#include <sys/resource.h>
unsigned long long search_probe_peak_memory(void) {
  struct rusage usage;
  if (getrusage(RUSAGE_SELF, &usage) != 0) return 0;
  return (unsigned long long)usage.ru_maxrss * 1024ull; /* Linux reports KiB */
}
#endif
