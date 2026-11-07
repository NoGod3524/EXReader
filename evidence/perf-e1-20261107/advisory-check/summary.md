# Existing R3 numeric reachability

Numeric diagnostic only: exact frozen eight inputs/font, R3 timed 32 sequential/16 random at 800x1000 margin32. Five fresh pinned Windows processes. Final reference PPM phase omitted; RSS is for timed plan plus hashes. No Poppler/review/signature baseline enforcement. Linux budgets are ineligible on this Windows CPU/compiler.

advisory: true; accepted: false.

| Input | First visible p95 ms | Sequential p95 ms | Random p95 ms | Peak bytes p95 |
|---|---:|---:|---:|---:|
| pg11-alice | 36.622 | 8.368 | 28.543 | 38662144 |
| pg84-frankenstein | 55.542 | 8.679 | 56.361 | 65589248 |
| pg1342-pride | 54.253 | 25.753 | 82.714 | 50761728 |
| pg2701-moby | 53.466 | 13.069 | 65.453 | 38662144 |
| irs-w9 | 64.962 | 64.946 | 69.027 | 38653952 |
| nist-ai-rmf | 112.799 | 527.058 | 557.932 | 132333568 |
| nist-csf2 | 180.055 | 84.794 | 82.618 | 53821440 |
| nasa-solar-system | 1444.681 | 1173.297 | 1163.975 | 79265792 |

| Budget environment | Above numeric limits (metric/case) |
|---|---|
| amd-epyc-7763 | pg11-alice/open_ms, pg84-frankenstein/open_ms, pg1342-pride/open_ms, pg2701-moby/open_ms, nist-ai-rmf/open_ms, nist-csf2/open_ms |
| amd-epyc-9v45 | pg11-alice/open_ms, pg84-frankenstein/font_open_ms, pg84-frankenstein/open_ms, pg1342-pride/font_open_ms, pg1342-pride/open_ms, pg2701-moby/font_open_ms, pg2701-moby/open_ms, pg2701-moby/first_visible_ms, pg2701-moby/sequential_render_ms, irs-w9/open_ms, nist-ai-rmf/open_ms, nist-csf2/open_ms, nasa-solar-system/font_open_ms, nasa-solar-system/open_ms, nasa-solar-system/first_visible_ms, nasa-solar-system/sequential_render_ms, nasa-solar-system/sequential_total_ms, nasa-solar-system/random_render_ms, nasa-solar-system/random_total_ms |
| intel-xeon-8573c | pg11-alice/open_ms, pg84-frankenstein/open_ms, pg1342-pride/open_ms, pg2701-moby/open_ms, irs-w9/open_ms, nist-ai-rmf/open_ms, nist-csf2/open_ms |
