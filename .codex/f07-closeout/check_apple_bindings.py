"""Retain dyld bindings/exports for already authenticated Mach-O bytes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parent
source = Path('C:/Users/Oscar/OneDrive/Desktop/deepseekHarness/.tmp/exr-baseline/tools/f07_authoritative_symbols_20261103.py')
spec = importlib.util.spec_from_file_location('f07', source)
f07 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f07)
f07.START = time.monotonic()
bin_dir = ROOT / 'llvm-tools/llvm-tools-1.99.0-x86_64-pc-windows-msvc/llvm-tools-preview/lib/rustlib/x86_64-pc-windows-msvc/bin'
objdump = bin_dir / 'llvm-objdump.exe'
observations = []
for name in ('macos-0.bin', 'iphone-0.bin', 'ipad-0.bin', 'library-macos-53.bin', 'library-iphone-53.bin'):
    p = ROOT / name
    ops = [f07.run([str(objdump), '--macho', '--private-header', '--dylibs-used', '--dylib-id', str(p)]),
           f07.run([str(objdump), '--macho', '--bind', '--lazy-bind', '--weak-bind', str(p)]),
           f07.run([str(objdump), '--macho', '--exports-trie', str(p)]),
           f07.run([str(objdump), '--macho', '--dyld-info', str(p)]),
           f07.run([str(objdump), '--macho', '--private-headers', str(p)])]
    assert all(f07.operation_ok(op) for op in ops)
    sqlite_exports = [line for line in ops[2]['out'].splitlines() if re.search(r'\b_sqlite3_', line)]
    sqlite_bindings = [line for op in (ops[1], ops[3]) for line in op['out'].splitlines() if re.search(r'\b_sqlite3_', line)]
    record = {'member': name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'operations': ops,
              'sqlite_export_lines': sqlite_exports, 'sqlite_binding_lines': sqlite_bindings}
    observations.append(record)
    print(name, 'exports=', len(sqlite_exports), 'bindings=', len(sqlite_bindings), flush=True)
(ROOT / 'apple-bindings-observations.json').write_text(json.dumps(observations, indent=2), encoding='utf-8')
