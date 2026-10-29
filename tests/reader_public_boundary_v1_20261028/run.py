"""Explicit 17-module + 1 Android caller + 7-validation integration; Actions-only.

Preserves original builders/behavior assertions. Old source allowlists are NOT
reported passed: the named new exact-scope guard replaces those entrypoints.
This proves named module/Android caller repairs, never full F07/P0 or physical devices.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'build/public-boundary-v1'
BASE = 'f331d5da3ac491143d8f525089140f5d2365fa97'
BRANCH = 'codex/reader-public-boundary-v1-20261028'
# Complete Apache-2.0 plus LLVM exception block, not marker-word qualification.
# Official LLVM 18.1.8 LICENSE.TXT blob fa6ac540007032cbd0ec772a1c72e6cb5527a4fe.
LLVM_LICENSE_BLOCK = "Apache License\n                           Version 2.0, January 2004\n                        http://www.apache.org/licenses/\n\n    TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION\n\n    1. Definitions.\n\n      \"License\" shall mean the terms and conditions for use, reproduction,\n      and distribution as defined by Sections 1 through 9 of this document.\n\n      \"Licensor\" shall mean the copyright owner or entity authorized by\n      the copyright owner that is granting the License.\n\n      \"Legal Entity\" shall mean the union of the acting entity and all\n      other entities that control, are controlled by, or are under common\n      control with that entity. For the purposes of this definition,\n      \"control\" means (i) the power, direct or indirect, to cause the\n      direction or management of such entity, whether by contract or\n      otherwise, or (ii) ownership of fifty percent (50%) or more of the\n      outstanding shares, or (iii) beneficial ownership of such entity.\n\n      \"You\" (or \"Your\") shall mean an individual or Legal Entity\n      exercising permissions granted by this License.\n\n      \"Source\" form shall mean the preferred form for making modifications,\n      including but not limited to software source code, documentation\n      source, and configuration files.\n\n      \"Object\" form shall mean any form resulting from mechanical\n      transformation or translation of a Source form, including but\n      not limited to compiled object code, generated documentation,\n      and conversions to other media types.\n\n      \"Work\" shall mean the work of authorship, whether in Source or\n      Object form, made available under the License, as indicated by a\n      copyright notice that is included in or attached to the work\n      (an example is provided in the Appendix below).\n\n      \"Derivative Works\" shall mean any work, whether in Source or Object\n      form, that is based on (or derived from) the Work and for which the\n      editorial revisions, annotations, elaborations, or other modifications\n      represent, as a whole, an original work of authorship. For the purposes\n      of this License, Derivative Works shall not include works that remain\n      separable from, or merely link (or bind by name) to the interfaces of,\n      the Work and Derivative Works thereof.\n\n      \"Contribution\" shall mean any work of authorship, including\n      the original version of the Work and any modifications or additions\n      to that Work or Derivative Works thereof, that is intentionally\n      submitted to Licensor for inclusion in the Work by the copyright owner\n      or by an individual or Legal Entity authorized to submit on behalf of\n      the copyright owner. For the purposes of this definition, \"submitted\"\n      means any form of electronic, verbal, or written communication sent\n      to the Licensor or its representatives, including but not limited to\n      communication on electronic mailing lists, source code control systems,\n      and issue tracking systems that are managed by, or on behalf of, the\n      Licensor for the purpose of discussing and improving the Work, but\n      excluding communication that is conspicuously marked or otherwise\n      designated in writing by the copyright owner as \"Not a Contribution.\"\n\n      \"Contributor\" shall mean Licensor and any individual or Legal Entity\n      on behalf of whom a Contribution has been received by Licensor and\n      subsequently incorporated within the Work.\n\n    2. Grant of Copyright License. Subject to the terms and conditions of\n      this License, each Contributor hereby grants to You a perpetual,\n      worldwide, non-exclusive, no-charge, royalty-free, irrevocable\n      copyright license to reproduce, prepare Derivative Works of,\n      publicly display, publicly perform, sublicense, and distribute the\n      Work and such Derivative Works in Source or Object form.\n\n    3. Grant of Patent License. Subject to the terms and conditions of\n      this License, each Contributor hereby grants to You a perpetual,\n      worldwide, non-exclusive, no-charge, royalty-free, irrevocable\n      (except as stated in this section) patent license to make, have made,\n      use, offer to sell, sell, import, and otherwise transfer the Work,\n      where such license applies only to those patent claims licensable\n      by such Contributor that are necessarily infringed by their\n      Contribution(s) alone or by combination of their Contribution(s)\n      with the Work to which such Contribution(s) was submitted. If You\n      institute patent litigation against any entity (including a\n      cross-claim or counterclaim in a lawsuit) alleging that the Work\n      or a Contribution incorporated within the Work constitutes direct\n      or contributory patent infringement, then any patent licenses\n      granted to You under this License for that Work shall terminate\n      as of the date such litigation is filed.\n\n    4. Redistribution. You may reproduce and distribute copies of the\n      Work or Derivative Works thereof in any medium, with or without\n      modifications, and in Source or Object form, provided that You\n      meet the following conditions:\n\n      (a) You must give any other recipients of the Work or\n          Derivative Works a copy of this License; and\n\n      (b) You must cause any modified files to carry prominent notices\n          stating that You changed the files; and\n\n      (c) You must retain, in the Source form of any Derivative Works\n          that You distribute, all copyright, patent, trademark, and\n          attribution notices from the Source form of the Work,\n          excluding those notices that do not pertain to any part of\n          the Derivative Works; and\n\n      (d) If the Work includes a \"NOTICE\" text file as part of its\n          distribution, then any Derivative Works that You distribute must\n          include a readable copy of the attribution notices contained\n          within such NOTICE file, excluding those notices that do not\n          pertain to any part of the Derivative Works, in at least one\n          of the following places: within a NOTICE text file distributed\n          as part of the Derivative Works; within the Source form or\n          documentation, if provided along with the Derivative Works; or,\n          within a display generated by the Derivative Works, if and\n          wherever such third-party notices normally appear. The contents\n          of the NOTICE file are for informational purposes only and\n          do not modify the License. You may add Your own attribution\n          notices within Derivative Works that You distribute, alongside\n          or as an addendum to the NOTICE text from the Work, provided\n          that such additional attribution notices cannot be construed\n          as modifying the License.\n\n      You may add Your own copyright statement to Your modifications and\n      may provide additional or different license terms and conditions\n      for use, reproduction, or distribution of Your modifications, or\n      for any such Derivative Works as a whole, provided Your use,\n      reproduction, and distribution of the Work otherwise complies with\n      the conditions stated in this License.\n\n    5. Submission of Contributions. Unless You explicitly state otherwise,\n      any Contribution intentionally submitted for inclusion in the Work\n      by You to the Licensor shall be under the terms and conditions of\n      this License, without any additional terms or conditions.\n      Notwithstanding the above, nothing herein shall supersede or modify\n      the terms of any separate license agreement you may have executed\n      with Licensor regarding such Contributions.\n\n    6. Trademarks. This License does not grant permission to use the trade\n      names, trademarks, service marks, or product names of the Licensor,\n      except as required for reasonable and customary use in describing the\n      origin of the Work and reproducing the content of the NOTICE file.\n\n    7. Disclaimer of Warranty. Unless required by applicable law or\n      agreed to in writing, Licensor provides the Work (and each\n      Contributor provides its Contributions) on an \"AS IS\" BASIS,\n      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or\n      implied, including, without limitation, any warranties or conditions\n      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A\n      PARTICULAR PURPOSE. You are solely responsible for determining the\n      appropriateness of using or redistributing the Work and assume any\n      risks associated with Your exercise of permissions under this License.\n\n    8. Limitation of Liability. In no event and under no legal theory,\n      whether in tort (including negligence), contract, or otherwise,\n      unless required by applicable law (such as deliberate and grossly\n      negligent acts) or agreed to in writing, shall any Contributor be\n      liable to You for damages, including any direct, indirect, special,\n      incidental, or consequential damages of any character arising as a\n      result of this License or out of the use or inability to use the\n      Work (including but not limited to damages for loss of goodwill,\n      work stoppage, computer failure or malfunction, or any and all\n      other commercial damages or losses), even if such Contributor\n      has been advised of the possibility of such damages.\n\n    9. Accepting Warranty or Additional Liability. While redistributing\n      the Work or Derivative Works thereof, You may choose to offer,\n      and charge a fee for, acceptance of support, warranty, indemnity,\n      or other liability obligations and/or rights consistent with this\n      License. However, in accepting such obligations, You may act only\n      on Your own behalf and on Your sole responsibility, not on behalf\n      of any other Contributor, and only if You agree to indemnify,\n      defend, and hold each Contributor harmless for any liability\n      incurred by, or claims asserted against, such Contributor by reason\n      of your accepting any such warranty or additional liability.\n\n    END OF TERMS AND CONDITIONS\n\n    APPENDIX: How to apply the Apache License to your work.\n\n      To apply the Apache License to your work, attach the following\n      boilerplate notice, with the fields enclosed by brackets \"[]\"\n      replaced with your own identifying information. (Don't include\n      the brackets!)  The text should be enclosed in the appropriate\n      comment syntax for the file format. We also recommend that a\n      file or class name and description of purpose be included on the\n      same \"printed page\" as the copyright notice for easier\n      identification within third-party archives.\n\n    Copyright [yyyy] [name of copyright owner]\n\n    Licensed under the Apache License, Version 2.0 (the \"License\");\n    you may not use this file except in compliance with the License.\n    You may obtain a copy of the License at\n\n       http://www.apache.org/licenses/LICENSE-2.0\n\n    Unless required by applicable law or agreed to in writing, software\n    distributed under the License is distributed on an \"AS IS\" BASIS,\n    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.\n    See the License for the specific language governing permissions and\n    limitations under the License.\n\n\n---- LLVM Exceptions to the Apache 2.0 License ----\n\nAs an exception, if, as a result of your compiling your source code, portions\nof this Software are embedded into an Object form of such source code, you\nmay redistribute such embedded portions in such Object form without complying\nwith the conditions of Sections 4(a), 4(b) and 4(d) of the License.\n\nIn addition, if you combine or link compiled forms of this Software with\nsoftware that is licensed under the GPLv2 (\"Combined Software\") and if a\ncourt of competent jurisdiction determines that the patent provision (Section\n3), the indemnity provision (Section 9) or other Section of the License\nconflicts with the conditions of the GPLv2, you may retroactively and\nprospectively choose to deem waived or otherwise exclude such Section(s) of\nthe License, but only in their entirety and only with respect to the Combined\nSoftware."
OWNERS = tuple('apps/reader/' + path for path in (
    'revisions/CMakeLists.txt', 'revisions/EXReaderRevisionsConfig.cmake.in',
    'revisions/include/reader_selector_bytes_v1.h', 'revisions/src/selector_bytes_v1.cpp',
    'reading-state/CMakeLists.txt', 'reading-state/EXReaderReadingStateConfig.cmake.in',
    'reading-state/include/reader_reading_state_retained_raw_v1.h', 'reading-state/src/reading_state.cpp',
    'reading-commands/CMakeLists.txt', 'reading-commands/EXReaderReadingCommandsConfig.cmake.in',
    'reading-commands/src/reading_commands.cpp', 'annotation-import/CMakeLists.txt',
    'annotation-import/EXReaderAnnotationImportConfig.cmake.in', 'annotation-import/src/annotation_import.cpp',
    'annotation-export/CMakeLists.txt', 'annotation-export/EXReaderAnnotationExportConfig.cmake.in',
    'annotation-export/src/annotation_export.cpp'))
ADDED = tuple('tests/reader_public_boundary_v1_20261028/' + p for p in
              ('CMakeLists.txt', 'codec_v1.c', 'retained_v1.cpp', 'run.py', 'test_contract.py')) + (
    '.github/workflows/reader-public-boundary-v1-20261028.yml',
    'docs/reader-total-progress/reader-public-boundary-v1-20261028.md')
NEW_OWNER = {OWNERS[2], OWNERS[3], OWNERS[6]}
HOSTS = ('examples/android/app/src/main/cpp/wave3_product_jni.inc',)
TARGETS = ('linux', 'windows', 'android', 'macos', 'iphone', 'ipad')
EXPECTED_WIRES = {'wire-v1.json','wire-v2.json','wire-v3.json','wire-epub-0.json','wire-epub-1.json','wire-epub-2.json'}
EXCLUSIONS = ['tests/gtk_sdk342_package/run.py::guard', 'tests/android_sdk342_package/run.py::guard',
              'tests/reader_f06_packages/identity.py::guard', 'tests/reader_selector_bytes/run.py::main source/build orchestration',
              'tests/reader_next_c06/run.py::guards/main baseline build and historical Mac-record orchestration']


def need(value, message):
    if not value:
        raise AssertionError(message)


def actions():
    need(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only: no local execution')
    need(os.environ.get('GITHUB_REPOSITORY') == 'NoGod3524/EXReader', 'repository identity')


def identity():
    return dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'])


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def command(args, label=None, timeout=1800, expected=0, env=None, cwd=ROOT):
    args = list(map(str, args))
    print('RUN', shlex.join(args), flush=True)
    p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
    if label:
        folder = OUT / 'logs'; folder.mkdir(parents=True, exist_ok=True)
        (folder / (label+'.stdout.txt')).write_text(p.stdout, encoding='utf-8')
        (folder / (label+'.stderr.txt')).write_text(p.stderr, encoding='utf-8')
        save(folder / (label+'.command.json'), dict(argv=args, cwd=str(cwd), exit_code=p.returncode))
    print((p.stdout+p.stderr)[-8000:], flush=True)
    if expected is not None:
        need(p.returncode == expected, (label, args, p.returncode, expected))
    return p


def load(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    obj = importlib.util.module_from_spec(spec); spec.loader.exec_module(obj)
    return obj


def guard():
    actions()
    need(os.environ['GITHUB_REF'] == 'refs/heads/'+BRANCH, 'feature branch only')
    need(command(['git','rev-parse','HEAD']).stdout.strip() == os.environ['GITHUB_SHA'], 'source SHA')
    command(['git','merge-base','--is-ancestor',BASE,'HEAD'])
    changes = command(['git','diff','--name-status',BASE,'HEAD']).stdout.splitlines()
    actual = {line.split('\t')[1]:line.split('\t')[0] for line in changes}
    expected = {path:('A' if path in NEW_OWNER or path in ADDED else 'M') for path in (*OWNERS,*HOSTS,*ADDED)}
    need(actual == expected, ('exact authorized 25 paths', actual, expected))
    need(not command(['git','status','--porcelain','--untracked-files=no']).stdout.strip(), 'tracked source dirty')
    # Exact full old test/SDK source freeze follows from the 25-path equality;
    # explicit tree hashes remain easy to audit without trusting this statement.
    frozen = {}
    for path in ('src','include','cmake','CMakeLists.txt','bindings','tools','tests/fixtures',
                 'tests/reader_f06_packages','tests/reader_selector_bytes','tests/reader_gtk_raw_wave3',
                 'tests/gtk_sdk342_package','tests/android_sdk342_package','tests/sdk342_aggregate',
                 'tests/reader_wave3_c09','tests/reader_next_c06','tests/reader_reading_commands','tests/reader_annotation_export'):
        old = command(['git','rev-parse',BASE+':'+path]).stdout.strip()
        current = command(['git','rev-parse','HEAD:'+path]).stdout.strip()
        need(old == current, 'frozen path '+path); frozen[path] = current
    data = dict(identity(), base_sha=BASE, source_scope_passed=True, original_source_guards_excluded=EXCLUSIONS,
                frozen=frozen, authorized_paths_sha256={p:digest(ROOT/p) for p in (*OWNERS,*HOSTS,*ADDED)},
                f07_accepted=False, physical_device=False)
    save(OUT/'source.json', data); return data


def layout(target):
    if target == 'linux':
        return ROOT/'build/reading-library/stage', ROOT/'build/gtk-raw-wave3/raw-stage', ROOT/'build/gtk-raw-wave3/raw-stage', ROOT/'build/gtk-raw-wave3'
    if target == 'windows':
        base = ROOT/'build/f06/windows-build'
        return base/'sdk-stage', base/'raw-stage', base/'product-stage', base
    if target == 'android':
        base = ROOT/'build/wave3'
        return base/'sdk-stage', base/'stage', base/'stage', base
    base = ROOT/'build/f06'/('macos-build' if target == 'macos' else 'iphonesimulator-build')
    return base/'sdk', base/'product', base/'product', base


def build(target):
    guard()
    sdk, stage, product, base = layout(target)
    need(all(not prefix.exists() for prefix in set((sdk,stage,product))), 'fresh empty SDK/module/product producer prefixes required')
    (ROOT/'build/f06').mkdir(parents=True, exist_ok=True)
    if target == 'linux':
        load('tests/gtk_sdk342_package/run.py','boundary_gtk342').build()
    elif target == 'windows':
        builder = load('tests/reader_f06_packages/build.py','boundary_f06_build')
        original_module = builder.module
        def module(path, name):
            obj = original_module(path, name)
            if path == 'tests/reader_wave3_c09/build.py':
                original_run = obj.H.run
                def keep_rsp(args, label, *pos, **kw):
                    args = list(args)
                    if len(args)>1 and str(args[0])=='cmake' and str(args[1])=='--build':
                        args += ['--verbose','--','-d','keeprsp']
                    return original_run(args,label,*pos,**kw)
                obj.H.run = keep_rsp
            return obj
        builder.module = module
        payload = builder.windows()
        load('tests/reader_f06_packages/identity.py','boundary_f06_id').package('windows',payload)
    elif target == 'android':
        ndk_prebuild()
        load('tests/android_sdk342_package/run.py','boundary_android342').build()
    else:
        command([sys.executable,'tests/sdk342_aggregate/apple_f06.py',target], 'original-apple-f06', timeout=6000)
    need(not (stage/'include/reader_selector_bytes_detail.h').exists(), 'private header still installed')
    save(OUT/'build.json',dict(identity(),target=target, original_builder_passed=True, fresh_prefixes=True))


def cross_options(target, sdk, stage, product):
    options = ['-DCMAKE_BUILD_TYPE=Release','-DCMAKE_PREFIX_PATH='+ ';'.join(map(str,dict.fromkeys((stage,product,sdk)))),
               '-DEXR_SDK='+str(sdk),'-DEXR_SDK_VERSION=3.42.0']
    if target == 'android':
        options += ['-DCMAKE_TOOLCHAIN_FILE='+os.environ['C11_TOOLCHAIN'],'-DANDROID_ABI=x86_64',
                    '-DANDROID_PLATFORM=android-26','-DANDROID_STL=c++_static','-DCMAKE_POSITION_INDEPENDENT_CODE=ON',
                    '-DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=BOTH']
    if target in ('iphone','ipad'):
        options += ['-DCMAKE_SYSTEM_NAME=iOS','-DCMAKE_OSX_SYSROOT=iphonesimulator','-DCMAKE_OSX_ARCHITECTURES=arm64',
                    '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0','-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO']
    elif target == 'macos':
        options += ['-DCMAKE_OSX_DEPLOYMENT_TARGET=12.0']
    selected_packages=set()
    for prefix in dict.fromkeys((stage,product,sdk)):
        for folder in sorted((prefix/'lib/cmake').glob('*')):
            if folder.is_dir() and folder.name not in selected_packages:
                options += ['-D'+folder.name+'_DIR='+str(folder)];selected_packages.add(folder.name)
    return options


def configure_negatives(target, sdk, stage, product):
    results=[]
    source=OUT/'negative-source'; source.mkdir(parents=True,exist_ok=True)
    (source/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.24)\nproject(PublicGuard LANGUAGES C CXX)\nfind_package(EXReaderRevisions 0.4.0 EXACT CONFIG REQUIRED)\n')
    for case in ('valid','missing-header','wrong-version','comment-spoof','missing-capability','conflicting-capability','mixed-archive','stale-private','legacy-prefix','retained-header','retained-version','retained-capability','same-prefix-wrong-archive'):
        prefix=OUT/'negative-prefix'; shutil.rmtree(prefix,ignore_errors=True); shutil.copytree(stage,prefix)
        header=prefix/'include/reader_selector_bytes_v1.h'; config=prefix/'lib/cmake/EXReaderRevisions'
        targets=config/'EXReaderRevisionsTargets.cmake'
        if case=='missing-header': header.unlink()
        if case in ('wrong-version','comment-spoof'):
            header.write_text(header.read_text().replace('#define READER_REV_SELECTOR_BYTES_API_VERSION "1.0.0"','#define READER_REV_SELECTOR_BYTES_API_VERSION "9.0.0"') + ('\n/*\n#define READER_REV_SELECTOR_BYTES_API_VERSION "1.0.0"\n*/\n' if case=='comment-spoof' else ''))
        if case=='missing-capability': targets.write_text(targets.read_text().replace('EXR_READER_PUBLIC_SELECTOR_BYTES_V1=1',''))
        if case=='conflicting-capability': targets.write_text(targets.read_text().replace('EXR_READER_PUBLIC_SELECTOR_BYTES_V1=1','EXR_READER_PUBLIC_SELECTOR_BYTES_V1=1;EXR_READER_PUBLIC_SELECTOR_BYTES_V1=0'))
        if case=='same-prefix-wrong-archive':
            for path in config.glob('EXReaderRevisionsTargets-*.cmake'):
                path.write_text(path.read_text().replace('/libreader_revisions.a','/libreader_revision_hash.a').replace('/reader_revisions.lib','/reader_revision_hash.lib'))
        if case=='mixed-archive':
            locations=list(config.glob('EXReaderRevisionsTargets-*.cmake')); need(locations,'archive exports')
            for path in locations: path.write_text(path.read_text().replace('${_IMPORT_PREFIX}/lib/',str(stage/'lib')+'/'))
        if case=='stale-private': shutil.copyfile(ROOT/'apps/reader/revisions/include/reader_selector_bytes_detail.h',prefix/'include/reader_selector_bytes_detail.h')
        if case.startswith('retained-'):
            header=prefix/'include/reader_reading_state_retained_raw_v1.h'
            if case=='retained-header':header.unlink()
            elif case=='retained-version':header.write_text(header.read_text().replace('#define READER_RS_RETAINED_RAW_API_VERSION "1.0.0"','#define READER_RS_RETAINED_RAW_API_VERSION "9.0.0"'))
            else:
                state_targets=prefix/'lib/cmake/EXReaderReadingState/EXReaderReadingStateTargets.cmake'
                state_targets.write_text(state_targets.read_text().replace('EXR_READER_PUBLIC_RETAINED_RAW_V1=1','EXR_READER_PUBLIC_RETAINED_RAW_V1=0'))
        package='EXReaderReadingCommands 0.2.0' if case.startswith('retained-') else 'EXReaderRevisions 0.4.0'
        (source/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.24)\nproject(PublicGuard LANGUAGES C CXX)\nfind_package('+package+' EXACT CONFIG REQUIRED)\n')
        selected=OUT/'legacy-stage' if case=='legacy-prefix' else prefix
        options=cross_options(target,sdk,selected,prefix if product==stage else product)
        p=command(['cmake','-S',source,'-B',OUT/('negative-'+case),'-G','Ninja',*options], 'negative-'+case, expected=None)
        need((p.returncode==0)==(case=='valid'), ('guard outcome',case,p.returncode))
        results.append(dict(case=case,expected_success=case=='valid',exit_code=p.returncode,passed=True))
    shutil.rmtree(OUT/'negative-prefix')
    return results


def snapshot(folder):
    folder=Path(folder);need(folder.is_dir(),'snapshot root missing')
    files={};directories=[]
    for path in sorted(folder.rglob('*')):
        need(not path.is_symlink(),'native snapshot may not contain aliases')
        relative=path.relative_to(folder).as_posix();need(safe_member(relative),'unsafe native snapshot name')
        if path.is_file():files[relative]=digest(path)
        elif path.is_dir():directories.append(relative)
        else:need(False,'special native snapshot entry')
    return dict(files=files,directories=sorted(directories))


def exact_copy(source,destination):
    """Own test trees only. Replacement includes absence/deletions, never merge."""
    source,destination=Path(source),Path(destination)
    before=snapshot(source)
    temporary=destination.with_name(destination.name+'.incoming')
    need(not temporary.exists(),'stale snapshot staging directory')
    temporary.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(source,temporary)
    need(snapshot(temporary)==before and snapshot(source)==before,'copy snapshot changed')
    if destination.exists():shutil.rmtree(destination)
    temporary.rename(destination)
    need(snapshot(destination)==before,'installed snapshot mismatch')
    return before


class Native:
    def __init__(self,target,programs,data):
        self.target,self.programs,self.data=target,programs,data
        self.udid=None;self.devices={};self.remote='/data/local/tmp/exr-public-boundary-v1-'+os.environ['GITHUB_RUN_ID']+'-'+os.environ['GITHUB_RUN_ATTEMPT']
        self.env=dict(os.environ,SELECTOR_TXT_SHA=hashlib.sha256(b'A real public SDK text capture has enough context for stable matching.').hexdigest(),
                      C06_TXT_SHA=hashlib.sha256(b'A real public SDK text capture has enough context for stable matching.').hexdigest(),
                      BOUNDARY_TXT_SHA=digest(data/'fixtures/book.txt'),BOUNDARY_EPUB_SHA=digest(data/'fixtures/book.epub'),BOUNDARY_PDF_SHA=digest(data/'pdf.pdf'))
        try:
            self.prepare(target,programs)
        except BaseException:
            try:self.close()
            except Exception as cleanup:print('Native setup cleanup failed:',repr(cleanup),flush=True)
            raise
    def prepare(self,target,programs):
        if target=='android':
            command(['adb','shell','mkdir','-p',self.remote])
            for name,path in programs.items(): command(['adb','push',path,self.remote+'/'+name])
            command(['adb','shell','chmod','755',*[self.remote+'/'+n for n in programs]])
        elif target in ('iphone','ipad'):
            inventory=json.loads(command(['xcrun','simctl','list','runtimes','available','--json']).stdout)
            runtimes=sorted((r for r in inventory['runtimes'] if r.get('platform')=='iOS'),key=lambda r:tuple(map(int,r['version'].split('.'))))
            need(runtimes,'iOS runtime unavailable');runtime=runtimes[-1]
            family='iPhone' if target=='iphone' else 'iPad'
            device_type=next(d['identifier'] for d in runtime['supportedDeviceTypes'] if d.get('productFamily')==family)
            self.udid=command(['xcrun','simctl','create','exr-boundary-'+os.environ['GITHUB_RUN_ID']+'-'+target,device_type,runtime['identifier']]).stdout.strip()
            self.devices=dict(udid=self.udid,runtime=runtime['identifier'],device_type=device_type,fresh=True)
            command(['xcrun','simctl','bootstatus',self.udid,'-b'],timeout=600)
            for name,path in programs.items():
                bundle=OUT/(name+'.app');bundle.mkdir(exist_ok=True)
                shutil.copyfile(path,bundle/name);(bundle/name).chmod(0o755)
                bundleid='org.exreader.publicboundary.'+name
                (bundle/'Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier=bundleid,CFBundleExecutable=name,CFBundlePackageType='APPL',CFBundleVersion='1',CFBundleShortVersionString='1.0',MinimumOSVersion='15.0',UIDeviceFamily=[1,2])))
                command(['codesign','--force','--sign','-',bundle],name+'-sign')
                command(['xcrun','simctl','install',self.udid,bundle],name+'-install')
                installed=command(['xcrun','simctl','get_app_container',self.udid,bundleid,'app']).stdout.strip()
                container=command(['xcrun','simctl','get_app_container',self.udid,bundleid,'data']).stdout.strip()
                self.programs[name]=(Path(installed)/name,Path(container)/'Documents/boundary-data')
    def android_snapshot(self,folder):
        def shell(script):return command(['adb','shell',script],timeout=180).stdout
        base='cd '+shlex.quote(folder)+' && '
        need(not shell(base+'find . ! -type f ! -type d').strip(),'Android snapshot special entry or symlink')
        files={}
        for line in shell(base+'find . -type f -exec sha256sum {} \\;').splitlines():
            match=re.fullmatch(r'([0-9a-f]{64})  \./(.+)',line)
            need(match is not None,'Android hash inventory format')
            sha,name=match.groups();need(safe_member(name) and name not in files,'Android duplicate/unsafe file')
            files[name]=sha
        directories=[]
        for line in shell(base+'find . -type d').splitlines():
            if line=='.':continue
            need(line.startswith('./') and safe_member(line[2:]),'Android directory inventory')
            directories.append(line[2:])
        return dict(files=files,directories=sorted(directories))
    def run(self,name,args=(),label=None,timeout=180):
        args=list(map(str,args));label=(self.target+'-'+(label or name))
        keys=('SELECTOR_TXT_SHA','C06_TXT_SHA','BOUNDARY_TXT_SHA','BOUNDARY_EPUB_SHA','BOUNDARY_PDF_SHA')
        if self.target=='android':
            remote_data=self.remote+'/'+self.data.name
            command(['adb','shell','rm','-rf',remote_data],label+'-clear-owned-snapshot')
            before=snapshot(self.data)
            command(['adb','push',str(self.data),self.remote+'/'],label+'-push',timeout=180)
            need(self.android_snapshot(remote_data)==before,'Android input snapshot differs')
            translated=[a.replace(str(self.data),remote_data) for a in args]
            variables=[key+'='+self.env[key] for key in keys]
            p=command(['adb','shell',shlex.join(['env',*variables,self.remote+'/'+name,*translated])],label,timeout,expected=None)
            after=self.android_snapshot(remote_data)
            incoming=self.data.with_name(self.data.name+'.pulled');need(not incoming.exists(),'stale Android receive')
            incoming.mkdir()
            command(['adb','pull',remote_data+'/.',incoming],label+'-pull',timeout=180)
            need(snapshot(incoming)==after and self.android_snapshot(remote_data)==after,'Android output snapshot differs/changed')
            exact_copy(incoming,self.data);shutil.rmtree(incoming)
        elif self.udid:
            program,destination=self.programs[name]
            exact_copy(self.data,destination)
            translated=[a.replace(str(self.data),str(destination)) for a in args]
            variables=['SIMCTL_CHILD_'+key+'='+self.env[key] for key in keys]
            p=command(['env',*variables,'xcrun','simctl','spawn',self.udid,program,*translated],label,timeout,expected=None)
            exact_copy(destination,self.data)
        else:
            p=command([self.programs[name],*args],label,timeout,expected=None,env=self.env)
        need(p.returncode==0,(label,p.returncode));return p.stdout
    def close(self):
        if self.udid:
            errors=[]
            for action in ('shutdown','delete'):
                try:command(['xcrun','simctl',action,self.udid],expected=None)
                except Exception as error:errors.append(repr(error))
            need(not errors,('owned simulator cleanup',errors))


def built_program(folder,name,target):
    path=Path(folder)/(name+'.app')/name if target in ('iphone','ipad') else Path(folder)/(name+('.exe' if target=='windows' else ''))
    need(path.is_file(),'actual configured native program missing: '+str(path))
    return path


def native(target):
    actions();sdk,stage,product,base=layout(target)
    builddir=OUT/'native-build';options=cross_options(target,sdk,stage,product)
    command(['cmake','-S',HERE,'-B',builddir,'-G','Ninja',*options],target+'-native-configure')
    command(['cmake','--build',builddir,'--parallel','4','--verbose','--','-d','keeprsp'],target+'-native-build')
    names=('public-codec-v1','public-retained-v1','original-selector-bytes','original-c06')
    programs={name:built_program(builddir,name,target) for name in names}
    legacy=OUT/'legacy-stage'
    need(not legacy.exists(),'fresh empty legacy-OFF prefix required')
    for module in ('revisions','reading-state','annotation-import','annotation-export'):
        folder=OUT/('legacy-'+module)
        legacy_options=cross_options(target,sdk,legacy,product)
        legacy_options+=['-DCMAKE_INSTALL_PREFIX='+str(legacy),'-DREADER_PRODUCT_PREFIX='+str(product),'-DEXR_READER_SELECTOR_BYTES_CANDIDATE=OFF']
        if module=='annotation-import':legacy_options+=['-DREADER_ANNOTATION_IMPORT_BUILD=ON']
        command(['cmake','-S',ROOT/'apps/reader'/module,'-B',folder,'-G','Ninja',*legacy_options],target+'-legacy-'+module+'-configure')
        command(['cmake','--build',folder,'--parallel','4'],target+'-legacy-'+module+'-build')
        command(['cmake','--install',folder],target+'-legacy-'+module+'-install')
    legacy_build=OUT/'legacy-c06'
    command(['cmake','-S',ROOT/'tests/reader_next_c06/consumer','-B',legacy_build,'-G','Ninja','-DC06_RAW=OFF',*cross_options(target,sdk,legacy,product)],target+'-legacy-c06-configure')
    command(['cmake','--build',legacy_build,'--parallel','4'],target+'-legacy-c06-build')
    programs['original-c06-legacy']=built_program(legacy_build,'c06-probe',target)
    need(not (legacy/'include/reader_selector_bytes_v1.h').exists() and not (legacy/'include/reader_reading_state_retained_raw_v1.h').exists(),'raw API leaked into OFF install')
    data=OUT/'native-data';data.mkdir(exist_ok=True)
    command([sys.executable,'tests/reader_reading_state/make_fixtures.py',data/'fixtures'],target+'-fixtures')
    shutil.copyfile(ROOT/'tests/fixtures/pdf-public-text.pdf',data/'pdf.pdf')
    shutil.copyfile(ROOT/'tests/fixtures/fonts/primary.ttf',data/'font.ttf')
    targets=('iphone','ipad') if target=='iphone' else (target,)
    reports=[]
    for entry in targets:
        runner=Native(entry,dict(programs),data)
        report=dict(identity(),target=entry,passed=False,f07_accepted=False,physical_device=False)
        try:
            codec=runner.run('public-codec-v1')
            retained=runner.run('public-retained-v1',[data/'fixtures',data/'pdf.pdf',data/'font.ttf',data/(entry+'-retained')])
            need('passed=true' in codec and 'passed=true' in retained,'native success markers')
            work=data/(entry+'-original');probe=programs['original-selector-bytes']
            for phase in ('legacy','seed','receive','reopen','nullable','versions'):
                runner.run('original-selector-bytes',[phase,data/'pdf.pdf',work],phase,timeout=180)
            original=load('tests/reader_selector_bytes/run.py','boundary_original_selector')
            def invoke(args,name=None,timeout=180):
                need(str(args[0])==str(probe),'only original consumer invocation')
                return runner.run('original-selector-bytes',args[1:],name,timeout)
            original.run=invoke
            report['original_protocol']=original.protocol(probe,work)
            report['original_graph']=original.graph_cases(probe,work)
            portable=load('tests/reader_next_c06/run.py','boundary_original_c06')
            c06=data/(entry+'-c06');c06.mkdir()
            def original_probe(exe,*args,label=None):
                which='original-c06' if str(exe)==str(programs['original-c06']) else 'original-c06-legacy'
                need(str(exe) in (str(programs['original-c06']),str(programs['original-c06-legacy'])),'original C06 executable')
                output=runner.run(which,args,'c06-'+(label or which),900)
                return portable.Result(subprocess.CompletedProcess([str(exe),*map(str,args)],0,output))
            portable.probe=original_probe
            off=portable.legacy_phase('off',programs['original-c06-legacy'],c06/'legacy-off')
            raw=portable.legacy_phase('raw',programs['original-c06'],c06/'legacy-raw')
            need(off==raw,'unchanged C06 legacy wire output parity')
            portable.raw_phase(programs['original-c06'],programs['original-c06-legacy'],data/'pdf.pdf',c06/'raw')
            need(not portable.FAILED,'original C06 assertions failed')
            report['original_c06_checks']=portable.CHECKS
            retained_wires={p.name:digest(p) for p in (data/(entry+'-retained')).glob('wire-*.json')}
            need(set(retained_wires)==EXPECTED_WIRES,'exact nonempty retained wire inventory')
            report.update(passed=True,native_device=runner.devices,program_sha256={n:digest(p) for n,p in programs.items()},
                          retained_wires=retained_wires,
                          pure_capture_selected=(stage/'include/reader_reading_state_capture_raw_candidate.h').exists())
        finally:
            runner.close();save(OUT/('native-'+entry+'.json'),report)
        reports.append(report)
    # All negative config fixtures use copied prefixes, never modify producer bytes.
    negatives=configure_negatives(target,sdk,stage,product)
    save(OUT/'native.json',dict(identity(),target=target,passed=True,entries=reports,configuration_controls=negatives))


def symbol_present(text, symbol, defined, windows=False):
    """Only the named public C function, not prefixes or arbitrary weak imports."""
    for line in text.splitlines():
        if windows:
            match=re.fullmatch(r'\s*[0-9A-Fa-f]+\s+([0-9A-Fa-f]{8,16})\s+(UNDEF|SECT[0-9A-Fa-f]+)\s+notype\s+\(\)\s+External\s+\|\s+'+re.escape(symbol)+r'\s*',line)
            if match:
                value,section=match.groups()
                if defined and section.startswith('SECT'):return True
                if not defined and section=='UNDEF' and int(value,16)==0:return True
        elif re.search(r'\s'+('T' if defined else 'U')+r'\s+_?'+re.escape(symbol)+r'$',line):
            return True
    return False


def ninja_dependency_groups(text):
    groups={};current=None
    for line in text.splitlines():
        if not line or line.startswith("ninja: Entering directory "):continue
        match=re.fullmatch(r'(.+): #deps (\d+), deps mtime \d+ \((VALID|STALE)\)',line)
        if match:
            name,count,status=match.groups();need(name not in groups,'duplicate dependency object')
            current=dict(declared_count=int(count),status=status,paths=[]);groups[name]=current
        else:
            need(current is not None and line.startswith('    ') and line[4:],'malformed/truncated Ninja dependency group')
            current['paths'].append(line[4:])
    need(groups,'no actual Ninja dependency groups')
    for name,group in groups.items():
        need(len(group['paths'])==group['declared_count']>0,('Ninja dependency count mismatch',name))
    return groups


def make_dependency_group(text):
    need(text.endswith('\n') and not text.endswith('\\\n'),'unterminated Make depfile')
    joined=text.replace('\\\n',' ')
    match=re.fullmatch(r'([^\n]+?\.(?:o|obj)):[ \t]*(.+)\n',joined,re.S)
    need(match is not None,'one complete object depfile rule required')
    name,body=match.groups();need('\n' not in body,'unexpected second Make rule')
    tokens=re.findall(r'(?:\\.|[^\\ \t\r\n])+',body)
    paths=[re.sub(r'\\(.)',r'\1',token) for token in tokens]
    need(paths,'empty Make dependency list')
    return {name:dict(paths=paths,status='VALID',declared_count=len(paths))}


def ninja_explicit_inputs(text,node,rule_prefix):
    lines=text.splitlines()
    if lines and lines[0].startswith("ninja: Entering directory "):lines=lines[1:]
    need(len(lines)>=3 and lines[0]==node+':' and lines[1].startswith('  input: '+rule_prefix),'exact Ninja node/rule binding')
    need(lines.count('  outputs:')==1,'complete Ninja query output section')
    end=lines.index('  outputs:');inputs=[]
    for line in lines[2:end]:
        need(line.startswith('    ') and line[4:],'malformed Ninja query input')
        if not line[4:].startswith('|'):inputs.append(line[4:])
    outputs=lines[end+1:]
    need(all(line.startswith('    ') and line[4:] for line in outputs),'malformed Ninja query output')
    return inputs,[line[4:] for line in outputs]


def owned_dependency_proof(source,graph_objects,groups,folder,required_headers,graph_sources=None):
    def normal(path):return os.path.normcase(str((folder/Path(path)).resolve()))
    expected=normal(source);linked={normal(p) for p in graph_objects}
    matches=[]
    for obj,group in groups.items():
        paths=[normal(p) for p in group['paths']]
        graph_source=graph_sources.get(obj) if graph_sources is not None else None
        source_bound=normal(graph_source)==expected if graph_source is not None else expected in paths
        if graph_sources is not None:source_bound=graph_source is not None and source_bound
        if source_bound and normal(obj) in linked:
            matches.append((obj,group,paths))
    need(len(matches)==1,'exact source/linked archive object dependency binding missing or ambiguous')
    obj,group,paths=matches[0]
    need(group['status']=='VALID' and paths.count(expected)<2,'stale or ambiguous source dependency')
    need(graph_sources is not None or paths.count(expected)==1,'source dependency missing')
    need(not any(Path(p).name=='reader_selector_bytes_detail.h' for p in paths),'private selector implementation dependency remains')
    for header in required_headers:need(normal(header) in paths,'installed public dependency missing: '+str(header))
    return dict(source=source,archive_object=obj,actual_compiler_dependency_seen=True,
                source_binding='exact Ninja compiler input and archive object' if graph_sources is not None else 'compiler depfile source and archive object',
                dependency_count=len(paths),required_public_headers=list(map(str,required_headers)),
                private_selector_header_absent=True)


def lld_rows(text):
    rows=[]
    for line in text.splitlines():
        if not line.strip():continue
        if line.split()==['VMA','LMA','Size','Align','Out','In','Symbol']:continue
        columns=line.split(None,4)
        need(len(columns)==5 and all(re.fullmatch(r'[0-9a-fA-F]+',c) for c in columns[:4]),'unparsed LLD map row')
        rows.append((int(columns[0],16),int(columns[2],16),columns[4].strip()))
    need(rows,'empty LLD map');return rows


def lld_symbol_origin(text,symbol):
    current=None;found=[]
    for address,size,value in lld_rows(text):
        if ':(' in value:
            origin=re.fullmatch(r'(.+):\([^\n]*\)',value)
            need(origin is not None,'unrecognized LLD input contribution');current=(origin[1],address,address+size)
        elif value.startswith('.'):current=None
        elif value==symbol:
            need(current is not None,'named symbol has no actual LLD contribution')
            need(current[1]<=address<current[2],'named symbol outside selected LLD contribution')
            found.append((current[0],address))
    need(len(found)==1,'named LLD definition missing/duplicated')
    return found[0]


def android_link_binding(text,image,folder):
    matches=[]
    for line in text.splitlines():
        args=shlex.split(line)
        outputs=[args[i+1] for i,arg in enumerate(args[:-1]) if arg=='-o']
        if any((folder/p).resolve()==image.resolve() for p in outputs):matches.append((line,args,outputs))
    need(len(matches)==1,'unique actual product link command missing/ambiguous')
    line,args,outputs=matches[0]
    need(len(outputs)==1 and not any('@' in a for a in args),'unsupported product link output/response form')
    maps=[a[len('-Wl,-Map,'):] for a in args if a.startswith('-Wl,-Map,')]
    need(len(maps)==1 and maps[0] and ',' not in maps[0],'exact actual linker map option missing/ambiguous')
    return (folder/maps[0]).resolve(),line


def android_caller_proof(folder,home,stage,deps,copy):
    symbol='reader_rs_encode_retained_raw_v1'
    query=command(['ninja','-C',folder,'-t','query','exreader_product'],'android-product-alias').stdout
    image_inputs,_=ninja_explicit_inputs(query,'exreader_product','phony')
    need(len(image_inputs)==1,'unique product link output required');image_name=image_inputs[0]
    image=(folder/image_name).resolve();need(image.is_file() and image.name=='libexreader_product.so','actual product ELF missing')
    query=command(['ninja','-C',folder,'-t','query',image_name],'android-product-link-input').stdout
    objects,_=ninja_explicit_inputs(query,image_name,'CXX_SHARED_LIBRARY_LINKER')
    objects=[p for p in objects if p.endswith('.o')];need(objects,'actual product link objects missing')
    sources={}
    for index,obj in enumerate(objects):
        query=command(['ninja','-C',folder,'-t','query',obj],'android-product-compiler-'+str(index)).stdout
        inputs,outputs=ninja_explicit_inputs(query,obj,'CXX_COMPILER')
        need(len(inputs)==1 and inputs[0].endswith('.cpp') and image_name in outputs,'exact Android compiler/link edge')
        sources[obj]=inputs[0]
    proof=owned_dependency_proof(str(home/'catalog_jni.cpp'),objects,ninja_dependency_groups(deps),folder,
        [ROOT/HOSTS[0],stage/'include/reader_reading_state_retained_raw_v1.h'],sources)
    obj=folder/proof['archive_object'];need(obj.is_file(),'actual Android caller object missing');copy(obj);copy(image)
    nm=Path(os.environ['ANDROID_HOME'])/'ndk'/os.environ['C11_NDK']/'toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-nm'
    object_symbols=command([nm,'-A',obj],'android-caller-symbols').stdout
    need(symbol_present(object_symbols,symbol,False),'Android caller must import public retained entry')
    need('reader_rs_encode_retained_raw_v3' not in object_symbols,'Android private retained import remains')
    commands=command(['ninja','-C',folder,'-t','commands',image_name],'android-product-exact-link-command').stdout
    mapfile,link_command=android_link_binding(commands,image,folder)
    need(mapfile.is_file() and mapfile.is_relative_to(ROOT),'actual Android product link map missing/escaping');copy(mapfile)
    provider,address=lld_symbol_origin(mapfile.read_text(),symbol)
    archive=stage/'lib/libreader_reading_state_codec.a';member='reading_state.cpp.o'
    need(provider==str(archive)+'('+member+')','named Android symbol mapped to wrong installed archive/member')
    owner_symbols=command([nm,'-A',archive],'android-retained-provider-symbols').stdout
    prefix=r'(?:'+re.escape(str(archive))+':'+re.escape(member)+r':|'+re.escape(str(archive)+'('+member+'):')+r')'
    need(len(re.findall(r'^'+prefix+r'\s+[0-9a-fA-F]+\s+T\s+'+symbol+r'$',owner_symbols,re.M))==1,'exact mapped archive member must define retained symbol')
    final_symbols=command([nm,'-A',image],'android-product-final-symbols').stdout
    addresses=re.findall(r'^'+re.escape(str(image))+r':\s+([0-9a-fA-F]+)\s+[Tt]\s+'+symbol+r'$',final_symbols,re.M)
    need(len(addresses)==1 and int(addresses[0],16)==address,'final ELF named symbol differs from map definition')
    need('reader_rs_encode_retained_raw_v3' not in final_symbols,'final Android image retains private entry')
    proof.update(caller_object_sha256=digest(obj),final_link_image=str(image.relative_to(ROOT)),final_link_image_sha256=digest(image),
                 installed_provider=str(archive.relative_to(ROOT)),installed_provider_sha256=digest(archive),map_sha256=digest(mapfile),
                 public_import=symbol,provider_member=member,final_symbol_address=address,actual_link_command=link_command)
    return proof


def ndk_file_record(root,path):
    root,path=Path(root).absolute(),Path(path).absolute()
    need(path.is_relative_to(root) and '..' not in path.parts,'external input outside exact NDK root')
    resolved=path.resolve();need(resolved.is_relative_to(root.resolve()) and path.is_file(),'NDK input missing or escaping alias')
    return dict(path=path.relative_to(root).as_posix(),resolved=resolved.relative_to(root.resolve()).as_posix(),
                bytes=path.stat().st_size,sha256=digest(path),symlink=os.readlink(path) if path.is_symlink() else None)


def ndk_prebuild():
    root=Path(os.environ['ANDROID_HOME'])/'ndk'/os.environ['C11_NDK'];toolroot=root/'toolchains/llvm/prebuilt/linux-x86_64'
    report=dict(identity(),root=str(root),revision=os.environ['C11_NDK'],api=26,abi='x86_64',complete=False,tools={},inputs={},notices={})
    try:
        properties=(root/'source.properties').read_text();need(re.search(r'^Pkg.Revision\s*=\s*27\.0\.12077973\s*$',properties,re.M),'actual NDK revision mismatch')
        report['source_properties']=properties
        for name in ('clang','clang++','ld.lld','llvm-ar','llvm-nm','llvm-readelf','llvm-strip'):
            report['tools'][name]=ndk_file_record(root,toolroot/'bin'/name)
        for name in ('meta/abis.json','meta/platforms.json','meta/system_libs.json'):
            report[name]=dict(record=ndk_file_record(root,root/name),contents=(root/name).read_text())
        for path in sorted(root.iterdir()):
            if path.is_file() and (path.name.startswith('NOTICE') or path.name.startswith('LICENSE')):
                report['notices'][path.name]=ndk_file_record(root,path)
                into=OUT/'logs/ndk-notices'/path.name;into.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,into)
                need(digest(into)==report['notices'][path.name]['sha256'],'pre-build retained notice bytes differ')
        candidates=list((toolroot/'sysroot/usr/lib/x86_64-linux-android').rglob('*'))
        for runtime in (toolroot/'lib/clang').glob('*/lib/linux'):
            candidates+=list(runtime.glob('*x86_64*'));candidates+=list((runtime/'x86_64').rglob('*'))
        for path in sorted(set(candidates)):
            if path.is_file() and path.suffix in ('.a','.o','.so'):
                record=ndk_file_record(root,path);report['inputs'][record['path']]=record
        need(report['inputs'],'bounded NDK x86_64 input inventory empty')
        ninjas={str(Path(p).absolute()) for p in [shutil.which('ninja'),*(str(p) for p in (Path(os.environ['ANDROID_HOME'])/'cmake').glob('*/bin/ninja'))] if p}
        report['ninja_tools']={p:dict(sha256=digest(p),resolved=str(Path(p).resolve())) for p in sorted(ninjas)}
        report['complete']=True
    finally:save(OUT/'ndk-before.json',report)


def selected_ndk_record(before,path):
    root=Path(before['root']);post=ndk_file_record(root,path);pre=before['inputs'].get(post['path'])
    need(pre is not None and pre==post,'selected NDK input missing before build or changed afterward')
    return post


def llvm_runtime_notice_coverage(record,notices):
    # Redistribution gate only, NOT a provider/selection allowlist. Every actual
    # map origin is inventoried; unknown license coverage remains an explicit gap.
    relative=record['path']
    if record['resolved']!=relative or record['symlink'] is not None:return False
    known=(re.fullmatch(r'toolchains/llvm/prebuilt/linux-x86_64/lib/clang/[^/]+/lib/linux/libclang_rt\.builtins-x86_64-android\.a',relative)
           or re.fullmatch(r'toolchains/llvm/prebuilt/linux-x86_64/lib/clang/[^/]+/lib/linux/x86_64/libunwind\.a',relative)
           or relative in ('toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/x86_64-linux-android/libc++_static.a',
                           'toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/x86_64-linux-android/libc++abi.a'))
    text=notices.get('NOTICE.toolchain','')
    return bool(known and notices.get('NOTICE','') and ' '.join(LLVM_LICENSE_BLOCK.split()) in ' '.join(text.split()))


def ndk_driver_binding(command_text,cache_text,before):
    args=shlex.split(command_text)
    if args[:2]==[':','&&']:args=args[2:]
    need(args and args[0] not in ('env','cd'),'unsupported driver command form')
    root=Path(before['root']);driver=Path(args[0]);name=driver.name
    need(name in ('clang','clang++') and driver==root/'toolchains/llvm/prebuilt/linux-x86_64/bin'/name,'selected linker driver is not recorded NDK clang')
    key='CMAKE_CXX_COMPILER' if name=='clang++' else 'CMAKE_C_COMPILER'
    configured=re.findall(r'^'+key+r':[A-Z_]+=(.+)$',cache_text,re.M)
    need(configured==[str(driver)],'selected driver differs from actual configured compiler')
    need(ndk_file_record(root,driver)==before['tools'][name],'selected driver differs from pre-build bytes')
    need(not any(a in ('-target','--target','--sysroot','-isysroot','-Xclang','--') or a.startswith(('-target=','-isysroot=')) for a in args),
         'unsupported driver target/sysroot override form')
    targets=[a[len('--target='):] for a in args if a.startswith('--target=')]
    sysroots=[a[len('--sysroot='):] for a in args if a.startswith('--sysroot=')]
    need(targets==['x86_64-none-linux-android26'],'actual driver target/API mismatch')
    expected=root/'toolchains/llvm/prebuilt/linux-x86_64/sysroot'
    need(sysroots==[str(expected)],'actual driver sysroot mismatch')
    return dict(driver=before['tools'][name],target=targets[0],sysroot=sysroots[0])


def validate_archive_members(magic,listing,selected):
    need(magic==b'!<arch>\n','thin/unsupported selected archive')
    need(listing and len(listing)==len(set(listing)) and all(safe_member(m) for m in listing),'empty/duplicate/unsafe archive members')
    need(None not in selected and all(m in listing for m in selected),'map-selected archive member absent')


def require_prebuild_identity(before):
    need(before['complete'] and all(before.get(k)==v for k,v in identity().items()),'NDK pre-build source/run/attempt mismatch')


def ndk_capture(destination,files,copy):
    result=dict(identity(),complete=False,external_map_inputs=[],images=[],gaps=[],f07_accepted=False,
                scope='map-selected inputs of the actual mapped .cxx images listed here, requiring host and product',
                excluded_scope=['unlisted APK native SDK/JNI images','all link operands beyond mapped contributions','DT_NEEDED/public-provider audit'])
    try:
        before=json.loads((OUT/'ndk-before.json').read_text())
        require_prebuild_identity(before)
        root=Path(before['root']);toolroot=root/'toolchains/llvm/prebuilt/linux-x86_64'
        for name,record in before['tools'].items():need(ndk_file_record(root,toolroot/'bin'/name)==record,'NDK tool changed across producer')
        notices={}
        for name,record in before['notices'].items():
            need(ndk_file_record(root,root/name)==record,'NDK notice changed across producer')
            retained=OUT/'logs/ndk-notices'/name;need(retained.is_file() and digest(retained)==record['sha256'],'retained notice copy missing/changed')
            notices[name]=retained.read_text()
        result['notice_records']=before['notices'];result['prebuild_sha256']=digest(OUT/'ndk-before.json')
        member_cache={};copied=set();canonical={}
        for cache in (ROOT/'examples/android/app/.cxx').rglob('CMakeCache.txt'):
            folder=cache.parent;text=cache.read_text();copy(cache)
            home=re.findall(r'^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$',text,re.M)
            if home!=[str(ROOT/'examples/android/app/src/main/cpp')]:continue
            ninja_paths=re.findall(r'^CMAKE_MAKE_PROGRAM:FILEPATH=(.+)$',text,re.M);need(len(ninja_paths)==1,'actual Ninja path missing')
            ninja=Path(ninja_paths[0]);need(before['ninja_tools'].get(str(ninja))==dict(sha256=digest(ninja),resolved=str(ninja.resolve())),'actual Ninja not pinned before producer')
            label='ndk-'+folder.relative_to(ROOT).as_posix().replace('/','_')
            commands=command([ninja,'-C',folder,'-t','commands'],label+'-commands').stdout
            command([ninja,'-C',folder,'-t','deps'],label+'-deps')
            for path in folder.rglob('*'):
                if path.is_file() and (path.name in ('build.ninja','rules.ninja','.ninja_deps','.ninja_log') or path.suffix=='.rsp'):copy(path)
            images={}
            for line in commands.splitlines():
                args=shlex.split(line)
                if '-shared' not in args or not any(a.startswith('-Wl,-Map,') for a in args):continue
                outputs=[args[i+1] for i,a in enumerate(args[:-1]) if a=='-o'];need(len(outputs)==1,'mapped shared link output ambiguous')
                image=(folder/outputs[0]).resolve();mapfile,actual=android_link_binding(commands,image,folder)
                driver_binding=ndk_driver_binding(actual,text,before)
                need(image.is_relative_to(ROOT) and mapfile.is_relative_to(ROOT),'linked image/map escapes workspace')
                need(image.name not in images,'duplicate mapped Android image');images[image.name]=True;copy(image);copy(mapfile)
                image_record=dict(image=str(image.relative_to(ROOT)),image_sha256=digest(image),map=str(mapfile.relative_to(ROOT)),map_sha256=digest(mapfile),command=actual,driver_binding=driver_binding,contributors=[])
                result['images'].append(image_record)
                selected={};workspace_inputs={}
                for address,size,value in lld_rows(mapfile.read_text()):
                    if ':(' not in value:continue
                    origin=re.fullmatch(r'(.+):\([^\n]*\)',value);need(origin is not None,'unparsed map contribution')
                    name=origin[1]
                    if name=='<internal>':continue
                    archive=re.fullmatch(r'(.+\.a)\(([^()]+)\)',name)
                    path_name,member=(archive[1],archive[2]) if archive else (name,None)
                    path=Path(path_name) if Path(path_name).is_absolute() else folder/path_name
                    need('..' not in path.parts,'map input traversal requires explicit diagnosis')
                    if path.is_relative_to(ROOT):
                        need(path.is_file() and path.resolve().is_relative_to(ROOT),'workspace map input missing/escaping')
                        workspace_inputs.setdefault(str(path),set()).add(member);continue
                    if not path.is_relative_to(root):result['gaps'].append('unknown external origin '+name);continue
                    selected.setdefault(str(path),set()).add(member)
                for path_name,members in workspace_inputs.items():
                    path=Path(path_name);copy(path)
                    image_record['contributors'].append(dict(path=str(path.relative_to(ROOT)),members=sorted(m for m in members if m),sha256=digest(path)))
                for path_name,members in selected.items():
                    path=Path(path_name);record=selected_ndk_record(before,path);relative=record['path']
                    previous=canonical.setdefault(record['resolved'],relative);need(previous==relative,'multiple selected aliases for same NDK input')
                    row=dict(record,map=image_record['map'],image=image_record['image'],members=sorted(m for m in members if m),copied=False)
                    result['external_map_inputs'].append(row)
                    if not llvm_runtime_notice_coverage(record,notices):
                        result['gaps'].append('selected input license coverage unclear; bytes withheld: '+relative);continue
                    if relative not in member_cache:
                        listing=command([toolroot/'bin/llvm-ar','t',path],label+'-members-'+str(len(member_cache))).stdout.splitlines()
                        member_cache[relative]=listing
                    with path.open('rb') as f:validate_archive_members(f.read(8),member_cache[relative],members)
                    into=destination/'ndk-inputs'/relative;into.parent.mkdir(parents=True,exist_ok=True)
                    if relative not in copied:
                        shutil.copyfile(path,into);need(digest(into)==record['sha256'],'retained NDK bytes differ')
                        files[into.relative_to(destination).as_posix()]=dict(sha256=digest(into),bytes=into.stat().st_size,mode=into.stat().st_mode&0o777,symlink_target=None);copied.add(relative)
                    row.update(copied=True,retained='ndk-inputs/'+relative,copy_sha256=digest(into),archive_members=member_cache[relative])
            need({'libexreader_host.so','libexreader_product.so'}<=set(images),'actual host/product mapped link outputs missing')
        need(result['images'] and result['external_map_inputs'],'no original map-selected NDK inputs captured')
        # Licensing/unknown-root gaps never authorize copying or F07. Keep this
        # distinct from the narrowly measured repaired public-interface boundary.
        result['complete']=not result['gaps']
    except Exception as error:
        result['error']=repr(error);raise
    finally:save(OUT/'ndk-capture.json',result)
    return result


def package_identity(target):
    folder=ROOT/'build/f06'/target
    result=json.loads((folder/'result.json').read_text())
    for key,value in identity().items():need(result[key]==value,(target,key))
    need(result['passed'] is True and result['target']==target,'original F06 result')
    manifest=json.loads((folder/'manifest.json').read_text())
    need(manifest['source_sha']==os.environ['GITHUB_SHA'],'package source')
    need(manifest['provenance']['run_id']==os.environ['GITHUB_RUN_ID'] and manifest['provenance']['attempt']==os.environ['GITHUB_RUN_ATTEMPT'],'package run/attempt')
    archive=folder/manifest['archive']['name']
    need(digest(archive)==manifest['archive']['sha256']==result['archive']['sha256'],'actual package bytes')
    # Original F06 package/unpack/entry assertions already ran unchanged. Retain
    # every byte and their identity reports, not only the passed boolean.
    return dict(result=result,manifest=manifest,archive_sha256=digest(archive),
                reports_sha256={p.name:digest(p) for p in folder.glob('*.json')})


def capture(target):
    actions();sdk,stage,product,base=layout(target)
    report=dict(identity(),target=target,capture_complete=False,named_boundary_accepted=False,f07_accepted=False,
                full_six_f07_accepted=False,unresolved=['Android-specific private OPDS/hash edge (not asserted for Windows)','source-copy sha256.inc ownership lead','final platform weak/import-provider gaps'])
    destination=OUT/'evidence';destination.mkdir(parents=True,exist_ok=False)
    files={};root=ROOT.resolve()
    def copy(path):
        path=Path(path);need(path.is_file(),'capture file missing '+str(path))
        relative=path.relative_to(ROOT).as_posix()
        if relative in files:return
        resolved=path.resolve();need(resolved.is_relative_to(root),'capture symlink escapes source workspace')
        into=destination/relative;into.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,into)
        files[relative]=dict(sha256=digest(into),bytes=into.stat().st_size,mode=path.stat().st_mode&0o777,
                             symlink_target=os.readlink(path) if path.is_symlink() else None)
    def tree(folder):
        need(folder.is_dir(),'required evidence tree '+str(folder))
        for path in sorted(folder.rglob('*')):
            need(not(path.is_symlink() and path.is_dir()),'directory alias requires explicit closure')
            if path.is_file():copy(path)
    try:
        if target=='android':
            copy(OUT/'ndk-before.json')
            report['ndk_provenance']=ndk_capture(destination,files,copy)
            report['ndk_provenance_complete']=report['ndk_provenance']['complete']
        source=json.loads((OUT/'source.json').read_text());need(source['source_sha']==os.environ['GITHUB_SHA'],'source identity')
        for prefix in dict.fromkeys((sdk,stage,product)):tree(prefix)
        need(not list(stage.glob('include/**/reader_selector_bytes_detail.h')),'private header installed')
        cache_records={};dependencies={};manifests={};proofs={};android_proof=None
        source_names={'reading-state':'reading_state.cpp','reading-commands':'reading_commands.cpp','annotation-import':'annotation_import.cpp','annotation-export':'annotation_export.cpp'}
        archive_names={'revisions':'reader_revisions','reading-state':'reader_reading_state_codec','reading-commands':'reader_reading_commands','annotation-import':'reader_annotation_import','annotation-export':'reader_annotation_export'}
        folders=list((ROOT/'build').rglob('CMakeCache.txt'))
        if (ROOT/'examples/android/app/.cxx').is_dir():folders+=list((ROOT/'examples/android/app/.cxx').rglob('CMakeCache.txt'))
        for cache in folders:
            if OUT in cache.parents:continue
            text=cache.read_text(errors='replace')
            homes=re.findall(r'^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$',text,re.M)
            if not homes:continue
            folder=cache.parent;home=Path(homes[0]).resolve();relative=folder.relative_to(ROOT).as_posix()
            raw='EXR_READER_SELECTOR_BYTES_CANDIDATE:BOOL=ON' in text
            owner=home.name if home.parent==ROOT/'apps/reader' and home.name in ('revisions','reading-state','reading-commands','annotation-import','annotation-export') else None
            copy(cache);cache_records[relative]=dict(home=str(home),raw=raw,owner=owner)
            if (folder/'install_manifest.txt').is_file():
                copy(folder/'install_manifest.txt');manifests[relative]=(folder/'install_manifest.txt').read_text().splitlines()
            metadata={'build.ninja','rules.ninja','.ninja_deps','.ninja_log','link.txt','DependInfo.cmake','compiler_depend.make','compiler_depend.internal','depend.make','flags.make','cmake_install.cmake'}
            dependency='';ninja_deps=None
            for path in folder.rglob('*'):
                if path.is_file() and (path.name in metadata or path.suffix in ('.d','.rsp','.map') or (owner and path.suffix in ('.o','.obj'))):
                    copy(path)
                    if path.name in ('compiler_depend.make','compiler_depend.internal','depend.make') or path.suffix=='.d':dependency+=path.read_text(errors='replace')+'\n'
            if (folder/'build.ninja').is_file():
                label='graph-'+relative.replace('/','_')
                for tool in ('commands','deps'):
                    p=command(['ninja','-C',folder,'-t',tool],label+'-'+tool)
                    if tool=='deps':ninja_deps=p.stdout
            if target=='android' and home==ROOT/'examples/android/app/src/main/cpp':
                need(android_proof is None and raw and ninja_deps is not None,'unique actual raw Android host dependency graph required')
                android_proof=android_caller_proof(folder,home,stage,ninja_deps,copy)
            if owner and raw and owner in source_names:
                need(owner not in proofs,'ambiguous raw build owner '+owner)
                name=archive_names[owner];archive_name=name+'.lib' if os.name=='nt' else 'lib'+name+'.a'
                built=folder/archive_name;installed=stage/'lib'/archive_name
                need(built.is_file() and installed.is_file() and digest(built)==digest(installed),'actual built archive differs from installed owner')
                copy(built)
                if ninja_deps is not None:
                    groups=ninja_dependency_groups(ninja_deps)
                    query=command(['ninja','-C',folder,'-t','query',archive_name],'archive-input-'+owner).stdout
                    archive_inputs,_=ninja_explicit_inputs(query,archive_name,'CXX_STATIC_LIBRARY_LINKER')
                    graph_objects=[p for p in archive_inputs if p.endswith(('.o','.obj'))]
                    need(graph_objects and len(graph_objects)==len(archive_inputs),'archive explicit inputs must all be objects')
                    graph_sources={}
                    for number,obj in enumerate(graph_objects):
                        query=command(['ninja','-C',folder,'-t','query',obj],'compiler-input-'+owner+'-'+str(number)).stdout
                        inputs,outputs=ninja_explicit_inputs(query,obj,'CXX_COMPILER')
                        need(len(inputs)==1 and inputs[0].endswith('.cpp') and archive_name in outputs,'unique actual C++ source/archive edge required')
                        graph_sources[obj]=inputs[0]
                else:
                    graph_sources=None
                    depfiles=list((folder/'CMakeFiles'/(name+'.dir')).rglob(source_names[owner]+'.o.d'))
                    need(len(depfiles)==1,'exact Make object depfile missing or ambiguous')
                    groups=make_dependency_group(depfiles[0].read_text())
                    link=folder/'CMakeFiles'/(name+'.dir')/'link.txt'
                    need(link.is_file(),'actual Make archive link command missing')
                    graph_objects=[token for token in shlex.split(link.read_text()) if token.endswith(('.o','.obj'))]
                required=[stage/'include'/('reader_reading_state_retained_raw_v1.h' if owner=='reading-commands' else 'reader_selector_bytes_v1.h')]
                proof=owned_dependency_proof(str(home/'src'/source_names[owner]),graph_objects,groups,folder,required,graph_sources)
                need((folder/proof['archive_object']).is_file(),'linked object bytes absent')
                proof.update(built_archive_sha256=digest(built),installed_archive_sha256=digest(installed))
                proofs[owner]=proof
        need(set(proofs)==set(source_names),'all four exact producer TU dependencies required')
        if target=='android':need(android_proof is not None,'actual Android retained caller proof missing')
        for owner,header in (('revisions','reader_selector_bytes_v1.h'),('reading-state','reader_reading_state_retained_raw_v1.h')):
            expected=(stage/'include'/header).resolve()
            owners=[cache_records[name]['owner'] for name,paths in manifests.items() if cache_records[name]['raw'] and expected in [Path(p).resolve() for p in paths]]
            need(owners==[owner],('public header exact install owner',header,owners))
        names={'revisions':'reader_revisions','reading-state':'reader_reading_state_codec','reading-commands':'reader_reading_commands','annotation-import':'reader_annotation_import','annotation-export':'reader_annotation_export'}
        target_names={'revisions':'EXReaderRevisions::reader_revisions','reading-state':'EXReaderReadingState::reader_reading_state_codec','reading-commands':'EXReaderReadingCommands::reader_reading_commands','annotation-import':'EXReaderAnnotationImport::reader_annotation_import','annotation-export':'EXReaderAnnotationExport::reader_annotation_export'}
        target_files=list((OUT/'native-build').glob('bound-targets-*.txt'));need(len(target_files)==1,'actual target location record')
        target_rows=[line.split('\t') for line in target_files[0].read_text().splitlines()]
        need(len(target_rows)==5 and all(len(row)==2 for row in target_rows),'target location structure')
        target_locations=dict(target_rows);need(set(target_locations)==set(target_names.values()),'exact imported target inventory')
        symbol_tables={};archive_identity={}
        for owner,name in names.items():
            archive=stage/'lib'/((name+'.lib') if os.name=='nt' else ('lib'+name+'.a'))
            need(archive.is_file(),'installed owner archive '+str(archive))
            need(Path(target_locations[target_names[owner]]).resolve()==archive.resolve(),'actual exported target redirected to another archive')
            owners=[cache_records[key]['owner'] for key,paths in manifests.items() if cache_records[key]['raw'] and archive.resolve() in [Path(p).resolve() for p in paths]]
            need(owners==[owner],('exact archive install owner',owner,owners))
            if os.name=='nt':argv=['dumpbin','/symbols',archive]
            elif target=='android':argv=[str(Path(os.environ['ANDROID_HOME'])/'ndk'/os.environ['C11_NDK']/'toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-nm'),'-A',archive]
            elif sys.platform=='darwin':argv=['xcrun','nm','-A',archive]
            else:argv=['nm','-A',archive]
            text=command(argv,'native-owner-'+owner).stdout
            need('reader_rs_encode_retained_raw_v3' not in text,'private C++ entry remains in '+owner)
            symbol_tables[owner]=text;archive_identity[owner]=dict(path=str(archive.relative_to(ROOT)),sha256=digest(archive),exported_target=target_names[owner],configured_target_file=target_locations[target_names[owner]])
        encode='reader_revision_selector_encode_v1';decode='reader_revision_selector_decode_v1';retained='reader_rs_encode_retained_raw_v1'
        for owner,symbol in (('revisions',encode),('revisions',decode),('reading-state',retained)):
            need(symbol_present(symbol_tables[owner],symbol,True,os.name=='nt'),('actual public definition',owner,symbol))
            need(sum(symbol_present(t,symbol,True,os.name=='nt') for t in symbol_tables.values())==1,'ambiguous project public definition')
        for owner,symbol in (('reading-state',encode),('reading-state',decode),('annotation-import',encode),('annotation-export',encode),('reading-commands',retained)):
            need(symbol_present(symbol_tables[owner],symbol,False,os.name=='nt'),('actual installed consumer import',owner,symbol))
        entries=('iphone','ipad') if target=='iphone' else (target,)
        packages={}
        for entry in entries:
            packages[entry]=package_identity(entry)
            for folder in (ROOT/'build/f06'/entry,ROOT/'build/f06'/('unpacked-'+entry)):
                tree(folder)
        # Original final producer binaries/maps and package envelopes, not probe
        # binaries mislabeled as a host. Some final functions may be dead-stripped;
        # this gate asserts installed owner boundaries, not whole-image F07.
        if target=='linux':
            tree(base/'retained-host');tree(base/'retained-package');tree(ROOT/'build/gtk-sdk342')
            for p in base.glob('*.json'):copy(p)
            for folder in ('gtk-navigation-ui','gtk-batch-ui','gtk-navigation-backend','gtk-batch-backend','gtk-batch-owner-faults'):
                if (ROOT/'build'/folder).exists():tree(ROOT/'build'/folder)
        elif target=='windows':tree(base/'host');tree(ROOT/'build/f06/windows-payload')
        elif target=='android':
            tree(ROOT/'build/f06/android-payload');tree(base/'artifacts')
            for path in (ROOT/'examples/android/app/.cxx').rglob('*'):
                if path.is_file() and path.suffix in ('.so','.map','.rsp','.o'):copy(path)
        else:
            tree(ROOT/'build/f06'/('macos-payload' if target=='macos' else 'iphone-payload'))
        native=json.loads((OUT/'native.json').read_text());need(native['passed'] is True,'native gate not passed')
        for entry in entries:
            local=json.loads((OUT/('native-'+entry+'.json')).read_text());need(local['passed'] is True,'native entry failed '+entry)
        tree(OUT/'native-build');tree(OUT/'native-data');tree(OUT/'legacy-stage');tree(OUT/'legacy-c06')
        for path in OUT.glob('*.json'):copy(path)
        tree(OUT/'logs')
        report.update(capture_complete=True,named_boundary_accepted=True,source=source,installed_archives=archive_identity,
                      actual_compiler_dependencies=proofs,android_retained_caller=android_proof,public_headers_unique_install_owner=True,
                      private_header_absent=True,private_cpp_entry_absent=True,packages=packages,native=native,
                      final_whole_image_f07_audit=False,original_source_guards_excluded=EXCLUSIONS)
    except Exception as error:
        report['error']=repr(error)
        raise
    finally:
        if target=='android' and (OUT/'ndk-capture.json').is_file():copy(OUT/'ndk-capture.json')
        if (OUT/'logs').is_dir():
            tree(OUT/'logs')
        save(OUT/'capture.json',report)
        save(destination/'inventory.json',dict(identity(),files=files,report=report))


def safe_member(name):
    path=PurePosixPath(name)
    return bool(name) and not path.is_absolute() and '\\' not in name and ':' not in name and all(p not in ('','.','..') for p in name.split('/'))


def verify_delivered_entry(bundle,target,record):
    prefix='build/f06/'+target+'/'
    def read(name):return json.loads(bundle.read(prefix+name))
    manifest,result=read('manifest.json'),read('result.json')
    config,entry,unpack=read('configuration.json'),read('entry.json'),read('unpack.json')
    for item in (result,config):
        for key,value in identity().items():need(item[key]==value,('F06 identity',target,key))
    need(result==record['result'] and manifest==record['manifest'],'recorded F06 result drift')
    need(result['passed'] and result['target']==manifest['target']==target,'F06 target/pass')
    need(manifest['source_sha']==os.environ['GITHUB_SHA'] and manifest['sdk_version']=='3.42.0','F06 source/version')
    need(manifest['provenance']['run_id']==os.environ['GITHUB_RUN_ID'] and manifest['provenance']['attempt']==os.environ['GITHUB_RUN_ATTEMPT'],'F06 provenance')
    need(config['build_recipe_sha256']==digest(ROOT/'tests/reader_f06_packages/build.py'),'original F06 build recipe')
    need(hashlib.sha256(bundle.read(prefix+'configuration.json')).hexdigest()==result['configuration_sha256'],'configuration digest')
    need(hashlib.sha256(bundle.read(prefix+'entry.json')).hexdigest()==result['entry_report_sha256'],'entry report digest')
    block=manifest['archive'];need(safe_member(block['name']) and '/' not in block['name'],'nested archive name')
    raw=bundle.read(prefix+block['name'])
    need(len(raw)==block['bytes'] and hashlib.sha256(raw).hexdigest()==block['sha256'] and result['archive']==block,'nested raw archive identity')
    with zipfile.ZipFile(io.BytesIO(raw)) as inner:
        names=inner.namelist();need(len(names)==len(set(names)) and all(safe_member(n) for n in names),'nested ZIP path inventory')
        need(set(names)==set(manifest['files'])|set(manifest['metadata_files']),'complete nested ZIP inventory')
        need(json.loads(inner.read('manifest.json'))=={k:v for k,v in manifest.items() if k!='archive'},'inner/outer manifest equality')
        sums=''.join(row['sha256']+'  '+name+'\n' for name,row in sorted(manifest['files'].items())).encode()
        need(inner.read('SHA256SUMS')==sums and hashlib.sha256(sums).hexdigest()==block['checksums_sha256'],'exact complete checksum list')
        for name in names:
            data=inner.read(name)
            need(bundle.read('build/f06/unpacked-'+target+'/'+name)==data,'actual unpacked bytes '+name)
            if name in manifest['files']:
                meta=manifest['files'][name];need(len(data)==meta['bytes'] and hashlib.sha256(data).hexdigest()==meta['sha256'],'delivered file digest '+name)
        executable=hashlib.sha256(inner.read(manifest['entry'])).hexdigest()
        need(executable==result['program_sha256']==manifest['files'][manifest['entry']]['sha256']==unpack['entry_sha256'],'actual delivered native entry')
    need(unpack['inner_matches_outer'] and unpack['checksums_checked']==len(manifest['files']),'original unpack assertions')
    if target in ('linux','windows','macos'):need(entry['passed'] and entry['source_sha']==os.environ['GITHUB_SHA'] and entry['sdk_version']=='3.42.0','original desktop entry')
    elif target=='android':need(entry['launch_passed'] and entry['installed_apk_sha256']==executable,'actual Android installed launch')
    else:need(entry['launch_exit']==0 and entry['installed_executable_sha256']==executable,'actual simulator installed launch')
    return dict(target=target,entry_sha256=executable,files=len(manifest['files']),archive_sha256=block['sha256'])


def authenticate():
    actions();report=dict(identity(),named_six_boundary_accepted=False,f07_accepted=False,full_six_f07_accepted=False,artifacts=[])
    def api(path):return json.loads(command(['gh','api','repos/NoGod3524/EXReader/'+path]).stdout)
    run_id=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT']
    try:
        record=api('actions/runs/'+run_id+'/attempts/'+attempt)
        need(record['head_sha']==os.environ['GITHUB_SHA'] and record['head_branch']==BRANCH and str(record['run_attempt'])==attempt,'immutable run identity')
        need(record['path']=='.github/workflows/reader-public-boundary-v1-20261028.yml','workflow path')
        jobs=api('actions/runs/'+run_id+'/attempts/'+attempt+'/jobs?per_page=100')['jobs']
        artifacts=api('actions/runs/'+run_id+'/artifacts?per_page=100')['artifacts']
        transport=load('tools/check_parallel_integration.py','boundary_artifact_transport')
        wires=[];covered=[]
        for target in ('linux','windows','android','macos','iphone'):
            matching=[j for j in jobs if j['name']=='boundary-'+target]
            need(len(matching)==1 and matching[0]['conclusion']=='success','producer not successful '+target)
            name='public-boundary-'+target+'-'+run_id+'-'+attempt
            matches=[a for a in artifacts if a['name']==name and not a['expired']]
            need(len(matches)==1,'missing/ambiguous artifact '+name);a=matches[0]
            need(a['workflow_run']['head_sha']==os.environ['GITHUB_SHA'] and str(a['workflow_run']['id'])==run_id,'artifact source/run')
            archive=OUT/(target+'-artifact.zip');archive.parent.mkdir(parents=True,exist_ok=True)
            with archive.open('w+b') as output:transport.download_artifact_zip(a['id'],output)
            need(archive.stat().st_size==a['size_in_bytes'] and 'sha256:'+digest(archive)==a['digest'],'upload ZIP identity')
            with zipfile.ZipFile(archive) as bundle:
                all_names=bundle.namelist()
                need(len(all_names)==len(set(all_names)) and all(safe_member(n[:-1] if n.endswith('/') else n) for n in all_names),'unsafe ZIP inventory')
                names=[info.filename for info in bundle.infolist() if not info.is_dir()]
                inventory=json.loads(bundle.read('inventory.json'))
                for key,value in identity().items():need(inventory[key]==value,(target,key))
                need(set(names)==set(inventory['files'])|{'inventory.json'},'complete file inventory')
                for path,meta in inventory['files'].items():
                    data=bundle.read(path);need(len(data)==meta['bytes'] and hashlib.sha256(data).hexdigest()==meta['sha256'],'file digest '+path)
                measured=inventory['report'];need(measured['target']==target and measured['capture_complete'] and measured['named_boundary_accepted'],'incomplete owner proof')
                need(measured['source']['authorized_paths_sha256']=={path:digest(ROOT/path) for path in (*OWNERS,*HOSTS,*ADDED)},'reviewed source manifest drift')
                expected_entries={'iphone','ipad'} if target=='iphone' else {target}
                need({entry['target'] for entry in measured['native']['entries']}==expected_entries,'artifact native target inventory')
                need(measured['f07_accepted'] is False and measured['final_whole_image_f07_audit'] is False,'scope inflation')
                for packaged in expected_entries:verify_delivered_entry(bundle,packaged,measured['packages'][packaged])
                for entry in measured['native']['entries']:
                    for key,value in identity().items():need(entry[key]==value,('native entry identity',target,key))
                    need(entry['passed'] and set(entry['retained_wires'])==EXPECTED_WIRES,'native entry/wire inventory')
                    for name,sha in entry['retained_wires'].items():
                        need(hashlib.sha256(bundle.read('build/public-boundary-v1/native-data/'+entry['target']+'-retained/'+name)).hexdigest()==sha,'actual retained wire bytes')
                    covered.append(entry['target']);wires.append(entry['retained_wires'])
                report['artifacts'].append({k:a[k] for k in ('id','name','size_in_bytes','digest')})
            archive.unlink()
        need(sorted(covered)==sorted(TARGETS),'six actual entries not covered')
        need(all(wire==wires[0] for wire in wires),'cross-platform retained wire mismatch')
        report.update(named_six_boundary_accepted=True,entries=covered,cross_platform_retained_wires_equal=True,
                      limitations=['whole-image F07 provider/runtime gates separate','unrelated private/source-copy edges remain','no physical iOS/Android device proof'])
    finally:
        save(OUT/'authenticated.json',report);print(json.dumps(report),flush=True)


def main():
    actions();p=argparse.ArgumentParser();p.add_argument('phase',choices=('guard','build','native','capture','authenticate'));p.add_argument('--target',choices=TARGETS);args=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if args.phase=='guard':guard()
    elif args.phase=='authenticate':authenticate()
    else:
        need(args.target,'target required');globals()[args.phase](args.target)


if __name__=='__main__':main()
