# SPDX-License-Identifier: MIT
"""Documented accessibility contract of the frozen GTK host.

Every value below is transcribed from the audited source at the fixed
implementation start (examples/linux/reader.c, accounts_ui.inc,
collections_ui.inc and metadata_ui.inc).  The audit asserts only what the
baseline itself claims: the accessible names it sets through
atk_object_set_name(), the shortcut strings its own button labels advertise,
and the roles the widgets own.  No screen-reader heuristic is modelled here.

Start commit: f43baf9182d75907c0cb5d6f77048f27bca8c950
SDK contract: 9854061be331fe603a1822d9b2b36ee357154927 (3.40.0, ABI 1)
"""

START_SHA = 'f43baf9182d75907c0cb5d6f77048f27bca8c950'
SDK_SHA = '9854061be331fe603a1822d9b2b36ee357154927'
SDK_VERSION = '3.40.0'
SDK_ABI = 1
WINDOW_TITLE = 'EXReader Linux'

# reader.c: titles[] created left to right inside a horizontal GtkBox, so this
# list is also the visual left-to-right order that focus order must follow.
TOOLBAR = [
    'Import F1',
    'Shelf F2',
    'Previous F3',
    'Next F4',
    'A+ F5',
    'A\u2212 F6',
    'Text F7',
    'Add note F8',
    'Notes F9',
    'Delete F10',
]

# reader.c: atk_object_set_name() calls on the shelf, reader and action rows.
NAMES = {
    'shelf_list': 'Bookshelf',
    'search': 'Search bookshelf',
    'details': 'Edit book details',
    'more': 'More library actions',
    'page_image': 'Rendered page; selectable text is in the adjacent panel',
    'page_text': 'Selectable page text',
    'comment': 'Annotation comment',
    'notes_list': 'Saved notes; activate to return to selected text',
}

# accounts_ui.inc: accounts_entry(...,access) and gtk_button_new_with_mnemonic().
ACCOUNT_ENTRIES = {
    'root': 'HTTPS WebDAV root',
    'user': 'WebDAV username',
    'password': 'WebDAV password',
}
ACCOUNT_RADIOS = ['Remember in system secure storage', 'Only for this app session']
ACCOUNT_BUTTONS = ['Load saved', 'Apply credentials', 'Forget credentials',
                   'Scan library', 'Cancel scan', 'Retry scan', 'Disconnect']
ACCOUNT_DIALOG = 'Account and Sync'

# metadata_ui.inc
METADATA_DIALOG = 'Book details'
METADATA_NAMES = {'title': 'Book title', 'author': 'Book author', 'favorite': 'Favorite book'}

# collections_ui.inc: collections_access() and gtk_button_new_with_mnemonic().
COLLECTIONS_DIALOG = 'Library collections'
COLLECTIONS_NAMES = {
    'type': 'Collection type',
    'removed': 'Removed collections',
    'groups': 'Collection groups',
    'members': 'Collection members',
}
COLLECTIONS_BUTTONS = ['New', 'Rename', 'Delete', 'Restore', 'Enter shelf', 'Up', 'Root',
                       'Previous groups', 'Next groups', 'Earlier books', 'Later books',
                       'Add selected book', 'Remove membership', 'Position']

IMPORT_DIALOG = 'Import book'

# reader.c: gtk_menu_item_new_with_label() inside the "More" menu button popup.
MORE_MENU_ITEMS = ['Collections\u2026', 'Account / Sync\u2026']

# Roles the platform assigns; asserted as families so a GTK minor bump that
# renames a role is reported rather than silently failing a product claim.
LIST_ROLES = ('list', 'list box', 'table', 'tree', 'tree table')
DIALOG_ROLES = ('dialog', 'alert', 'frame')
ENTRY_ROLES = ('entry', 'text', 'password text')
BUTTON_ROLES = ('push button', 'toggle button', 'menu button', 'menu item', 'check box',
                'radio button', 'check menu item', 'radio menu item')

# Every phase must execute for audit_completed to be true.
PHASES = [
    'bridge',
    'shelf',
    'shelf-tab-order',
    'menu',
    'collections-dialog',
    'import-dialog',
    'import-books',
    'shelf-rows',
    'reader',
    'annotations',
    'status-messages',
    'metadata-dialog',
    'account-dialog',
]

# The named checks this audit must record.  A check that is never recorded is
# filled in as an unevaluated failure, so a broken phase can never be mistaken
# for a passing or skipped requirement.
CHECKS = [
    ('atspi_bridge_exposes_main_window', 'bridge'),
    ('shelf_toolbar_names_and_actions', 'shelf'),
    ('shelf_list_named', 'shelf'),
    ('shelf_action_row_names', 'shelf'),
    ('shelf_search_entry', 'shelf'),
    ('shelf_tab_order_reaches_controls', 'shelf-tab-order'),
    ('shelf_tab_order_follows_visual_order', 'shelf-tab-order'),
    ('shelf_tab_order_cycles_without_trap', 'shelf-tab-order'),
    ('more_menu_items_named', 'menu'),
    ('more_menu_keyboard_activation', 'menu'),
    ('collections_dialog_identity', 'collections-dialog'),
    ('collections_dialog_controls_named', 'collections-dialog'),
    ('collections_dialog_escape_restores_focus', 'collections-dialog'),
    ('import_dialog_identity_and_focus', 'import-dialog'),
    ('import_dialog_escape_restores_focus', 'import-dialog'),
    ('import_books_visible_on_shelf', 'import-books'),
    ('shelf_row_names', 'shelf-rows'),
    ('shelf_rows_focusable', 'shelf-rows'),
    ('reader_panel_names', 'reader'),
    ('reader_tab_order_reaches_panels', 'reader'),
    ('annotation_note_rows_named', 'annotations'),
    ('status_message_exposed_as_name_change', 'status-messages'),
    ('metadata_dialog_identity_and_focus', 'metadata-dialog'),
    ('metadata_dialog_controls_named', 'metadata-dialog'),
    ('metadata_dialog_escape_restores_focus', 'metadata-dialog'),
    ('account_dialog_identity_and_focus', 'account-dialog'),
    ('account_entries_and_buttons_named', 'account-dialog'),
    ('account_password_secret_not_reachable_through_atspi', 'account-dialog'),
    ('account_dialog_escape_restores_focus', 'account-dialog'),
]

# Capabilities this AT-SPI audit cannot decide.  They are reported as gaps and
# never as passes, which is why ORCA_ACCEPTED stays false in every report.
GAPS = [
    'Orca or any real screen reader speech output (no speech capture, no reader build)',
    'AT-SPI live-region / announcement semantics: the audited GTK3 host sets no live '
    'region attribute and at-spi2-core on the runner predates object:announcement',
    'Braille display output and BRLTTY integration',
    'Visible focus ring, contrast and theme rendering (WCAG 1.4.3/1.4.11/2.4.7)',
    'Password-field semantics at the AT-SPI layer: GTK3 exports no password attribute, '
    'so an assistive client cannot be told that the field is secret before reading it',
    'IME composition, caret browsing and selection announcement for the rendered page image',
    'Network-backed account scan states (preparing, scanning, cancel, retry) because this '
    'audit runs offline against a local library only',
    'Non-GTK hosts: Windows, Apple and Android surfaces are outside this package',
    'Event coalescing and AT-SPI cache latency under a large library',
]
ORCA_ACCEPTED = False
