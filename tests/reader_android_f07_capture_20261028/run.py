"""Capture the unchanged common-source Android 3.42 producer's real outputs."""
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import zipfile

from contract import ROOT, OUT, BASE, actions_only, digest, file_digest, guard, identity, require, save, elf_allocated

RAW = OUT / 'raw'
INVENTORY = {}
COMMANDS = []


def retain(path, category, boundary=ROOT):
    path = Path(os.path.abspath(path))
    relative = path.relative_to(ROOT).as_posix()
    target = path.resolve(strict=True)
    require(target.is_relative_to(boundary.resolve()), 'input escapes allowed root: ' + str(path))
    require(target.is_file(), 'nonregular capture input: ' + str(path))
    destination = RAW / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    value = dict(path=relative, bytes=target.stat().st_size, sha256=file_digest(target), category=category)
    if path.is_symlink():
        value.update(symlink=os.readlink(path), resolved=target.relative_to(ROOT).as_posix())
    if relative in INVENTORY:
        require(INVENTORY[relative]['sha256'] == value['sha256'], 'capture input changed during collection')
        return value
    shutil.copyfile(target, destination)
    require(file_digest(destination) == value['sha256'], 'retained copy differs')
    INVENTORY[relative] = value
    return value


def shared_name(path):
    return re.sub(r'\.so(?:\.[0-9]+)+$', '.so', Path(path).name)


def shared_file(path):
    return re.fullmatch(r'.+\.so(?:\.[0-9]+)*', Path(path).name) is not None


def retain_tree(path, category):
    require(path.is_dir() and not path.is_symlink(), 'missing or symbolic capture prefix: ' + str(path))
    entries = []
    for item in sorted(path.rglob('*')):
        require(not item.is_symlink() or item.resolve().is_relative_to(path.resolve()), 'prefix link escapes')
        require(not (item.is_symlink() and item.is_dir()), 'directory symlink needs explicit capture support')
        if item.is_file():
            entries.append(retain(item, category, path))
    require(entries, 'empty capture prefix')
    return entries


def command(label, argv, cwd=ROOT, input_path=None):
    result = subprocess.run(list(map(str, argv)), cwd=cwd, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    record = dict(label=label, argv=list(map(str, argv)), cwd=str(cwd), exit=result.returncode,
                  stdout_sha256=digest(result.stdout.encode()), stderr_sha256=digest(result.stderr.encode()))
    if input_path is not None:
        record.update(input=str(input_path.relative_to(ROOT)), input_sha256=file_digest(input_path))
    logs = OUT / 'commands'
    logs.mkdir(parents=True, exist_ok=True)
    (logs / (label + '.stdout')).write_text(result.stdout)
    (logs / (label + '.stderr')).write_text(result.stderr)
    COMMANDS.append(record)
    save(OUT / 'commands.json', COMMANDS)
    require(result.returncode == 0, 'inspection command failed: ' + label)
    return result.stdout


def native_tools():
    ndk = Path(os.environ['ANDROID_HOME']) / 'ndk' / os.environ['C11_NDK']
    require(os.environ['C11_NDK'] == '27.0.12077973', 'NDK drift')
    tools = ndk / 'toolchains/llvm/prebuilt/linux-x86_64/bin'
    for name in ('llvm-readelf', 'llvm-nm'):
        tool = tools / name
        require(tool.is_file(), 'missing NDK native inspector')
        command(name + '-version', [tool, '--version'])
    save(OUT / 'toolchain.json', dict(ndk=str(ndk), source_properties=(ndk / 'source.properties').read_text(),
         tools={name: dict(path=str(tools / name), sha256=file_digest(tools / name))
                for name in ('llvm-readelf', 'llvm-nm')}))
    return tools


def native_report(path, label, tools):
    record = retain(path, 'native image/archive')
    command(label + '-symbols', [tools / 'llvm-nm', '-g', path], input_path=path)
    if shared_file(path):
        command(label + '-elf', [tools / 'llvm-readelf', '--all', path], input_path=path)
        command(label + '-dynamic-symbols', [tools / 'llvm-nm', '-D', '-g', path], input_path=path)
        record = dict(record, elf=elf_allocated(path.read_bytes()))
    return record


def inspect_ninja(cache, number):
    directory = cache.parent
    text = cache.read_text()
    match = re.search(r'^CMAKE_MAKE_PROGRAM:[^=]+=(.+)$', text, re.M)
    require(match is not None, 'CMake did not retain its actual Ninja path')
    ninja = Path(match[1])
    require(ninja.is_file(), 'recorded Ninja unavailable')
    commands = command('ninja-%03d-commands' % number, [ninja, '-t', 'commands'], directory)
    # These inspection tools do NOT execute any compile/link command.
    command('ninja-%03d-compdb' % number, [ninja, '-t', 'compdb'], directory)
    for filename in ('CMakeCache.txt', 'build.ninja', 'rules.ninja', 'compile_commands.json', 'install_manifest.txt', '.ninja_log'):
        for item in directory.glob(filename):
            retain(item, 'generated build graph')
    rules = directory / 'CMakeFiles/rules.ninja'
    if rules.is_file(): retain(rules, 'generated build graph')
    outputs, gaps, external = [], [], []
    for line in commands.splitlines():
        tokens = shlex.split(line)
        if '-o' not in tokens:
            continue
        output = Path(tokens[tokens.index('-o') + 1])
        output = Path(os.path.abspath(output if output.is_absolute() else directory / output))
        if not shared_file(output):
            continue
        require(output.resolve().is_relative_to(ROOT), 'link output outside repository workspace')
        item = dict(path=output.relative_to(ROOT).as_posix(), argv=tokens, inputs=[], maps=[])
        for token in tokens:
            if token.startswith('@'):
                rsp = Path(token[1:]); rsp = rsp if rsp.is_absolute() else directory / rsp
                rsp = Path(os.path.abspath(rsp))
                if rsp.is_file() and rsp.resolve().is_relative_to(ROOT):
                    retain(rsp, 'link response file')
                    item.setdefault('responses', []).append(rsp.relative_to(ROOT).as_posix())
                else:
                    gaps.append('Link response file unavailable: ' + str(rsp))
            if token.startswith('-Wl,-Map,'):
                mapping = Path(token[len('-Wl,-Map,'):])
                mapping = mapping if mapping.is_absolute() else directory / mapping
                mapping = Path(os.path.abspath(mapping))
                retain(mapping, 'actual final link map')
                item['maps'].append(mapping.relative_to(ROOT).as_posix())
            if not (token.endswith(('.a', '.o')) or shared_file(token)) or token.startswith('-'):
                continue
            candidate = Path(token)
            candidate = Path(os.path.abspath(candidate if candidate.is_absolute() else directory / candidate))
            if candidate == output:
                continue
            if not candidate.is_file():
                gaps.append('Named link input unavailable: ' + str(candidate))
            elif candidate.resolve().is_relative_to(ROOT):
                item['inputs'].append(retain(candidate, 'actual named link input')['path'])
            else:
                external.append(dict(path=str(candidate), sha256=file_digest(candidate), bytes=candidate.stat().st_size))
        require(output.is_file(), 'linked image unavailable: ' + str(output))
        item['sha256'] = file_digest(output)
        outputs.append(item)
    return dict(cache=cache.relative_to(ROOT).as_posix(), linked_outputs=outputs,
                external_named_inputs=external, unresolved=gaps)


def capture():
    actions_only()
    report = dict(identity(), capture_complete=False, full_f07_accepted=False,
                  scope='Android evidence capture only; independent closure audit still required', failures=[])
    try:
        source = json.loads((OUT / 'source.json').read_text())
        require(all(source[k] == v for k, v in identity().items()), 'source guard belongs to another run')
        tools = native_tools()
        sdk, modules = ROOT / 'build/wave3/sdk-stage', ROOT / 'build/wave3/stage'
        report['sdk_prefix'] = retain_tree(sdk, 'actual installed SDK')
        report['module_prefix'] = retain_tree(modules, 'actual installed product/optional modules')
        installed_headers = sorted((sdk / 'include/exr').glob('*.h'))
        original_headers = sorted((ROOT / 'include/exr').glob('*.h'))
        require({p.name for p in installed_headers} == {p.name for p in original_headers}, 'installed SDK header inventory differs')
        require(all(p.read_bytes() == (ROOT / 'include/exr' / p.name).read_bytes() for p in installed_headers), 'installed SDK header bytes differ')
        require('#define EXR_VERSION "3.42.0"' in (sdk / 'include/exr/base.h').read_text(), 'not SDK 3.42')
        require(list((modules / 'lib/cmake').rglob('*Targets.cmake')), 'missing installed module ownership exports')
        for folder in (ROOT / 'build/wave3/logs', ROOT / 'build/f06/android'):
            retain_tree(folder, 'original producer log/F06 identity')
        retain(ROOT / 'build/f06/android-payload/build.json', 'unchanged producer metadata')
        for script in sorted((ROOT / 'build/f06').glob('android-sdk342-build-step-*.sh')):
            retain(script, 'original transformed SDK342 build recipe')
        result = json.loads((ROOT / 'build/f06/android/result.json').read_text())
        entry = json.loads((ROOT / 'build/f06/android/entry.json').read_text())
        require(result['passed'] is True and result['target'] == 'android', 'original F06 identity did not pass')
        for key in ('source_sha', 'run_id', 'attempt'):
            require(result[key] == entry[key] == identity()[key], 'F06 identity mismatch: ' + key)
        apk = ROOT / 'build/f06/unpacked-android/artifacts/app-debug.apk'
        pulled = ROOT / 'build/f06/installed-android.apk'
        expected = result['program_sha256']
        for candidate in (apk, pulled, ROOT / 'build/wave3/artifacts/app-debug.apk',
                          ROOT / 'examples/android/app/build/outputs/apk/debug/app-debug.apk'):
            require(file_digest(candidate) == expected == entry['installed_apk_sha256'], 'actual packaged/installed APK differs')
            retain(candidate, 'actual packaged/installed APK')
        require(entry['launch_passed'] is True and entry['api'] == '34' and entry['abi'] == 'x86_64', 'wrong actual F06 entry')
        require(file_digest(ROOT / 'build/f06/android/entry.json') == result['entry_report_sha256'], 'entry report hash differs')
        require(file_digest(ROOT / 'build/f06/android/configuration.json') == result['configuration_sha256'], 'configuration hash differs')
        caches = sorted(set((ROOT / 'build/wave3').glob('*/CMakeCache.txt')) |
                        set((ROOT / 'examples/android/app/.cxx').rglob('CMakeCache.txt')))
        require(caches, 'no actual caches')
        graphs = [inspect_ninja(cache, i) for i, cache in enumerate(caches)]
        report['build_graphs'] = graphs
        report['response_or_named_input_gaps'] = [g for graph in graphs for g in graph['unresolved']]
        linked = [item for graph in graphs for item in graph['linked_outputs']]
        require(linked, 'no actual shared-library link commands')
        native = {}
        for i, item in enumerate(linked):
            path = ROOT / item['path']
            native[item['path']] = native_report(path, 'linked-%03d' % i, tools)
        sdk_images = [native_report(path, 'installed-sdk-%03d' % i, tools)
                      for i, path in enumerate(sorted(p for p in (sdk / 'lib').iterdir() if shared_file(p)))]
        require(sdk_images, 'installed shared SDK images absent')
        report['installed_sdk_images'] = sdk_images
        report['sdk_install_transform_gaps'] = []
        archives = sorted(set(sdk.rglob('*.a')) | set(modules.rglob('*.a')))
        require(archives and list(modules.rglob('*.a')), 'missing actual installed archives')
        report['installed_archives'] = [native_report(path, 'archive-%03d' % i, tools) for i, path in enumerate(archives)]
        packaged = []
        with zipfile.ZipFile(apk) as archive:
            infos = [i for i in archive.infolist() if i.filename.startswith('lib/') and not i.is_dir()]
            require(infos and len({i.filename for i in infos}) == len(infos), 'missing/duplicate APK native entry')
            for i, info in enumerate(infos):
                require(re.fullmatch(r'lib/x86_64/[A-Za-z0-9_.+-]+\.so', info.filename), 'unexpected APK native path/ABI')
                require(0 < info.file_size < 512 * 1024**2 and not info.flag_bits & 1, 'bad APK native entry')
                path = OUT / 'apk-native' / info.filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(info))
                item = native_report(path, 'apk-%03d' % i, tools)
                matches = [link for link in linked if shared_name(link['path']) == path.name and
                           native[link['path']]['elf']['allocated_sha256'] == item['elf']['allocated_sha256']]
                installed_matches = [image for image in sdk_images if shared_name(image['path']) == path.name and
                                     image['elf']['allocated_sha256'] == item['elf']['allocated_sha256']]
                if path.name in ('libexreader_host.so', 'libexreader_product.so'):
                    require(matches, 'APK host/product ELF differs from exact raw link output: ' + path.name)
                    mapname = 'sdk-host-link.map' if path.name == 'libexreader_host.so' else 'product-link.map'
                    require(all(any(Path(m).name == mapname for m in link['maps']) for link in matches), 'final host/product link map missing')
                else:
                    require(installed_matches, 'APK native dependency has no actual installed SDK match: ' + path.name)
                    named_links = [link for link in linked if shared_name(link['path']) == path.name]
                    require(named_links, 'SDK raw link output/commands unavailable: ' + path.name)
                    if not matches:
                        report['sdk_install_transform_gaps'].append(dict(image=path.name, raw_link_outputs=named_links,
                            detail='Installed image matches APK, but allocated sections differ from pre-install link output; inspect original install transform. No equivalence is inferred.'))
                item = dict(item, apk_entry=info.filename, apk_sha256=expected, matched_link_outputs=matches,
                            matched_installed_sdk=installed_matches,
                            binding='all allocated sections + PT_LOAD virtual layout; APK whole hash separately bound to actual installed APK')
                packaged.append(item)
        require({'libexreader_host.so', 'libexreader_product.so', 'libexreader_jni.so'} <=
                {Path(item['apk_entry']).name for item in packaged}, 'required native family missing')
        report['packaged_images'] = packaged
        report['linked_images'] = native
        require(not report['response_or_named_input_gaps'], 'link capture gaps remain; retain original evidence and repair only additive collector')
        report['capture_complete'] = True
        report['remaining_verification'] = [
            'Independent replay of exact retained input hashes and native symbol dumps is required.',
            'No single-SDK/product-SQLite-provider or public-only module import acceptance is asserted by this collector.',
            'System -l inputs/toolchain defaults require independent resolution against retained commands and pinned NDK identity.',
            'This is a new source/run, never replacement evidence for original run 40678657371.',
            'Full six-platform F07, full behavioral regression, physical devices, signing and release remain separate.']
    except Exception as error:
        report['failures'].append(str(error))
        raise
    finally:
        save(OUT / 'inventory.json', dict(identity(), files=INVENTORY))
        save(OUT / 'capture.json', report)
        print(json.dumps({k: report[k] for k in ('capture_complete', 'full_f07_accepted', 'failures')}, sort_keys=True))


if __name__ == '__main__':
    actions_only()
    {'guard': guard, 'capture': capture}[sys.argv[1]]()
