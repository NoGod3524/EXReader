# SPDX-License-Identifier: MIT
"""Mapping of the existing GTK and Windows check ids onto the six final surfaces.

kind says what a check can prove:
  name     accessible name / role exposed in the accessibility tree
  state    accessible state or exposed value
  order    focus order / reachability
  operate  a keyboard action that was performed and whose effect was observed

A control that merely exists (name/state/order) never makes a surface operable;
only a passing ``operate`` check does.
"""

SURFACES = ['bookshelf', 'import', 'reading', 'annotation', 'settings', 'exit']

GTK = {
    'shelf_toolbar_names_and_actions': ('bookshelf', 'name'),
    'shelf_list_named': ('bookshelf', 'name'),
    'shelf_action_row_names': ('bookshelf', 'name'),
    'shelf_search_entry': ('bookshelf', 'name'),
    'shelf_tab_order_reaches_controls': ('bookshelf', 'order'),
    'shelf_tab_order_follows_visual_order': ('bookshelf', 'order'),
    'tab_cycle_elements_named': ('bookshelf', 'name'),
    'shelf_tab_order_cycles_without_trap': ('bookshelf', 'operate'),
    'more_menu_items_named': ('bookshelf', 'name'),
    'more_menu_keyboard_activation': ('bookshelf', 'operate'),
    'shelf_row_names': ('bookshelf', 'name'),
    'shelf_rows_focusable': ('bookshelf', 'order'),
    'import_dialog_identity_and_focus': ('import', 'name'),
    'import_dialog_escape_restores_focus': ('import', 'operate'),
    'import_books_visible_on_shelf': ('import', 'operate'),
    'reader_panel_names': ('reading', 'name'),
    'reader_tab_order_reaches_panels': ('reading', 'order'),
    'annotation_note_rows_named': ('annotation', 'name'),
    'status_message_exposed_as_name_change': ('annotation', 'state'),
    'collections_dialog_identity': ('settings', 'name'),
    'collections_dialog_controls_named': ('settings', 'name'),
    'collections_type_selector_reachable': ('settings', 'operate'),
    'collections_dialog_escape_restores_focus': ('settings', 'operate'),
    'metadata_dialog_identity_and_focus': ('settings', 'name'),
    'metadata_dialog_controls_named': ('settings', 'name'),
    'metadata_dialog_escape_restores_focus': ('settings', 'operate'),
    'account_dialog_identity_and_focus': ('settings', 'name'),
    'account_dialog_declares_modality': ('settings', 'state'),
    'account_entries_and_buttons_named': ('settings', 'name'),
    'account_password_secret_not_reachable_through_atspi': ('settings', 'state'),
    'account_dialog_escape_restores_focus': ('settings', 'operate'),
    'atspi_bridge_exposes_main_window': ('bookshelf', 'name'),
    'exit_alt_f4_window_closed': ('exit', 'operate'),
    'exit_process_ended_without_kill': ('exit', 'operate'),
    'exit_window_named_and_focused_before_close': ('exit', 'name'),
}

WINDOWS = {
    'SH-01': ('bookshelf', 'name'), 'SH-02': ('bookshelf', 'name'),
    'SH-03': ('bookshelf', 'name'), 'SH-04': ('bookshelf', 'name'),
    'SH-05': ('bookshelf', 'operate'), 'SH-06': ('bookshelf', 'state'),
    'SH-07': ('bookshelf', 'state'),
    'OR-01': ('bookshelf', 'operate'), 'OR-02': ('bookshelf', 'name'),
    'OR-03': ('bookshelf', 'name'), 'OR-04': ('bookshelf', 'name'),
    'OR-05': ('bookshelf', 'state'), 'OR-06': ('bookshelf', 'name'),
    'OR-07': ('bookshelf', 'order'), 'OR-08': ('bookshelf', 'operate'),
    'OR-09': ('bookshelf', 'operate'), 'OR-10': ('bookshelf', 'state'),
    'OR-11': ('bookshelf', 'operate'),
    'KB-01': ('bookshelf', 'order'), 'KB-02': ('bookshelf', 'order'),
    'KB-03': ('bookshelf', 'order'), 'KB-04': ('bookshelf', 'state'),
    'KB-06': ('bookshelf', 'operate'), 'KB-07': ('bookshelf', 'operate'),
    'IM-01': ('import', 'name'), 'IM-02': ('import', 'name'),
    'IM-03': ('import', 'operate'), 'IM-04': ('import', 'state'),
    'IM-06': ('import', 'order'),
    'RD-01': ('reading', 'name'), 'RD-02': ('reading', 'name'),
    'RD-03': ('reading', 'order'), 'RD-04': ('reading', 'state'),
    'RD-05': ('reading', 'operate'), 'RD-06': ('reading', 'state'),
    'RD-07': ('reading', 'operate'),
    'AN-01': ('annotation', 'name'), 'AN-02': ('annotation', 'name'),
    'AN-03': ('annotation', 'operate'), 'AN-04': ('annotation', 'name'),
    'AN-05': ('annotation', 'operate'), 'AN-06': ('annotation', 'operate'),
    'ST-01': ('settings', 'name'), 'ST-02': ('settings', 'operate'),
    'ST-03': ('settings', 'state'), 'ST-04': ('settings', 'name'),
    'ST-05': ('settings', 'operate'),
    'EXIT-01': ('exit', 'name'), 'EXIT-02': ('exit', 'operate'),
    'EXIT-03': ('exit', 'operate'),
}

# Native check names of the exit probe, per platform.
EXIT_CHECKS = {
    'gtk': ['exit_window_named_and_focused_before_close', 'exit_alt_f4_window_closed',
            'exit_process_ended_without_kill'],
    'windows': ['EXIT-01', 'EXIT-02', 'EXIT-03'],
}
