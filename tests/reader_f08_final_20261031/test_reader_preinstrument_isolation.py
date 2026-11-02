"""Pre-instrument owned-directory controls; run only in the existing Actions control job."""
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
import reader_android as R

DATA=b'preserved old evidence'
DIGEST=hashlib.sha256(DATA).hexdigest()
PATH=R.READER_ISOLATION_PATH

def listing(name="validation.json",digest=DIGEST,size=len(DATA)):
    return "PRESENT\nregular file|%d|%s/%s\nHASHES\n%s  %s/%s"%(size,PATH,name,digest,PATH,name)

class Fixture:
    def __init__(self):
        self.now=0.;self.calls=[];self.deleted=False;self.absent=False
        self.inventory=listing();self.inventory_count=0;self.after=None
        self.fail_name=None;self.timeout=False;self.missing=False;self.bad_copy=False
        self.still_present=False;self.expire_pull=False
    def execute(self,args,timeout):
        self.calls.append((args,timeout))
        if self.timeout:raise subprocess.TimeoutExpired(args,timeout)
        if args[0]=="pull":
            if self.fail_name=="pull":return subprocess.CompletedProcess(args,1,b'',b'pull failed')
            dst=Path(args[2]);dst.mkdir()
            if not self.missing:(dst/"validation.json").write_bytes(b'wrong' if self.bad_copy else DATA)
            if self.expire_pull:self.now=21.
            return subprocess.CompletedProcess(args,0,b'copied',b'')
        if "rm -rf" in args[1]:
            if self.fail_name=="remove":return subprocess.CompletedProcess(args,1,b'',b'remove failed')
            self.deleted=True
            return subprocess.CompletedProcess(args,0,b'REMOVED',b'')
        self.inventory_count+=1
        if self.fail_name=="query":return subprocess.CompletedProcess(args,1,b'',b'query failed')
        if self.absent or (self.deleted and not self.still_present):text="ABSENT"
        elif self.after is not None and self.inventory_count>1:text=self.after
        else:text=self.inventory
        return subprocess.CompletedProcess(args,0,text.encode(),b'')

class PreinstrumentIsolation(unittest.TestCase):
    def invoke(self,f,root,deadline=100):
        return R.isolate_reader_evidence(root,{"source_sha":"a"*40,"run_id":"control","attempt":"1"},
                                        deadline,f.execute,lambda:f.now)
    def rejected(self,f,deadline=100):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(Exception):self.invoke(f,root,deadline)
            receipt=R.load(Path(root)/"isolation-prereader/receipt.json")
            self.assertIsNotNone(receipt["first_error"])
            self.assertFalse(receipt["absence_verified"])
            return receipt
    def test_01_absent_noop(self):
        f=Fixture();f.absent=True
        with tempfile.TemporaryDirectory() as root:
            v=self.invoke(f,root)
            self.assertTrue(v["absence_verified"]);self.assertTrue(v["noop"])
            self.assertFalse(v["backup_verified"]);self.assertFalse(f.deleted)
            self.assertEqual(len(f.calls),1)
    def test_02_verified_backup_then_remove(self):
        f=Fixture()
        with tempfile.TemporaryDirectory() as root:
            v=self.invoke(f,root)
            self.assertTrue(v["backup_verified"] and v["deleted"] and v["absence_verified"])
            self.assertEqual((Path(root)/"isolation-prereader/backup/validation.json").read_bytes(),DATA)
            names=[c["name"] for c in v["commands"]]
            self.assertLess(names.index("inventory-after-backup"),names.index("remove-fixed-evidence"))
            self.assertTrue(all(0<t<=20 for _,t in f.calls))
            self.assertFalse(v["acceptance_override"])
    def test_03_wrong_exact_path(self):
        f=Fixture();f.inventory=listing().replace(PATH,PATH+"-other")
        self.rejected(f);self.assertFalse(f.deleted)
    def test_04_symlink_or_escape(self):
        for text in (listing().replace("regular file","symbolic link"),listing("../old")):
            with self.subTest(text=text):
                f=Fixture();f.inventory=text;self.rejected(f);self.assertFalse(f.deleted)
    def test_05_query_nonzero(self):
        f=Fixture();f.fail_name="query";self.rejected(f);self.assertFalse(f.deleted)
    def test_06_query_timeout(self):
        f=Fixture();f.timeout=True;self.rejected(f);self.assertFalse(f.deleted)
    def test_07_quantity_or_byte_limit(self):
        lines=["regular file|0|%s/f%d"%(PATH,i) for i in range(10001)]
        hashes=["%s  %s/f%d"%(DIGEST,PATH,i) for i in range(10001)]
        for text in (listing(size=R.READER_ISOLATION_MAX_BYTES+1),
                     "PRESENT\n"+"\n".join(lines)+"\nHASHES\n"+"\n".join(hashes)):
            with self.subTest(kind=text[:50]):
                f=Fixture();f.inventory=text;self.rejected(f);self.assertFalse(f.deleted)
    def test_08_pull_failure(self):
        f=Fixture();f.fail_name="pull";self.rejected(f);self.assertFalse(f.deleted)
    def test_09_missing_backup_entry(self):
        f=Fixture();f.missing=True;self.rejected(f);self.assertFalse(f.deleted)
    def test_10_hash_mismatch(self):
        f=Fixture();f.bad_copy=True;self.rejected(f);self.assertFalse(f.deleted)
    def test_11_remote_changes_after_backup(self):
        f=Fixture();f.after=listing(digest="0"*64);self.rejected(f);self.assertFalse(f.deleted)
    def test_12_remove_failure(self):
        f=Fixture();f.fail_name="remove";v=self.rejected(f)
        self.assertTrue(v["backup_verified"]);self.assertFalse(f.deleted)
    def test_13_directory_remains(self):
        f=Fixture();f.still_present=True;v=self.rejected(f)
        self.assertTrue(v["backup_verified"]);self.assertTrue(v["deleted"])
    def test_14_absolute_deadlines(self):
        f=Fixture();f.expire_pull=True;self.rejected(f);self.assertFalse(f.deleted)
        f=Fixture();self.rejected(f,deadline=0);self.assertEqual(f.calls,[])
        f=Fixture();f.absent=True
        with tempfile.TemporaryDirectory() as root:
            v=self.invoke(f,root,deadline=5)
            self.assertEqual(v["deadline_mono"],5);self.assertEqual(f.calls[0][1],5)

if __name__=="__main__":unittest.main()
