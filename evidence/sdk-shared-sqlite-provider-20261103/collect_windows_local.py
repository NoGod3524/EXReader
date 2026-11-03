"""Retain raw Windows symbols/imports and identify implementation vs import thunks."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def run(name, argv):
    p = subprocess.run(list(map(str, argv)), capture_output=True, timeout=60)
    (OUT / (name + '.stdout.txt')).write_bytes(p.stdout)
    (OUT / (name + '.stderr.txt')).write_bytes(p.stderr)
    if p.returncode:
        raise RuntimeError(f'{name}: rc={p.returncode}; see retained stderr')
    return p.stdout.decode('utf-8', 'strict')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--llvm-bin', type=Path, required=True)
    args = parser.parse_args()
    stage = ROOT / 'build/sdk-stage'
    images = {'provider': stage / 'bin/libreader_sqlite3.dll',
              'sdk': stage / 'bin/libexreader.dll',
              'consumer': ROOT / 'build/sdk-integration/shared-sqlite-consumer.exe'}
    nm, readobj, objdump = (args.llvm_bin / name for name in ('llvm-nm.exe', 'llvm-readobj.exe', 'llvm-objdump.exe'))
    result = {'acceptance_assessed': False, 'scope': 'SDK core shared-provider contract; local Windows only',
              'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'sdk_version': re.search(r'#define EXR_VERSION "([^"]+)"', (ROOT / 'include/exr/base.h').read_text())[1],
              'tools': {}, 'images': {}, 'stage_scan': []}
    for tool in (nm, readobj, objdump):
        version = run(tool.stem + '-version', [tool, '--version'])
        result['tools'][tool.stem] = {'path': str(tool), 'sha256': hashlib.sha256(tool.read_bytes()).hexdigest(), 'version': version}
    for role, path in images.items():
        symbols = run(role + '-nm', [nm, '--format=posix', path])
        tables = run(role + '-coff', [readobj, '--coff-imports', '--coff-exports', path])
        defined = {parts[0]: parts[1] for line in symbols.splitlines()
                   if len(parts := line.split()) >= 2 and parts[0].startswith('sqlite3_')
                   and parts[1] not in ('U', 'w', 'v')}
        imports = {}
        for block in re.findall(r'(?ms)^Import \{(.*?)^\}', tables):
            dll = re.search(r'(?m)^\s*Name:\s+(\S+)', block)[1]
            for symbol in re.findall(r'(?m)^\s*Symbol:\s+(\S+)', block):
                if symbol.startswith('sqlite3_'):
                    imports[symbol] = dll
        exports = []
        for block in re.findall(r'(?ms)^Export \{(.*?)^\}', tables):
            name = re.search(r'(?m)^\s*Name:\s+(\S+)', block)
            if name and name[1].startswith('sqlite3_'):
                exports.append(name[1])
        thunks = []
        if role != 'provider':
            if not imports or set(imports.values()) != {images['provider'].name}:
                raise RuntimeError(role + ': SQLite imports do not all select the one provider DLL')
            if not defined or any(imports.get(name) != images['provider'].name for name in defined):
                raise RuntimeError(role + ': definition/import correspondence not established')
            assembly = run(role + '-sqlite-thunks', [objdump, '--disassemble', '--no-show-raw-insn',
                '--disassemble-symbols=' + ','.join(sorted(defined)), path])
            blocks = {m[1]: m[2] for m in re.finditer(r'(?ms)^[0-9a-f]+ <([^>]+)>:\n(.*?)(?=^[0-9a-f]+ <|\Z)', assembly)}
            for name in defined:
                instructions = [line.split(':', 1)[1].strip() for line in blocks.get(name, '').splitlines()
                                if re.match(r'^\s*[0-9a-f]+:', line)]
                jumps = [line for line in instructions if line.split()[0] in ('jmp', 'jmpq')]
                if (len(jumps) != 1 or '__imp_' + name not in jumps[0] or any(
                    line.split()[0] not in ('jmp', 'jmpq', 'nop', 'nopl', 'nopw', 'int3') for line in instructions)):
                    raise RuntimeError(role + '/' + name + ': not a verified IAT jump thunk')
                thunks.append(name)
        result['images'][role] = {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'raw_sqlite_defined_count': len(defined), 'raw_sqlite_types': dict(collections.Counter(defined.values())),
            'sqlite_exports': sorted(exports), 'sqlite_imports': imports,
            'verified_import_thunks': sorted(thunks), 'implementation_definitions': sorted(set(defined) - set(thunks))}
    owners = collections.defaultdict(list)
    for role, image in result['images'].items():
        for name in image['implementation_definitions']:
            owners[name].append(role)
    if not owners or any(roles != ['provider'] for roles in owners.values()):
        raise RuntimeError('SQLite implementation definitions do not have one unique provider')
    if any(result['images'][r]['sqlite_exports'] for r in ('sdk', 'consumer')):
        raise RuntimeError('A second application image exports SQLite')
    if result['images']['provider']['sqlite_imports'] or not result['images']['provider']['sqlite_exports']:
        raise RuntimeError('Provider is not a defining/exporting implementation')
    result['unique_implementation_provider_observed'] = True
    result['implementation_identifiers'] = len(owners)
    for path in sorted(stage.rglob('*')):
        if path.is_file() and 'sqlite' in str(path.relative_to(stage)).lower():
            result['stage_scan'].append({'path': path.relative_to(stage).as_posix(), 'bytes': path.stat().st_size,
                                        'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    (OUT / 'stage-sqlite-scan.txt').write_text('\n'.join(
        f"{r['path']}\t{r['bytes']}\t{r['sha256']}" for r in result['stage_scan']) + '\n', encoding='utf-8')
    result['fts5_tests'] = []
    for name in ('fts5-provider.xml', 'fts5-integration.xml'):
        cases = list(ET.parse(OUT / name).getroot().iter('testcase'))
        if len(cases) != 1 or any(c.find('failure') is not None or c.find('skipped') is not None
                                 or c.find('error') is not None for c in cases):
            raise RuntimeError('FTS5 test result missing, failed or skipped: ' + name)
        result['fts5_tests'].append({'name': cases[0].attrib['name'], 'passed': 1, 'total': 1, 'junit': name})
    (OUT / 'windows-local.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({r: {k: v for k, v in image.items() if k in ('raw_sqlite_defined_count', 'raw_sqlite_types')}
                      | {'verified_import_thunks': len(image['verified_import_thunks']),
                         'implementation_definitions': len(image['implementation_definitions']),
                         'sqlite_exports': len(image['sqlite_exports'])} for r, image in result['images'].items()}, indent=2))
    print('Local implementation ownership observed once; acceptance remains unassessed.')


if __name__ == '__main__':
    main()
