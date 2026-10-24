#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Query the relocated pkg-config metadata with a real pkg-config/pkgconf.

The distribution rewrites each .pc prefix to a pcfiledir-relative expression, so
the metadata only counts as usable when the real tool resolves it after the move:
every package must validate, resolve its prefix inside the extracted tree, keep
all -I/-L directories present inside that tree, and one installed component must
actually compile and link through the pkg-config output (with an /INCLUDE:<symbol>
from the real library, so a wrong -L or -l cannot pass).
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import distlib
import reduce_archives

SYMBOL_OK = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')


def find_tool(candidates):
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found
    return None


def run(command, env=None):
    done = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          env=env)
    return done.returncode, done.stdout.strip(), done.stderr.strip()


def inside(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False


def flag_paths(text, flag):
    paths = []
    for token in text.split():
        if token.startswith(flag) and len(token) > len(flag):
            paths.append(token[len(flag):])
        elif token.startswith(flag + ' ') and len(token) > len(flag):
            paths.append(token[len(flag):].strip())
    return paths


def convert_libs(tokens):
    """pkg-config link flags to MSVC link arguments."""
    conversion = []
    for token in tokens:
        if token.startswith('-l') and len(token) > 2:
            conversion.append(token[2:] + '.lib')
        elif token.startswith('-L') and len(token) > 2:
            conversion.append('/LIBPATH:' + token[2:])
        elif token.startswith('-'):
            continue
        elif token.startswith('/'):
            conversion.append(token)
        else:
            conversion.append(token)
    return conversion


def choose_symbol(dumpbin, library):
    names = reduce_archives.dump_symbols(dumpbin, library)
    usable = sorted(name for name in names
                    if name and name[0] not in '_?' and set(name) <= SYMBOL_OK and
                    not name.lower().startswith(('atexit', 'crt', 'main')))
    return usable[0] if usable else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cl', default='cl')
    parser.add_argument('--dumpbin', default='dumpbin')
    parser.add_argument('--expect', type=int, default=0,
                        help='minimum number of .pc files that must be present')
    args = parser.parse_args()
    prefix = args.prefix.resolve(strict=True)
    tool = find_tool(('pkg-config', 'pkgconf'))
    distlib.require(tool, 'no pkg-config or pkgconf implementation is available')
    version = run([tool, '--version'])[1]
    packages = sorted(path for path in prefix.rglob('*.pc'))
    distlib.require(packages, 'the relocated prefix carries no pkg-config metadata')
    distlib.require(len(packages) >= max(args.expect, 1),
                    'the relocated prefix carries %d .pc files, fewer than expected' % len(packages))
    directories = sorted({path.parent.as_posix() for path in packages})
    environment = dict(os.environ)
    environment['PKG_CONFIG_PATH'] = os.pathsep.join(directories)
    environment['PKG_CONFIG_LIBDIR'] = os.pathsep.join(directories)
    results, outside, failed = [], [], []
    for path in packages:
        name = path.stem
        record = {'name': name, 'pc': str(path.relative_to(prefix))}
        code, _, error = run([tool, '--exists', name], env=environment)
        record['exists'] = code == 0
        code, validate_out, validate_error = run([tool, '--validate', str(path)], env=environment)
        message = (validate_out or validate_error)[:200]
        unsupported = code != 0 and ('unknown option' in message.lower() or
                                     'unrecognized' in message.lower() or
                                     'invalid option' in message.lower())
        record['validate'] = code == 0 or unsupported
        record['validate_unsupported'] = unsupported
        record['validate_output'] = message
        if not record['exists'] or not record['validate']:
            failed.append({'name': name, 'exists': record['exists'],
                           'validate': record['validate'], 'error': record['validate_output']})
            results.append(record)
            continue
        code, resolved, error = run([tool, '--variable=prefix', name], env=environment)
        record['variable_prefix'] = resolved
        code, cflags, error = run([tool, '--cflags', name], env=environment)
        record['cflags'] = cflags
        code, libs, error = run([tool, '--libs', name], env=environment)
        record['libs'] = libs
        include_dirs = flag_paths(cflags, '-I')
        library_dirs = flag_paths(libs, '-L')
        record['include_dirs'] = include_dirs
        record['library_dirs'] = library_dirs
        fresh = bool(resolved) and Path(resolved).is_dir() and inside(resolved, prefix)
        record['prefix_inside_relocated_tree'] = fresh
        if not fresh:
            outside.append({'name': name, 'prefix': resolved})
        for directory in include_dirs + library_dirs:
            if not Path(directory).is_dir() or not inside(directory, prefix):
                outside.append({'name': name, 'path': directory})
        record['ok'] = fresh and not any(item['name'] == name for item in outside)
        results.append(record)
    consumer = {'linked': False, 'ran': False, 'attempts': []}

    def compile_and_run(source_text, include_dirs, libs_text, forced_symbol, tag):
        attempt = {'tag': tag, 'linked': False, 'ran': False}
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / 'pkgconfig-probe.c'
            source.write_text(source_text, encoding='utf-8')
            command = [args.cl, '/nologo', '/c', str(source)]
            for directory in include_dirs:
                command.append('/I' + directory)
            code, output, error = run(command)
            attempt['compile_output'] = (output or error)[-400:]
            if code != 0:
                attempt['error'] = 'compile'
                return attempt
            executable = folder / 'pkgconfig-probe.exe'
            arguments = convert_libs(libs_text.split())
            link = [args.cl, '/nologo', '/Fe:' + str(executable),
                    str(folder / 'pkgconfig-probe.obj'), '/link'] + arguments
            if forced_symbol:
                link.append('/INCLUDE:' + forced_symbol)
            code, output, error = run(link)
            attempt['link_output'] = (output or error)[-800:]
            attempt['linked'] = code == 0 and executable.is_file()
            if attempt['linked']:
                code, output, error = run([str(executable)])
                attempt['ran'] = code == 0
                attempt['run_returncode'] = code
                attempt['stdout'] = (output or '')[:200]
            return attempt

    webp_source = ('#include <webp/decode.h>\n'
                   '#include <stdio.h>\n'
                   'int main(void) {\n'
                   '  int version = WebPGetDecoderVersion();\n'
                   '  printf("%d\n", version);\n'
                   '  return version > 0 ? 0 : 1;\n'
                   '}\n')
    empty_source = 'int main(void) { return 0; }\n'
    for record in results:
        if not record.get('ok'):
            continue
        include_dirs = record.get('include_dirs', [])
        libs_text = record.get('libs', '')
        libraries = []
        for directory in record.get('library_dirs', []):
            for token in libs_text.split():
                if token.startswith('-l') and len(token) > 2:
                    candidate = Path(directory) / (token[2:] + '.lib')
                    if candidate.is_file():
                        libraries.append(candidate)
        if not libraries:
            continue
        headers = [Path(directory) / 'webp' / 'decode.h' for directory in include_dirs]
        if any(path.is_file() for path in headers):
            attempt = compile_and_run(webp_source, include_dirs, libs_text, None,
                                      record['name'] + ':webp-api')
            consumer['attempts'].append(attempt)
            if attempt['linked'] and attempt['ran']:
                consumer.update(attempt, package=record['name'],
                                library=str(libraries[0].relative_to(prefix)), libs=libs_text)
                break
        symbol = choose_symbol(args.dumpbin, libraries[0])
        if symbol:
            attempt = compile_and_run(empty_source, include_dirs, libs_text, symbol,
                                      record['name'] + ':forced-symbol')
            attempt['symbol'] = symbol
            consumer['attempts'].append(attempt)
            if attempt['linked'] and attempt['ran']:
                consumer.update(attempt, package=record['name'],
                                library=str(libraries[0].relative_to(prefix)), libs=libs_text)
                break
    outside_paths = [item for item in outside]
    report = {'schema': 'reader-distribution-windows-pkgconfig-v1',
              'prefix': str(prefix), 'tool': tool, 'tool_version': version,
              'directories': directories, 'packages': len(results), 'results': results,
              'outside_paths': outside_paths, 'failed': failed,
              'resolved_inside_prefix': not outside_paths and bool(results),
              'consumer': consumer,
              'accepted': bool(results) and not outside_paths and not failed and
                          all(item.get('ok') for item in results) and
                          consumer.get('linked') is True and consumer.get('ran') is True}
    distlib.write_json(args.output, report)
    print(json.dumps({'tool': tool, 'version': version, 'packages': len(results),
                      'outside': len(outside_paths), 'failed': len(failed),
                      'consumer': consumer.get('package'), 'linked': consumer.get('linked'),
                      'ran': consumer.get('ran'), 'accepted': report['accepted']}))
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())
