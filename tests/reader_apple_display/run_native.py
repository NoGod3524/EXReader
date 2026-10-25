#!/usr/bin/env python3
"""Actions-only native installation, fresh consumers and real process supervision."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(args, log=None, **kwargs):
    print('+', ' '.join(map(str, args)), flush=True)
    p = subprocess.run(list(map(str, args)), text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, **kwargs)
    if log:
        Path(log).write_text(p.stdout)
    print(p.stdout if len(p.stdout) <= 12000 else p.stdout[-12000:], flush=True)
    p.check_returncode()
    return p.stdout.strip()


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + '\n')


def wait_json(path, stage=None, seconds=90):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if path.exists():
            data = json.loads(path.read_text())
            if stage is None or data.get('stage') == stage:
                print('D06_NATIVE_PHASE='+json.dumps(data,sort_keys=True),flush=True)
                return data
        time.sleep(.5)
    raise RuntimeError(f'Timed out waiting for real native report {path} stage={stage}')


def native_build(kind, out):
    sdk = 'macosx' if kind == 'macos' else ('iphoneos' if kind == 'iphoneos' else 'iphonesimulator')
    arch = 'arm64' if kind == 'iphoneos' else platform.machine()
    sdkpath = run(['xcrun', '--sdk', sdk, '--show-sdk-path'])
    source = os.environ['GITHUB_SHA']
    prefix = out / 'installed'
    build = out.parent / ('module-' + kind)
    cmake = ['cmake', '-S', ROOT / 'extras/apple-reader-display', '-B', build,
             '-DCMAKE_BUILD_TYPE=Release', f'-DCMAKE_INSTALL_PREFIX={prefix}',
             f'-DCMAKE_OSX_SYSROOT={sdkpath}', f'-DCMAKE_OSX_ARCHITECTURES={arch}',
             f'-DADR_SOURCE_SHA={source}', '-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY',
             '-DCMAKE_OSX_DEPLOYMENT_TARGET=' + ('12.0' if kind == 'macos' else '15.0')]
    if kind != 'macos':
        cmake += ['-DCMAKE_SYSTEM_NAME=iOS']
    run(cmake, out / 'configure.log')
    run(['cmake', '--build', build, '--parallel', '3'], out / 'build.log')
    run(['cmake', '--install', build], out / 'install.log')
    library = prefix / 'lib/libAppleReaderDisplay.a'
    header = prefix / 'include/ADRDisplayLease.h'
    consumer = out / 'fresh-consumer'
    consumer.mkdir()
    for name in ('ProbeSupport.h', 'MacProbe.m' if kind == 'macos' else 'IOSProbe.m'):
        shutil.copyfile(HERE / name, consumer / name)
    shutil.copyfile(ROOT / 'extras/apple-reader-display/examples/ReaderDisplayExample.m', consumer / 'Example.m')
    macros = {'ADR_PROBE_SOURCE': source, 'ADR_PROBE_RUN': os.environ['GITHUB_RUN_ID'],
              'ADR_PROBE_ATTEMPT': os.environ['GITHUB_RUN_ATTEMPT'], 'ADR_PLATFORM': kind,
              'ADR_LIBRARY_SHA': digest(library), 'ADR_HEADER_SHA': digest(header)}
    (consumer / 'identity.h').write_text('\n'.join(f'#define {key} "{value}"' for key, value in macros.items()) + '\n')
    target = f'{arch}-apple-macos12.0' if kind == 'macos' else f'{arch}-apple-ios15.0' + ('' if kind == 'iphoneos' else '-simulator')
    common = ['xcrun', '--sdk', sdk, 'clang', '-target', target, '-isysroot', sdkpath,
              '-fobjc-arc', '-fblocks', '-Wall', '-Wextra', '-Werror=return-type',
              '-I', prefix / 'include', '-I', consumer]
    run([*common, '-c', consumer / 'Example.m', '-o', consumer / 'Example.o'], out / 'example.log')
    if kind == 'macos':
        binary = out / 'display-probe'
        frameworks = ['-framework', 'Foundation', '-framework', 'IOKit']
        sourcefile = consumer / 'MacProbe.m'
    else:
        app = out / 'DisplayProbe.app'
        app.mkdir()
        binary = app / 'DisplayProbe'
        frameworks = ['-framework', 'Foundation', '-framework', 'UIKit']
        sourcefile = consumer / 'IOSProbe.m'
        plist = {'CFBundleIdentifier':'org.exreader.displayprobe', 'CFBundleExecutable':'DisplayProbe',
                 'CFBundleName':'DisplayProbe', 'CFBundleDisplayName':'DisplayProbe',
                 'CFBundlePackageType':'APPL', 'CFBundleVersion':'1', 'CFBundleShortVersionString':'1.0',
                 'MinimumOSVersion':'15.0', 'LSRequiresIPhoneOS':True, 'UIDeviceFamily':[1,2],
                 'UILaunchScreen':{}, 'UISupportedInterfaceOrientations':['UIInterfaceOrientationPortrait', 'UIInterfaceOrientationLandscapeLeft', 'UIInterfaceOrientationLandscapeRight'],
                 'UIApplicationSceneManifest':{'UIApplicationSupportsMultipleScenes':True,
                    'UISceneConfigurations':{'UIWindowSceneSessionRoleApplication':[
                        {'UISceneConfigurationName':'Display', 'UISceneDelegateClassName':'DisplaySceneDelegate'}]}},
                 'NSUserActivityTypes':['org.exreader.display.second']}
        (app / 'Info.plist').write_bytes(plistlib.dumps(plist))
    linkmap = out / 'consumer.linkmap'
    run([*common, '-H', sourcefile, library, *frameworks, '-Wl,-map,' + str(linkmap), '-o', binary], out / 'consumer-build.log')
    if sdk == 'iphonesimulator':
        run(['codesign', '--force', '--sign', '-', binary.parent], out / 'simulator-adhoc.log')
    # Distribution target is deliberately unsigned. No archive, profile or upload.
    run(['xcrun', 'nm', '-g', library], out / 'library-symbols.log')
    run(['xcrun', 'nm', '-g', binary], out / 'consumer-symbols.log')
    write(out / 'build-identity.json', {'schema':1, 'source':source, 'run':os.environ['GITHUB_RUN_ID'],
        'attempt':os.environ['GITHUB_RUN_ATTEMPT'], 'platform':kind, 'arch':arch, 'target':target,
        'sdk':sdk, 'sdkVersion':run(['xcrun','--sdk',sdk,'--show-sdk-version']),
        'binary':str(binary.relative_to(out)), 'binarySHA256':digest(binary),
        'library':'installed/lib/libAppleReaderDisplay.a', 'librarySHA256':digest(library),
        'header':'installed/include/ADRDisplayLease.h', 'headerSHA256':digest(header),
        'signing':'unsigned' if kind == 'iphoneos' else ('simulator-only-ad-hoc' if kind != 'macos' else 'none'),
        'consumerSourceSHA256':digest(sourcefile), 'supportSHA256':digest(consumer/'ProbeSupport.h')})
    # Save exact public SDK declarations actually used by the compiler.
    sdk_headers = ['System/Library/Frameworks/Foundation.framework/Headers/NSObject.h']
    sdk_headers += (['System/Library/Frameworks/IOKit.framework/Headers/pwr_mgt/IOPMLib.h'] if kind == 'macos' else
                    ['System/Library/Frameworks/UIKit.framework/Headers/UIApplication.h',
                     'System/Library/Frameworks/UIKit.framework/Headers/UIScreen.h',
                     'System/Library/Frameworks/UIKit.framework/Headers/UIScene.h'])
    write(out / 'apple-public-headers.json', {p:digest(Path(sdkpath)/p) for p in sdk_headers})
    return binary


def macos(binary, out):
    run([binary, 'core', out/'raw-core.json'], out/'runtime.log')
    with (out/'hold.log').open('w') as log:
        child = subprocess.Popen([str(binary), 'hold', str(out/'hold.json')], stdout=log, stderr=log)
        try:
            held = wait_json(out/'hold.json', seconds=15)
            assert held['identity']['pid'] == child.pid and held['status'] == 0 and held['queriedProperties']
            run([binary,'query',out/'query-before.json',str(child.pid)], out/'query-before.log')
            before = json.loads((out/'query-before.json').read_text())
            assert before['displayAssertions'] >= 1 and before['returnCode'] == 0
            child.kill(); code = child.wait(timeout=10)
            assert code == -signal.SIGKILL
            end = time.monotonic()+15
            index = 0
            while True:
                path = out/f'query-after-{index}.json'
                run([binary,'query',path,str(child.pid)])
                after = json.loads(path.read_text())
                if after['displayAssertions'] == 0: break
                if time.monotonic() > end: raise RuntimeError('Assertion survived process termination')
                time.sleep(.5); index += 1
            write(out/'termination.json', {'schema':1,'pid':child.pid,'exitCode':code,
                'before':'query-before.json','after':path.name,'hold':'hold.json',
                'status':'PASS','method':'real child SIGKILL and independent IOPMCopyAssertionsByProcess queries'})
        finally:
            if child.poll() is None: child.kill(); child.wait(timeout=10)


def ios(binary, kind, out):
    devices = json.loads(run(['xcrun','simctl','list','devices','available','--json']))['devices']
    choices = [(runtime,d) for runtime, ds in devices.items() for d in ds
               if d.get('isAvailable') and d['name'].startswith('iPhone' if kind == 'iphone' else 'iPad')]
    if not choices: raise RuntimeError('No actual requested simulator available')
    runtime, device = sorted(choices, key=lambda x:(x[0],x[1]['name']))[-1]
    udid = device['udid']; bundle = 'org.exreader.displayprobe'
    if device['state'] != 'Booted': run(['xcrun','simctl','boot',udid])
    run(['xcrun','simctl','bootstatus',udid,'-b'], out/'boot.log')
    run(['xcrun','simctl','install',udid,binary.parent], out/'install-app.log')
    container = Path(run(['xcrun','simctl','get_app_container',udid,bundle,'data']))
    report = container/'Documents/report.json'
    write(out/'simulator.json', {'runtime':runtime, 'device':device, 'bundle':bundle, 'dataContainer':str(container)})

    def launch(mode, fresh=True):
        if fresh and report.exists(): report.unlink()
        text = run(['xcrun','simctl','launch',udid,bundle,'--mode',mode], out/f'launch-{mode}-{time.monotonic_ns()}.log')
        pid = int(text.rsplit(':',1)[1].strip())
        command = run(['ps','-p',str(pid),'-o','command='])
        assert '/DisplayProbe.app/DisplayProbe' in command
        return pid

    def terminate(pid, name):
        run(['xcrun','simctl','terminate',udid,bundle], out/f'terminate-{name}.log')
        deadline = time.monotonic()+10
        while True:
            p = subprocess.run(['ps','-p',str(pid),'-o','command='], capture_output=True, text=True)
            if p.returncode != 0: break
            if time.monotonic() > deadline: raise RuntimeError('Native simulator process remained alive')
            time.sleep(.2)
        write(out/f'terminate-{name}.json', {'pid':pid,'psExitCode':p.returncode,'psOutput':p.stdout,
            'status':'PASS','method':'simctl terminate then host process-table absence'})

    core_pid = launch('core')
    core = wait_json(report,'complete')
    assert core['identity']['pid'] == core_pid
    shutil.copyfile(report,out/'raw-core.json')
    terminate(core_pid,'core')
    lifecycle_pid = launch('lifecycle')
    active = wait_json(report,'active')
    assert active['identity']['pid'] == lifecycle_pid
    shutil.copyfile(report,out/'raw-active.json')
    run(['xcrun','simctl','launch',udid,'com.apple.Preferences'], out/'background-transition.log')
    wait_json(report,'background'); shutil.copyfile(report,out/'raw-background.json')
    same_pid = launch('lifecycle', fresh=False)
    assert same_pid == lifecycle_pid
    wait_json(report,'resumed'); shutil.copyfile(report,out/'raw-lifecycle.json')
    terminate(lifecycle_pid,'lifecycle')
    reopen_pid = launch('reopen')
    assert reopen_pid != lifecycle_pid
    wait_json(report,'complete'); shutil.copyfile(report,out/'raw-reopen.json')
    terminate(reopen_pid,'reopen')
    multi_pid = launch('multiscene')
    wait_json(report,'complete'); shutil.copyfile(report,out/'raw-multiscene.json')
    terminate(multi_pid,'multiscene')
    write(out/'termination.json', {'status':'PASS','method':'real simulator process termination and new process launch',
        'oldPID':lifecycle_pid,'newPID':reopen_pid,'oldWitness':'terminate-lifecycle.json',
        'active':'raw-active.json','background':'raw-background.json','resumed':'raw-lifecycle.json','reopened':'raw-reopen.json'})


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Execution is restricted to GitHub Actions'
    assert run(['git','rev-parse','HEAD'], cwd=ROOT) == os.environ['GITHUB_SHA']
    parser = argparse.ArgumentParser(); parser.add_argument('platform',choices=['macos','iphone','ipad','iphoneos'])
    parser.add_argument('--out',type=Path,required=True); args=parser.parse_args()
    out=args.out.resolve(); out.mkdir(parents=True,exist_ok=False)
    binary=native_build(args.platform,out)
    if args.platform == 'macos': macos(binary,out)
    elif args.platform != 'iphoneos': ios(binary,args.platform,out)
    else:
        result=subprocess.run(['codesign','--verify',str(binary.parent)],capture_output=True,text=True)
        assert result.returncode != 0, 'iphoneos target must remain unsigned'
        write(out/'unsigned-build.json',{'status':'PASS','codesignVerifyExit':result.returncode,'runtime':'NOT_RUN_NO_DEVICE',
            'binarySHA256':digest(binary),'deviceAcceptance':'PENDING'})


if __name__ == '__main__': main()
