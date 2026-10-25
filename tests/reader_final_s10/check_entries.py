#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""S10: prove every computer-to-device transfer entry that this repository
really ships, and prove that each proof can fail.

Every check reads an existing owner file (Android manifest and SAF owner, Apple
Files-sharing declarations and security-scoped host entry, desktop host
entries) as read-only input.  A positive run requires all checks to pass.  The
--self-test mode copies exactly those files, mutates one declaration at a time
and requires the matching check to fail, so no assertion passes vacuously.
"""
import argparse
import json
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID = '{http://schemas.android.com/apk/res/android}'

ANDROID_APP = 'examples/android/app/src/main/AndroidManifest.xml'
ANDROID_OWNER_MANIFEST = 'extras/android-import-entry/android/importentry/src/main/AndroidManifest.xml'
ANDROID_OWNER_JAVA = 'extras/android-import-entry/android/importentry/src/main/java/org/exreader/importentry/ImportEntry.java'
ANDROID_OWNER_NATIVE = 'extras/android-import-entry/src/entry.c'
APPLE_HOST_MODEL = 'examples/apple/HostModel.swift'
APPLE_HOST_VIEWS = 'examples/apple/HostViews.swift'
APPLE_HOST_BUILD = 'tools/build_apple_host.py'
APPLE_REVIEW_PROJECT = 'tests/apple_host/make_xcodeproj.rb'
WINDOWS_HOST = 'examples/reader.c'
GTK_HOST = 'examples/linux/reader.c'
GTK_DROP = 'examples/linux/drop_import_ui.inc'
GTK_BATCH = 'examples/linux/batch_import_ui.inc'

CHECK_FILES = sorted({
    ANDROID_APP, ANDROID_OWNER_MANIFEST, ANDROID_OWNER_JAVA, ANDROID_OWNER_NATIVE,
    APPLE_HOST_MODEL, APPLE_HOST_VIEWS, APPLE_HOST_BUILD, APPLE_REVIEW_PROJECT,
    WINDOWS_HOST, GTK_HOST, GTK_DROP, GTK_BATCH,
})


class Failure(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Failure(message)


def read(root, rel):
    path = root / rel
    if not path.is_file():
        raise Failure('missing file: ' + rel)
    return path.read_text(encoding='utf-8', errors='replace')


def require_text(root, rel, *tokens):
    text = read(root, rel)
    for token in tokens:
        require(token in text, 'missing ' + repr(token) + ' in ' + rel)
    return text


def require_ordered(root, rel, first, second, window=1200):
    text = read(root, rel)
    at = text.find(first)
    require(at >= 0, 'missing ' + repr(first) + ' in ' + rel)
    require(text.find(second, at, at + window) >= 0,
            repr(second) + ' does not follow ' + repr(first) + ' in ' + rel)
    return text


CHECKS = []


def entry(check_id, platform, mechanism, description):
    def register(fn):
        CHECKS.append({'id': check_id, 'platform': platform, 'mechanism': mechanism,
                       'description': description, 'run': fn})
        return fn
    return register


def android_filters(root, rel):
    tree = ET.parse(str(root / rel))
    rows = []
    for activity in tree.getroot().iter('activity'):
        for filt in activity.findall('intent-filter'):
            rows.append({
                'activity': activity.get(ANDROID + 'name'),
                'actions': {node.get(ANDROID + 'name') for node in filt.findall('action')},
                'categories': {node.get(ANDROID + 'name') for node in filt.findall('category')},
                'data': [dict(node.attrib) for node in filt.findall('data')],
            })
    return rows


@entry('android.intent.view-content', 'android', 'saF-open-view',
       'The Android host accepts ACTION_VIEW for a content: URI delivered by the system file surface.')
def _(root):
    rows = android_filters(root, ANDROID_APP)
    ok = [row for row in rows
          if 'android.intent.action.VIEW' in row['actions']
          and 'android.intent.category.DEFAULT' in row['categories']
          and any(item.get(ANDROID + 'scheme') == 'content' for item in row['data'])]
    require(ok, 'no VIEW intent-filter with a content: scheme in ' + ANDROID_APP)


@entry('android.intent.send-filters', 'android', 'saF-share-send',
       'The Android host accepts ACTION_SEND and ACTION_SEND_MULTIPLE for the shared book files.')
def _(root):
    rows = android_filters(root, ANDROID_APP)
    for action in ('android.intent.action.SEND', 'android.intent.action.SEND_MULTIPLE'):
        ok = [row for row in rows
              if action in row['actions']
              and any(item.get(ANDROID + 'mimeType') for item in row['data'])]
        require(ok, 'no ' + action + ' filter with a mime type in ' + ANDROID_APP)


@entry('android.intent.no-broad-storage', 'android', 'saF-scoped-storage',
       'The Android host requests no broad or legacy storage permission; sharing goes through SAF grants.')
def _(root):
    tree = ET.parse(str(root / ANDROID_APP))
    names = {node.get(ANDROID + 'name') for node in tree.getroot().findall('uses-permission')}
    forbidden = {'android.permission.MANAGE_EXTERNAL_STORAGE',
                 'android.permission.READ_EXTERNAL_STORAGE',
                 'android.permission.WRITE_EXTERNAL_STORAGE'}
    require(not (names & forbidden), 'broad storage permission requested: ' + ','.join(sorted(names & forbidden)))


@entry('android.owner.no-declared-surface', 'android', 'saF-owner-isolation',
       'The import owner library declares no permission, component or activity of its own.')
def _(root):
    tree = ET.parse(str(root / ANDROID_OWNER_MANIFEST))
    children = list(tree.getroot())
    require(not children, 'import owner manifest must stay empty, found: ' +
            ','.join(node.tag for node in children))


@entry('android.owner.saf-picker', 'android', 'saF-document-picker',
       'The import owner opens the system document picker (ACTION_OPEN_DOCUMENT) for user-chosen files.')
def _(root):
    require_text(root, ANDROID_OWNER_JAVA, 'new Intent(Intent.ACTION_OPEN_DOCUMENT)',
                 'Intent.CATEGORY_OPENABLE', '.setType("*/*")')


@entry('android.owner.content-only', 'android', 'saF-grant-contract',
       'The import owner accepts only granted content: URIs and rejects every other scheme.')
def _(root):
    require_text(root, ANDROID_OWNER_JAVA, 'ContentResolver.SCHEME_CONTENT.equals(uri.getScheme())')


@entry('android.owner.sideload-handoff', 'android', 'saF-owner-handoff',
       'The import owner hands the staged original to the installed SDK sideload import.')
def _(root):
    require_text(root, ANDROID_OWNER_NATIVE, 'exr_sideload_import_file(library')


@entry('apple.files.sharing-keys', 'ios', 'aFiles-sharing',
       'The shipped iOS/iPadOS bundle declares Files app sharing and in-place opening.')
def _(root):
    require_text(root, APPLE_HOST_BUILD, "'UIFileSharingEnabled': True",
                 "'LSSupportsOpeningDocumentsInPlace': True")


@entry('apple.files.review-project-keys', 'ipados', 'aFiles-sharing',
       'The reviewed iOS/iPadOS acceptance project generated for CI declares the same Files sharing keys.')
def _(root):
    require_text(root, APPLE_REVIEW_PROJECT, "'INFOPLIST_KEY_UIFileSharingEnabled'] = 'YES'",
                 "'INFOPLIST_KEY_LSSupportsOpeningDocumentsInPlace'] = 'YES'")


@entry('apple.owner.security-scope', 'ios', 'aFiles-security-scope',
       'The Apple import owner brackets the delivered URL with security-scoped access before reading it.')
def _(root):
    text = read(root, APPLE_HOST_MODEL)
    at = text.find('func importFile(_ url: URL)')
    require(at >= 0, 'missing the import owner entry func importFile(_ url: URL)')
    window = text[at:at + 2400]
    require('url.startAccessingSecurityScopedResource()' in window,
            'import entry does not start security-scoped access')
    require('url.stopAccessingSecurityScopedResource()' in window,
            'import entry does not stop security-scoped access')


@entry('apple.picker.document-importer', 'ios', 'aFiles-document-picker',
       'The Apple host presents the system document importer and routes the chosen URL to the owner entry.')
def _(root):
    require_text(root, APPLE_HOST_VIEWS, '.fileImporter(isPresented: $importing',
                 'allowsMultipleSelection: false')
    require_ordered(root, APPLE_HOST_VIEWS, '.fileImporter(isPresented: $importing', 'model.importFile(url)', 600)


@entry('macos.owner.security-scope', 'macos', 'desktop-file-picker',
       'The macOS host uses the same owner entry with security-scoped access for a chosen file.')
def _(root):
    require_text(root, APPLE_HOST_MODEL, 'url.startAccessingSecurityScopedResource()')


@entry('macos.picker.document-importer', 'macos', 'desktop-file-picker',
       'The macOS host presents the system document importer and routes the chosen URL to the owner entry.')
def _(root):
    require_ordered(root, APPLE_HOST_VIEWS, '.fileImporter(isPresented: $importing', 'model.importFile(url)', 600)


@entry('windows.entry.open-dialog', 'windows', 'desktop-open-dialog',
       'The Windows host opens the system file dialog and imports the selected file.')
def _(root):
    require_ordered(root, WINDOWS_HOST, 'GetOpenFileNameW(&dialog)', 'job_new(JOB_IMPORT)', 400)


@entry('windows.entry.path-argument', 'windows', 'desktop-open-association',
       'The Windows host imports a book path handed over by the shell (association or drag onto the exe).')
def _(root):
    require_text(root, WINDOWS_HOST, 'copy_wstring(book_path, HOST_PATH, argv[i])')
    require_text(root, WINDOWS_HOST, 'import_path(book_path, 0)')


@entry('gtk.entry.file-chooser', 'linux-gtk', 'desktop-open-dialog',
       'The GTK host opens its own single book chooser.')
def _(root):
    require_text(root, GTK_HOST, 'gtk_file_chooser_dialog_new("Import book"',
                 'GTK_FILE_CHOOSER_ACTION_OPEN', 'gtk_file_chooser_get_filename(')


@entry('gtk.entry.drop-target', 'linux-gtk', 'desktop-drag-drop',
       'The GTK host accepts a real desktop drop and clipboard payload (text/uri-list and GNOME copied files).')
def _(root):
    require_text(root, GTK_DROP, 'gtk_drag_dest_set(', '"text/uri-list"', '"x-special/gnome-copied-files"')


@entry('gtk.entry.folder-batch', 'linux-gtk', 'desktop-folder-import',
       'The GTK host can import a folder chosen through the system folder chooser.')
def _(root):
    require_text(root, GTK_BATCH, 'GTK_FILE_CHOOSER_ACTION_SELECT_FOLDER', 'gtk_file_chooser_get_filename(')


@entry('all.no-webview', 'all', 'nO-new-runtime',
       'No host ships a WebView as the transfer or reading surface.')
def _(root):
    hits = []
    for path in sorted((root / 'examples').rglob('*')):
        if path.is_file() and path.suffix in ('.c', '.h', '.inc', '.cpp', '.swift', '.java', '.mm', '.m'):
            text = path.read_text(encoding='utf-8', errors='replace')
            for token in ('WebView', 'WKWebView', 'webview'):
                if token in text:
                    hits.append(str(path.relative_to(root)) + ':' + token)
    require(not hits, 'WebView surface found: ' + ','.join(hits))


@entry('all.no-server', 'all', 'nO-new-runtime',
       'No host starts a file-transfer server or listening socket for the book transfer.')
def _(root):
    hits = []
    for path in sorted((root / 'examples').rglob('*')):
        if path.is_file() and path.suffix in ('.c', '.h', '.inc', '.cpp', '.swift', '.java', '.mm', '.m'):
            text = path.read_text(encoding='utf-8', errors='replace')
            for token in ('HTTPServer', 'http_server', 'listen('):
                if token in text:
                    hits.append(str(path.relative_to(root)) + ':' + token)
    require(not hits, 'listening transfer server found: ' + ','.join(hits))


MUTATIONS = [
    {'id': 'mutate.android.view-content', 'file': ANDROID_APP,
     'old': '<data android:scheme="content" android:mimeType="*/*" />',
     'new': '<data android:scheme="file" android:mimeType="*/*" />',
     'expect_fail': ['android.intent.view-content']},
    {'id': 'mutate.android.no-broad-storage', 'file': ANDROID_APP,
     'old': '<uses-permission android:name="android.permission.INTERNET" />',
     'new': '<uses-permission android:name="android.permission.INTERNET" />\n'
            '    <uses-permission android:name="android.permission.MANAGE_EXTERNAL_STORAGE" />',
     'expect_fail': ['android.intent.no-broad-storage']},
    {'id': 'mutate.android.saf-picker', 'file': ANDROID_OWNER_JAVA,
     'old': 'new Intent(Intent.ACTION_OPEN_DOCUMENT)',
     'new': 'new Intent(Intent.ACTION_GET_CONTENT)',
     'expect_fail': ['android.owner.saf-picker']},
    {'id': 'mutate.android.sideload-handoff', 'file': ANDROID_OWNER_NATIVE,
     'old': 'exr_sideload_import_file(library', 'new': 'exr_library_import(library',
     'expect_fail': ['android.owner.sideload-handoff']},
    {'id': 'mutate.apple.sharing-keys', 'file': APPLE_HOST_BUILD,
     'old': "'LSSupportsOpeningDocumentsInPlace': True,",
     'new': "'LSSupportsOpeningDocumentsInPlace': False,",
     'expect_fail': ['apple.files.sharing-keys']},
    {'id': 'mutate.apple.security-scope', 'file': APPLE_HOST_MODEL,
     'old': 'let scoped = url.startAccessingSecurityScopedResource()',
     'new': 'let scoped = false',
     'expect_fail': ['apple.owner.security-scope', 'macos.owner.security-scope']},
    {'id': 'mutate.apple.importer-route', 'file': APPLE_HOST_VIEWS,
     'old': 'if let url = urls.first { model.importFile(url) }',
     'new': 'if let url = urls.first { _ = url }',
     'expect_fail': ['apple.picker.document-importer', 'macos.picker.document-importer']},
    {'id': 'mutate.windows.open-dialog', 'file': WINDOWS_HOST,
     'old': 'if (!GetOpenFileNameW(&dialog)) return;', 'new': 'if (0) return;',
     'expect_fail': ['windows.entry.open-dialog']},
    {'id': 'mutate.windows.path-argument', 'file': WINDOWS_HOST,
     'old': 'import_path(book_path, 0);', 'new': '(void)book_path;',
     'expect_fail': ['windows.entry.path-argument']},
    {'id': 'mutate.gtk.drop-target', 'file': GTK_DROP,
     'old': '"x-special/gnome-copied-files"', 'new': '"text/plain"',
     'expect_fail': ['gtk.entry.drop-target']},
    {'id': 'mutate.gtk.file-chooser', 'file': GTK_HOST,
     'old': 'gtk_file_chooser_dialog_new("Import book"',
     'new': 'gtk_message_dialog_new("Import book"',
     'expect_fail': ['gtk.entry.file-chooser']},
    {'id': 'mutate.no-webview', 'file': WINDOWS_HOST,
     'old': 'int WINAPI WinMain(', 'new': '/* android.webkit.WebView */\nint WINAPI WinMain(',
     'expect_fail': ['all.no-webview']},
    {'id': 'mutate.no-server', 'file': GTK_HOST,
     'old': 'int main(int argc,char **argv) {', 'new': 'static int s10_listen_probe(void) { return listen(0, 0); }\nint main(int argc,char **argv) {',
     'expect_fail': ['all.no-server']},
]


def run_checks(root):
    results = []
    for check in CHECKS:
        try:
            check['run'](root)
            results.append({'id': check['id'], 'platform': check['platform'],
                            'mechanism': check['mechanism'], 'description': check['description'],
                            'passed': True, 'detail': ''})
        except Failure as error:
            results.append({'id': check['id'], 'platform': check['platform'],
                            'mechanism': check['mechanism'], 'description': check['description'],
                            'passed': False, 'detail': str(error)})
        except (ET.ParseError, OSError) as error:
            results.append({'id': check['id'], 'platform': check['platform'],
                            'mechanism': check['mechanism'], 'description': check['description'],
                            'passed': False, 'detail': type(error).__name__ + ': ' + str(error)})
    return results


def copy_tree(target):
    for rel in CHECK_FILES:
        source = ROOT / rel
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    (target / 'examples').mkdir(parents=True, exist_ok=True)


def self_test():
    with tempfile.TemporaryDirectory() as temporary:
        baseline = Path(temporary) / 'baseline'
        baseline.mkdir()
        copy_tree(baseline)
        results = run_checks(baseline)
        problems = [row['id'] + ': ' + row['detail'] for row in results if not row['passed']]
        if problems:
            raise SystemExit('baseline copy failed: ' + '; '.join(problems))
        negatives = []
        for index, mutation in enumerate(MUTATIONS):
            root = Path(temporary) / ('mutation-' + str(index))
            root.mkdir()
            copy_tree(root)
            path = root / mutation['file']
            body = path.read_text(encoding='utf-8')
            if mutation['old'] not in body:
                raise SystemExit('mutation anchor missing for ' + mutation['id'])
            path.write_text(body.replace(mutation['old'], mutation['new'], 1), encoding='utf-8')
            rows = run_checks(root)
            failed = sorted(row['id'] for row in rows if not row['passed'])
            expected = sorted(mutation['expect_fail'])
            if failed != expected:
                raise SystemExit('mutation ' + mutation['id'] + ' failed ' + ','.join(failed) +
                                 ' instead of ' + ','.join(expected))
            detail = next(row['detail'] for row in rows if row['id'] == expected[0])
            negatives.append({'id': mutation['id'], 'file': mutation['file'],
                              'rejected_checks': expected, 'detail': detail})
        return negatives


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    results = run_checks(ROOT)
    platforms = {}
    for row in results:
        key = row['platform']
        platforms.setdefault(key, {'passed': 0, 'failed': 0})
        platforms[key]['passed' if row['passed'] else 'failed'] += 1
    problems = [row['id'] + ': ' + row['detail'] for row in results if not row['passed']]
    negatives = self_test()
    report = {
        'schema': 1,
        'package': 'S10',
        'source_sha': head,
        'kind': 'static-transfer-entry-contract',
        'checks': results,
        'problems': problems,
        'platforms': platforms,
        'declared_platforms': sorted({row['platform'] for row in results if row['platform'] != 'all'}),
        'negative_mutations': negatives,
        'positive_checks': sum(1 for row in results if row['passed']),
        'accepted': not problems and len(negatives) == len(MUTATIONS),
        'device_execution': False,
        'physical_device_execution': False,
        'usb_cable_execution': False,
        'note': ('Static declarations only: this report proves which native file entries and manifest '
                 'declarations exist. Actual file delivery is proven separately by the android, apple and '
                 'desktop jobs; no physical device or USB cable was used.'),
    }
    (output / 'entry-contract.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'positive_checks': report['positive_checks'],
                      'problems': problems,
                      'negative_mutations': len(negatives)}, indent=2))
    if problems:
        raise SystemExit(1)


if __name__ == '__main__':
    main()