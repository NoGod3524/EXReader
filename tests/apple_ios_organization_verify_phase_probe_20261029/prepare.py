#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only reversible generated-host instrumentation; no owner edits."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = '59d350c225b9c0b644cbc4b7a266c52726518e35'
BRANCH = 'codex/apple-ios-organization-verify-phase-probe-20261029'
PACKAGE = 'tests/apple_ios_organization_verify_phase_probe_20261029/'
WORKFLOW = '.github/workflows/apple-ios-organization-verify-phase-probe-20261029.yml'
PATHS = [WORKFLOW] + [PACKAGE + p for p in ('prepare.py', 'AppPhaseRecorder.swift', 'VerifyPhaseTests.swift', 'collect.py')]
OUT = ROOT / 'build/ios-verify-phase-probe'
FORMAL = 'tests/apple_ios_organization_20261028/ui/IOSOrganizationAcceptanceTests.swift'
FORMAL_SHA = 'deeed62b7083fb4a3e85ccd866a9a9eb4fdbca8e0c86bb88136b0fca400161ff'
BOOK_SHA = '0c54c6c969cb720875557d8f877d0733cc65dd1e80d74d098fb18ba65bf42bdb'
CLASS = 'IOSOrganizationVerifyPhaseTests'
CASES = ['test00Transport', 'test01TagPrefix', 'test02TagPrefix', 'test03TagPrefix']
HOSTS = ['HostViews.swift', 'HostModel.swift', 'HostOrganization.swift']
ATS = {'NSExceptionDomains': {'127.0.0.1': {'NSExceptionAllowsInsecureHTTPLoads': True}}}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(path):
    return {p.relative_to(path).as_posix(): digest(p) for p in sorted(path.rglob('*')) if p.is_file()}


def command(*argv):
    return subprocess.check_output(list(map(str, argv)), cwd=ROOT, text=True).strip()


def run(*argv):
    subprocess.run(list(map(str, argv)), cwd=ROOT, check=True)


class Rewrite:
    def __init__(self, text):
        self.original = self.text = text
        self.pairs = []

    def once(self, old, new):
        require(self.text.count(old) == 1, 'unique source anchor required: ' + old[:100])
        self.text = self.text.replace(old, new)
        self.pairs.append((old, new))

    def finish(self):
        reverse = self.text
        for old, new in reversed(self.pairs):
            require(reverse.count(new) == 1, 'reverse anchor ambiguous')
            reverse = reverse.replace(new, old)
        require(reverse == self.original, 'original byte reconstruction differs')
        return self.text


def host_sources():
    original = {n: (ROOT / 'examples/apple' / n).read_text() for n in HOSTS}
    views, model, org = (Rewrite(original[n]) for n in HOSTS)
    views.once('Button("验证原件") { model.verifyOrganizationOriginal(book, organization: organization) }',
        'Button("验证原件") { let phase = OrgPhase.activation(model, organization, book.sdkID); model.verifyOrganizationOriginal(book, organization: organization, phaseParent: phase) }')
    views.once('organization.prepareMembership(kind: kind, groupID: group.id, bookKey: book.id)',
        'organization.prepareMembership(kind: kind, groupID: group.id, bookKey: book.id, phaseParent: OrgPhase.selection(organization, kind))')
    views.once('.disabled(organization.busy || model.organizationVerificationBusy)',
        '.disabled(OrgPhase.panel(organization.busy || model.organizationVerificationBusy, organization, model))')

    model.once('        self.accountProfile = profile\n', '        OrgPhase.boot()\n        self.accountProfile = profile\n')
    model.once('                if fresh {\n', '                if fresh {\n                    OrgPhase.files(folder, after: false)\n')
    model.once('                    self.defaults.removeObject(forKey: "EXRLastBook")\n',
        '                    OrgPhase.files(folder, after: true)\n                    self.defaults.removeObject(forKey: "EXRLastBook")\n')
    model.once('                    self.traceUITest("startup-publish rows=\\(rows.count)")\n',
        '                    OrgPhase.event(4, self, a: Int64(rows.count))\n                    self.traceUITest("startup-publish rows=\\(rows.count)")\n')
    start = model.text.index('    func verifyOrganizationOriginal(')
    end = model.text.index('\n    func openBook(_ row:', start)
    before = model.text[start:end]
    m = Rewrite(before)
    m.once('organization: HostOrganization) {', 'organization: HostOrganization, phaseParent: UInt64 = 0) {')
    m.once('        guard !organizationVerificationBusy else { return }',
        '        OrgPhase.event(12, self, op: phaseParent, a: organizationVerificationBusy ? 1 : 0)\n'
        '        guard !organizationVerificationBusy else { OrgPhase.event(13, self, op: phaseParent); return }')
    m.once('        organizationVerificationBusy = true',
        '        organizationVerificationBusy = true\n        OrgPhase.event(14, self, op: phaseParent, a: 0, b: 1)')
    m.once('        queue.async {', '        OrgPhase.event(40, self, op: phaseParent)\n        queue.async {\n            OrgPhase.event(15, self, op: phaseParent)')
    m.once('                try session.library.exportSyncOriginal',
        '                OrgPhase.event(16, self, op: phaseParent)\n                try session.library.exportSyncOriginal')
    m.once('                let expected = HostSourceFingerprint(',
        '                OrgPhase.event(43, self, op: phaseParent, a: product.sdkID)\n                let expected = HostSourceFingerprint(')
    m.once('                    cancel: HostCancelBox())\n',
        '                    cancel: HostCancelBox())\n                OrgPhase.event(17, self, op: phaseParent)\n')
    m.once('                DispatchQueue.main.async {\n                    self.organizationVerificationBusy = false\n                    organization.bootstrap',
        '                DispatchQueue.main.async {\n                    OrgPhase.event(18, self, op: phaseParent)\n                    self.organizationVerificationBusy = false\n                    OrgPhase.event(14, self, op: phaseParent, a: 1, b: 0)\n                    organization.bootstrap')
    m.once('sha256: product.sha256, bytes: UInt64(product.bytes))',
        'sha256: product.sha256, bytes: UInt64(product.bytes), phaseParent: phaseParent)')
    m.once('            } catch {\n                DispatchQueue.main.async {\n                    self.organizationVerificationBusy = false\n                    organization.reportError(self.describe(error))',
        '            } catch {\n                OrgPhase.event(41, self, op: phaseParent)\n                DispatchQueue.main.async {\n                    OrgPhase.event(19, self, op: phaseParent)\n                    self.organizationVerificationBusy = false\n                    OrgPhase.event(14, self, op: phaseParent, a: 1, b: 0)\n                    organization.reportError(self.describe(error), phaseParent: phaseParent)')
    model.once(before, m.finish())

    org.once('        self.productURL = productURL\n',
        '        self.productURL = productURL\n        OrgPhase.event(1, self, a: 0, b: 0)\n')
    org.once('private func run<T>(_ work: @escaping () throws -> T, publish: @escaping (T) -> Void)',
        'private func run<T>(phaseKind: Int64, phaseParent: UInt64 = 0, _ work: @escaping () throws -> T, publish: @escaping (T, UInt64) -> Void)')
    org.once('        queued += 1; busy = true\n',
        '        let phaseOp = OrgPhase.operation(self, kind: phaseKind, parent: phaseParent)\n'
        '        OrgPhase.event(21, self, op: phaseOp, a: Int64(queued), b: busy ? 1 : 0)\n'
        '        queued += 1; busy = true\n'
        '        OrgPhase.event(22, self, op: phaseOp, a: Int64(queued), b: busy ? 1 : 0)\n')
    org.once('        queue.async {\n            let result = Result { try work() }',
        '        queue.async {\n            OrgPhase.event(23, self, op: phaseOp)\n'
        '            let result = Result { try work() }\n            OrgPhase.event(24, self, op: phaseOp, a: OrgPhase.result(result))')
    org.once('                self.queued -= 1; self.busy = self.queued != 0\n',
        '                OrgPhase.event(25, self, op: phaseOp, a: Int64(self.queued), b: self.busy ? 1 : 0)\n'
        '                self.queued -= 1; self.busy = self.queued != 0\n'
        '                OrgPhase.event(26, self, op: phaseOp, a: Int64(self.queued), b: self.busy ? 1 : 0)\n')
    org.once('case .success(let value): publish(value)', 'case .success(let value): publish(value, phaseOp)')
    org.once('case .failure(let error): self.prepared = false; self.message = error.localizedDescription\n                }',
        'case .failure(let error): self.prepared = false; self.message = error.localizedDescription; OrgPhase.event(31, self, op: phaseOp, a: 1)\n                }\n                OrgPhase.event(27, self, op: phaseOp)')
    org.once('func prepareMembership(kind: Int, groupID: String, bookKey: String)',
        'func prepareMembership(kind: Int, groupID: String, bookKey: String, phaseParent: UInt64 = 0)')
    org.once('func bootstrap(bookKey: String, format: String, sha256: String, bytes: UInt64)',
        'func bootstrap(bookKey: String, format: String, sha256: String, bytes: UInt64, phaseParent: UInt64 = 0)')
    org.once('func reportError(_ text: String) { message = text }',
        'func reportError(_ text: String, phaseParent: UInt64 = 0) { message = text; OrgPhase.event(31, self, op: phaseParent, a: 1) }')
    kinds = ['inspectPending', 'loadGroups', 'loadMembers', 'prepareGroup', 'prepareMembership',
             'commitGroup', 'commitMembership', 'reviewCompetingRename', 'recoverEdit', 'abandonPending', 'bootstrap']
    # Each original publication gets an operation argument; no TLS, extra queue
    # hop, changed work closure or user-visible debug property is introduced.
    for number, name in enumerate(kinds, 1):
        match = re.search(r'^    (?:private )?func ' + name + r'\(', org.text, re.M)
        require(match is not None, 'missing operation ' + name)
        next_method = re.search(r'^    (?:private )?func ', org.text[match.end():], re.M)
        end = match.end() + next_method.start() if next_method else len(org.text)
        before = org.text[match.start():end]
        segment = Rewrite(before)
        parent = ', phaseParent: phaseParent' if name in ('prepareMembership', 'bootstrap') else ''
        segment.once('        run({', f'        run(phaseKind: {number}{parent}, {{')
        explicit = 'publish: { _ in' in segment.text
        if explicit:
            segment.once('publish: { _ in', 'publish: { _, phaseID in')
        phase = 'phaseID' if explicit else '$1'
        message = {'inspectPending': '2', 'prepareGroup': '3',
            'prepareMembership': '($0.3 ? 4 : 5)', 'commitGroup': '6', 'commitMembership': '7',
            'reviewCompetingRename': '8', 'recoverEdit': '9', 'abandonPending': '10',
            'bootstrap': '($0.0 ? 11 : 12)'}.get(name)
        assignments = {'inspectPending': 'self.message = "有待恢复的整理操作。"',
            'prepareGroup': 'self.message = "已读取分组版本。"',
            'prepareMembership': 'self.message = $0.3 ? "书籍需要验证原件后建立历史。" : "已读取成员版本。"',
            'commitGroup': 'self.message = $0.1', 'commitMembership': 'self.message = $0.1',
            'reviewCompetingRename': 'self.message = "竞争版本已提交。"', 'recoverEdit': 'self.message = $0.1',
            'abandonPending': 'self.message = "未提交的待处理操作已放弃。"',
            'bootstrap': 'self.message = $0.0 ? $0.1 : "原件验证完成，书籍历史已建立；请重新读取成员版本。"'}
        if name in assignments:
            # Immediately after the actual assignment, before any subsequent
            # refresh enqueue; inspectPending records only its original branch.
            assignment = assignments[name]
            segment.once(assignment, assignment + f'; OrgPhase.event(31, self, op: {phase}, a: {message})')
        elif name == 'loadGroups':
            hook = f'; OrgPhase.event(5, self, op: {phase}, a: Int64(kind), b: Int64($0.count), c: deleted ? 1 : 0) '
        else:
            hook = f'; OrgPhase.event(6, self, op: {phase}, a: Int64($0.count)) '
        if name not in assignments:
            position = segment.text.rfind('})')
            require(position >= 0, 'publication end missing')
            tail = segment.text[position:]
            segment.once(tail, hook + tail)
        org.once(before, segment.finish())
    require(len(re.findall(r'run\(phaseKind:', org.text)) == 11 and '        run({' not in org.text, 'operation coverage differs')
    return dict(zip(HOSTS, (views.finish(), model.finish(), org.finish())))


def ui_source():
    formal = (ROOT / FORMAL).read_text()
    require(digest(ROOT / FORMAL) == FORMAL_SHA, 'frozen UI differs')
    r = Rewrite(formal)
    r.once('import XCTest\n', 'import XCTest\nimport CryptoKit\nimport Darwin\n')
    r.once('final class IOSOrganizationAcceptanceTests:', 'final class ' + CLASS + ':')
    r.once('        element.tap()\n', '        if phaseTapArmed { phaseNativeTap(element) } else { element.tap() }\n')
    r.once('        app.launch()\n', '        phaseConfigureLaunch()\n        app.launch()\n')
    # Keep original screenshot/tree order, and finalize even when attachments throw.
    r.once('    override func tearDownWithError() throws {\n',
        '    override func tearDownWithError() throws {\n        defer { phaseFinish(); app.terminate() }\n')
    r.once('        app.terminate()\n    }\n    private func node',
        '    }\n    private func node')
    base = r.finish()
    begin = formal.index('        launch(fresh: true)\n', formal.index('    private func lifecycle('))
    stop_marker = '        XCTAssertTrue(wait { self.label("organization.message").contains("原件验证完成") })\n'
    end = formal.index(stop_marker, begin) + len(stop_marker)
    prefix = formal[begin:end]
    p = Rewrite(prefix)
    p.once('chooseBook(bookID); tap("organization.verify-original")',
        'chooseBook(bookID); phaseTapArmed = true; tap("organization.verify-original"); phaseTapArmed = false')
    p.once(stop_marker,
        '        phaseWaitStarted = mach_absolute_time()\n'
        '        XCTAssertTrue(phaseWaitResult(wait { self.phasePredicate { self.phaseLabel(self.label("organization.message")).contains("原件验证完成") } }))\n')
    fragment = (ROOT / PACKAGE / 'VerifyPhaseTests.swift').read_text()
    require(fragment.count('/* ORIGINAL_TAG_PREFIX */') == 1, 'UI fragment anchor differs')
    fragment = fragment.replace('/* ORIGINAL_TAG_PREFIX */', p.finish())
    require(base.endswith('}\n'), 'UI class end differs')
    return base[:-2] + '\n' + fragment + '\n}\n'


def generated(workspace):
    workspace = Path(workspace)
    generated_root = workspace / 'build/ios-verify-phase-probe/generated'
    original = (ROOT / 'tests/apple_host/make_xcodeproj.rb').read_text()
    r = Rewrite(original)
    r.once("['3.40.0', '3.41.0'].include?(sdk_version)", "['3.40.0', '3.41.0', '3.42.0'].include?(sdk_version)")
    r.once("page_theme == 'ON' && sdk_version != '3.41.0'", "page_theme == 'ON' && !['3.41.0', '3.42.0'].include?(sdk_version)")
    anchor = "test_directory = ARGV[2] ? File.expand_path(ARGV[2]) : File.join(root, 'tests/apple_host')"
    mapping = '{' + ', '.join(repr(n) + ' => ' + repr(str(generated_root / 'host' / n)) for n in HOSTS) + '}'
    r.once(anchor, 'phase_sources = ' + mapping + '\nsources = sources.map { |p| phase_sources.fetch(File.basename(p), p) } + [' + repr(str(generated_root / 'host/AppPhaseRecorder.swift')) + ']\n' + anchor)
    anchor = "    settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'org.exreader.host.uitests'"
    r.once(anchor, anchor + "\n    settings['INFOPLIST_FILE'] = File.join(File.dirname(target.project.path), 'PhaseTests-Info.plist')")
    team = Rewrite((ROOT / 'tests/reader_team24_apple/make_project.rb').read_text())
    team.once("'tests/apple_host/make_xcodeproj.rb'", repr(str(generated_root / 'make_xcodeproj_phase.rb')))
    result = {'host/' + n: value for n, value in host_sources().items()}
    result['host/AppPhaseRecorder.swift'] = (ROOT / PACKAGE / 'AppPhaseRecorder.swift').read_text()
    result['ui/VerifyPhaseTests.swift'] = ui_source()
    result['make_xcodeproj_phase.rb'] = r.finish()
    result['make_project_phase.rb'] = team.finish()
    return result


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin', 'macOS Actions only')
    source = command('git', 'rev-parse', 'HEAD')
    require(source == os.environ['GITHUB_SHA'] and os.environ['GITHUB_RUN_ATTEMPT'] == '1'
            and os.environ['GITHUB_REF_NAME'] == BRANCH, 'wrong source/attempt/branch')
    delta = command('git', 'diff', '--name-status', BASE, source).splitlines()
    require(sorted(delta) == sorted('A\t' + p for p in PATHS), 'exact five additions required')
    require(not command('git', 'status', '--porcelain', '--untracked-files=all'), 'dirty source')
    OUT.mkdir(parents=True, exist_ok=False)
    evidence = OUT / 'evidence'; evidence.mkdir()
    content = generated(ROOT)
    for name, value in content.items():
        path = OUT / 'generated' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(value)
    run(sys.executable, 'tests/apple_sdk342_package/run.py', '--target', 'iphonesimulator')
    run(sys.executable, 'tests/apple_host/prepare_fixtures.py', '--resources', OUT / 'resources')
    require(digest(OUT / 'resources/Sample.epub') == BOOK_SHA, 'fixture differs')
    project = OUT / 'generated/project'; project.mkdir()
    (project / 'PhaseTests-Info.plist').write_bytes(plistlib.dumps({'NSAppTransportSecurity': ATS}))
    run('ruby', OUT / 'generated/make_project_phase.rb', project, OUT / 'resources', OUT / 'generated/ui', 'base')
    for name in ('Info-iOS.plist', 'Info-macOS.plist'):
        path = project / name; info = plistlib.loads(path.read_bytes())
        require(info['EXRSourceSHA'] == source and info['EXRSDKVersion'] == '3.42.0'
                and info['EXRPageThemeEnabled'] is True and 'NSAppTransportSecurity' not in info, 'generated Info baseline differs')
        (project / ('Before-' + name)).write_bytes(path.read_bytes())
        info['NSAppTransportSecurity'] = ATS; path.write_bytes(plistlib.dumps(info))
    sdk = json.loads((ROOT / 'build/apple-sdk342/iphonesimulator/identity.json').read_text())
    require((sdk['source_sha'], sdk['run_id'], sdk['attempt'], sdk['product']['sdk_version']) ==
            (source, os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'], '3.42.0'), 'SDK identity differs')
    shutil.copytree(OUT / 'generated', evidence / 'generated')
    guard = {'source_sha': source, 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'base': BASE, 'producer_workspace': str(ROOT), 'sdk_version': '3.42.0', 'sdk_package_identity': sdk,
        'paths': sorted(PATHS), 'existing_blobs_unchanged': True, 'reverse_reconstruction_equal': True,
        'package_files': {p: digest(ROOT / p) for p in PATHS}, 'generated': inventory(evidence / 'generated'),
        'fixtures': inventory(OUT / 'resources'), 'selected_cases': CASES, 'formal_ui_sha256': FORMAL_SHA,
        'ats': ATS, 'formal_credit': 0, 'product_accepted': False}
    (evidence / 'source-guard.json').write_text(json.dumps(guard, indent=2, sort_keys=True) + '\n')
    run('git', 'diff', '--exit-code')
    print(json.dumps({'source_admitted': True, 'reverse_reconstruction_equal': True, 'selected_cases': CASES}))


if __name__ == '__main__':
    main()
