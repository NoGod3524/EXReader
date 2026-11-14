"""Build the audit using clang-cl and the installed Windows SDK. No source patching."""
import argparse
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def build(args):
    env = {k.upper(): v for k, v in os.environ.items()}
    vc = Path(env.get('EXR_MSVC', 'C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.44.35207'))
    sdk = Path(env.get('EXR_WINSDK', 'C:/Program Files (x86)/Windows Kits/10'))
    sdk_version = env.get('EXR_WINSDK_VERSION', '10.0.26100.0')
    env['INCLUDE'] = ';'.join(str(p) for p in [vc/'include', *[sdk/'Include'/sdk_version/n for n in ('ucrt','shared','um','winrt')]])
    env['LIB'] = ';'.join(str(p) for p in [vc/'lib/x64', *[sdk/'Lib'/sdk_version/n/'x64' for n in ('ucrt','um')]])
    llvm = Path(env.get('LLVM_ROOT', r'C:\Users\Oscar\Documents\Codex\sanitize-toolchain-20261107\llvm'))
    env['PATH'] = os.pathsep.join([str(llvm/'bin'), str(vc/'bin/Hostx64/x64'), str(sdk/'bin'/sdk_version/'x64'), env['PATH']])
    rt = next((llvm / 'lib/clang').glob('*/lib/windows'))
    deps = Path(env.get('EXR_DEPS', 'C:/Users/Oscar/exr-deps'))
    link = f'/libpath:{rt} clang_rt.asan_dynamic-x86_64.lib /wholearchive:clang_rt.asan_static_runtime_thunk-x86_64.lib clang_rt.ubsan_standalone-x86_64.lib clang_rt.profile-x86_64.lib'
    command = ['cmake', '-S', str(HERE), '-B', str(args.build), '-G', 'Ninja',
               '-DCMAKE_BUILD_TYPE=RelWithDebInfo', '-DCMAKE_TRY_COMPILE_CONFIGURATION=RelWithDebInfo',
               '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', f'-DCMAKE_C_COMPILER={(llvm / "bin/clang-cl.exe").as_posix()}',
               f'-DCMAKE_LINKER={(llvm / "bin/lld-link.exe").as_posix()}', '-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded',
               f'-DCMAKE_AR={(llvm / "bin/llvm-lib.exe").as_posix()}',
               f'-DCMAKE_RC_COMPILER={(sdk / "bin" / sdk_version / "x64/rc.exe").as_posix()}',
               f'-DCMAKE_MT={(llvm / "bin/llvm-mt.exe").as_posix()}',
               '-DCMAKE_C_FLAGS=-fsanitize=address,undefined /clang:-fno-omit-frame-pointer /clang:-fno-optimize-sibling-calls /clang:-fno-sanitize-ignorelist -fprofile-instr-generate -fcoverage-mapping',
               f'-DCMAKE_EXE_LINKER_FLAGS={link}', f'-DCMAKE_SHARED_LINKER_FLAGS={link}']
    for key, value in dict(EXR_BUILD_SHARED_COMPAT='OFF', EXR_BUILD_TOOLS='ON', EXR_BUILD_TESTS='OFF',
                           EXR_BUILD_FUZZ='ON', EXR_ENABLE_IMAGE_AVIF='OFF',
                           EXR_ENABLE_IMAGE_TIFF='OFF', EXR_ENABLE_IMAGE_WEBP='OFF').items():
        command.append(f'-D{key}={value}')
    sources = dict(EXPAT=deps/'expat', FREETYPE=deps/'freetype-VER-2-15-0', MINIZ=deps/'miniz',
                   SQLITE=deps/'sqlite', STB=deps/'stb', LCMS=deps/'lcms',
                   MBEDTLS=deps/'mbedtls', MINIMP3=deps/'minimp3', OPENJPEG=Path(env.get('EXR_OPENJPEG',
                   'C:/Users/Oscar/Documents/Codex/cjk-punctuation-compression-20261106/deps/openjpeg-2.5.4')))
    command.extend(f'-DFETCHCONTENT_SOURCE_DIR_{name}={path.as_posix()}' for name, path in sources.items())
    subprocess.run(command, env=env, check=True)
    subprocess.run(['cmake', '--build', str(args.build), '--target', 'exreader-sanitize', 'sanitize-control',
                    'exreader-fuzz', 'exreader-fuzz-font', 'exreader-fuzz-layout', 'exreader-fuzz-render',
                    '--parallel', '8'], env=env, check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    build(parser.parse_args())
