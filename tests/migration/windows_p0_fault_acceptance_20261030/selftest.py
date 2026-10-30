"""Actions-only adversarial tests of evidence validation, NOT native product fixtures."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
import zipfile
assert os.environ.get('GITHUB_ACTIONS') == 'true'
root = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('audit', root / 'tools/reader_composition/windows_p0_fault_independent_20261030.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
class EvidenceTests(unittest.TestCase):
    def report(self):
        return dict(schema=1, kind='windows-p0-fault-readiness', source_sha='a'*40,
                    run_id='1', attempt='1', source_admitted=True,
                    product_tests_executed=False, accepted=False, full_p0_acceptance=False,
                    physical_power_loss_qualified=False, directory_fsync_equivalent=False,
                    cases=[dict(id='M%02d'%i,status='pending',passed=False,reason='not bound') for i in range(1,11)],
                    frozen_objects={'sample':'b'*40},changed_paths=['sample'])
    def check(self,r):
        return audit.verify_readiness(r,'a'*40,1,1)
    def test_honest_pending(self):
        self.assertFalse(self.check(self.report())['accepted'])
    def test_no_claim_escalation(self):
        for flag in ('accepted','full_p0_acceptance','product_tests_executed','physical_power_loss_qualified','directory_fsync_equivalent'):
            with self.subTest(flag=flag):
                r=self.report();r[flag]=True
                with self.assertRaises(AssertionError):self.check(r)
    def test_case_integrity(self):
        for mode in ('missing','duplicate','pass','empty_reason'):
            r=self.report()
            if mode=='missing':r['cases'].pop()
            elif mode=='duplicate':r['cases'][1]=copy.deepcopy(r['cases'][0])
            elif mode=='pass':r['cases'][0].update(status='passed',passed=True)
            else:r['cases'][0]['reason']=''
            with self.assertRaises(AssertionError):self.check(r)
    def test_source_run_attempt(self):
        for key in ('source_sha','run_id','attempt'):
            r=self.report();r[key]='other'
            with self.assertRaises(AssertionError):self.check(r)
    def test_zip_paths(self):
        for names in (['../readiness.json'],['/readiness.json'],['x:readiness.json'],['readiness.json','readiness.json'],['readiness.json','extra']):
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w') as z:
                for name in names:z.writestr(name,json.dumps(self.report()))
            with self.assertRaises(AssertionError):audit.read_archive(stream.getvalue())
    def test_zip_positive(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr('readiness.json',json.dumps(self.report()))
        self.assertEqual(audit.read_archive(stream.getvalue()),self.report())
if __name__=='__main__':unittest.main()
