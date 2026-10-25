import XCTest
final class ActionFocusTests: XCTestCase {
 var app: XCUIApplication!
 var steps: [String] = []
 override func setUpWithError() throws { continueAfterFailure = false; app = XCUIApplication() }
 override func tearDownWithError() throws {
  let trace = XCTAttachment(string: app.debugDescription); trace.name="final-native-tree";trace.lifetime = .keepAlways;add(trace)
  let record = XCTAttachment(string: steps.joined(separator:"\n"));record.name="executed-actions";record.lifetime = .keepAlways;add(record);app.terminate()
 }
 func node(_ id:String)->XCUIElement {app.descendants(matching:.any).matching(identifier:id).firstMatch}
 func wait(_ predicate:()->Bool)->Bool {let end=Date().addingTimeInterval(90);while Date()<end {if predicate(){return true};RunLoop.current.run(until:Date().addingTimeInterval(0.2))};return predicate()}
 func tap(_ id:String) {XCTAssertTrue(wait{self.node(id).exists && self.node(id).isEnabled && self.node(id).isHittable},id);node(id).tap()}
 func text(_ id:String)->String {let n=node(id);return n.label.isEmpty ? (n.value as? String ?? "") : n.label}
 func mark(_ name:String) {steps.append(name);let tree=XCTAttachment(string:app.debugDescription);tree.name=name+"-tree";tree.lifetime = .keepAlways;add(tree);let shot=XCTAttachment(screenshot:app.screenshot());shot.name=name;shot.lifetime = .keepAlways;add(shot);print("D06_ACTION "+name)}
 func testRepresentativeActions() {
  app.launchArguments=["-EXRUITestFixtures","1","-EXRFreshState","1"];app.launch()
  XCTAssertTrue(wait{self.node("library.title").exists && !self.node("library.busy").exists});mark("shelf")
  tap("library.import.epub");XCTAssertTrue(wait{self.node("library.book.0").exists && !self.node("library.busy").exists});mark("import-fixture-native-entry")
  tap("library.book.0");XCTAssertTrue(wait{self.node("reader.page").exists && !self.node("reader.busy").exists});mark("open")
  let before=text("reader.location");tap("reader.next");XCTAssertTrue(wait{!self.node("reader.busy").exists && self.text("reader.location") != before});mark("next-page")
  tap("reader.search");XCTAssertTrue(node("search.query").waitForExistence(timeout:15));node("search.query").tap();node("search.query").typeText("D06_UNMATCHED_TOKEN");XCTAssertTrue((node("search.query").value as? String ?? "").contains("D06_UNMATCHED_TOKEN"));mark("search-text-focus")
  tap("search.find");XCTAssertTrue(wait{self.text("search.status").contains("没有匹配结果")});mark("search-result")
  tap("search.close");XCTAssertFalse(node("search.query").exists);mark("search-close")
  tap("reader.navigation");XCTAssertTrue(node("navigation.close").waitForExistence(timeout:15));mark("directory");tap("navigation.close")
  tap("reader.more");tap("reader.records");XCTAssertTrue(node("reading.close").waitForExistence(timeout:15));mark("records");tap("reading.close")
  tap("reader.back");XCTAssertTrue(wait{self.node("library.title").exists});mark("back-shelf")
 }
}
