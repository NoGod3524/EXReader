"""Actions-only real 3.40/3.41 preload regressions for source and installed use."""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess

assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
p = argparse.ArgumentParser()
for key in ('sdk340', 'sdk341', 'stage340', 'stage341', 'module', 'output'):
    p.add_argument('--' + key, type=Path, required=True)
a = p.parse_args()
out = a.output.resolve(); out.parent.mkdir(parents=True, exist_ok=True)
summary = {key: os.environ[value] for key, value in
           [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')]}
summary.update(accepted=False, cases={}, failures=[], sdk={}, guard_files={})
template = '''cmake_minimum_required(VERSION 3.24)
project(ExistingSdkTargets LANGUAGES C CXX)
if(PRELOAD_KIND STREQUAL "private")
  set(PACKAGE_PREFIX_DIR "${PRELOADED}")
  include("${PRELOADED}/lib/cmake/EXReader/EXReaderDependencies.cmake")
  set(_observe EXReader::vendor_file_miniz)
else()
  set(EXReader_DIR "${PRELOADED}/lib/cmake/EXReader")
  find_package(EXReader ${PRELOAD_VERSION} EXACT CONFIG REQUIRED COMPONENTS library)
  set(_observe EXReader::exr_library)
endif()
get_target_property(_before "${_observe}" IMPORTED_LOCATION)
if(NOT _before)
  get_target_property(_configs "${_observe}" IMPORTED_CONFIGURATIONS)
  list(GET _configs 0 _config)
  string(TOUPPER "${_config}" _config)
  get_target_property(_before "${_observe}" IMPORTED_LOCATION_${_config})
endif()
file(WRITE "${CMAKE_BINARY_DIR}/target-before.txt" "${_before}")
set(EXReader_DIR "${SELECTED}/lib/cmake/EXReader")
if(ROUTE STREQUAL "source")
  set(EXR_SDK "${SELECTED}")
  if(SELECT_VERSION STREQUAL "3.41.0")
    set(EXR_SDK_VERSION 3.41.0 CACHE STRING "Explicit approved candidate" FORCE)
  endif()
  add_subdirectory("${MODULE}" module)
else()
  set(EXReaderOriginalExport_DIR "${PACKAGE}/lib/cmake/EXReaderOriginalExport")
  find_package(EXReaderOriginalExport 0.1.0 EXACT CONFIG REQUIRED)
endif()
get_target_property(_after "${_observe}" IMPORTED_LOCATION)
if(NOT _after)
  get_target_property(_after "${_observe}" IMPORTED_LOCATION_${_config})
endif()
file(WRITE "${CMAKE_BINARY_DIR}/target-after.txt" "${_after}")
file(WRITE "${CMAKE_BINARY_DIR}/reported-version.txt" "${EXReader_VERSION}")
'''
try:
    sdks = {'3.40.0': a.sdk340.resolve(), '3.41.0': a.sdk341.resolve()}
    packages = {'3.40.0': a.stage340.resolve(), '3.41.0': a.stage341.resolve()}
    for version, sdk in sdks.items():
        header = sdk / 'include/exr/base.h'
        assert '#define EXR_VERSION "' + version + '"' in header.read_text(), 'real SDK header differs'
        config = sdk / 'lib/cmake/EXReader/EXReaderConfig.cmake'
        assert 'set(EXReader_VERSION "' + version + '")' in config.read_text(), 'real SDK Config differs'
        summary['sdk'][version] = {'prefix': str(sdk), 'header_sha256': hashlib.sha256(header.read_bytes()).hexdigest()}
        package_config = packages[version] / 'lib/cmake/EXReaderOriginalExport'
        for name in ('EXReaderOriginalExportConfig.cmake', 'EXReaderSdkTargetGuard.cmake'):
            path = package_config / name
            if path.exists():
                dest = out.parent / 'configs' / (version + '-' + name)
                dest.parent.mkdir(exist_ok=True); shutil.copyfile(path, dest)
                summary['guard_files'][version + '/' + name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for preload_kind, route in itertools.product(('full', 'private'), ('source', 'installed')):
        for preloaded, selected in (('3.40.0', '3.41.0'), ('3.41.0', '3.40.0'),
                                   ('3.40.0', '3.40.0'), ('3.41.0', '3.41.0')):
            name = preload_kind + '-' + route + '-' + preloaded + '-to-' + selected
            source = out.parent / name / 'source'; source.mkdir(parents=True)
            build = source.parent / 'build'
            (source / 'CMakeLists.txt').write_text(template, encoding='utf-8')
            command = ['cmake', '-S', str(source), '-B', str(build), '-G', 'Ninja',
                       '-DCMAKE_BUILD_TYPE=Release', '-DPRELOADED=' + str(sdks[preloaded]),
                       '-DPRELOAD_VERSION=' + preloaded, '-DSELECTED=' + str(sdks[selected]),
                       '-DSELECT_VERSION=' + selected, '-DROUTE=' + route,
                       '-DPRELOAD_KIND=' + preload_kind,
                       '-DMODULE=' + str(a.module.resolve()), '-DPACKAGE=' + str(packages[selected])]
            process = subprocess.run(command, capture_output=True, text=True, timeout=600)
            log = source.parent / 'configure.log'; text = process.stdout + process.stderr
            log.write_text('$ ' + ' '.join(command) + '\n' + text, encoding='utf-8')
            before = (build / 'target-before.txt').read_text().strip()
            assert Path(before).resolve().is_relative_to(sdks[preloaded]), 'preload did not create its real SDK target'
            assert Path(before).is_file(), 'preloaded actual archive absent'
            must_refuse = preloaded != selected
            actual_refusal = process.returncode != 0 and ('SDK imported target header origin mismatch' in text
                                                        or 'SDK imported target archive origin mismatch' in text)
            after = (build / 'target-after.txt').read_text().strip() if (build / 'target-after.txt').exists() else None
            item = {'preloaded_version': preloaded, 'selected_version': selected, 'route': route, 'preload_kind': preload_kind,
                    'exit': process.returncode, 'refusal_expected': must_refuse, 'refused_by_origin_gate': actual_refusal,
                    'preloaded_location': before, 'preloaded_archive_sha256': hashlib.sha256(Path(before).read_bytes()).hexdigest(),
                    'post_location': after, 'reported_version': (build / 'reported-version.txt').read_text().strip()
                    if (build / 'reported-version.txt').exists() else None,
                    'log': str(log.relative_to(out.parent)), 'passed': actual_refusal if must_refuse else process.returncode == 0}
            summary['cases'][name] = item
            if not item['passed']:
                summary['failures'].append(name + (': existing foreign target escaped EXACT' if process.returncode == 0
                                                  else ': refusal was not the intended provenance gate'))
    assert len(summary['cases']) == 16
    summary['accepted'] = not summary['failures']
except Exception as error:
    summary['failures'].append(repr(error))
finally:
    out.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary), flush=True)
raise SystemExit(0 if summary['accepted'] else 1)
