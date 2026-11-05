# Android account and sync status

The host owns its sync session and displays a read-only status snapshot. This
candidate prevents a new start while a prior session is closing and checks
cancellation again at the handoff from original preparation to native sync.

The dedicated API 34 x86_64 host scenario uses a TLS WebDAV fixture. It checks
no-session status, a real 401 and the failed/needs-credentials view, reopening
and refreshing that view, saving corrected credentials in Android Keystore,
cancelling a blocked native upload, retrying to a completed sweep, and removing
credentials while retaining the library binding. The existing C11 suite
separately checks that reading and refreshing a failed status does not mutate
revisions, outbox or sync rows. Existing account restart and session-only
checks are retained in the host sync suite. These are emulator and fixture
results, not evidence for a physical device or a particular cloud provider.

Run 40627098367 on 01d09928d9229a71399db8a4b2ad67550b9f689b passed the
dedicated scenario, organization suite and C11/navigation/reading step. Both
retained sync runners failed at `explicit_receive_preserves_sdk_and_product`:
the copied workflow defaulted to an SDK 3.40 expectation while building 3.41.
That failure remains recorded. Commit c33455a957b02c4e64bf1d5a466b633f51b71ba7
passes the built version explicitly to both unchanged runners. The corrected push run [40630302205/1](https://github.com/NoGod3524/EXReader/actions/runs/40630302205)
on that source passed the dedicated scenario, organization sync, C11/navigation/
reading, original versioned sync regression, and strict 3.41 adapter. It
preserved artifact 12792577560 (expires 2027-01-26). The focused runner in
that run inherited two unrelated provider-identity booleans from the receive
fixture; those fields are not evidence from the focused scenario. The retained
sync suites independently assert provider identity. The follow-up reporting
change sets those two focused-runner fields to false; it does not change the
scenario or product code. The repository-wide catalog is not updated here:
its progress audit and integration onto shared source remain separate work.
