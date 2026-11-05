import XCTest
import Foundation

// D11's native action sequence and toolbar-scrolling rules, now observed from a
// separate macOS process. No debug app handler, injected SDK or product mutation.
final class StorageActions: XCTestCase {
 var app: XCUIApplication!
 var rows: [[String:Any]] = []
 override func setUpWithError() throws { continueAfterFailure=false; app=XCUIApplication() }
 override func tearDownWithError() throws {
  let tree=XCTAttachment(string:app.debugDescription);tree.name="final-native-tree";tree.lifetime = .keepAlways;add(tree)
  let shot=XCTAttachment(screenshot:app.screenshot());shot.name="final-native-screen";shot.lifetime = .keepAlways;add(shot)
  let data=try JSONSerialization.data(withJSONObject:rows,options:[.sortedKeys]);let record=XCTAttachment(string:String(decoding:data,as:UTF8.self));record.name="actions.json";record.lifetime = .keepAlways;add(record);app.terminate()
 }
 func node(_ id:String)->XCUIElement {app.descendants(matching:.any).matching(identifier:id).firstMatch}
 func wait(_ predicate:()->Bool)->Bool {let end=Date().addingTimeInterval(45);while Date()<end {if predicate(){return true};RunLoop.current.run(until:Date().addingTimeInterval(0.2))};return predicate()}
 func tap(_ id:String) {
  XCTAssertTrue(node(id).waitForExistence(timeout:30),id)
  let toolbar=["reader.first","reader.previous","reader.next","reader.font.decrease","reader.font.increase","reader.select","reader.notes","reader.search","reader.navigation"].contains(id)
  func viewport()->CGRect {let window=app.windows.firstMatch.frame.insetBy(dx:-2,dy:-2);return toolbar && node("reader.tools.scroll").exists ? window.intersection(node("reader.tools.scroll").frame) : window}
  for _ in 0..<12 {let frame=node(id).frame;if !frame.isEmpty && viewport().contains(frame) && node(id).isHittable {break};if toolbar && node("reader.tools.scroll").exists {let tools=node("reader.tools.scroll");if !frame.isEmpty && frame.midX<tools.frame.midX {tools.swipeRight()} else {tools.swipeLeft()}} else {break}}
  XCTAssertTrue(wait{viewport().contains(self.node(id).frame) && self.node(id).isEnabled && self.node(id).isHittable},id);node(id).tap()
 }
 func text(_ id:String)->String {let n=node(id);return (n.value as? String).flatMap{$0.isEmpty ? nil:$0} ?? n.label}
 @discardableResult func observe(_ path:String)->[String:Any] {
  let done=expectation(description:"Independent store read: "+path);var result:[String:Any]=[:];var failure:String?
  URLSession.shared.dataTask(with:URL(string:"http://127.0.0.1:19718/"+path)!) {data,response,error in
   defer {done.fulfill()}
   if let error=error {failure=error.localizedDescription;return}
   guard let data=data,let value=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any] else {failure="missing observer JSON";return}
   result=value;if (response as? HTTPURLResponse)?.statusCode != 200 {failure=String(describing:value)}
  }.resume()
  wait(for:[done],timeout:60);XCTAssertNil(failure,failure ?? "");XCTAssertEqual(result["ok"] as? Bool,true)
  return result
 }
 func snapshot(_ label:String) { observe("snapshot?label="+label) }
 func begin(_ id:String) {XCTAssertTrue(wait{!self.node("reader.busy").exists && !self.node("library.busy").exists});snapshot(id+".before")}
 func mark(_ id:String,_ native:String,_ value:String="",enabled:Bool=true) {
  XCTAssertTrue(wait{!self.node("reader.busy").exists && !self.node("library.busy").exists});snapshot(id+".after")
  let row:[String:Any]=["action":id,"native_id":native,"exposed":true,"enabled":enabled,"executed":true,"result":"passed","input":id == "no_unexpected_revision" ? "independent-public-readback" : "native-touch","keyboard_focus":"unverified","value":value,"before":id+".before","after":id+".after"]
  rows.append(row);let data=try! JSONSerialization.data(withJSONObject:row,options:[.sortedKeys]);print("D18_ACTION "+String(decoding:data,as:UTF8.self))
  // Dots are treated as filename extensions by xcresult export. Keep semantic
  // action IDs unchanged but give each attachment a unique extension-free stem.
  let stem="d18-"+id.replacingOccurrences(of:".",with:"-")
  let tree=XCTAttachment(string:app.debugDescription);tree.name=stem+"-tree";tree.lifetime = .keepAlways;add(tree)
  let shot=XCTAttachment(screenshot:app.screenshot());shot.name=stem+"-screen";shot.lifetime = .keepAlways;add(shot)
 }
 func more(_ id:String,_ label:String) {
  let trigger=node("reader.more").buttons.firstMatch
  XCTAssertTrue(wait{trigger.exists && trigger.frame.width>0 && trigger.frame.height>0 && self.app.windows.firstMatch.frame.contains(trigger.frame)})
  trigger.coordinate(withNormalizedOffset:CGVector(dx:0.5,dy:0.5)).tap()
  XCTAssertTrue(wait{self.node(id).exists || self.app.buttons[label].exists})
  if node(id).exists {tap(id)} else {app.buttons[label].tap()}
 }
 func pickerCancel() {
  XCTAssertTrue(wait{self.app.buttons["Cancel"].exists || self.app.buttons["取消"].exists})
  if app.buttons["Cancel"].exists {app.buttons["Cancel"].tap()} else {app.buttons["取消"].tap()}
  XCTAssertTrue(wait{self.node("library.book.0").exists && self.node("library.book.0").isHittable})
 }
 func tapLabel(_ labels:[String])->Bool {
  for label in labels {
   for kind in [XCUIElement.ElementType.button,.cell,.staticText,.other] {
    let matches=app.descendants(matching:kind).matching(NSPredicate(format:"label == %@",label))
    for i in 0..<matches.count {let n=matches.element(boundBy:i);if n.isHittable && n.isEnabled {n.tap();return true}}
   }
  };return false
 }
 func selectBrokenInNativePicker() {
  tap("library.import.picker")
  XCTAssertTrue(wait{self.app.buttons["Cancel"].exists || self.app.buttons["取消"].exists})
  // Files opens Recents or the remembered directory. Browse into the actual
  // app Documents folder populated by the independent fixture driver.
  var selected=false
  for _ in 0..<12 {
   let files=app.descendants(matching:.any).matching(NSPredicate(format:"label CONTAINS %@","D18-Broken"))
   for i in 0..<files.count {let file=files.element(boundBy:i);if file.isHittable && file.isEnabled {file.tap();selected=true;break}}
   if selected {break}
   if tapLabel(["EXReader"]) {RunLoop.current.run(until:Date().addingTimeInterval(1));continue}
   if tapLabel(["On My iPhone","On My iPad","我的 iPhone","我的 iPad"]) {RunLoop.current.run(until:Date().addingTimeInterval(1));continue}
   if tapLabel(["Browse","浏览"]) {RunLoop.current.run(until:Date().addingTimeInterval(1));continue}
   if tapLabel(["Locations","位置"]) {RunLoop.current.run(until:Date().addingTimeInterval(1));continue}
   RunLoop.current.run(until:Date().addingTimeInterval(0.5))
  }
  XCTAssertTrue(selected,"Actual native picker did not expose seeded broken EPUB: "+app.debugDescription)
  // Some Files versions select a row then require Open rather than opening it.
  if app.buttons["Open"].exists && app.buttons["Open"].isHittable {app.buttons["Open"].tap()}
  XCTAssertTrue(wait{self.node("library.error").exists && !self.node("library.busy").exists && self.node("library.book.0").isHittable},app.debugDescription)
 }
 func test17NativeActionsAndRejectedStorage() {
  app.launchArguments=["-EXRUITestFixtures","1","-EXRFreshState","1"];app.launch()
  XCTAssertTrue(wait{self.node("library.title").exists && !self.node("library.busy").exists})
  observe("prepare")
  begin("import");tap("library.import.epub");XCTAssertTrue(wait{self.node("library.book.0").exists && !self.node("library.busy").exists});mark("import","library.import.epub","original D11 native fixture import")
  snapshot("book.open.before");tap("library.book.0");XCTAssertTrue(wait{self.node("reader.page").exists && !self.node("reader.busy").exists});XCTAssertFalse(node("reader.state").exists,"HOST_REVIEW macro leak");let opened=observe("snapshot?label=opened.idle")
  let first=text("reader.location")
  begin("next");tap("reader.next");XCTAssertTrue(wait{!self.node("reader.busy").exists && self.text("reader.location") != first});mark("next","reader.next",text("reader.location"))
  begin("previous");tap("reader.previous");XCTAssertTrue(wait{!self.node("reader.busy").exists && self.text("reader.location")==first});mark("previous","reader.previous",first)
  begin("search");tap("reader.search");XCTAssertTrue(node("search.query").waitForExistence(timeout:15))
  begin("disabled_noop");let disabled=node("search.find");XCTAssertFalse(disabled.isEnabled);let statusBefore=text("search.status");let queryBefore=node("search.query").value as? String ?? "";let box=disabled.frame
  XCTAssertTrue(box.width>0 && box.height>0 && app.windows.firstMatch.frame.contains(box));disabled.coordinate(withNormalizedOffset:CGVector(dx:0.5,dy:0.5)).tap();RunLoop.current.run(until:Date().addingTimeInterval(0.5))
  XCTAssertFalse(node("search.find").isEnabled);XCTAssertEqual(text("search.status"),statusBefore);XCTAssertEqual(node("search.query").value as? String ?? "",queryBefore);mark("disabled_noop","search.find",statusBefore,enabled:false)
  node("search.query").tap();node("search.query").typeText("D18_UNMATCHED_TOKEN");tap("search.find");XCTAssertTrue(wait{self.text("search.status").contains("没有匹配结果")});mark("search","search.query",text("search.status"))
  begin("close.search");tap("search.close");XCTAssertTrue(wait{!self.node("search.query").exists});mark("close.search","search.close")
  begin("directory");tap("reader.navigation");XCTAssertTrue(node("navigation.close").waitForExistence(timeout:15));mark("directory","reader.navigation")
  begin("close.directory");tap("navigation.close");XCTAssertTrue(wait{!self.node("navigation.close").exists});mark("close.directory","navigation.close")
  begin("records");more("reader.records","阅读记录");XCTAssertTrue(node("reading.close").waitForExistence(timeout:15));mark("records","reader.records")
  begin("close.records");tap("reading.close");XCTAssertTrue(wait{!self.node("reading.close").exists});mark("close.records","reading.close")
  begin("settings");more("reader.theme","阅读主题");XCTAssertTrue(node("theme.close").waitForExistence(timeout:15));mark("settings","reader.theme","page theme only; not full preferences")
  begin("close.settings");tap("theme.close");XCTAssertTrue(wait{!self.node("theme.close").exists});mark("close.settings","theme.close")
  begin("back");tap("reader.back");XCTAssertTrue(wait{self.node("library.title").exists});mark("back","reader.back")
  begin("cancel");tap("library.import.picker");pickerCancel();mark("cancel","library.import.picker","real native picker Cancel")
  begin("reject.badfile");selectBrokenInNativePicker();mark("reject.badfile","library.import.picker",text("library.error"))
  begin("resume");tap("library.book.0");XCTAssertTrue(wait{self.node("reader.page").exists && !self.node("reader.busy").exists});mark("resume","library.book.0","reopen; dedicated Continue not granted")
  begin("continue_after_return");tap("reader.next");XCTAssertTrue(wait{!self.node("reader.busy").exists && self.text("reader.location") != first});mark("continue_after_return","reader.next")
  begin("no_unexpected_revision");let finalObservation=observe("snapshot?label=final.idle")
  let baseline=opened["semantic"] as! [String:String];let finalState=finalObservation["semantic"] as! [String:String]
  XCTAssertEqual(baseline["sources_sha256"],finalState["sources_sha256"])
  XCTAssertEqual(baseline["revisions_sha256"],finalState["revisions_sha256"])
  mark("no_unexpected_revision","independent-public-sdk-and-readonly-catalog","original bytes, revisions and outbox match opened.idle; ordinary progress kept separately; independent verifier repeats comparison")
 }
}
