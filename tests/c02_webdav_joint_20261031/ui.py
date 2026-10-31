import hashlib,os,sys,types
from common import *
def load():
 actions();old=ROOT/'tests/gtk_managed_webdav_20261031/ui.py'
 text=old.read_text()
 before=' return Session((PAYLOAD/"bin/exreader-linux").resolve(),(PAYLOAD/"Reader.otf").resolve(),folder)'
 after=' profile=folder/"profile";profile.mkdir(parents=True,exist_ok=True,mode=0o700)\n db=profile/"library.sqlite"\n operation="check" if db.exists() else "create"\n subprocess.run([str((PAYLOAD/"bin/exreader-c02-admission").resolve()),operation,str(db.resolve())],check=True,capture_output=True)\n'+before
 assert text.count(before)==1;text=text.replace(before,after)
 sys.path.insert(0,str(old.parent))
 namespace=dict(__file__=str(old),__name__='_joint_ui')
 exec(compile(text,str(OUT/'derived-ui.py'),'exec'),namespace)
 save(OUT/'ui-fixture-adaptation.json',dict(original_sha256=sha(old),derived_sha256=hashlib.sha256(text.encode()).hexdigest(),
  only_change='explicit create/check of the existing Session profile before launch',assertions_removed=False))
 (OUT/'derived-ui.py').write_text(text)
 return types.SimpleNamespace(**namespace)
if __name__=='__main__':load().main()
