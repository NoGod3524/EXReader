/* Measurement-only additions to a generated copy of examples/reader.c. */
#include <psapi.h>
static int typography_count(void) {
  PROCESS_MEMORY_COUNTERS_EX memory = {0};
  memory.cb = sizeof(memory);
  if (!GetProcessMemoryInfo(GetCurrentProcess(), (PROCESS_MEMORY_COUNTERS *)&memory, sizeof(memory))) return 0;
  host_probe_log("peak_working_set_bytes", (double)memory.PeakWorkingSetSize);
  host_probe_log("peak_commit_bytes", (double)memory.PeakPagefileUsage);
  size_t total = 0, parts = 0;
  exr_publication_parts(g.session.publication, &parts);
  if (!g.session.active || !g.session.bounded || !parts) return 0;
  double started = host_probe_ms();
  for (size_t part = 0; part < parts; part++) {
    exr_pager *pager = NULL;
    exr_error error = {0};
    exr_status status = bounded_pager(&g.session, part, &pager, &error);
    if (status != EXR_OK) return 0;
    for (size_t index = 0;; index++) {
      const exr_layout *layout = NULL;
      status = exr_pager_get(pager, index, &layout, &error);
      if (pager_eof(status, &error)) break;
      if (status != EXR_OK || !layout) { exr_pager_free(pager); return 0; }
      total++;
    }
    exr_pager_free(pager);
  }
  host_probe_log("total_pages", (double)total);
  host_probe_log("count_ms", host_probe_ms()-started);
  return total > 20;
}
