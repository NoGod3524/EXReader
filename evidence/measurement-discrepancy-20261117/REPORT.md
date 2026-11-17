# PDF render measurement discrepancy

## Result

The initial 15-minute CPU gate and subsequent retries expired before the first capture. The alternating reproduction and isolation runs have zero qualifying timing samples. The reported 3.283 ms versus 6.755 ms (2.06×) gap remains unresolved.

| Measurement | Samples | Minimum | Median | Maximum | Spread |
| --- | ---: | ---: | ---: | ---: | ---: |
| Host CPU, one-second windows during the first wait | 120 | 88.48% | 99.81% | 100.00% | 11.52 percentage points |
| Host CPU, one-second windows in the final retry | 74 | 46.18% | 75.93% | 98.77% | 52.59 percentage points |
| Wrapper, 1200 px render p50/p95 | 0 of 3 invocations | — | — | — | — |
| Bare capture, 1200 px render p50/p95 | 0 of 3 invocations | — | — | — | — |

CPU is the system-wide busy fraction from Windows GetSystemTimes. All 194 retained windows exceeded the 15% launch limit. Other processes were compiling and running tests during the first wait. [Initial CPU samples](preflight-cpu.json) · [Final retry CPU samples](retry-gate.json)

The queued sequence alternated wrapper then bare capture three times. Each wrapper invocation requested 12 measured rounds and two repeats at widths 600, 1200, and 2400. Each bare invocation requested five measured rounds at its default widths of 1200 and 2400. The reproduction targets their shared 1200 px result.

Test host was an Intel Core Ultra 7 256V (8 cores, 8 logical processors), Windows 11 build 26200, Python 3.14.7, with the Balanced power plan. The staged input was the 20-page PPTX PDF (SHA-256 **2bfb94aa6905f27915e309b3c820fef3ba13492dddedfb93d97a10e8d7679729**). The staged Release DLL was the handoff build for main at **04e7a31a1**, SHA-256 **e55e1617577416041b8ce6c35b454ef4bf10e4f5aa08679cddbaa470a5419d54**.

## Verified findings

1. Both entry points use the same render loop and a fresh child process per width. The wrapper invokes the capture parent with one width at a time. A bare capture with multiple widths also spawns a fresh process for each width and passes **--child** to each. Both time the **exr_fixed_render** call, which includes the engine’s bitmap allocation. The timer stops before copying, hashing, PNG/zlib output, and bitmap free. Snapshot writes occur between renders in the first measured round, so their indirect effect on later calls still needs the controlled run. The current entry points set neither affinity nor process priority. [Capture source at the tested commit](https://github.com/NoGod3524/EXReader/blob/04e7a31a151b677153a3fbc5795d6a80f26faa67/tools/benchmark_pdf_rect.py)
2. The original wrapper gated only once for all widths and repeats. On timeout it emitted a warning and then ran the capture. The regression test reproduced the missing second gate, and a two-repeat case showed that a field labeled “median” used the larger repeat value. The wrapper now gates each repeat, exits with an error on timeout, records CPU before and during each capture, and calculates the median for either odd or even counts. The established spread remains **100 × (max − min) / min** over repeat p50s. CPU during capture includes the benchmark workload.
3. The prior 1bfb83ede first-screen report lists 3.388 ms. Its archived capture has **3.3869 ms** as the median of the 20 pages’ first visits and **4.2308 ms** as their maximum. The initial render of page 1 in that capture is **3.9495 ms**. The report describes CPU as 14–23%, while its companion benchmark JSON records 52.78% in the idle CPU field. The reported first-screen values therefore lack a confirmed common definition and load record. [Prior report](../pdf-perf-final/REPORT.md) · [Archived render samples](../pdf-perf-final/first-render-1200.json) · [Archived benchmark JSON](../pdf-perf-final/bench.json)

The code establishes equivalent timer boundaries and equivalent per-width process isolation for the two original entry points. The effects of 5, 12, and 20 rounds, snapshot interleaving, process reuse, affinity, priority, and first-render warm state remain unmeasured on this DLL.

## Recommended project standard

Use **tools/bench_engine.py** with the 15% idle gate, 20 measured rounds after one full warmup, and three fresh-process repeats per width. Keep page order, fixture and DLL hashes, Python version, CPU model, power mode, affinity, and priority fixed and recorded for comparisons. Report each repeat’s p50 and nearest-rank p95, the medians across repeats, the p50 spread, and the CPU percentages before and during each repeat. Keep the per-page timings from capture as raw evidence.

Report first screen as page 1’s first render after a single open in a fresh process, with the open time reported separately. The wrapper now exposes the first page render sample from its warmup round. Its existing repeated-open setup makes that sample a useful diagnostic, while a dedicated single-open run supplies the first-screen measurement. Use bare capture to save pixel snapshots for comparison.

## Verification

- The new regression test fails on the original wrapper and passes after the fix. It checks that the second capture is refused when its gate times out, that per-repeat CPU stays associated with the right timings, and that even repeat counts use a true median.
- The CLI exits with code 1 and writes no report when invoked with a zero-second idle timeout.
- Python compilation and git diff whitespace checks passed. Changes are confined to the Python benchmark wrapper, its regression test, and the evidence.
