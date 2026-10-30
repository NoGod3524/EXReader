# Restart acquired-window failure candidate

Base: 638976413692412fd7cc15d7e508d0382d1faffd (documentation child of tested
6db7c3dc1005c7fd22f91b02a150bfdd671f723c).
Branch: codex/p0-win-restart-window-lock-20261030.

The only production control-flow change routes a failed first lease_window to
done rather than fail after lm_wl_acquire has succeeded. It returns a retained
REFUSED object, preserving EXCLUSIVE until explicit lm_rr_close. No admission,
COMMIT, pending clear, automatic retry, or permanent lock is introduced.
Before-acquire failures still return zero and NULL and release their pins.
The result generation/pending fields have not been populated at this point;
their zero values do not describe the disk. Evidence snapshots the open-time
reason/native code before lm_rr_check can report restart-not-qualified.

The public header, production CMake, original workflow, original probe and
original 26-case runner are unchanged. The new after-acquire hook is compiled
only under LM_RR_TEST_AFTER_ACQUIRE, a PRIVATE definition of the independent
window_lock executable. That target directly compiles the same restart source,
does not link the installed restart archive, and is not installed. The normal
installed production library contains no new hook reference or definition.
The existing public pre-acquire lm_rr_set_window_probe API is not changed.

The new workflow retains the original installed 26 cases and older regressions,
then runs two independent real Windows range-lock cases:
- clean PENDING=1: after successful EXCLUSIVE acquisition a helper locks [0,80);
  the reader refuses with restart-lease-window and retains its object. After the
  helper unlocks, shared is still BUSY due to EXCLUSIVE. Explicit close leaves
  shared STALE, and a fresh reader succeeds, proving no permanent handle leak.
- drift: the helper writes generation=5/PENDING=0 after acquisition, then locks
  [0,80). Refusal retains EXCLUSIVE while alive without restoring bytes. After
  reader death the shared result is measured and a new reader refuses generation.
  No durable crash isolation is claimed; the missing persistent marker remains.

The fixture uses bounded pipe handshakes, not sleeps, to establish ordering.
Receipt separates unconfirmed result fields from actual lease-byte measurements.
Compile definitions, object/archive symbols and both link maps establish which
source variant ran. The two-case receipt remains separate from the unchanged
26-case receipt.

Status: pending the single authorized Actions run. Candidate only; 95/108 unchanged.
