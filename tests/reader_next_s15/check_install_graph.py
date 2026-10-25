"""Actions-only negative controls for the EXReader 3.41 install graph.

Runs real CMake configure attempts and requires each refusal to come from the
intended version/link rule, never from a missing toolchain. The mixed-SDK case
relabels only package metadata of the approved 3.41 install (proved by hashing
the shipped archives) and first proves that relabelled graph resolves as 3.40.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
parser = argparse.ArgumentParser()
parser.add_argument('--module-src', required=True)
parser.add_argument('--stage', required=True)
parser.add_argument('--sdk', required=True)
parser.add_argument('--work', required=True)
parser.add_argument('--consumer', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
module_src = Path(args.module_src).resolve(); stage = Path(args.stage).resolve()
sdk = Path(args.sdk).resolve(); work = Path(args.work).resolve()
consumer = Path(args.consumer).resolve(); output = Path(args.output).resolve()
work.mkdir(parents=True, exist_ok=True); output.parent.mkdir(parents=True, exist_ok=True)
summary = {'accepted': False, 'platform': os.environ['RUNNER_OS'], 'cases': {}, 'failures': [],
           'sdk': {}, 'relabel': {}}


def require(v, m):
    if not v: raise AssertionError(m)


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def configure(name, source, build, prefix, extra, expect_fail, markers):
    build.mkdir(parents=True, exist_ok=True)
    command = [os.environ.get('CMAKE_EXECUTABLE', 'cmake'), '-S', str(source), '-B', str(build),
               '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
               '-DCMAKE_PREFIX_PATH=' + str(prefix)] + extra
    log = work / (name + '.log')
    proc = subprocess.run(command, capture_output=True, text=True, timeout=600)
    log.write_text(''.join(['$ ' + ' '.join(command) + '\n', proc.stdout, proc.stderr]), encoding='utf-8')
    text = proc.stdout + proc.stderr
    case = {'command': command, 'exit': proc.returncode, 'log': log.name,
            'markers': {m: (m in text) for m in markers}}
    if expect_fail:
        require(proc.returncode != 0, name + ' unexpectedly succeeded')
        missing = [m for m in markers if m not in text]
        require(not missing, name + ' did not fail for the intended reason, missing ' + repr(missing))
        case['refused'] = True
    else:
        require(proc.returncode == 0, name + ' failed: ' + text[-4000:])
        case['refused'] = False
    summary['cases'][name] = case
    return case


try:
    base = (sdk / 'include/exr/base.h').read_text()
    version = re.search(r'#define EXR_VERSION "([0-9.]+)"', base)
    abi = re.search(r'#define EXR_ABI_VERSION ([0-9]+)u', base)
    config = (sdk / 'lib/cmake/EXReader/EXReaderConfig.cmake').read_text()
    config_version = (sdk / 'lib/cmake/EXReader/EXReaderConfigVersion.cmake').read_text()
    require(version and version.group(1) == '3.41.0', 'install is not the approved 3.41 SDK')
    require(abi and abi.group(1) == '1', 'install ABI is not 1')
    require('set(EXReader_VERSION "3.41.0")' in config, 'EXReaderConfig version')
    require('set(PACKAGE_VERSION "3.41.0")' in config_version, 'EXReaderConfigVersion version')
    summary['sdk'] = {'version': version.group(1), 'abi': int(abi.group(1))}

    # The approved 3.41 install must refuse the unchanged default pin.
    configure('sdk_default_pin_refused_by_341_install', module_src, work / 'default-pin', sdk, [],
              expect_fail=True, markers=['3.40.0', 'EXReader'])
    # Any other pin is rejected before a target or header is used.
    configure('sdk_unsupported_pin_refused', module_src, work / 'unsupported-pin', sdk,
              ['-DEXR_SDK_VERSION=3.39.0'], expect_fail=True,
              markers=['Unsupported exact reader SDK version: 3.39.0'])
    # An installed module must carry its exact SDK dependency to consumers.
    configure('consumer_without_exact_sdk_refused', consumer, work / 'consumer-no-sdk', stage, [],
              expect_fail=True, markers=['EXReader', '3.41.0'])

    # Mixed graph: metadata-only relabel of the approved install, archives unchanged.
    graph = work / 'sdk-340-graph'
    if graph.exists(): shutil.rmtree(graph)
    shutil.copytree(sdk, graph)
    relabelled = graph / 'lib/cmake/EXReader/EXReaderConfig.cmake'
    text = relabelled.read_text().replace('set(EXReader_VERSION "3.41.0")', 'set(EXReader_VERSION "3.40.0")')
    relabelled.write_text(text, encoding='utf-8')
    relabelled_version = graph / 'lib/cmake/EXReader/EXReaderConfigVersion.cmake'
    text = relabelled_version.read_text().replace('set(PACKAGE_VERSION "3.41.0")', 'set(PACKAGE_VERSION "3.40.0")')
    relabelled_version.write_text(text, encoding='utf-8')
    archives = [p for p in sdk.rglob('*') if p.is_file() and p.suffix in ('.a', '.lib')]
    require(archives, 'no shipped static archive to bind')
    summary['relabel'] = {'archives': {str(p.relative_to(sdk)): sha(p) for p in archives}}
    for p in archives:
        require(sha(p) == sha(graph / p.relative_to(sdk)), 'relabel changed a shipped archive')
    tiny = work / 'graph-340-probe'
    tiny.mkdir(exist_ok=True)
    (tiny / 'CMakeLists.txt').write_text(
        'cmake_minimum_required(VERSION 3.24)\nproject(Graph340Probe LANGUAGES C)\n'
        'find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED COMPONENTS library)\n'
        'message(STATUS "graph-340-resolves ${EXReader_VERSION}")\n', encoding='utf-8')
    configure('relabelled_graph_resolves_as_340', tiny, work / 'graph-340-build', graph, [],
              expect_fail=False, markers=[])
    configure('mixed_sdk_graph_refused', consumer, work / 'consumer-mixed', stage + ';' + str(graph), [],
              expect_fail=True, markers=['EXReader', '3.41.0'])
    summary['accepted'] = True
except Exception as exc:
    summary['failures'].append(repr(exc))
finally:
    output.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary), flush=True)
raise SystemExit(0 if summary['accepted'] else 1)
