"""Actions-only real old SDK and imported-target cache checks."""
import json
import os
from pathlib import Path
import shutil
import subprocess

OLD_SDK = '9854061be331fe603a1822d9b2b36ee357154927'

def check(core, out, raw, old, product, sdk, dav):
    # Genuine independent old source; no header/version/target substitution.
    src = core.archive(OLD_SDK, 'sdk340-source')
    core.run(['cmake', '--preset', 'reading-library', '-S', src,
              '-B', out / 'sdk340-build', '-DCMAKE_INSTALL_PREFIX=' + str(out / 'sdk340-stage')],
             'sdk340-configure')
    core.run(['cmake', '--build', out / 'sdk340-build', '--parallel', '4'], 'sdk340-build', 3000)
    core.run(['cmake', '--install', out / 'sdk340-build'], 'sdk340-install')
    sdk340 = out / 'sdk340-stage'
    prefix = ';'.join(map(str, [raw, dav, product, sdk]))
    def path(p): return p.absolute().as_posix()
    def find(package, version, location, components=''):
        return ('find_package(' + package + ' ' + version + ' EXACT CONFIG REQUIRED ' + components
                + ' PATHS "' + path(location / 'lib/cmake' / package) + '" NO_DEFAULT_PATH)\n')
    def configure(name, body, expected=None, selected_prefix=None):
        source = out / (name + '-source');source.mkdir()
        (source / 'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.24)\nproject(OriginGuard LANGUAGES C CXX)\n'
            + 'if(MSVC)\n  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")\nendif()\n' + body)
        (source / 'main.c').write_text('int main(void){return 0;}\n')
        p = subprocess.run(['cmake', '-S', source, '-B', out / name, '-G', 'Ninja',
                            '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_PREFIX_PATH=' + (selected_prefix or prefix)],
                           capture_output=True, encoding='utf-8', errors='replace')
        log = p.stdout + p.stderr
        (out / (name + '.log')).write_text(log)
        if expected:
            assert p.returncode and expected in log, (name, p.returncode, log)
        else:
            assert p.returncode == 0, (name, log)
        return out / name, source
    binary, proof = configure('actual-sdk340', find('EXReader', '3.40.0', sdk340, 'COMPONENTS core library')
        + 'add_executable(version main.c)\ntarget_link_libraries(version PRIVATE EXReader::exr_core)\n')
    (proof / 'main.c').write_text('#include <exr/base.h>\n#include <stdio.h>\n#include <string.h>\nint main(void){puts(exr_version());return strcmp(exr_version(),"3.40.0")!=0;}\n')
    core.run(['cmake', '--build', binary], 'actual-sdk340-build')
    observed = core.run([binary / ('version' + core.SUFFIX)], 'actual-sdk340-version').strip()
    assert observed == '3.40.0'
    checks = ['genuine-3.40.0-runtime']
    reset = ('set(EXReader_DIR "' + path(sdk / 'lib/cmake/EXReader') + '" CACHE PATH "" FORCE)\n'
             + 'set(EXReaderRevisions_DIR "' + path(raw / 'lib/cmake/EXReaderRevisions') + '" CACHE PATH "" FORCE)\n')
    for name, preload, error in [
        ('cached-revisions', find('EXReaderRevisions', '0.3.0', old), 'legacy capability family'),
        ('cached-sdk340', find('EXReader', '3.40.0', sdk340, 'COMPONENTS core library'), 'EXReader::exr_'),
        ('cached-both', find('EXReader', '3.40.0', sdk340, 'COMPONENTS core library')
                       + find('EXReaderRevisions', '0.3.0', old), 'legacy capability family')]:
        configure(name, preload + reset + find('EXReaderReadingState', '0.2.0', raw), error)
        checks.append(name + '-refused')
    # A mutable caller option must not downgrade the configured candidate identity.
    configure('caller-unsets-option', find('EXReaderRevisions', '0.3.0', old)
        + reset + 'set(EXR_READER_SELECTOR_BYTES_CANDIDATE OFF)\n'
        + find('EXReaderCommands', '0.2.0', raw), 'legacy capability family')
    checks.append('caller-unset-cannot-bypass')
    relocated = out / 'relocated-candidate';shutil.copytree(raw, relocated)
    alias = out / 'candidate-alias'
    if os.name == 'nt':
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(relocated)], check=True, capture_output=True)
    else:
        alias.symlink_to(relocated, target_is_directory=True)
    for label, install in [('relocated', relocated), ('canonical-alias', alias)]:
        # Repeat find calls in the same directory to exercise safe re-inclusion.
        body = ''
        for _ in range(2):
            for package in ['EXReaderCommands', 'EXReaderSync', 'EXReaderSession',
                            'EXReaderReadingCommands', 'EXReaderAnnotationView']:
                body += find(package, '0.2.0', install)
        body += 'add_executable(version main.c)\ntarget_link_libraries(version PRIVATE EXReaderSession::reader_session)\n'
        binary, source = configure(label, body, selected_prefix=';'.join(map(str, [install, dav, product, sdk])))
        (source / 'main.c').write_text('#include <reader_session.h>\nint main(void){return 0;}\n')
        core.run(['cmake', '--build', binary], label + '-build')
        core.run([binary / ('version' + core.SUFFIX)], label + '-execute')
        checks.append(label + '-accepted')
    result = {'accepted': True, 'old_sdk_source': OLD_SDK, 'old_sdk_runtime': observed, 'checks': checks}
    (out / 'profiles.json').write_text(json.dumps(result, indent=2) + '\n')
    return result

