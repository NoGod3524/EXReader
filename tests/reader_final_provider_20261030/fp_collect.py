"""Collect real native tables from an already-built final image and run the provider audit.

Only read-only inspection tools (nm/llvm-nm, readelf/otool/dumpbin) are run. No compile, link or
configure happens here; the map must already exist next to the final image from the producer.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import fp_core as C
import fp_maps as M

NM = ('llvm-nm', 'nm')


def tool(names):
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    raise ValueError('no inspector among ' + ','.join(names))


def run(args, out):
    done = subprocess.run(list(map(str, args)), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(done.stdout)
    Path(str(out) + '.stderr').write_bytes(done.stderr)
    C.require(done.returncode == 0, 'native inspection failed: %s: %s' % (args[0], done.stderr[:200]))
    return done.stdout.decode('utf-8', errors='strict')


def sha_name(path):
    return C.sha(path.encode())[:16]


def needed(platform, image, out):
    if platform in ('linux', 'android'):
        text = run([tool(('llvm-readelf', 'readelf')), '-d', image], out / 'needed.txt')
        return re.findall(r'\(NEEDED\)\s+Shared library: \[([^\]]+)\]', text)
    if platform in ('macos', 'iphone', 'ipad'):
        text = run([tool(('otool',)), '-L', image], out / 'needed.txt')
        return [line.split(' (')[0].strip() for line in text.splitlines()[1:] if line.strip()]
    text = run([tool(('dumpbin',)), '/dependents', image], out / 'needed.txt')
    return re.findall(r'^\s+(\S+\.dll)\s*$', text, re.M | re.I)


def collect(config, out):
    """config: platform, sdk_version, image, map, map_format, roles{role:[prefix]}, archives[list],
    product_catalog_marker, apple (bool: canonicalise leading underscore)."""
    out = Path(out)
    platform = config['platform']
    C.require(platform in C.PLATFORMS, 'unknown platform')
    image = Path(config['image'])
    map_text = Path(config['map']).read_text(encoding='utf-8', errors='strict')
    parsed = M.PARSERS[config['map_format']](map_text)
    cwd = config.get('link_cwd', '.')
    norm = lambda p: os.path.normpath(os.path.join(cwd, p)).replace(chr(92), '/')
    nm = tool(NM)
    archives = {}
    for index, archive in enumerate(config['archives']):
        text = run([nm, '-A', '-g', archive], out / 'native' / ('archive-%d.nm.txt' % index))
        archives[norm(archive)] = {m: {k: sorted(v) for k, v in row.items()} for m, row in M.parse_nm_archive(text).items()}
    selected = [[norm(a), m] for a, m in parsed['members']]
    pending = []
    for loose in parsed['objects']:
        path = norm(loose)
        if not loose.endswith('.o'):
            pending.append(dict(kind='non_object_map_input', input=loose))
            continue
        if M.classify(path, config['roles']) == 'system':
            continue
        selected.append([path, os.path.basename(path)])
        if Path(path).is_file():
            row = M.parse_nm_object(run([nm, '-A', '-g', path], out / 'native' / ('object-%s.nm.txt' % sha_name(path))))
            archives[path] = {os.path.basename(path): {k: sorted(v) for k, v in row.items()}}
    undefined = run([nm, '-u', image], out / 'native' / 'image-undefined.nm.txt').split()
    final_undefined = [s for s in undefined if re.match(r'^[A-Za-z_][\w.@$]*$', s)]
    evidence = dict(identity=C.identity(platform, config.get('sdk_version')), platform=platform,
        image=dict(path=str(image), sha256=C.digest(image)), map=dict(path=config['map'], sha256=C.digest(config['map']),
        format=parsed['format']), roles=config['roles'], archives=archives, selected=selected,
        product_catalog_archives=config['product_catalog_archives'],
        dynamic_needed=needed(platform, image, out / 'native'), final_undefined=final_undefined,
        system_exports=config.get('system_exports', []))
    canon = (lambda s: s[1:] if s.startswith('_') else s) if config.get('apple') else (lambda s: s)
    findings = M.audit(_as_sets(evidence), canon)
    if platform in ('linux', 'android'):
        readelf = tool(('llvm-readelf', 'readelf'))
        dynamic = dict(symbols=M.parse_dyn_syms(run([readelf, '-W', '--dyn-syms', image], out / 'native' / 'dyn-syms.txt')),
                       verneed=M.parse_verneed(run([readelf, '-W', '-V', image], out / 'native' / 'versions.txt')),
                       needed=evidence['dynamic_needed'])
        more, waiting = M.audit_dynamic(dynamic)
        findings += more
        pending += waiting
        evidence['dynamic'] = dynamic
    else:
        pending.append(dict(kind='dynamic_symbol_versions_not_applicable_or_not_implemented', platform=platform))
    references = M.sqlite_reference_rows(_as_sets(evidence), canon)
    result = dict(evidence['identity'], pending=pending, sqlite_references=references, image=evidence['image'], map=evidence['map'], findings=findings,
                  passed=not findings, selected_members=len(parsed['members']), archives=len(archives))
    for flag in C.ACCEPT_FLAGS:
        result[flag] = False
    C.save(out / 'evidence.json', evidence)
    C.save(out / 'result.json', result)
    return result


def _as_sets(evidence):
    copy = dict(evidence)
    copy['archives'] = {a: {m: {k: set(v) for k, v in row.items()} for m, row in t.items()}
                        for a, t in evidence['archives'].items()}
    return copy
