import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bench_engine


class BenchEngineTest(unittest.TestCase):
    def test_idle_gate_precedes_each_capture_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / 'bench.json'
            args = ['bench_engine.py', '--library', 'unused.dll', '--input', 'unused.pdf',
                    '--expect-pages', '1', '--widths', '1200', '--repeat', '2',
                    '--out', str(path)]
            samples = iter([(3, 5, 1), (5, 9, 3)])

            def capture(_, library, input_pdf, pages, widths, runs, directory):
                p50, p95, first = next(samples)
                directory.mkdir(parents=True, exist_ok=True)
                (directory / '1200.json').write_text(json.dumps({
                    'p50_ms': p50, 'p95_ms': p95, 'open_ms': 0.1,
                    'pages': [{'p50_ms': p50, 'first_render_ms': first}],
                }), encoding='utf-8')

            sequence = []

            def gate(*_):
                value = [4.0, None][len(sequence)]
                sequence.append(value)
                return value

            with patch.object(sys, 'argv', args), patch.object(bench_engine, 'wait_idle', side_effect=gate), \
                    patch.object(bench_engine, 'cpu_times', side_effect=[(0, 0), (80, 100)], create=True), \
                    patch.object(bench_engine, 'run_capture', side_effect=capture) as run:
                with self.assertRaisesRegex(SystemExit, 'CPU'):
                    bench_engine.main()
                self.assertEqual(run.call_count, 1)
                self.assertEqual(sequence, [4.0, None])
                self.assertFalse(path.exists())

            samples = iter([(3, 5, 1), (5, 9, 3)])
            with patch.object(sys, 'argv', args), patch.object(bench_engine, 'wait_idle', side_effect=[9.0, 4.0]), \
                    patch.object(bench_engine, 'cpu_times', side_effect=[(0, 0), (70, 100), (70, 100), (145, 200)], create=True), \
                    patch.object(bench_engine, 'run_capture', side_effect=capture):
                bench_engine.main()

            row = json.loads(path.read_text(encoding='utf-8'))['widths']['1200']
            self.assertEqual(row['p50_ms_median'], 4)
            self.assertEqual(row['p95_ms_median'], 7)
            self.assertEqual(row['first_page_render_ms_median'], 2)
            self.assertEqual([r['pre_cpu_percent'] for r in row['repeats']], [9, 4])
            self.assertEqual([r['capture_cpu_percent'] for r in row['repeats']], [30, 25])


if __name__ == '__main__':
    unittest.main()
