# D20 — Windows actual-display capability and regressions

## Scope and execution

Fixed seed `d263ce5228838ac90c0a0dc13a5193d4a7739681`; frozen SDK
`edddc463c06ed5731195cdb8f06b2df6dff7699e`. These are development identities,
not a production-acceptance grant. Only D20 tests/workflow/docs are changed.
No product owner, SDK, shared build, old test, assertion or budget changes.

All executable work, syntax, fixtures, builds, UI automation, screenshots,
artifact downloads/extraction/hashing and verification run only in GitHub
Actions. Only GitHub-hosted ephemeral Windows runners may change display or
high-contrast state. No user computer, registry DPI edit, undocumented setter,
reboot, logoff, simulated DPI message or target-process awareness injection.
The scale and contrast state are read back again and restored in `finally`.

The fresh legacy-selector compact host uses the complete original D08 installed
SDK/module build recipe, on **the same current source as the harness**. Search,
navigation, records, import/organize and preferences are ON; raw3 and review
macros are OFF. No prior executable or prior passing result is combined.

## Reuse, not a replacement for the old judge

Exact D08 source `30158c44dcd9ebf27e028b85f60c4fe374b9c90b` is read through Git
inside Actions. `reuse.py` projects only repository/build/evidence paths and
records original/adapted hashes with exact reverse projection. The old build,
modal native-descendant focus checks, keyboard import/open, geometry, screenshots,
UIA, loaded-module inventory and painted-color sampling are reused unchanged.
The obsolete old `run_all` and its DPI setter are **not invoked**.
All four original D08 negative controls are re-run with their unchanged old
contract; eight additional D20 controls reject false coverage and missing scopes.

## Actual scale and contrast

1. Before requests, enumerate actual native monitor/work/virtual-screen pixels,
   every supported display mode, actual runner session and graphics adapters.
2. Open the documented `ms-settings:display` URI. Select an exact offered scale
   only in the uniquely identified native Settings scale ComboBox. Missing,
   disabled or ambiguous capability stays pending, with raw UIA/capture evidence.
3. Never infer scale from the requested label. Require both native monitor scale
   and a newly-created **independent PMv2 probe window** to read 100/96, 150/144
   or 200/192. The probe is not the target program.
4. Separately preserve the target's `GetDpiForWindow`, awareness and monitor scale.
   An unaware target returning 96 at an actually higher monitor scale is a target
   DPI finding, not evidence that the monitor failed to change.
5. Set high contrast only with documented `SPI_SETHIGHCONTRAST`, without profile
   persistence, and require the actual `SPI_GETHIGHCONTRAST` flag before testing.

Unavailable configurations have no product pass, fake screenshot or repeated
100% result. The actual 100% normal/high/default/small baseline is mandatory.
A newly achieved scale runs the full same-source native regression: shelf,
reading, forward/reverse keyboard traversal, page turns, four modal entries,
More expand/collapse and note-editor reachability, status native/UIA text and
pixel/bounds evidence, return-to-shelf and separate shelf-search focus.

The original D08 painted-color judgment remains pending unless an enabled
sampled pair actually fails its unchanged threshold. Palette or nonuniform
pixels do not certify text semantics, all glyph contrast, focus-ring contrast,
ICC conversion, screen readers, or every glyph's clipping. Those grants remain
explicitly out of scope/pending. Product failures are retained for C09.

## Evidence and limits

The strict job downloads the **original ZIP in Actions**, verifies its metadata,
bytes, SHA256, expiry, source/run/attempt and actual native job, every indexed
file, program/hash/link/compile identities, old/new negative controls, and a
credential-pattern/token scan. Its output separates evidence validity from
product acceptance. A green evidence job never means full accessibility passed.

At most three complete CI rounds including reruns; docs seals use `[skip ci]`.
No PR, default branch, tag or Release operation.

## Preserved history

D08 run `40226179285` attempt 1, tested harness
`d885475a6eb93677055b27d168a7f50e601bf6b4`, separately built product target
`9321de84eb9c8d3d57cafbeaa8b0a28fe2a26a08`: all 12 requested configurations
were actual 100%. Eight 150/200 requests failed coverage; contrast was pending;
all shelf-search focus cases failed, six default-window bounds cases failed.
D08 CI1 `40225000270/1` and earlier D02 failures remain historical facts. New
seed observations are not retroactive passes for those runs.

## Primary API references (checked 2026-10-26)

- [SystemParametersInfo](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-systemparametersinfoa): old logical-DPI setter is documented “Do not use”; high-contrast and physical work-area contracts.
- [GetDpiForWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getdpiforwindow): return depends on target awareness; unaware windows report 96.
- [Launch Settings](https://learn.microsoft.com/en-us/windows/apps/develop/launch/launch-settings): documented display URI; availability varies by SKU/version.

## CI1 后的能力驱动补全

CI1 证明 Settings 缩放 ComboBox 存在且 enabled，但主窗子树中未找到150/200。
CI2 将按真实 Settings provider PID 枚举可能位于 desktop sibling 的 XAML popup，
记录全部实际提供的 percent 选择项。原1024×768的100%完整回归先执行；之后仅为
高缩放探测选择已真实枚举的1600×1200模式（如存在），使用原生模式test/apply并
回读，finally恢复原模式。此物理模式变化与缩放分别记录；不计成新的DPI能力，
也不让较宽工作区覆盖原100% More失败。历史CI1见 ITERATION-1.md。
