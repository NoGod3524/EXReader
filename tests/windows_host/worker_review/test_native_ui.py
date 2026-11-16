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


if __name__ == '__main__':
    unittest.main()
