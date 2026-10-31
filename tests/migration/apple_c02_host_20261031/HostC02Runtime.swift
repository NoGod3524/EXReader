// SPDX-License-Identifier: MIT
// Runs the production HostLibrary and its fixed authority factory inside the app UID.
import Foundation
import CryptoKit
import Darwin
import CEXReader
import CEXReaderC02
#if os(iOS)
import UIKit
#endif

private struct ReviewFailure: Error { let message: String }
private func require(_ condition: Bool, _ message: String) throws {
    if !condition { throw ReviewFailure(message: message) }
}
private func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
private func writeJSON(_ value: Any, _ path: URL) throws {
    try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .prettyPrinted]).write(to: path, options: .atomic)
}
private func identity(_ path: URL) throws -> [String: Any] {
    let descriptor = path.path.withCString { open($0,O_RDONLY | O_NOFOLLOW | O_CLOEXEC) }
    try require(descriptor >= 0, "native open for fstat")
    defer { close(descriptor) }
    var info = stat()
    try require(fstat(descriptor,&info) == 0, "native fstat")
    var result: [String: Any] = ["path":path.path,"device":UInt64(truncatingIfNeeded:info.st_dev),
        "inode":UInt64(truncatingIfNeeded:info.st_ino),"mode":UInt32(info.st_mode),"uid":info.st_uid,
        "links":UInt64(info.st_nlink),"bytes":Int64(info.st_size),"euid":geteuid()]
    if UInt32(info.st_mode) & UInt32(S_IFMT) == UInt32(S_IFREG) {
        let file = FileHandle(fileDescriptor:descriptor,closeOnDealloc:false)
        result["sha256"] = digest(try file.readToEnd() ?? Data())
    }
    return result
}
private enum Runtime {
    static let home = URL(fileURLWithPath: NSHomeDirectory())
    static let output = home.appendingPathComponent("Documents/c02-evidence", isDirectory: true)
    static let libraries = home.appendingPathComponent("Library/Application Support/EXReaderC02Review", isDirectory: true)
    static var stop: UInt32 = 0
    static var phaseName = ""
    static var rows: [[String: Any]] = []
    static let source = Bundle.main.object(forInfoDictionaryKey: "EXRSourceSHA") as? String ?? ""
    static let run = Bundle.main.object(forInfoDictionaryKey: "EXRRun") as? String ?? ""
    static let attempt = Bundle.main.object(forInfoDictionaryKey: "EXRAttempt") as? String ?? ""
    static var platform: String {
#if os(iOS)
        return "iphonesimulator"
#else
        return "macos"
#endif
    }
    static var authority: URL {
#if os(iOS)
        return home.appendingPathComponent(".exreader-c02-admission", isDirectory: true)
#else
        var buffer = [CChar](repeating: 0, count: 4096)
        precondition(pc02_user_authority(&buffer, 4096) != 0)
        return URL(fileURLWithPath: String(cString: buffer), isDirectory: true)
#endif
    }
    static func target(_ name: String) -> URL { libraries.appendingPathComponent(name+"/library.sqlite") }
    static func prepare(_ name: String) throws -> URL {
        let path = target(name)
        try FileManager.default.createDirectory(at: path.deletingLastPathComponent(), withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        return path
    }
    static func routes() throws -> Set<String> {
        guard FileManager.default.fileExists(atPath: authority.path) else { return [] }
        return Set(try FileManager.default.contentsOfDirectory(atPath: authority.path).filter {
            $0.utf8.count == 64 && $0.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
        })
    }
    static func create(_ name: String) throws -> (URL, URL) {
        let path = try prepare(name), before = try routes()
        try HostC02Admission.perform(.create, path: path)
        let added = try routes().subtracting(before)
        try require(added.count == 1, "explicit create reserves exactly one route")
        return (path, authority.appendingPathComponent(added.first!))
    }
    static func snapshot() throws -> [String: Any] {
        var result: [String: Any] = [:]
        if FileManager.default.fileExists(atPath:authority.path) { result["."] = try identity(authority) }
        if let walk = FileManager.default.enumerator(at: authority, includingPropertiesForKeys: [.isRegularFileKey]) {
            for case let path as URL in walk {
                result[String(path.path.dropFirst(authority.path.count+1))] = try identity(path)
            }
        }
        return result
    }
    static func observe(_ name: String, _ body: () throws -> [String: Any]) throws {
        let before = HostC02Review.sdkOpenCalls
        var observation = try body()
        observation["name"] = name
        observation["source"] = source
        observation["run"] = run
        observation["attempt"] = attempt
        observation["uid"] = geteuid()
        observation["pid"] = getpid()
        observation["sdk_open_count"] = HostC02Review.sdkOpenCalls-before
        if let target = observation["target"] as? String {
            let path = URL(fileURLWithPath:target)
            observation["parent_identity"] = try identity(path.deletingLastPathComponent())
            if FileManager.default.fileExists(atPath:target) { observation["library_identity"] = try identity(path) }
        }
        rows.append(["name": name, "passed": true, "observation": observation])
        let data = try JSONSerialization.data(withJSONObject: observation, options: [.sortedKeys])
        print("C02-HOST-OBS "+String(decoding: data, as: UTF8.self))
        fflush(stdout)
        try save(complete: false)
    }
    static func save(complete: Bool) throws {
        let value: [String: Any] = ["schema":"c02-host-admission-v1","source":source,"run":run,"attempt":attempt,
            "platform":platform,"actual_sdk":true,"phase":phaseName,"complete":complete,"passed":true,
            "cases":rows,"scope":try identity(home),"scope_factory":HostC02Review.scopes,
            "authority":authority.path,"native":try snapshot()]
        try writeJSON(value, output.appendingPathComponent(phaseName+".json"))
    }
}

private func openNative(_ path: URL, _ mode: UInt32, _ controls: UnsafePointer<pc02_controls>? = nil) throws -> OpaquePointer? {
    var lease: OpaquePointer?
#if os(iOS)
    let ok = try HostC02Admission.mobile(path: path) { scope, relative in
        ".exreader-c02-admission".withCString { authority in
            relative.withCString { pc02_open_in(scope, authority, $0, mode, nil, controls, &lease) }
        }
    }
#else
    let ok = Runtime.authority.path.withCString { authority in
        path.path.withCString { pc02_open(authority, $0, mode, nil, controls, &lease) }
    }
#endif
    try require((ok != 0) == (lease != nil), "native return and lease agree")
    return lease
}
private func ownerAdmitted(_ path: URL) throws -> Bool {
    guard let lease = try openNative(path, UInt32(PC02_OWNER)) else { return false }
    try require(pc02_check(lease) != 0 && pc02_close(lease) != 0, "native owner check and close")
    return true
}
private func refused(_ path: URL) throws -> [String: Any] {
    let before = HostC02Review.sdkOpenCalls
    do { _ = try HostLibrary(path: path); throw ReviewFailure(message:"ordinary HostLibrary admitted") }
    catch is HostC02Failure {}
    try require(HostC02Review.sdkOpenCalls == before, "refusal before actual SDK")
    return ["admitted":false,"target":path.path]
}
private func reviewBarrier(_ context: UnsafeMutableRawPointer?, _ phase: UInt32) {
    guard phase == Runtime.stop else { return }
    do {
        try writeJSON(["phase":phase,"pid":getpid(),"uid":geteuid(),"source":Runtime.source,
                       "target":Runtime.target(Runtime.phaseName == "enrollment-crash" ? "enrollment" : "pending").path],
                      Runtime.output.appendingPathComponent(Runtime.phaseName+"-barrier.json"))
    } catch { _exit(91) }
    while true { sleep(1) }
}
private func emptySDKProof(_ context: UnsafeMutableRawPointer?, _ path: UnsafePointer<CChar>?, _ descriptor: Int32,
                           _ pending: UnsafePointer<pc02_pending_record>?, _ terminal: UnsafePointer<CChar>?) -> Int32 {
    guard let path, pending == nil, terminal == nil else { return 0 }
    var library: OpaquePointer?, error = exr_error()
    guard exr_library_open(path, &library, &error) == EXR_OK, let library else { return 0 }
    defer { exr_library_close(library) }
    var books: UnsafeMutablePointer<exr_book>?, count = 0
    let ok = exr_library_books(library, nil, &books, &count, &error) == EXR_OK && count == 0
    exr_books_free(books,count)
    return ok ? 1 : 0
}
private func crashEnrollment() throws {
    let target = try Runtime.prepare("enrollment")
    var library: OpaquePointer?, error = exr_error()
    try target.path.withCString { try hostCheck(exr_library_open($0, &library, &error), error) }
    exr_library_close(library)
    Runtime.stop = UInt32(PC02_ENROLL_STATE)
    var controls = pc02_controls()
    controls.phase = reviewBarrier
#if os(iOS)
    let result = try HostC02Admission.mobile(path: target) { scope, relative in
        ".exreader-c02-admission".withCString { authority in
            relative.withCString {
                pc02_authority_create_in(scope, authority) != 0
                    ? pc02_enroll_in(scope, authority, $0, 0, emptySDKProof, nil, &controls) : 0
            }
        }
    }
#else
    let result = Runtime.authority.path.withCString { authority in
        target.path.withCString {
            pc02_authority_create(authority) != 0 ? pc02_enroll(authority, $0, 0, emptySDKProof, nil, &controls) : 0
        }
    }
#endif
    throw ReviewFailure(message:"enrollment never reached durable barrier: "+String(result))
}
private func crashPending() throws {
    let (target, _) = try Runtime.create("pending")
    Runtime.stop = UInt32(PC02_PENDING_DURABLE)
    var controls = pc02_controls()
    controls.phase = reviewBarrier
    guard let owner = try withUnsafePointer(to: &controls, { try openNative(target, UInt32(PC02_OWNER), $0) }) else {
        throw ReviewFailure(message:"pending owner refused")
    }
    var capability: OpaquePointer?
    let manifest = digest(Data(("host-admission:"+Runtime.source).utf8))
    let input = digest(Data(("host-input:"+Runtime.source).utf8))
    let result = manifest.withCString { bound in input.withCString { pc02_begin(owner, bound, $0, &capability) } }
    throw ReviewFailure(message:"pending never reached durable barrier: "+String(result))
}
private func waitUntil(_ condition: () -> Bool) throws {
    let limit = Date().addingTimeInterval(30)
    while !condition() && Date() < limit {
        RunLoop.current.run(mode:.default,before:Date().addingTimeInterval(0.02))
    }
    try require(condition(), "actual HostModel startup deadline")
}
private func modelFolder() throws -> URL {
    try FileManager.default.url(for:.applicationSupportDirectory,in:.userDomainMask,
                                appropriateFor:nil,create:true).appendingPathComponent("EXReader")
}
private func baseline() throws {
    try Runtime.observe("model-admission-before-catalog") {
        let folder = try modelFolder()
        let catalog = folder.appendingPathComponent("reader-catalog.db")
        var model: HostReaderModel? = HostReaderModel()
        model!.start()
        try waitUntil { !model!.busy }
        try require(model!.admissionRequired && !model!.libraryReady, "unknown model requires explicit action")
        try require(!FileManager.default.fileExists(atPath:catalog.path) &&
                    !FileManager.default.fileExists(atPath:folder.appendingPathComponent("library.sqlite").path),
                    "model did not create SDK or catalog before admission")
        model!.prepareLibrary(.create)
        try waitUntil { !model!.busy }
        try require(model!.libraryReady && FileManager.default.fileExists(atPath:catalog.path),
                    "explicit UI action opens actual SDK then catalog")
        model = nil
        return ["admitted":true,"target":folder.appendingPathComponent("library.sqlite").path]
    }
    try Runtime.observe("explicit-enrollment-recovery") {
        let path = Runtime.target("enrollment")
        _ = try refused(path)
        try HostC02Admission.perform(.recoverEnrollment, path:path)
        let library = try HostLibrary(path:path)
        try require(try library.books().isEmpty, "recovery proves real empty SDK")
        return ["admitted":true,"target":path.path]
    }
    try Runtime.observe("unknown-check-never-creates") {
        let path = try Runtime.prepare("unknown"), before = try Runtime.routes()
        let value = try refused(path)
        try require(!FileManager.default.fileExists(atPath:path.path) && before == Runtime.routes(), "unknown open creates nothing")
        return value
    }
    try Runtime.observe("clean-admits-before-sdk") {
        let (path, _) = try Runtime.create("clean")
        let library = try HostLibrary(path:path)
        try require(try library.books().isEmpty, "actual initial SDK contents")
        return ["admitted":true,"target":path.path,"canonical_sdk_path":library.path.path]
    }
    try Runtime.observe("pending-refuses-before-sdk") { try refused(Runtime.target("pending")) }
    try Runtime.observe("missing-binding-refuses-before-sdk") {
        let (path, route) = try Runtime.create("missing-binding")
        try FileManager.default.moveItem(at:route.appendingPathComponent("binding"),to:route.appendingPathComponent("binding-preserved"))
        return try refused(path)
    }
    try Runtime.observe("replaced-target-refuses-before-sdk") {
        let (path, _) = try Runtime.create("replacement"), original = path.appendingPathExtension("retained")
        let before = try identity(path)
        try FileManager.default.moveItem(at:path,to:original)
        try Data(contentsOf:original).write(to:path)
        try require((try identity(path))["inode"] as? UInt64 != before["inode"] as? UInt64, "actual native replacement")
        return try refused(path)
    }
    let (path, _) = try Runtime.create("borrow")
    let text = path.deletingLastPathComponent().appendingPathComponent("sample.txt")
    try Data("C02 original UTF-8 text.\n".utf8).write(to:text)
    var library: HostLibrary? = try HostLibrary(path:path)
    let imported = try library!.importUnique(file:text,title:"C02 text")
    let contents = try library!.books()
    try require(contents.count == 1 && contents[0].title == "C02 text", "actual SDK import")
    var document: HostDocument? = try library!.document(bookID:imported.id)
    weak var weakLibrary = library
    library = nil
    try Runtime.observe("last-borrow-blocks-owner") {
        let admitted = try ownerAdmitted(path)
        try require(!admitted && weakLibrary != nil && document!.text.count > 0, "document owns SH library")
        return ["owner_admitted":admitted,"borrow_kind":"document","target":path.path]
    }
    document = nil
    try Runtime.observe("final-borrow-release-allows-owner") {
        let admitted = try ownerAdmitted(path)
        try require(admitted && weakLibrary == nil, "last document closes SDK then shared lease")
        return ["owner_admitted":admitted,"target":path.path]
    }
    try Runtime.observe("independent-host-library-reopen") {
        let one = try HostLibrary(path:path), two = try HostLibrary(path:path)
        try require(try one.books().count == two.books().count, "same fixed authority reopen")
        try require(try !ownerAdmitted(path), "two reader leases block owner")
        return ["admitted":true,"target":path.path]
    }
    for fixed in [false,true] {
        try Runtime.observe(fixed ? "fixed-last-owner" : "publication-last-owner") {
            let (target, _) = try Runtime.create(fixed ? "fixed" : "publication")
            var held: HostLibrary? = try HostLibrary(path:target)
            let resource = Bundle.main.url(forResource:"Sample",withExtension:fixed ? "pdf" : "epub")!
            let book = try held!.importUnique(file:resource,title:"C02 borrowed").id
            weak var weakOwner = held
            var borrowed: AnyObject?
            if fixed {
                let font = try HostFont(data:Data(contentsOf:Bundle.main.url(forResource:"Reader",withExtension:"otf")!))
                borrowed = try held!.fixed(bookID:book,font:font)
            } else { borrowed = try HostPublication(library:held!,bookID:book,cancel:HostCancelBox()) }
            held = nil
            try require(borrowed != nil && weakOwner != nil && !ownerAdmitted(target), "borrowed SDK object retains library")
            borrowed = nil
            try require(weakOwner == nil && ownerAdmitted(target), "borrowed SDK object final release")
            return ["admitted":true,"target":target.path]
        }
    }
}
private func freshPreserve() throws {
    try Runtime.observe("fresh-preserves-existing-library-and-catalog") {
        let folder = try modelFolder()
        let library = folder.appendingPathComponent("library.sqlite")
        let catalog = folder.appendingPathComponent("reader-catalog.db")
        let before = [digest(try Data(contentsOf:library)),digest(try Data(contentsOf:catalog))]
        let model = HostReaderModel()
        model.start()
        try waitUntil { !model.busy }
        try require(!model.libraryReady && !model.errorText.isEmpty, "fresh profile refuses existing actual state")
        try require(before == [digest(try Data(contentsOf:library)),digest(try Data(contentsOf:catalog))],
                    "fresh preserved exact actual database bytes")
        return ["admitted":false,"target":library.path,"before_sha256":before]
    }
}
private func execute() {
    do {
        try FileManager.default.createDirectory(at:Runtime.output,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
        guard let index = CommandLine.arguments.firstIndex(of:"--phase"), index+1 < CommandLine.arguments.count else {
            throw ReviewFailure(message:"phase required")
        }
        Runtime.phaseName = CommandLine.arguments[index+1]
        switch Runtime.phaseName {
        case "enrollment-crash": try crashEnrollment()
        case "pending-crash": try crashPending()
        case "baseline": try baseline(); try Runtime.save(complete:true)
        case "fresh-preserve": try freshPreserve(); try Runtime.save(complete:true)
        case "fresh":
            let before = try Runtime.snapshot()
            try Runtime.observe("fresh-process-pending-refusal") { try refused(Runtime.target("pending")) }
            let after = try Runtime.snapshot()
            try require(NSDictionary(dictionary:before).isEqual(to:after), "fresh refusal never mutates native authority")
            try Runtime.save(complete:true)
        default: throw ReviewFailure(message:"unsupported phase")
        }
        exit(0)
    } catch {
        try? writeJSON(["passed":false,"error":String(describing:error),"phase":Runtime.phaseName,
                        "uid":geteuid(),"pid":getpid()],Runtime.output.appendingPathComponent("failure.json"))
        fputs("C02 runtime failed: \(error)\n",stderr)
        exit(1)
    }
}
#if os(iOS)
@main private final class RuntimeApp: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
    func application(_ application: UIApplication,didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey:Any]? = nil) -> Bool {
        window = UIWindow(frame:UIScreen.main.bounds)
        window?.rootViewController = UIViewController()
        window?.makeKeyAndVisible()
        DispatchQueue.main.async { execute() }
        return true
    }
}
#else
@main private struct RuntimeApp {
    static func main() { execute() }
}
#endif
