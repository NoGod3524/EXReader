# Windows font lifecycle: remaining acceptance blocker

The common candidate already contains the Windows font library UI and the
large-TXT candidate. The earlier native UI evidence is recorded in
`reader-wave3-c09/root-validation.json`; it does not measure the host lease
counter. `H.windows.font_library` therefore remains partial.

Source review found that a non-TXT font switch uses `JOB_OPEN`, which restores
from durable progress. When a save has failed or bounded EPUB recovery has held
the progress record, that record can be older than the displayed frame. The
candidate now refuses the switch in those states (and while a bounded frame has
not been saved), retaining the current font and frame. This is a conservative
mitigation, not proof that every successful reopen preserves the live position.

Independent Windows acceptance still needs to observe successful and failed
lease opens/releases and library close on the actual host, including replacement,
rollback, same-font selection and shutdown. It must exercise a noninitial EPUB
position and establish that the old logical point lies in the accepted new page,
and that bad-font failure retains the exact frame and selected font. It must
also cover failed and held progress saves. The existing UI suite checks import,
switch, restoration and restart but does not establish these requirements.
The 32-lease and 128 MiB budgets and existing assertions are unchanged. No
acceptance is granted by the mitigation or by the retained suite alone.
