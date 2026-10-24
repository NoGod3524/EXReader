#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Registration of the thirteen optional application packages.

This table is the registration, not the evidence: every version, header, archive,
configuration file, licence text and system dependency it names is read back from
the installed prefix, and the composed job fails when the prefix disagrees.

id                package                 project                     version
catalog           product catalog         EXReaderProductCatalog      0.1.0  bundled SQLite
revisions         revision store          EXReaderRevisions           0.3.0
commands          typed book commands     EXReaderCommands            0.1.0
desktop-metadata  desktop metadata        EXReaderDesktopMetadata     0.1.0
webdav            WebDAV transport        EXReaderWebDAV              0.2.0  TLS + XML
session           account session         EXReaderSession             0.1.0
sync              synchronisation         EXReaderSync                0.1.0  crypto
credentials       credential storage      EXReaderCredentials         0.1.0  keyring
reading-state     reading state           EXReaderReadingState        0.1.0
search            in-book search          EXReaderSearch              0.1.0
preferences       preferences             EXReaderPreferences         0.1.0
batch-import      batch import            EXReaderBatchImport         0.1.0
sideload          sideload and export     EXReaderSideload            0.1.0
"""

import re

MIT_SHARED = ('shared', 'share/exreader/LICENSE')
MIT_OWN = ('package', None)

PACKAGES = [
    {'id': 'catalog', 'name': 'EXReader product catalog', 'project': 'EXReaderProductCatalog',
     'find': 'EXReaderProductCatalog', 'version': '0.1.0', 'source': 'apps/reader/store/native',
     'headers': ['include/exreader-product/catalog.h', 'include/exreader-product/sqlite3.h'],
     'archives': ['reader_catalog', 'reader_catalog_sqlite'],
     'assets': ['share/exreader-product/001_catalog.sql',
                'share/exreader-product/sqlite-public-domain.txt'],
     'config': 'lib/cmake/EXReaderProductCatalog',
     'licence': MIT_SHARED,
     'target': 'EXReaderProductCatalog::reader_catalog',
     'bundled': [{'library': 'sqlite3', 'archive': 'reader_catalog_sqlite',
                  'material': 'share/exreader-product/sqlite-public-domain.txt'}],
     'system': {'linux': [], 'windows': [], 'macos': []}},
    {'id': 'revisions', 'name': 'EXReader revision store', 'project': 'EXReaderRevisions',
     'find': 'EXReaderRevisions', 'version': '0.3.0', 'source': 'apps/reader/revisions',
     'headers': ['include/reader_revisions.h', 'include/reader_projection.h'],
     'archives': ['reader_revisions', 'reader_revision_hash'], 'assets': [],
     'config': 'lib/cmake/EXReaderRevisions', 'licence': MIT_SHARED,
     'target': 'EXReaderRevisions::reader_revisions', 'bundled': [],
     'system': {'linux': [], 'windows': [], 'macos': []}},
    {'id': 'commands', 'name': 'EXReader typed book commands', 'project': 'EXReaderCommands',
     'find': 'EXReaderCommands', 'version': '0.1.0', 'source': 'apps/reader/commands',
     'headers': ['include/reader_commands.h'], 'archives': ['reader_commands'], 'assets': [],
     'config': 'lib/cmake/EXReaderCommands', 'licence': MIT_SHARED,
     'target': 'EXReaderCommands::reader_commands', 'bundled': [],
     'system': {'linux': [], 'windows': [], 'macos': []}},
    {'id': 'desktop-metadata', 'name': 'EXReader desktop metadata',
     'project': 'EXReaderDesktopMetadata', 'find': 'EXReaderDesktopMetadata', 'version': '0.1.0',
     'source': 'apps/reader/desktop-metadata',
     'headers': ['include/reader_metadata.h'], 'archives': ['reader_desktop_metadata'], 'assets': [],
     'config': 'lib/cmake/EXReaderDesktopMetadata', 'licence': MIT_SHARED,
     'target': 'EXReaderDesktopMetadata::reader_desktop_metadata', 'bundled': [],
     'system': {'linux': [], 'windows': [], 'macos': []}},
    {'id': 'webdav', 'name': 'EXReader WebDAV transport', 'project': 'EXReaderWebDAV',
     'find': 'EXReaderWebDAV', 'version': '0.2.0', 'source': 'extras/webdav',
     'headers': ['include/exr_webdav.h'],
     'android_only': ['include/exr_webdav_android.h'],
     'archives': ['exr_webdav'], 'assets': ['share/exreader-webdav/LICENSE.txt'],
     'config': 'lib/cmake/EXReaderWebDAV', 'licence': MIT_OWN,
     'target': 'EXReaderWebDAV::exr_webdav', 'bundled': [],
     'system': {'linux': ['libcurl', 'libxml2'], 'windows': ['winhttp', 'xmllite', 'shlwapi'],
                'macos': ['libcurl', 'libxml2']}},
    {'id': 'session', 'name': 'EXReader account session', 'project': 'EXReaderSession',
     'find': 'EXReaderSession', 'version': '0.1.0', 'source': 'apps/reader/session',
     'headers': ['include/reader_session.h'], 'archives': ['reader_session'], 'assets': [],
     'config': 'lib/cmake/EXReaderSession', 'licence': MIT_SHARED,
     'target': 'EXReaderSession::reader_session', 'bundled': [],
     'system': {'linux': [], 'windows': [], 'macos': []}},
    {'id': 'sync', 'name': 'EXReader synchronisation', 'project': 'EXReaderSync',
     'find': 'EXReaderSync', 'version': '0.1.0', 'source': 'apps/reader/sync',
     'headers': ['include/reader_sync.h'], 'archives': ['reader_sync'], 'assets': [],
     'config': 'lib/cmake/EXReaderSync', 'licence': MIT_SHARED,
     'target': 'EXReaderSync::reader_sync', 'bundled': [],
     'system': {'linux': ['libcrypto'], 'windows': ['bcrypt'], 'macos': []}},
    {'id': 'credentials', 'name': 'EXReader credential storage', 'project': 'EXReaderCredentials',
     'find': 'EXReaderCredentials', 'version': '0.1.0', 'source': 'extras/credentials',
     'headers': ['include/exr_credentials.h'], 'archives': ['exr_credentials'],
     'assets': ['share/exreader-credentials/LICENSE.txt'],
     'config': 'lib/cmake/EXReaderCredentials', 'licence': MIT_OWN,
     'target': 'EXReaderCredentials::exr_credentials', 'bundled': [],
     'system': {'linux': ['libsecret-1'], 'windows': ['advapi32'],
                'macos': ['Security', 'CoreFoundation']}},
    {'id': 'reading-state', 'name': 'EXReader reading state', 'project': 'EXReaderReadingState',
     'find': 'EXReaderReadingState', 'version': '0.1.0', 'source': 'apps/reader/reading-state',
     'headers': ['include/reader_reading_state.h'], 'archives': ['reader_reading_state'],
     'assets': [], 'config': 'lib/cmake/EXReaderReadingState', 'licence': MIT_SHARED,
     'target': 'EXReaderReadingState::reader_reading_state', 'bundled': [],
     'system': {'linux': [], 'windows': [], 'macos': []}},
    {'id': 'search', 'name': 'EXReader in-book search', 'project': 'EXReaderSearch',
     'find': 'EXReaderSearch', 'version': '0.1.0', 'source': 'apps/reader/search',
     'headers': ['include/reader_search.h'], 'archives': ['reader_search'], 'assets': [],
     'config': 'lib/cmake/EXReaderSearch', 'licence': MIT_SHARED,
     'target': 'EXReaderSearch::reader_search', 'bundled': [],
     'system': {'linux': [], 'windows': [], 'macos': []}},
    {'id': 'preferences', 'name': 'EXReader preferences', 'project': 'EXReaderPreferences',
     'find': 'EXReaderPreferences', 'version': '0.1.0', 'source': 'apps/reader/preferences',
     'headers': ['include/reader_preferences.h'], 'archives': ['reader_preferences'], 'assets': [],
     'config': 'lib/cmake/EXReaderPreferences', 'licence': MIT_SHARED,
     'target': 'EXReaderPreferences::reader_preferences', 'bundled': [],
     'system': {'linux': [], 'windows': [], 'macos': []}},
    {'id': 'batch-import', 'name': 'EXReader batch import', 'project': 'EXReaderBatchImport',
     'find': 'EXReaderBatchImport', 'version': '0.1.0', 'source': 'apps/reader/batch-import',
     'headers': ['include/reader_batch_import.h'], 'archives': ['reader_batch_import'],
     'assets': [], 'config': 'lib/cmake/EXReaderBatchImport', 'licence': MIT_SHARED,
     'target': 'EXReaderBatchImport::reader_batch_import', 'bundled': [],
     'system': {'linux': [], 'windows': [], 'macos': []}},
    {'id': 'sideload', 'name': 'EXReader sideload and export', 'project': 'EXReaderSideload',
     'find': 'EXReaderSideload', 'version': None, 'version_source': 'none',
     'source': 'extras/sideload',
     'headers': ['include/exr_sideload.h'], 'archives': ['exr_sideload'], 'assets': [],
     'config': 'lib/cmake/EXReaderSideload', 'licence': MIT_SHARED,
     'target': 'EXReaderSideload::exr_sideload', 'bundled': [],
     'system': {'linux': [], 'windows': [], 'macos': []}},
]

# Symbol families that identify the library that must supply them. The first
# matching family names the library.
FAMILIES = [
    ('libcurl', ('curl_easy_', 'curl_multi_', 'curl_slist_', 'curl_global_', 'curl_share_',
                 'curl_version')),
    ('libxml2', ('xmlRead', 'xmlParse', 'xmlDoc', 'xmlFree', 'xmlNew', 'xmlNode', 'xmlGet',
                 'xmlStr', 'xmlXPath', 'xmlBuffer', 'xmlOutput', 'xmlInit', 'xmlCleanup',
                 'xmlSave', 'xmlTextReader', 'xmlCtxt', 'xmlSchema', 'xmlURI')),
    ('libcrypto', ('EVP_', 'OPENSSL_', 'CRYPTO_', 'SHA256_', 'SHA1_', 'SHA512_', 'HMAC_',
                   'RAND_bytes', 'ERR_', 'OPENSSL_init', 'crypto_', 'CC_SHA')),
    ('bcrypt', ('BCrypt',)),
    ('libsecret-1', ('secret_',)),
    ('Security', ('SecItem', 'SecKeychain', 'SecCopy', 'SecTrust', 'SecCertificate', 'SecIdentity',
                  'SecRandomCopyBytes', 'SecAccess')),
    ('CoreFoundation', ('CFRelease', 'CFRetain', 'CFString', 'CFData', 'CFDictionary', 'CFURL',
                        'CFGetTypeID', 'CFArray', 'CFNumber', 'CFError', 'CFBundle', 'CFRead',
                        'CFWrite', 'CFAllocator')),
    ('Foundation', ('NSURL', 'NSString', 'NSData', 'NSFileManager', 'NSJSONSerialization',
                    'NSObject', 'NSMutable')),
    ('advapi32', ('CredRead', 'CredWrite', 'CredDelete', 'CredFree', 'CredEnumerate',
                  'CredUIPromptForCredentials', 'CredMarshalCredential')),
    ('winhttp', ('WinHttp',)),
    ('xmllite', ('CreateXmlReader', 'CreateXmlWriter', 'XmlLite')),
    ('shlwapi', ('PathFileExists', 'PathRemoveFileSpec', 'SHLoadIndirectString')),
    ('user32', ('MessageBox', 'GetDC', 'ReleaseDC', 'CreateWindow')),
    ('gdi32', ('CreateFont', 'GetGlyphOutline')),
    ('sqlite3', ('sqlite3_',)),
]

# C and C++ runtime symbols are system by definition and are never redistributed.
RUNTIME_PREFIXES = ('_Z', '__cxx', '__gxx', '_Unwind', 'operator new', 'operator delete',
                    '__gxx_personality', '__cxa', '__dynamic_cast', '__stack_chk', '___chkstk',
                    '__security_', '_except_handler', '__CxxFrameHandler', '?',
                    '__imp_', '__std_', '_initterm', '_amsg_exit', '__acrt_', '_configure_narrow',
                    '_callnewh', '_errno', '_invalid_parameter', '_invoke_watson', '__p___argc',
                    '__p___argv', '_cexit', '_get_initial_narrow')
RUNTIME_NAMES = frozenset((
    'malloc', 'calloc', 'realloc', 'free', 'memcpy', 'memmove', 'memset', 'memcmp', 'strlen',
    'strcmp', 'strncmp', 'strcpy', 'strncpy', 'strcat', 'strstr', 'strchr', 'strrchr', 'strtol',
    'strtoll', 'strtod', 'atoi', 'atol', 'abs', 'qsort', 'bsearch', 'printf', 'fprintf', 'sprintf',
    'snprintf', 'vsnprintf', 'puts', 'fputs', 'fwrite', 'fread', 'fopen', 'fclose', 'fflush',
    'fseek', 'ftell', 'remove', 'rename', 'time', 'clock', 'clock_gettime', 'localtime',
    'gmtime', 'mktime', 'strftime', 'abort', 'exit', 'atexit', 'getenv', 'setlocale',
    'tolower', 'toupper', 'isdigit', 'isalpha', 'isspace', 'sqrt', 'pow', 'floor', 'ceil',
    'fabs', 'sin', 'cos', 'atan2', 'log', 'exp', 'fmod', 'round', 'lround', 'trunc',
    '__errno_location', '__assert_fail', '__stack_chk_fail', 'pthread_mutex_lock',
    'pthread_mutex_unlock', 'pthread_mutex_init', 'pthread_mutex_destroy', 'pthread_create',
    'pthread_join', 'pthread_cond_wait', 'pthread_cond_signal', 'pthread_once',
    'pthread_key_create', 'pthread_getspecific', 'pthread_setspecific', 'pthread_self',
    'GetLastError', 'SetLastError', 'CloseHandle', 'CreateFileW', 'ReadFile', 'WriteFile',
    'GetFileSizeEx', 'SetFilePointerEx', 'HeapAlloc', 'HeapFree', 'GetProcessHeap', 'Sleep',
    'GetTickCount', 'GetTickCount64', 'QueryPerformanceCounter', 'GetSystemTimeAsFileTime',
    'InitializeCriticalSection', 'EnterCriticalSection', 'LeaveCriticalSection',
    'DeleteCriticalSection', 'InitializeSRWLock', 'AcquireSRWLockExclusive',
    'ReleaseSRWLockExclusive', 'WaitForSingleObject', 'CreateEventW', 'SetEvent',
    'MultiByteToWideChar', 'WideCharToMultiByte', 'GetModuleHandleW', 'LoadLibraryW',
    'GetProcAddress', 'FreeLibrary', 'FormatMessageW', 'LocalFree', 'GetCurrentProcessId',
    'GetCurrentThreadId', 'CreateThread', '_beginthreadex', '_endthreadex',
))


def family(symbol):
    """Name the library a symbol belongs to, or 'runtime' for C/C++ runtime code."""
    plain = symbol[6:] if symbol.startswith('__imp_') else symbol
    for library, prefixes in FAMILIES:
        for prefix in prefixes:
            if plain.startswith(prefix):
                return library
    if symbol in RUNTIME_NAMES:
        return 'runtime'
    for prefix in RUNTIME_PREFIXES:
        if symbol.startswith(prefix):
            return 'runtime'
    return None


def by_id(identifier):
    for package in PACKAGES:
        if package['id'] == identifier:
            return package
    raise KeyError(identifier)


def archive_names(package, extension):
    return ['%s%s' % (name, extension) for name in package['archives']]


REGISTERED_IDS = tuple(package['id'] for package in PACKAGES)

CANONICAL = {
    'curl': 'libcurl', 'libcurl': 'libcurl',
    'xml2': 'libxml2', 'libxml2': 'libxml2',
    'crypto': 'libcrypto', 'libcrypto': 'libcrypto',
    'ssl': 'libssl', 'libssl': 'libssl',
    'secret-1': 'libsecret-1', 'libsecret-1': 'libsecret-1',
    'security': 'Security', 'corefoundation': 'CoreFoundation', 'foundation': 'Foundation',
    'pthread': 'Threads', 'thread': 'Threads',
}


def canonical(name):
    """Map a link name, framework name or family name to one library identity."""
    return CANONICAL.get(str(name).lower(), str(name))


def _digest_bytes(data):
    import hashlib as _hashlib
    return _hashlib.sha256(data).hexdigest()


def resolve(package, index):
    """Read one package's registered artefacts back from the installed prefix.

    index maps stage-relative paths to their bytes, so the generator (disk) and
    the aggregate (artifact) resolve exactly the same way.
    """
    missing = []
    record = {'id': package['id'], 'version': None, 'config_files': [], 'headers': [],
              'archives': [], 'assets': [], 'licence': None, 'missing': missing}
    prefix = package['config'] + '/'
    for path in sorted(index):
        if path.startswith(prefix):
            record['config_files'].append({'path': path, 'bytes': len(index[path]),
                                           'sha256': _digest_bytes(index[path])})
    version_file = package['config'] + '/' + package['find'] + 'ConfigVersion.cmake'
    if version_file in index:
        import re as _re
        found = _re.search(r'set\(PACKAGE_VERSION\s+"([^"]+)"\)', index[version_file].decode('utf-8', 'replace'))
        record['version'] = found.group(1) if found else None
        record['version_source'] = 'config'
    elif package.get('version') is None:
        # Registered as unversioned: this package installs no version file.
        record['version_source'] = 'none'
    else:
        record['version_source'] = 'missing'
        missing.append(version_file)
    for path in package['headers']:
        if path in index:
            record['headers'].append({'path': path, 'bytes': len(index[path]),
                                      'sha256': _digest_bytes(index[path])})
        else:
            missing.append(path)
    for name in package['archives']:
        found = None
        for extension in ('.a', '.lib'):
            for prefix in ('lib/', 'lib/lib'):
                candidate = prefix + name + extension
                if candidate in index:
                    found = candidate
                    break
            if found:
                break
        if found is None:
            missing.append('lib/' + name + '.a')
            continue
        record['archives'].append({'path': found, 'name': found.split('/')[-1],
                                   'bytes': len(index[found]), 'sha256': _digest_bytes(index[found])})
    for path in package['assets']:
        if path in index:
            record['assets'].append({'path': path, 'bytes': len(index[path]),
                                     'sha256': _digest_bytes(index[path])})
        else:
            missing.append(path)
    mode, own_path = package['licence']
    material = own_path if own_path else 'share/exreader/LICENSE'
    if mode == 'package':
        material = next((path for path in package['assets'] if 'LICENSE' in path.upper()), None)
    if material and material in index:
        record['licence'] = {'mode': mode, 'path': material, 'bytes': len(index[material]),
                             'sha256': _digest_bytes(index[material])}
    else:
        missing.append(material or 'licence')
    return record


def symbol_providers(symbols):
    """family -> archives in the prefix that define at least one symbol of it."""
    result = {}
    for path in symbols:
        for symbol in symbols[path].get('defined', []):
            library = family(symbol)
            if library is None:
                continue
            result.setdefault(library, set()).add(path)
    return {library: sorted(paths) for library, paths in result.items()}


def external_from_symbols(own_archives, symbols):
    """Symbols the package needs that no archive in the prefix defines."""
    undefined = set()
    for path in own_archives:
        undefined |= set(symbols.get(path, {}).get('undefined', []))
    provided = set()
    for path in symbols:
        provided |= set(symbols[path].get('defined', []))
    external = sorted(undefined - provided)
    families, unknown = {}, []
    for symbol in external:
        library = family(symbol)
        if library is None:
            unknown.append(symbol)
        else:
            families[library] = families.get(library, 0) + 1
    import hashlib as _hashlib
    return {'external_count': len(external),
            'external_sha256': _hashlib.sha256(('\n'.join(external) + '\n').encode('utf-8')).hexdigest(),
            'families': families,
            'unknown_count': len(unknown), 'unknown_sample': unknown[:16]}


LIBRARY_FILE = None


def library_name(base):
    """Reduce an installed library file name to its canonical library identity."""
    name = base
    for extension in ('.so', '.dylib', '.tbd', '.a', '.lib'):
        if extension in name:
            name = name.split(extension)[0]
            break
    if name.startswith('lib'):
        name = name[3:]
    return canonical(name)


def link_evidence(tokens, archive_names, expected):
    """Split one real link command: prefix archives, system libraries, frameworks."""
    archives, system, frameworks = [], [], []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == '-framework' and index + 1 < len(tokens):
            frameworks.append(tokens[index + 1])
            index += 2
            continue
        parts = token.split(',')[1:] if token.startswith('-Wl,') else [token]
        for part in parts:
            if part.startswith('-l') and len(part) > 2 and not part.startswith(('-libpath', '-link')):
                name = part[2:]
                base = 'lib%s.a' % name
                if base in archive_names:
                    archives.append(base)
                else:
                    system.append(canonical(name))
            elif not part.startswith(('-', '/')) and re.search(
                    r'[.](?:so(?:[.][0-9]+)*|dylib|tbd|a|lib)$', part, re.I):
                base = part.replace('\\', '/').split('/')[-1]
                if base in archive_names:
                    archives.append(base)
                else:
                    system.append(library_name(base))
        index += 1
    observed = sorted(set(system) | set(canonical(name) for name in frameworks))
    missing = sorted(name for name in expected if canonical(name) not in observed)
    return {'archives': sorted(set(archives)), 'system_libraries': sorted(set(system)),
            'frameworks': sorted(set(frameworks)), 'observed_libraries': observed,
            'expected_missing': missing}
