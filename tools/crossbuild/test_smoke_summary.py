"""Reject truncated pixels and first-hit-only smoke evidence."""
from pathlib import Path
import tempfile
import unittest

from smoke_summary import summarize


class SmokeEvidenceTest(unittest.TestCase):
    def test_requires_all_hits_and_complete_pixels(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            log = ('PASS open pages=215\n'
                   'PASS render width=2 height=1 ink_pixels=1\n'
                   'PASS search_all needle=deliveryneedle hits=1000\n')
            (directory / 'create.log').write_text(log)
            (directory / 'page.rgba').write_bytes(bytes(8))
            (directory / 'page.png').write_bytes(b'fixture')
            self.assertEqual(summarize(directory)['search_hits'], 1000)
            (directory / 'page.rgba').write_bytes(bytes(7))
            with self.assertRaises(ValueError):
                summarize(directory)
            (directory / 'page.rgba').write_bytes(bytes(8))
            (directory / 'create.log').write_text(log.replace('hits=1000', 'hits=1'))
            with self.assertRaises(ValueError):
                summarize(directory)


if __name__ == '__main__':
    unittest.main()
