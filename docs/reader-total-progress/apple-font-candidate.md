# Apple local font candidate

The starting source is `f34a4f27`; candidate source is
`22ebe335a58c86498f70012937b6ef9b13513da1`. The candidate defers acquiring a
saved imported font until opening a book, and replaces the reader session with
one using the bundled font when returning to the shelf. An accepted open keeps
the selected font; a rejected open leaves the shelf session intact. The
existing combined native test also checks page and location after an invalid
font import from a noninitial page. Existing assertions and shared library
limits remain in place.

Push-triggered [run 40627106478](https://github.com/NoGod3524/EXReader/actions/runs/40627106478)
was queued at the time of this record, with both SDK jobs waiting for macOS
runners. It has not established that this candidate builds or passes. The
previous [run 40350153254](https://github.com/NoGod3524/EXReader/actions/runs/40350153254)
failed the combined font/export/sync case on macOS, iPhone Simulator and iPad
Simulator; that failure is retained and is not superseded by a queued run.

Acceptance remains open. The combined case uses the bundled `Reader.otf` as
its imported font, so it cannot demonstrate changed pixels. It does not measure
the actual lease on selection, default, shelf exit or reopen. A distinct valid
font, logical anchor checks across reflow, direct lease lifecycle evidence and
restoration after reopening are still required on all three targets. Simulator
results would not establish physical-device behavior. Do not mark the catalog
items accepted on the strength of this candidate or the existing test alone.

## Retained failure inspection

[Actions run 40627448108](https://github.com/NoGod3524/EXReader/actions/runs/40627448108)
authenticated the three original ZIPs from run 40350153254 and inspected the
combined case logs. On macOS the first font import timed out. The retained
accessibility tree showed the fixture button outside the visible scroll
viewport, with the status still at “详情已刷新” and no imported row; an
offscreen tap or owner-busy timing are plausible but not proven causes. On
iPhone and iPad the existing case proceeded through its font steps and failed
later at the share control. These findings preserve the original failures and
do not establish the missing font acceptance outcomes.
