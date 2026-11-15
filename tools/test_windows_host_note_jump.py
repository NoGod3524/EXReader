#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Regression check for the whole-part annotation created from page 1."""
import unittest

from check_windows_host import check_note_jump


class NoteJumpTest(unittest.TestCase):
    def test_stored_range_controls_target(self):
        added = dict(book_id='1', part='0', part_path='chapter.xhtml',
                     page='1', offset='1140', range_len='1139')
        jumped = dict(added, page='0', page_count='12', offset='0', range_len='1329',
                      selection_active='1', selection_start='0', selection_end='15199')
        note = dict(id='1', storage='epub_notes', part='0', path='chapter.xhtml', start='0', end='15199')
        check_note_jump(added, jumped, [note], [dict(note, comment='updated')])
        # Reject the old creation-page target, clipped/shifted selections,
        # wrong chapter/book, missing evidence, and changed persisted ranges.
        for patch in ({'page': '1', 'offset': '1140'}, {'selection_end': '1329'},
                      {'selection_start': '1'}, {'selection_active': '0'},
                      {'part': '1'}, {'part_path': 'other.xhtml'}, {'book_id': '2'},
                      {'page': '12'}, {'range_len': '0'}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                check_note_jump(added, dict(jumped, **patch), [note], [note])
        with self.assertRaises(ValueError):
            check_note_jump(added, jumped, [], [])
        with self.assertRaises(ValueError):
            check_note_jump(added, jumped, [note], [dict(note, end='1329')])
        with self.assertRaises(KeyError):
            check_note_jump(added, jumped, [{k: v for k, v in note.items() if k != 'end'}], [note])
        # The start need not coincide with the page boundary, and end may
        # extend beyond it. The containing page uses a half-open interval.
        note = dict(note, start='1200', end='3000')
        jumped = dict(jumped, page='1', offset='1140', range_len='1139',
                      selection_start='1200', selection_end='3000')
        check_note_jump(added, jumped, [note], [note])
        with self.assertRaises(ValueError):
            check_note_jump(added, dict(jumped, offset='1201'), [note], [note])
        with self.assertRaises(ValueError):
            check_note_jump(added, dict(jumped, offset='0', range_len='1200'), [note], [note])


if __name__ == '__main__':
    unittest.main()
