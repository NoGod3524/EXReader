"""Real macOS bundle with shared SDK; no app/UI launch."""
import importlib.util
import json
import os
import plistlib
from pathlib import Path
import shutil
import sys
import traceback
import build_windows as B

def main():
    source,sdk_source=B.start('macos')
    sdk,product=B.OUT/'sdk',B.OUT/'product'
    B.run(['cmake','-S',sdk_source,'-B',B.OUT/'sdk-build','-G','Ninja',
           '-DCMAKE_BUILD_TYPE=Release','-DEXR_BUILD_TESTS=OFF','-DEXR_BUILD_TOOLS=OFF',
           '-DEXR_ENABLE_AAC=OFF','-DCMAKE_INSTALL_PREFIX='+sdk.resolve().as_posix()],'sdk-configure')
    B.run(['cmake','--build',B.OUT/'sdk-build','--parallel','4'],'sdk-build')
    B.run(['cmake','--install',B.OUT/'sdk-build'],'sdk-install')
    B.run([sys.executable,B.ROOT/'tools/build_apple_product.py','--sdk',sdk,'--sdk-version','3.42.0',
           '--target','macos','--product-prefix',product,'--selector-bytes-candidate','--wave3',
           '--build',B.OUT/'products-build'],'products',timeout=3600)
    sys.path.insert(0,str(B.ROOT/'tools'))
    import build_apple_host as H
    signing=[]
    command_index=0
    def host_run(*argv):
        nonlocal command_index
        argv=list(map(str,argv))
        command_index+=1
        if 'swiftc' in argv:
            # Diagnostics only; unchanged source set, flags and installed linkage.
            argv += ['-v','-Xlinker','-why_load']
            name='host-link'
        else:
            name='host-tool-%02d'%command_index
        if argv[0]=='codesign' and '/Frameworks/' in argv[-1]:
            bundled=Path(argv[-1])
            installed=sdk/'lib'/bundled.name
            assert bundled.read_bytes()==installed.read_bytes()
            signing.append(dict(name=bundled.name,installed_sha256=B.digest(installed.read_bytes()),
                                pre_sign_sha256=B.digest(bundled.read_bytes())))
        B.run(argv,name)
    H.run=host_run
    old=sys.argv
    try:
        sys.argv=['build_apple_host.py','--sdk',str(sdk),'--sdk-version','3.42.0','--platform','macos',
                  '--product-prefix',str(product),'--selector-bytes-candidate','--wave3','--page-theme',
                  '--output',str(B.OUT/'package')]
        H.main()
    finally:
        sys.argv=old
    app=B.OUT/'package/EXReader.app'
    binary=app/'Contents/MacOS/EXReader'
    B.run(['codesign','--verify','--deep','--strict',app],'package-signature')
    B.run(['ditto','-c','-k','--sequesterRsrc','--keepParent',app,B.OUT/'package.zip'],'package-archive')
    B.run(['ditto','-x','-k',B.OUT/'package.zip',B.OUT/'unpacked'],'package-extract')
    copied=B.OUT/'unpacked/EXReader.app/Contents/MacOS/EXReader'
    assert binary.read_bytes()==copied.read_bytes()
    B.run(['codesign','--verify','--deep','--strict',B.OUT/'unpacked/EXReader.app'],'unpacked-signature')
    info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
    assert info['EXRSourceSHA']==source and info['CFBundleShortVersionString']=='3.42.0'
    assert info['EXRWave3Enabled'] is True and info['EXRRawSelectorEnabled'] is True
    B.keep(binary,'host');B.keep(copied,'package-host');B.keep(B.OUT/'package.zip','package.zip')
    B.keep(B.OUT/'package/build.json','package-build.json')
    B.keep(B.OUT/'package/product-link.map','host.map')
    B.keep(B.OUT/'package/product-link.json','original-product-inspection.json')
    B.keep(product/'share/exreader-apple/product.json','product-manifest.json')
    B.run(['otool','-L',binary],'host-imports')
    B.run(['otool','-l',binary],'host-loadcommands')
    B.run(['nm','-g',binary],'host-symbols')
    B.run(['lipo','-info',binary],'host-architecture')
    B.run(['xcrun','clang','--version'],'inspector-version')
    for i,item in enumerate(signing):
        installed=sdk/'lib'/item['name']
        bundled=app/'Contents/Frameworks'/item['name']
        item['bundled_sha256']=B.digest(bundled.read_bytes())
        item['installed_file']='shared-installed-%d'%i
        item['bundled_file']='shared-bundled-%d'%i
        B.keep(installed,item['installed_file']);B.keep(bundled,item['bundled_file'])
        B.run(['otool','-D',bundled],'shared-id-%d'%i)
        B.run(['otool','-L',bundled],'shared-imports-%d'%i)
        B.run(['nm','-g',bundled],'shared-symbols-%d'%i)
        B.run(['lipo','-info',bundled],'shared-architecture-%d'%i)
    assert signing
    targets,interface=B.auxiliary(sdk,product,product,'macos')
    B.finish(source,'macos',sdk,product,product,targets,interface,
             'EXReader.app/Contents/MacOS/EXReader',
             dict(sdk_linkage='shared',signing=signing,diagnostic_flags=['-v','-why_load'],
                  ui_suites_run=False,app_launched=False))

if __name__=='__main__':
    try:
        main()
    except BaseException as error:
        B.EVIDENCE.mkdir(parents=True,exist_ok=True)
        (B.EVIDENCE/'failure.txt').write_text(traceback.format_exc())
        output=getattr(error,'output',None)
        if output:
            raw=output.encode() if isinstance(output,str) else output
            (B.EVIDENCE/'failure-output.log').write_bytes(raw)
            print(raw.decode('utf-8','replace'),flush=True)
        raise
