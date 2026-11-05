import hashlib,os,sys
from common import *
def main():
 actions()
 old=ROOT/'tests/gtk_managed_webdav_20261031/build.py'
 if sys.argv[1]=='compat':
  run('legacy-compat',[sys.executable,old,'compat'])
  return
 overlay()
 prefix=(OUT/'c02-prefix').resolve()
 text=old.read_text()
 a=' cmake("host","apps/reader/desktop",extra,install=False,targets=("exreader-linux",))'
 b=' joint_dependencies(cmake,SDK,PREFIX)\n extra+=["-DEXR_C02_PREFIX="+str(JOINT_C02_PREFIX),"-DEXR_READER_GTK_SEARCH=ON","-DEXR_READER_GTK_NAVIGATION=ON","-DREADER_SEARCH_PREFIX="+str(PREFIX),"-DREADER_NAVIGATION_PREFIX="+str(PREFIX)]\n'+a
 assert text.count(a)==1;text=text.replace(a,b)
 a='  "--binary",OUT/"host/gtk-host/exreader-linux","--output",OUT/"package"])'
 b='  "--c02-prefix",JOINT_C02_PREFIX,"--binary",OUT/"host/gtk-host/exreader-linux","--output",OUT/"package"])'
 assert text.count(a)==1;text=text.replace(a,b)
 a='build,"-G","Ninja","-DCMAKE_BUILD_TYPE=Release"';b='build,"-G",("Unix Makefiles" if name=="host" else "Ninja"),"-DCMAKE_BUILD_TYPE=Release"'
 assert text.count(a)==1;text=text.replace(a,b)
 def deps(original,sdk,products):
  c02_deps(sdk,prefix,owner=True)
  for component in ('search','navigation'):original('joint-'+component,'apps/reader/'+component)
 namespace=dict(__file__=str(old),__name__='_joint_build',joint_dependencies=deps,JOINT_C02_PREFIX=prefix)
 save(OUT/'recipe-adaptation.json',dict(original=str(old.relative_to(ROOT)),original_sha256=sha(old),
   changes=['install frozen C02/search/navigation dependencies','pass explicit C02 prefix','package explicit admission CLI','retain real CMake host link.txt using Unix Makefiles'],
   derived_sha256=hashlib.sha256(text.encode()).hexdigest(),assertions_removed=False))
 (OUT/'derived-build.py').write_text(text)
 exec(compile(text,str(OUT/'derived-build.py'),'exec'),namespace)
 namespace['build']()
 sdk=namespace['SDK'];products=namespace['PREFIX']
 cmake('c02-gtk','tests/migration/gtk_c02_host_20261031',[
  '-DEXR_SDK='+str(sdk),'-DCMAKE_PREFIX_PATH='+str(sdk),'-DEXR_C02_PREFIX='+str(prefix),
  '-DREADER_SEARCH_PREFIX='+str(products),'-DREADER_NAVIGATION_PREFIX='+str(products),
  '-DREADER_ORIGINAL_HASH_PREFIX='+str(products)],install=False,targets=('c02-gtk-host-check',))
 driver=ROOT/'tests/migration/gtk_c02_host_20261031/run.py'
 body=driver.read_text()
 mappings=[('"build/gtk/actual-host/gtk-host','"build/gtk-managed/host/gtk-host',4),
           ('"build/sdk-admission','"build/c02-webdav-joint/c02-sdk',3),
           ('root/"stage-sdk"','root/"build/gtk-managed/sdk-source/build/reading-library/stage"',1),
           ('root/"stage-c02"','root/"build/c02-webdav-joint/c02-prefix"',1),
           ('"8357eafa28423a7ab93ba08b823af80f01ad1505"','"'+M['sdk']+'"',1)]
 for a,b,count in mappings:
  assert body.count(a)==count,(a,body.count(a),count)
  body=body.replace(a,b)
 header='import sys\nsys.path.insert(0,'+repr(str(driver.parent))+')\n__file__='+repr(str(driver))+'\n'
 derived=OUT/'derived-gtk-driver.py';derived.write_text(header+body)
 save(OUT/'gtk-driver-adaptation.json',dict(source=M['c02'],original_sha256=sha(driver),
  derived_sha256=sha(derived),mappings=mappings,assertions_removed=False,
  reason='Original driver retains real link inputs from the current installed SDK/admission/managed host layout'))
 run('c02-gtk-original',[sys.executable,derived,
  '--host',OUT/'c02-gtk/c02-gtk-host-check','--admission',prefix/'bin/exreader-c02-admission',
  '--font',ROOT/'build/gtk-managed/package/EXReader-Linux/Reader.otf','--output',OUT/'gtk-original'])
 run('c02-gtk-raw-audit',[sys.executable,'tests/migration/c02_completion_audit_20261031/gtk_snapshots.py',
  '--root',OUT/'gtk-original','--output',OUT/'gtk-native-audit'])
if __name__=='__main__':main()
