# GTK keyboard and accessibility audit (G13)

Audit-only package. It adds no product code: the GTK receiver keeps ownership of
`examples/linux/**` and `apps/reader/**`. This document describes the audit that
`tests/reader_a11y_gtk/**` performs on the fixed source, how to replay it, what it
can and cannot decide, and how its result must be read.

- Fixed implementation start: `f43baf9182d75907c0cb5d6f77048f27bca8c950`
- Frozen SDK contract: `9854061be331fe603a1822d9b2b36ee357154927` (3.40.0, ABI 1)
- Branch: `codex/reader-a11y-gtk`
- Workflow: `.github/workflows/reader-a11y-gtk.yml`
- Recorded result: `docs/validation/reader-a11y-gtk.json`

## 1. What is audited

The real GTK product host `bin/exreader-linux` built from `apps/reader/desktop`
with `-DEXR_READER_BUILD_GTK=ON -DEXR_READER_GTK_ACCOUNT=ON`, over the installed
public SDK and the installed product modules. The host is the same binary the
account, shelf, collection and metadata owners exercise; nothing is stubbed and no
test-only build flag changes the audited widgets.

Surfaces, in the order the audit walks them:

| Surface | Keyboard path | Elements observed |
| --- | --- | --- |
| Bookshelf | `F2` | toolbar buttons, search entry, details button, more menu button, list box and its rows |
| Import | `F1` | file chooser dialog, its focus, Escape restore |
| Organize | more menu → `Collections…`, `Ctrl+E` | organizer dialog, type combo, removed checkbox, group/member lists, buttons; book-details dialog entries and favourite check box |
| Reading | `F2` then `Return` | rendered page image, selectable text view, comment entry, saved-note list |
| Annotation | `F7`, `Ctrl+A`, `F11`, `F8` | note rows and their names |
| Account | `Ctrl+Shift+A` | WebDAV root, username and password entries, storage radio buttons, seven buttons, Escape restore |
| Status messages | refused import | status label identity, name change, delivered accessibility events |

## 2. How it is observed

Two independent observation channels, both required:

1. **AT-SPI over the real accessibility D-Bus.** `tests/reader_a11y_gtk/atspi_client.py`
   talks to `at-spi2-registryd` through the platform `Atspi` GObject API and reads
   only what any assistive technology can read: `Name`, `Role`, the state set
   (`FOCUSED`, `FOCUSABLE`, `EDITABLE`, `MODAL`, `ENABLED`, ...), actions and their
   key bindings, relations, attributes, `AtkText`, screen extents, and the events the
   registry delivers (`object:property-change`, `object:state-changed`,
   `object:text-changed`, `object:announcement`, `focus:`, `window:`).
2. **Real X11 keystrokes.** `tests/reader_a11y_gtk/driver.py` launches the host and
   sends keys with `xdotool` to the mapped window under Xvfb plus openbox, so focus
   order, dialog restore and menu traversal are produced by the same input path a
   keyboard user produces. Every key is timestamped with the currently focused
   accessible name in `keys.log`.

Session bus, accessibility bus, registry, window manager, screen and app run inside
one `xvfb-run … dbus-run-session` block on the Actions runner. The audit reads
nothing from SDK private storage, no product SQLite table and no process memory; it
never patches the host.

The dependency on the bridge is deliberate and asserted: the credential checks in
`tests/linux_host/check_account_ui.py` set `NO_AT_BRIDGE=1`; this audit removes it,
and its first check fails loudly if the application never registers, instead of
degrading into a silent pass.

## 3. Named checks

`tests/reader_a11y_gtk/expectations.py` is the contract: every asserted name is
transcribed from an `atk_object_set_name()` call or a widget label in the audited
source, so the audit tests the baseline's own claims plus the platform guarantees
GTK provides (focusable rows, modal dialogs, focus restoration, event delivery).

| Check | Observes | Severity |
| --- | --- | --- |
| `atspi_bridge_exposes_main_window` | application present on the bus with frame `EXReader Linux` | blocking |
| `shelf_list_named` | list role plus name `Bookshelf` | blocking |
| `shelf_toolbar_names_and_actions` | ten buttons named exactly as their labels, each with a `click` action | blocking |
| `shelf_action_row_names` | `Edit book details` and `More library actions` | blocking |
| `shelf_search_entry` | entry named `Search bookshelf` with `EDITABLE` | blocking |
| `shelf_tab_order_reaches_controls` | 26 real `Tab` presses reach all 13 shelf controls | blocking |
| `shelf_tab_order_follows_visual_order` | focus order equals the extents-derived visual order | blocking |
| `tab_cycle_elements_named` | every element that takes keyboard focus has a non-empty name | blocking |
| `shelf_tab_order_cycles_without_trap` | focus returns to an already focused element | advisory |
| `more_menu_items_named` | menu items `Collections…` and `Account / Sync…` | advisory |
| `more_menu_keyboard_activation` | arrow keys plus `Return` open the organizer | blocking |
| `collections_dialog_identity` | modal dialog named `Library collections`, focus inside | blocking |
| `collections_dialog_controls_named` | type combo, removed check box, both lists, 14 buttons | blocking |
| `collections_type_selector_reachable` | the type selector is in the Tab cycle or reachable by its mnemonic | advisory |
| `collections_dialog_escape_restores_focus` | `Escape` closes and focus returns to the main window | blocking |
| `import_dialog_identity_and_focus` | dialog named `Import book` with keyboard focus | blocking |
| `import_dialog_escape_restores_focus` | `Escape` closes and focus returns | blocking |
| `import_books_visible_on_shelf` | three imported originals become shelf rows | blocking |
| `shelf_row_names` | every row exposes a non-empty `Name` | blocking |
| `shelf_rows_focusable` | every row reports `FOCUSABLE` | blocking |
| `reader_panel_names` | page image, selectable text, comment entry, notes list | blocking |
| `reader_tab_order_reaches_panels` | `Tab` reaches the text view and comment entry | advisory |
| `annotation_note_rows_named` | saved-note rows expose a non-empty `Name` | blocking |
| `status_message_exposed_as_name_change` | the status element keeps identity and emits `accessible-name` property change | blocking |
| `metadata_dialog_identity_and_focus` | modal `Book details`, focus on `Book title` | blocking |
| `metadata_dialog_controls_named` | `Book title`, `Book author`, `Favorite book` | blocking |
| `metadata_dialog_escape_restores_focus` | `Escape` closes and focus returns to the shelf | blocking |
| `account_dialog_identity_and_focus` | dialog `Account and Sync`, focus on `HTTPS WebDAV root` | blocking |
| `account_dialog_declares_modality` | the dialog exposes the MODAL state like the other two dialogs | advisory |
| `account_entries_and_buttons_named` | three entries, two storage radios, seven buttons | blocking |
| `account_password_secret_not_reachable_through_atspi` | the typed secret is not readable through `AtkText`; the secret marker is recorded separately as a gap | blocking |
| `account_dialog_escape_restores_focus` | `Escape` closes and focus returns | blocking |

Severity policy, fixed before the run:

- **blocking** — the element cannot be identified by an assistive client (WCAG 4.1.2),
  cannot be reached or activated from the keyboard (2.1.1), focus order contradicts
  the visual order (2.4.3), focus is lost when a dialog closes, a status change is
  not exposed as an event, or a secret is readable by an assistive client.
- **advisory** — role and menu-shape best practice where GTK's own role is a
  platform choice, and traversal properties that are informative but not a failure.

A check that a phase never reached is recorded as an unevaluated **failure**, never
as a pass or a skip, and it makes `audit_completed` false.

## 4. Acceptance, and what is not accepted

The report and `docs/validation/reader-a11y-gtk.json` keep three separate claims:

| Field | Meaning |
| --- | --- |
| `audit_completed` | every declared phase ran and every declared check was evaluated |
| `accessibility_accepted` | `audit_completed` **and** no blocking check failed |
| `orca_screen_reader_accepted`, `human_reader_review_accepted`, `complete_product` | always `false` here |

An AT-SPI audit **does not** grant Orca or any real screen-reader pass, human review,
braille output or visible-focus acceptance. `check_a11y_report.py` rejects any report
that claims those, and `--require-accepted` makes the workflow refuse (red) while a
blocking finding stands.

Recorded as explicit gaps, never as passes:

- Orca or any real screen-reader speech output (no speech capture, no reader build).
- AT-SPI live-region / announcement semantics: the GTK3 host sets no live region and
  the runner's at-spi2-core predates `object:announcement`, so automatic
  announcement of the status text is not established either way.
- Braille output and BRLTTY integration.
- Visible focus ring, contrast and theme rendering (WCAG 1.4.3, 1.4.11, 2.4.7).
- Password-field semantics at the AT-SPI layer: the entry exports no attribute that
  marks it as secret, so a client cannot know the field is masked before reading it.
- IME composition, caret browsing and selection announcement for the rendered page.
- Network-backed account scan states (preparing, scanning, cancel, retry): the audit
  runs offline against a local library, so only the pre-session account surface is
  observed.
- Non-GTK hosts (Windows, Apple, Android) — outside this package.
- Event coalescing and AT-SPI cache latency under a large library.

## 5. Replaying from the fixed source

```sh
gh workflow run reader-a11y-gtk.yml --ref codex/reader-a11y-gtk
```

The workflow first proves `HEAD == GITHUB_SHA`, that the fixed start is an ancestor,
that the SDK protected tree equals `9854061…`, and that `git diff --name-only
start..HEAD` stays inside this package's four paths. It then builds the host exactly
as the other owners do, runs the audit, validates the report and its digests, runs
the gate's own six-mutation self test, and refuses when the audit is incomplete or a
blocking finding stands. Evidence is uploaded even on refusal:

- `build/a11y-evidence/result.json` — machine-readable report with per-check
  element path, expected, actual, reproduction and minimal fix
- `build/a11y-evidence/tree/*.json`, `tree/*.txt` — AT-SPI tree per phase
- `build/a11y-evidence/shots/*.png` — screenshots per phase
- `build/a11y-evidence/keys.log` — every keystroke with the focused accessible name
- `build/a11y-evidence/logs/application.log`, `logs/window-tree.txt`
- `build/a11y-logs/*.log` — configure, build, audit and gate logs
- `source-binding.txt`, `build/a11y-package/build.json` — source and binary identity

## 6. Recorded result

Filled from the run recorded in `docs/validation/reader-a11y-gtk.json`; the validation
file is the authority for the exact source, run, attempt, artifact identity and
per-check outcome of a given run.

## 7. Limit of this package

This audit cannot repair what it finds. The GTK receiver owns
`examples/linux/reader.c`, `accounts_ui.inc`, `collections_ui.inc` and
`metadata_ui.inc`, and any minimal fix listed in a finding is a suggestion for that
owner with the exact call site, not a change made here. Shared build files, existing
workflows, the frozen SDK tree and the handoff directory stay untouched.
