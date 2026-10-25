# SPDX-License-Identifier: MIT
CASES = [
    'normal_numeric_switch', 'follows_system_exact', 'rejects_nonfinite_atomic',
    'rejects_out_of_range_atomic', 'wrong_thread_no_effect', 'reentrant_no_effect',
    'duplicate_attach_no_effect', 'null_window_rejected', 'preexisting_keep_preserved',
    'external_brightness_preserved', 'external_keep_preserved', 'unrelated_flags_preserved',
    'cancel_restore_retry', 'close_and_after_close', 'exclusive_same_window',
    'independent_windows', 'focus_loss_restore_no_autoactivate', 'pause_background_restore',
    'rotation_old_token_rejected', 'window_recreation_releases_old', 'destroyed_window_rejected',
    'hidden_window_activate_rejected', 'detach_old_callbacks_rejected',
]
PROCESS_CASES = ['actual_process_terminated', 'fresh_process_new_pid', 'reopen_default_window',
                 'no_permissions_or_services', 'global_brightness_unchanged']
UNAVAILABLE = ['physical_backlight', 'battery_or_power_policy', 'OEM_device_behavior', 'accessibility', 'formal_host_integration']
