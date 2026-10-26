import XCTest
import AppKit
final class D17Actions: XCTestCase {
 var app: XCUIApplication!
 var config: [String:String] = [:]
 var sequence = 0
 override func setUpWithError() throws {
  continueAfterFailure=false
  config=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:"/tmp/exreader-wave3-d17.json"))) as! [String:String]
  app=XCUIApplication()
 }
 override func tearDownWithError() throws { evidence("final"); app.terminate() }
 func evidence(_ name:String) {
  let tree=XCTAttachment(string:app.debugDescription);tree.name=name+"-tree";tree.lifetime = .keepAlways;add(tree)
  let screen=XCTAttachment(screenshot:XCUIScreen.main.screenshot());screen.name=name+"-screen";screen.lifetime = .keepAlways;add(screen)
 }
 func node(_ id:String)->XCUIElement {app.descendants(matching:.any).matching(identifier:id).firstMatch}
 func wait(_ condition:()->Bool)->Bool {let end=Date().addingTimeInterval(45);while Date()<end {if condition(){return true};RunLoop.current.run(until:Date().addingTimeInterval(0.2))};return condition()}
 func idle(){XCTAssertTrue(wait{!self.node("library.busy").exists && !self.node("reader.busy").exists})}
 func tap(_ id:String) {
  XCTAssertTrue(node(id).waitForExistence(timeout:30),id)
  let toolbar=["reader.first","reader.previous","reader.next","reader.font.decrease","reader.font.increase","reader.select","reader.notes","reader.search","reader.navigation"].contains(id)
  func viewport()->CGRect {let window=app.windows.firstMatch.frame.insetBy(dx:-2,dy:-2);return toolbar && node("reader.tools.scroll").exists ? window.intersection(node("reader.tools.scroll").frame) : window}
  for _ in 0..<12 {let frame=node(id).frame;if !frame.isEmpty && viewport().contains(frame) && node(id).isHittable {break};if toolbar && node("reader.tools.scroll").exists {let tools=node("reader.tools.scroll");if !frame.isEmpty && frame.midX<tools.frame.midX {tools.swipeRight()} else {tools.swipeLeft()}} else {break}}
  XCTAssertTrue(wait{viewport().contains(self.node(id).frame) && self.node(id).isEnabled && self.node(id).isHittable},id);node(id).click()
 }
 func text(_ id:String)->String {let n=node(id);return (n.value as? String).flatMap{$0.isEmpty ? nil:$0} ?? n.label}
 func snapshot(_ filename:String) throws {
  let process=Process();process.executableURL=URL(fileURLWithPath:config["python"]!);process.arguments=[config["observe_script"]!,filename];var env=ProcessInfo.processInfo.environment;env["GITHUB_ACTIONS"]="true";process.environment=env
  try process.run();process.waitUntilExit();XCTAssertEqual(process.terminationStatus,0,"independent SDK/catalog observer")
 }
 func step(_ action:String,_ native:String,_ body:() throws ->Void) throws {
  sequence+=1;let key="\(name)-\(sequence)-\(action)";idle();try snapshot(key+"-before.json");evidence(key+"-before")
  try body();idle();try snapshot(key+"-after.json");evidence(key+"-after")
  let row:[String:Any] = ["case":name,"action":action,"native_id":native,"before":key+"-before.json","after":key+"-after.json","input":"native-XCTest","executed":true,"result":"passed"]
  print("D17_ACTION "+String(decoding:try JSONSerialization.data(withJSONObject:row,options:[.sortedKeys]),as:UTF8.self))
 }
 func launch() {
  app.launchArguments=["-EXRUITestFixtures","1","-EXRFreshState","1"];app.launch();app.activate()
  XCTAssertTrue(wait{self.node("library.title").exists && !self.node("library.busy").exists})
 }
 func open(_ action:String) throws {
  try step(action,"library.import.epub") {tap("library.import.epub");XCTAssertTrue(wait{self.node("library.book.0").exists});idle()}
 }
 func more(_ id:String,_ label:String) {
  tap("reader.more");XCTAssertTrue(wait{self.node(id).exists || self.app.menuItems[label].exists})
  if node(id).exists {tap(id)} else {app.menuItems[label].click()}
 }
 // The observed Touch Bar Cancel frame starts at y=-1, but INTERSECTS the
 // desktop. Full containment (not intersection) is required. A remote native
 // panel service may own the actual sheet; never launch or substitute one.
 var pickerApplications:[XCUIApplication] {
  var result=[app!]
  let id="com.apple.appkit.xpc.openAndSavePanelService"
  if !NSRunningApplication.runningApplications(withBundleIdentifier:id).isEmpty {result.append(XCUIApplication(bundleIdentifier:id))}
  return result
 }
 func panelButton(_ labels:[String])->XCUIElement? {
  let matches=pickerApplications.flatMap{$0.descendants(matching:.button).matching(NSPredicate(format:"label IN %@",labels)).allElementsBoundByIndex}
  let visible=matches.filter { b in b.exists && b.isEnabled && b.isHittable && !b.frame.isEmpty && NSScreen.screens.contains{$0.frame.contains(b.frame)} }
  let frames=Set(visible.map{NSStringFromRect($0.frame)})
  return frames.count==1 ? visible.first:nil
 }
 func panelCancel()->XCUIElement? {panelButton(["Cancel","取消"])}
 func pickerDiagnostics(_ phase:String) {
  print("D17_PICKER_SCREENS \(phase) \(NSScreen.screens.map{NSStringFromRect($0.frame)})")
  for owner in pickerApplications {
   print("D17_PICKER_TREE \(phase) BEGIN\n"+owner.debugDescription+"\nD17_PICKER_TREE END")
   for b in owner.buttons.matching(NSPredicate(format:"label IN %@",["Cancel","取消","Open","打开"])).allElementsBoundByIndex {print("D17_PICKER_CONTROL \(phase) label=\(b.label) enabled=\(b.isEnabled) hittable=\(b.isHittable) frame=\(NSStringFromRect(b.frame))")}
  }
 }
 func showPicker() {
  app.activate();tap("library.import.picker")
  XCTAssertTrue(wait{self.pickerApplications.contains{$0.dialogs.count>0 || $0.sheets.count>0 || $0.buttons["Open"].exists || $0.buttons["打开"].exists}},app.debugDescription)
  pickerDiagnostics("presented");evidence("picker-visible")
  if panelCancel()==nil {app.activate();pickerDiagnostics("reactivated")}
  XCTAssertTrue(wait{self.panelCancel() != nil},app.debugDescription)
 }
 func test01ReadingActions() throws {
  launch();try open("import")
  try step("setup.open","library.book.0") {tap("library.book.0");XCTAssertTrue(wait{self.node("reader.page").exists});idle()}
  XCTAssertFalse(node("reader.state").exists,"review macro leak");let first=text("reader.location")
  try step("next","reader.next") {tap("reader.next");XCTAssertTrue(wait{!self.node("reader.busy").exists && self.text("reader.location") != first})}
  try step("previous","reader.previous") {tap("reader.previous");XCTAssertTrue(wait{!self.node("reader.busy").exists && self.text("reader.location")==first})}
  try step("setup.search","reader.search") {tap("reader.search");XCTAssertTrue(node("search.query").waitForExistence(timeout:15))}
  try step("disabled_noop","search.find") {
   let b=node("search.find");XCTAssertFalse(b.isEnabled);let before=text("search.status");let query=node("search.query").value as? String ?? "";let box=b.frame
   XCTAssertTrue(box.width>0 && box.height>0 && app.windows.firstMatch.frame.contains(box));b.coordinate(withNormalizedOffset:CGVector(dx:0.5,dy:0.5)).click()
   RunLoop.current.run(until:Date().addingTimeInterval(0.5));XCTAssertFalse(node("search.find").isEnabled);XCTAssertEqual(text("search.status"),before);XCTAssertEqual(node("search.query").value as? String ?? "",query)
  }
  try step("search","search.query") {node("search.query").click();node("search.query").typeText("D11_UNMATCHED_TOKEN");XCTAssertTrue((node("search.query").value as? String ?? "").contains("D11_UNMATCHED_TOKEN"));tap("search.find");XCTAssertTrue(wait{self.text("search.status").contains("没有匹配结果")})}
  try step("close.search","search.close") {tap("search.close");XCTAssertTrue(wait{!self.node("search.query").exists})}
  try step("directory","reader.navigation") {tap("reader.navigation");XCTAssertTrue(node("navigation.close").waitForExistence(timeout:15))}
  try step("close.directory","navigation.close") {tap("navigation.close");XCTAssertTrue(wait{!self.node("navigation.close").exists})}
  try step("records","reader.records") {more("reader.records","阅读记录");XCTAssertTrue(node("reading.close").waitForExistence(timeout:15))}
  try step("close.records","reading.close") {tap("reading.close");XCTAssertTrue(wait{!self.node("reading.close").exists})}
  try step("settings","reader.theme") {more("reader.theme","阅读主题");XCTAssertTrue(node("theme.close").waitForExistence(timeout:15))}
  try step("close.settings","theme.close") {tap("theme.close");XCTAssertTrue(wait{!self.node("theme.close").exists})}
  try step("back","reader.back") {tap("reader.back");XCTAssertTrue(wait{self.node("library.title").exists})}
  try step("resume","library.book.0") {tap("library.book.0");XCTAssertTrue(wait{self.node("reader.page").exists});idle();XCTAssertEqual(text("reader.location"),first)}
  try step("continue_after_return","reader.next") {tap("reader.next");XCTAssertTrue(wait{!self.node("reader.busy").exists && self.text("reader.location") != first})}
 }
 func test02PickerCancelAndRealRejection() throws {
  launch();try open("setup.import")
  try step("cancel","library.import.picker") {showPicker();let button=try XCTUnwrap(panelCancel());button.click();XCTAssertTrue(wait{self.node("library.book.0").isHittable && self.panelCancel()==nil})}
  // A real existing malformed file is selected and submitted. This is rejection,
  // not cancellation, and must preserve the same independent storage boundary.
  try step("reject_existing_broken","library.import.picker") {
   showPicker();XCTAssertTrue(FileManager.default.fileExists(atPath:config["broken"]!))
   let cancel=try XCTUnwrap(panelCancel());cancel.typeKey("g",modifierFlags:[.command,.shift])
   XCTAssertTrue(wait{self.pickerApplications.contains{$0.textFields.allElementsBoundByIndex.contains{$0.isHittable} || $0.comboBoxes.allElementsBoundByIndex.contains{$0.isHittable}}})
   // Cmd-Shift-G gives focus to the native Go To Folder field. Keyboard input
   // goes to that focused field; do not click the unrelated picker Search box.
   app.typeKey("a",modifierFlags:.command);app.typeText(config["broken"]!);app.typeKey(.return,modifierFlags:[])
   XCTAssertTrue(wait{self.panelButton(["Open","打开"]) != nil});pickerDiagnostics("broken-selected");try XCTUnwrap(panelButton(["Open","打开"])).click()
   XCTAssertTrue(wait{self.node("library.book.0").isHittable && self.panelCancel()==nil});idle()
   XCTAssertTrue(wait{self.node("library.error").exists || self.app.staticTexts.containing(NSPredicate(format:"label CONTAINS %@ OR label CONTAINS %@","失败","错误")).count>0},app.debugDescription)
  }
 }
}
