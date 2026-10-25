import XCTest
final class ActionFocusTests: XCTestCase {
 var app: XCUIApplication!
 var rows: [[String:Any]] = []
 override func setUpWithError() throws { continueAfterFailure = false; app = XCUIApplication() }
 override func tearDownWithError() throws {
  let trace=XCTAttachment(string:app.debugDescription); trace.name="final-native-tree";trace.lifetime = .keepAlways;add(trace)
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
 func mark(_ id:String,_ native:String,_ value:String="",enabled:Bool=true) {
  let row:[String:Any]=["case":name,"action":id,"native_id":native,"exposed":true,"enabled":enabled,"executed":true,"result":"passed","input":"native-pointer","focus":"unverified","value":value];rows.append(row)
  let data=try! JSONSerialization.data(withJSONObject:row,options:[.sortedKeys]);print("D11_ACTION "+String(decoding:data,as:UTF8.self))
  let tree=XCTAttachment(string:app.debugDescription);tree.name=id+"-tree";tree.lifetime = .keepAlways;add(tree)
 }
 func more(_ id:String,_ label:String) {
#if os(iOS)
  let trigger=node("reader.more").buttons.firstMatch
  XCTAssertTrue(wait{trigger.exists && trigger.frame.width>0 && trigger.frame.height>0 && self.app.windows.firstMatch.frame.contains(trigger.frame)})
  print("D11_MENU_AX hittable=\(trigger.isHittable)")
  trigger.coordinate(withNormalizedOffset:CGVector(dx:0.5,dy:0.5)).tap()
#else
  tap("reader.more")
#endif
  XCTAssertTrue(wait{self.node(id).exists || self.app.menuItems[label].exists || self.app.buttons[label].exists})
  if node(id).exists {tap(id)} else if app.menuItems[label].exists {app.menuItems[label].tap()} else {app.buttons[label].tap()}
 }
 func open() {
  app.launchArguments=["-EXRUITestFixtures","1","-EXRFreshState","1"];app.launch()
  XCTAssertTrue(wait{self.node("library.title").exists && !self.node("library.busy").exists})
  tap("library.import.epub");XCTAssertTrue(wait{self.node("library.book.0").exists && !self.node("library.busy").exists});mark("import","library.import.epub","authored fixture via native entry")
  tap("library.book.0");XCTAssertTrue(wait{self.node("reader.page").exists && !self.node("reader.busy").exists})
  XCTAssertFalse(node("reader.state").exists,"HOST_REVIEW macro leak")
 }
 func testReadingActions() {
  open();let first=text("reader.location")
  tap("reader.next");XCTAssertTrue(wait{!self.node("reader.busy").exists && self.text("reader.location") != first});mark("next","reader.next",text("reader.location"))
  tap("reader.previous");XCTAssertTrue(wait{!self.node("reader.busy").exists && self.text("reader.location")==first});mark("previous","reader.previous",first)
  tap("reader.search");XCTAssertTrue(node("search.query").waitForExistence(timeout:15));let disabled=node("search.find");XCTAssertFalse(disabled.isEnabled);let statusBefore=text("search.status");let queryBefore=node("search.query").value as? String ?? "";let box=disabled.frame
  XCTAssertTrue(box.width>0 && box.height>0 && app.windows.firstMatch.frame.contains(box))
  disabled.coordinate(withNormalizedOffset:CGVector(dx:0.5,dy:0.5)).tap()
  RunLoop.current.run(until:Date().addingTimeInterval(0.5));XCTAssertFalse(node("search.find").isEnabled);XCTAssertEqual(text("search.status"),statusBefore);XCTAssertEqual(node("search.query").value as? String ?? "",queryBefore);mark("disabled_noop","search.find",statusBefore,enabled:false)
  node("search.query").tap();node("search.query").typeText("D11_UNMATCHED_TOKEN");XCTAssertTrue((node("search.query").value as? String ?? "").contains("D11_UNMATCHED_TOKEN"));tap("search.find");XCTAssertTrue(wait{self.text("search.status").contains("没有匹配结果")});mark("search","search.query",text("search.status"))
  tap("search.close");XCTAssertTrue(wait{!self.node("search.query").exists});mark("close.search","search.close")
  tap("reader.navigation");XCTAssertTrue(node("navigation.close").waitForExistence(timeout:15));mark("directory","reader.navigation");tap("navigation.close");XCTAssertTrue(wait{!self.node("navigation.close").exists});mark("close.directory","navigation.close")
  more("reader.records","阅读记录");XCTAssertTrue(node("reading.close").waitForExistence(timeout:15));mark("records","reader.records");tap("reading.close");XCTAssertTrue(wait{!self.node("reading.close").exists});mark("close.records","reading.close")
  more("reader.theme","阅读主题");XCTAssertTrue(node("theme.close").waitForExistence(timeout:15));mark("settings","reader.theme","page theme only; not full F3 preferences");tap("theme.close");XCTAssertTrue(wait{!self.node("theme.close").exists});mark("close.settings","theme.close")
  tap("reader.back");XCTAssertTrue(wait{self.node("library.title").exists});mark("back","reader.back")
  tap("library.book.0");XCTAssertTrue(wait{self.node("reader.page").exists && !self.node("reader.busy").exists});mark("resume","library.book.0","reopen; dedicated Continue missing")
  tap("reader.next");XCTAssertTrue(wait{!self.node("reader.busy").exists && self.text("reader.location") != first});mark("continue_after_return","reader.next")
 }
 func testPickerCancel() {
  open();tap("reader.back");XCTAssertTrue(wait{self.node("library.title").exists});tap("library.import.picker")
  XCTAssertTrue(wait{self.app.buttons["Cancel"].exists || self.app.buttons["取消"].exists})
#if os(macOS)
  // The original failure was a TouchBar alias, not an unreachable picker.
  // Scope to actual native windows and require exactly one operable button.
  let candidates=app.windows.descendants(matching:.button).matching(NSPredicate(format:"label == %@ OR label == %@","Cancel","取消"))
  XCTAssertTrue(wait{candidates.count==1 && candidates.firstMatch.isEnabled && candidates.firstMatch.isHittable},app.debugDescription)
  candidates.firstMatch.tap()
#else
  if app.buttons["Cancel"].exists {app.buttons["Cancel"].tap()} else {app.buttons["取消"].tap()}
#endif
  XCTAssertTrue(wait{self.node("library.book.0").exists && self.node("library.book.0").isHittable});mark("cancel","library.import.picker")
 }
}
