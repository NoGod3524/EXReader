# SPDX-License-Identifier: MIT
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bench_large import Sampler


class LargeToolsTest(unittest.TestCase):
    def test_sampler_observes_transient_between_endpoints(self):
        seen = threading.Event()
        owner = threading.current_thread()

        def read():
            if threading.current_thread() is owner:
                return 1
            seen.set()
            return 9

        with Sampler(read, interval=0.001) as sample:
            self.assertTrue(seen.wait(2))
        self.assertEqual(sample.peak, 9)
        self.assertGreaterEqual(sample.count, 3)
        self.assertFalse(sample.thread.is_alive())

    def test_copies_whole_sources_then_prefix(self):
        from make_large_pdf import build, PdfReader, PdfWriter
        with tempfile.TemporaryDirectory() as tmp:
            a, b, out = (Path(tmp) / name for name in ('a.pdf', 'b.pdf', 'out.pdf'))
            for file, widths in [(a, [10, 20]), (b, [30])]:
                writer = PdfWriter()
                for w in widths:
                    writer.add_blank_page(width=w, height=40)
                with file.open('wb') as stream:
                    writer.write(stream)
            build([a, b], 7, out)
            reader = PdfReader(str(out))
            self.assertEqual([p.mediabox.width for p in reader.pages], [10, 20, 30, 10, 20, 30, 10])


if __name__ == '__main__':
    unittest.main()
