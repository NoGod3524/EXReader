# SPDX-License-Identifier: MIT
"""Offline checks for keyboard transport; these do not claim a product UI pass."""
import ctypes as C
import unittest
from unittest.mock import patch

import native_ui as ui


class KeyboardTransport(unittest.TestCase):
    def test_chord_releases_modifiers_and_uses_native_input_size(self):
        captured = []

        def send(count, inputs, size):
            self.assertEqual(size, 40 if C.sizeof(C.c_void_p) == 8 else 28)
            captured.extend((item.type, item.payload.keyboard.vk,
                             item.payload.keyboard.flags) for item in inputs)
            return count

        with patch.object(ui.U, 'SendInput', send), patch.object(ui.time, 'sleep'):
            ui.tap(ord('I'), (0x11, 0x10))
        self.assertEqual(captured, [(1, 0x11, 0), (1, 0x10, 0),
                                    (1, ord('I'), 0), (1, ord('I'), 2),
                                    (1, 0x10, 2), (1, 0x11, 2)])

    def test_partial_send_cannot_pass(self):
        with patch.object(ui.U, 'SendInput', return_value=1):
            with self.assertRaises(AssertionError):
                ui.tap(ord('I'), (0x11,))

    def test_filename_locator_excludes_the_search_edit(self):
        for modern in (True, False):
            classes = {1: '#32770', 2: 'FloatNotifySink' if modern else 'ComboBoxEx32',
                       3: 'ComboBox', 4: 'Edit', 5: 'Edit'}
            ids = {1: 0, 2: 0 if modern else 1148, 3: 1001, 4: 1001, 5: 1001}
            parents = {2: 1, 3: 2, 4: 3, 5: 1}

            def enumerate_children(dialog, callback, unused):
                for child in parents:
                    callback(child, 0)

            def class_name(window, buffer, size):
                buffer.value = classes.get(window, '')
                return len(buffer.value)

            with patch.multiple(ui.U, EnumChildWindows=enumerate_children,
                                GetClassNameW=class_name, GetParent=lambda w: parents.get(w, 0),
                                GetDlgCtrlID=lambda w: ids.get(w, 0),
                                IsWindowVisible=lambda w: True, IsWindowEnabled=lambda w: True):
                self.assertEqual(ui.filename_edit(1), 4)


if __name__ == '__main__':
    unittest.main()
