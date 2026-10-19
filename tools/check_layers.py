#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check compiled EXReader object references against the staged layer graph.

Requires GNU/LLVM nm and an unstripped CMake build. This checks external symbol
references in that configuration, not type/macro dependencies or dead code.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess


def references(build, nm):
    folder = build / 'CMakeFiles/exreader.dir'
    objects = sorted(p for p in folder.rglob('*')
                     if p.name.endswith(('.c.o', '.c.obj')))
    if not objects:
        raise ValueError('No EXReader C objects; build the exreader target first')
    # One invocation avoids spawning a process for each source file.
    result = subprocess.run([nm, '-g', '-P', '-A', *map(str, objects)],
                            check=True, capture_output=True, text=True)
    sources = {p.name.rsplit('.', 1)[0] for p in objects}
    owners, imports = {}, []
    for line in result.stdout.splitlines():
        match = re.match(r'^(.+?): (exr_\w+) ([A-Za-z])(?:\s|$)', line)
        if not match:
            continue
        path, symbol, kind = match.groups()
        source = Path(path).name.rsplit('.', 1)[0]
        if kind == 'U':
            imports.append((source, symbol))
        elif kind.isupper():
            if symbol in owners and owners[symbol] != source:
                raise ValueError(f'Ambiguous symbol {symbol}')
            owners[symbol] = source
    if not owners:
        raise ValueError('nm output contained no EXReader definitions')
    edges = {(source, owners[symbol], symbol) for source, symbol in imports
             if symbol in owners and owners[symbol] != source}
    return sources, edges


def permitted(layers, source, target):
    pending, seen = [source], set()
    while pending:
        layer = pending.pop()
        if layer == target:
            return True
        if layer not in seen:
            seen.add(layer)
            pending.extend(layers[layer])
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    parser.add_argument('--nm')
    parser.add_argument('--manifest', type=Path,
                        default=Path(__file__).with_name('layers.json'))
    parser.add_argument('--prune', action='store_true',
                        help='Remove resolved exceptions; never adds exceptions')
    args = parser.parse_args()
    cache = (args.build / 'CMakeCache.txt').read_text(encoding='utf-8')
    cached = re.search(r'^CMAKE_NM:FILEPATH=(.+)$', cache, re.M)
    nm = args.nm or (cached[1] if cached else shutil.which('nm'))
    if not nm:
        parser.error('GNU/LLVM nm is required')
    config = json.loads(args.manifest.read_text(encoding='utf-8'))
    layers, files = config['layers'], config['files']
    for layer, deps in layers.items():
        if layer in deps or any(dep not in layers for dep in deps):
            parser.error(f'Invalid layer dependencies: {layer}')
        if any(permitted(layers, dep, layer) for dep in deps):
            parser.error(f'Layer graph contains a cycle: {layer}')
    if any(layer not in layers for layer in files.values()):
        parser.error('Unknown file layer')
    sources, edges = references(args.build, nm)
    if sources != files.keys():
        parser.error(f'Source inventory mismatch: new={sorted(sources-files.keys())}, '
                     f'missing={sorted(files.keys()-sources)}')
    inverse = {edge for edge in edges
               if not permitted(layers, files[edge[0]], files[edge[1]])}
    baseline = {tuple(edge) for edge in config['exceptions']}
    new = inverse - baseline
    for source, target, symbol in sorted(new):
        print(f'NEW: {source} -> {target}: {symbol}')
    if args.prune and not new:
        config['exceptions'] = sorted(map(list, inverse))
        args.manifest.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    print(f'{len(sources)} objects, {len(edges)} symbol references, '
          f'{len(inverse)} remaining inverse references, {len(new)} new')
    return bool(new)


if __name__ == '__main__':
    raise SystemExit(main())
