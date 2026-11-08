/* SPDX-License-Identifier: MIT
 * Frozen workload v1: 120,000,000 dependent unsigned FNV-style mixing steps.
 * No SDK calls, input files, allocation, ISA dispatch, or runtime calibration.
 * Unsigned wraparound is defined; publishing the result prevents elimination.
 */
#include <stdint.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <time.h>
#endif
static volatile uint64_t reference_sink;
static double reference_now(void) {
#ifdef _WIN32
  LARGE_INTEGER counter, frequency;
  QueryPerformanceFrequency(&frequency);
  QueryPerformanceCounter(&counter);
  return (double)counter.QuadPart * 1000.0 / (double)frequency.QuadPart;
#else
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec * 1000.0 + t.tv_nsec / 1000000.0;
#endif
}
double perf_reference_ms(void) {
  uint64_t hash = UINT64_C(14695981039346656037);
  double start = reference_now();
  for (uint64_t i = 0; i < UINT64_C(120000000); ++i) {
    hash ^= i & 255;
    hash *= UINT64_C(1099511628211);
  }
  reference_sink = hash;
  return reference_now() - start;
}
