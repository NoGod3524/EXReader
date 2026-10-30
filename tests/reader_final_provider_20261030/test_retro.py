"""Synthetic tamper / wrong-provider cases for the retrospective artifact authentication."""
import copy
import io
import unittest
import zipfile

import fp_core as C
import fp_retro as R

RAW = b'PK-synthetic-artifact-bytes-' * 20
PIN = dict(run=7, attempt=1, source='a' * 40,
           artifact=dict(id=11, name='art-7-1', size=len(RAW), digest='sha256:' + C.sha(RAW)))
RUN = dict(id=7, run_attempt=1, head_sha='a' * 40, path=R.WORKFLOW_PATH, head_branch=C.BRANCH, status='completed')
META = dict(id=11, name='art-7-1', expired=False, size_in_bytes=len(RAW), digest=PIN['artifact']['digest'],
            workflow_run=dict(id=7, head_sha='a' * 40))

PRODUCT = '/w/raw-stage/lib/libreader_catalog_sqlite.a'
SDK = '/w/stage/lib/libreader_sdk_vendor_sqlite.a'
CONSUMER = ['/w/raw-stage/lib/libreader_catalog.a', 'catalog.c.o']


def evidence():
    def row(defined=(), undefined=()):
        return dict(defined=list(defined), weak=[], undefined=list(undefined))
    return dict(roles=dict(sdk=['/w/stage/'], product=['/w/raw-stage/']), product_catalog_archives=['libreader_catalog_sqlite.a'],
                archives={PRODUCT: {'sqlite3.c.o': row({'sqlite3_open_v2'})}, SDK: {'sqlite3.c.o': row({'sqlite3_open_v2'})},
                          CONSUMER[0]: {CONSUMER[1]: row(undefined={'sqlite3_open_v2'})}},
                selected=[[PRODUCT, 'sqlite3.c.o'], CONSUMER])


FINDING = dict(kind=R.ORIGINAL_KIND, symbol='sqlite3_open_v2', consumer=CONSUMER)


class Identity(unittest.TestCase):
    def test_exact_identity_accepted(self):
        self.assertTrue(R.verify_identity(RUN, META, RAW, PIN))

    def reject(self, run=None, meta=None, raw=None, pin=None):
        r, m, p = copy.deepcopy(RUN), copy.deepcopy(META), copy.deepcopy(PIN)
        (run or (lambda x: None))(r); (meta or (lambda x: None))(m); (pin or (lambda x: None))(p)
        with self.assertRaises(ValueError):
            R.verify_identity(r, m, RAW if raw is None else raw, p)

    def test_tampered_bytes(self):
        self.reject(raw=RAW[:50] + b'X' + RAW[51:])
        self.reject(raw=RAW[:-1])

    def test_tampered_digest_and_size(self):
        self.reject(pin=lambda p: p['artifact'].update(digest='sha256:' + '0' * 64))
        self.reject(meta=lambda m: m.update(digest='sha256:' + '0' * 64))
        self.reject(meta=lambda m: m.update(size_in_bytes=m['size_in_bytes'] + 1))

    def test_tampered_run_source_attempt_artifact(self):
        self.reject(run=lambda r: r.update(head_sha='b' * 40))
        self.reject(run=lambda r: r.update(run_attempt=2))
        self.reject(run=lambda r: r.update(id=8))
        self.reject(run=lambda r: r.update(head_branch='main'))
        self.reject(meta=lambda m: m.update(id=12))
        self.reject(meta=lambda m: m.update(name='other'))
        self.reject(meta=lambda m: m['workflow_run'].update(head_sha='b' * 40))
        self.reject(meta=lambda m: m.update(expired=True))

    def test_live_tamper_helper_rejects_all(self):
        self.assertEqual(len(R.tamper_checks(RUN, META, RAW, PIN)), 10)
        with self.assertRaises(ValueError):  # a baseline that is already wrong cannot yield meaningful rejections
            R.tamper_checks(RUN, META, RAW + b'!', PIN)


class Unpack(unittest.TestCase):
    def zipped(self, *names):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as bundle:
            for name in names:
                bundle.writestr(name, b'x')
        return buffer.getvalue()

    def test_good_and_unique(self):
        files = R.safe_unpack(self.zipped('final-provider/linux/result.json'))
        self.assertEqual(R.unique(files, 'final-provider/linux/result.json'), 'final-provider/linux/result.json')

    def test_traversal_duplicate_and_ambiguous_rejected(self):
        with self.assertRaises(ValueError):
            R.safe_unpack(self.zipped('../evil'))
        with self.assertRaises(ValueError):
            R.safe_unpack(self.zipped('a/b', 'a/b'))
        with self.assertRaises(ValueError):
            R.unique({'x/final-provider/linux/result.json': b'', 'y/final-provider/linux/result.json': b''}, 'final-provider/linux/result.json')


class Classification(unittest.TestCase):
    def test_single_selected_product_with_unselected_alternative(self):
        self.assertEqual(R.classify_original(FINDING, evidence())['status'], 'rule_defect_resolved_by_selected_product')

    def test_wrong_selected_sdk_provider_is_genuine(self):
        ev = evidence()
        ev['selected'] = [[SDK, 'sqlite3.c.o'], CONSUMER]
        self.assertEqual(R.classify_original(FINDING, ev)['status'], 'GENUINE_PROBLEM')

    def test_duplicate_selected_provider_is_genuine(self):
        ev = evidence()
        ev['selected'].append([SDK, 'sqlite3.c.o'])
        self.assertEqual(R.classify_original(FINDING, ev)['status'], 'GENUINE_PROBLEM')

    def test_no_selected_definer_is_genuine(self):
        ev = evidence()
        ev['selected'] = [CONSUMER]
        self.assertEqual(R.classify_original(FINDING, ev)['status'], 'GENUINE_PROBLEM')

    def test_missing_evidence_is_pending_not_false_positive(self):
        ev = evidence(); del ev['product_catalog_archives']
        self.assertEqual(R.classify_original(FINDING, ev)['status'], 'pending')
        ev = evidence(); ev['selected'] = [[PRODUCT, 'sqlite3.c.o']]
        self.assertEqual(R.classify_original(FINDING, ev)['status'], 'pending')
        other = dict(FINDING, symbol='reader_open')
        self.assertEqual(R.classify_original(other, evidence())['status'], 'pending')

    def test_no_alternative_recorded_is_pending(self):
        ev = evidence(); del ev['archives'][SDK]
        self.assertEqual(R.classify_original(FINDING, ev)['status'], 'pending')

    def test_cross_check_is_never_same_source(self):
        row = dict(status='resolved_by_selected_product', selected_definers=[], unselected_candidates=[])
        got = R.cross_check(FINDING, {(tuple(CONSUMER), 'sqlite3_open_v2'): row})
        self.assertFalse(got['same_source'])
        missing = R.cross_check(FINDING, {})
        self.assertEqual((missing['status'], missing['same_source']), ('pending', False))


if __name__ == '__main__':
    unittest.main(verbosity=2)
