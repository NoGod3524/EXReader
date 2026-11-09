"""Build the minimal JNI APK using SDK tools; no Gradle or product changes."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--ndk', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True, help='engine CMake build containing shared libraries')
    parser.add_argument('--smoke', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    sdk, ndk, build, smoke, out = [p.resolve() for p in (args.sdk, args.ndk, args.build, args.smoke, args.out)]
    source = ROOT / 'tools/platforms'
    bt = sdk / 'build-tools/35.0.0'
    platform = sdk / 'platforms/android-30/android.jar'
    windows = sys.platform == 'win32'
    suffix = '.bat' if windows else ''
    host = 'windows-x86_64' if windows else ('darwin-x86_64' if sys.platform == 'darwin' else 'linux-x86_64')
    clang = ndk / 'toolchains/llvm/prebuilt' / host / 'bin' / ('clang.exe' if windows else 'clang')

    def run(*command):
        print('ARGV:', [str(x) for x in command], flush=True)
        subprocess.run([str(x) for x in command], check=True)

    for name in ('classes', 'dex', 'assets'):
        (out / name).mkdir(parents=True, exist_ok=True)
    for name in ('smoke.epub', 'font.otf'):
        shutil.copyfile(smoke / name, out / 'assets' / name)
    run(clang, '--target=x86_64-linux-android24', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
        '-DPLATFORM_PROBE_EMBEDDED', '-I' + str(ROOT / 'include'), source / 'probe.c', source / 'android/jni.c',
        '-L' + str(build), '-lexreader', '-Wl,-z,max-page-size=16384', '-o', out / 'libplatform_probe.so')
    run('javac', '--release', '8', '-classpath', platform, '-d', out / 'classes', source / 'android/MainActivity.java',
        ROOT / 'bindings/jni/EXReader.java', ROOT / 'bindings/jni/EXReaderException.java')
    run('jar', 'cf', out / 'classes.jar', '-C', out / 'classes', '.')
    run(bt / ('d8' + suffix), '--lib', platform, '--min-api', '24', '--output', out / 'dex', out / 'classes.jar')
    run(bt / ('aapt.exe' if windows else 'aapt'), 'package', '-f', '-M', source / 'android/AndroidManifest.xml',
        '-I', platform, '-A', out / 'assets', '-F', out / 'unsigned.apk')
    with zipfile.ZipFile(out / 'unsigned.apk', 'a', zipfile.ZIP_DEFLATED) as apk:
        apk.write(out / 'dex/classes.dex', 'classes.dex')
        for name in ('libexreader.so', 'libexreader_jni.so', 'libplatform_probe.so'):
            apk.write((out if name == 'libplatform_probe.so' else build) / name, 'lib/x86_64/' + name)
    run(bt / ('zipalign.exe' if windows else 'zipalign'), '-f', '4', out / 'unsigned.apk', out / 'aligned.apk')
    key = out / 'debug.keystore'
    if not key.exists():
        run('keytool', '-genkeypair', '-keystore', key, '-storepass', 'android', '-keypass', 'android', '-alias',
            'androiddebugkey', '-dname', 'CN=EXReader Runtime Probe', '-keyalg', 'RSA', '-validity', '3650')
    run(bt / ('apksigner' + suffix), 'sign', '--ks', key, '--ks-pass', 'pass:android', '--out', out / 'platform-probe.apk', out / 'aligned.apk')
    run(bt / ('apksigner' + suffix), 'verify', '--verbose', out / 'platform-probe.apk')


if __name__ == '__main__':
    main()
