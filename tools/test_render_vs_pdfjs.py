"""No renderer, node or benchmark invocation required."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_vs_pdfjs import dispatch_round, identity, schedule, summary


class DesignTests(unittest.TestCase):
    def test_orders_and_reverse(self):
        forward = schedule(12)
        self.assertEqual(6,len(set(forward[:6])))
        self.assertEqual(forward[:6], forward[6:])
        self.assertTrue(all(set(row)=={'A','A0','P'} for row in forward))
        self.assertEqual([row[::-1] for row in forward], schedule(12,True))

    def test_dispatch_interleaves_actual_calls(self):
        for i in (0,1,2):
            calls, rows = [], []
            def fake(arm,page):
                calls.append((arm,page))
                return {'token':len(calls)}
            dispatch_round(i,6,False,fake,rows)
            self.assertEqual(calls,[(r['arm'],r['page']) for r in rows])
            self.assertEqual(list(range(1,19)),[r['token'] for r in rows])
            self.assertEqual([p for p in range(1,7) for _ in range(3)],
                             [p for _,p in calls])
            groups = [tuple(a for a,_ in calls[j:j+3]) for j in range(0,18,3)]
            self.assertEqual(6,len(set(groups)))
            if i==0:
                first=groups
            elif i==1:
                self.assertEqual([g[::-1] for g in first],groups)
            else:
                self.assertEqual(first[1:]+first[:1],groups)

    def test_identity(self):
        with TemporaryDirectory() as d:
            a, b = (Path(d)/k for k in ('a','b'))
            for f in (a,b):
                f.write_bytes(b'test')
            self.assertEqual(64,len(identity(a,b)))
            with self.assertRaises(ValueError):
                identity(a,a)
            b.write_bytes(b'other')
            with self.assertRaises(ValueError):
                identity(a,b)

    def test_pooled_distribution(self):
        s = summary([dict(ns=i,page=i,round=1) for i in range(1,21)])
        self.assertEqual((10.5,19,20,20,1), tuple(s[k] for k in
                         ('p50_ns','p95_ns','worst_ns','worst_page','worst_round')))
        self.assertAlmostEqual(20e9/210,s['throughput_pages_s'])


if __name__ == '__main__':
    unittest.main()
