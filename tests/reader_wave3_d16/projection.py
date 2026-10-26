"""Only D16's declared tap-driver actions differ from the immutable D10 test."""
OLD_SCROLL = '''            // Reach by the existing toolbar's native scrolling; never re-tap.
            for _ in 0..<12 {
                let e = node(id), tools = node("reader.tools.scroll")
                if tools.frame.contains(e.frame) && app.windows.firstMatch.frame.contains(e.frame) && e.isHittable { break }
                XCTAssertEqual(tools.elementType, .scrollView, "Only real scroll container may move")
                capture("offscreen-before-scroll-" + id)
                print("D10_TRACE scroll to " + id)
                if e.frame.midX < tools.frame.midX { tools.swipeRight() } else { tools.swipeLeft() }
            }
'''
NEW_SCROLL = '''            // D16: measure a fresh native viewport, then drag a bounded distance.
            // Slow release with a stationary hold avoids full-swipe momentum.
            // No hidden-control tap, retry tap, font reduction or app mutation.
            for index in 0..<12 {
                let e = node(id), tools = node("reader.tools.scroll")
                let frame = e.frame
                let viewport = tools.frame.intersection(app.windows.firstMatch.frame)
                if !frame.isEmpty && viewport.contains(frame) && e.isHittable { break }
                XCTAssertEqual(tools.elementType, .scrollView, "Only real scroll container may move")
                XCTAssertFalse(viewport.isEmpty, "Native toolbar viewport must be visible")
                XCTAssertFalse(frame.isEmpty, "Fresh target frame required: " + id)
                XCTAssertLessThanOrEqual(frame.width, viewport.width, "Target cannot fit native viewport: " + id)
                capture("offscreen-before-scroll-" + id)
                let limit = viewport.width * 0.55
                let delta = max(-limit, min(limit, viewport.midX - frame.midX))
                let startPoint = CGPoint(x: viewport.midX - delta / 2, y: viewport.midY)
                let endPoint = CGPoint(x: viewport.midX + delta / 2, y: viewport.midY)
                XCTAssertTrue(viewport.contains(startPoint) && viewport.contains(endPoint), "Native drag endpoints")
                A11yAudit.emit("D16_NATIVE_SCROLL", ["control": id, "iteration": index,
                    "frame_before": A11yAudit.frameJSON(frame), "viewport": A11yAudit.frameJSON(viewport),
                    "delta_x": Double(delta), "window": A11yAudit.frameJSON(app.windows.firstMatch.frame)])
                let origin = app.windows.firstMatch.coordinate(withNormalizedOffset: CGVector(dx: 0, dy: 0))
                let window = app.windows.firstMatch.frame
                let start = origin.withOffset(CGVector(dx: startPoint.x - window.minX, dy: startPoint.y - window.minY))
                let end = origin.withOffset(CGVector(dx: endPoint.x - window.minX, dy: endPoint.y - window.minY))
                start.press(forDuration: 0.05, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.25)
                A11yAudit.emit("D16_NATIVE_SCROLL_RESULT", ["control": id, "iteration": index,
                    "frame_after": A11yAudit.frameJSON(node(id).frame)])
            }
'''
PRECONDITION = '''        // D16: geometry MUST precede the final activation-point query as well.
        let finalFrame = node(id).frame
        let finalWindow = app.windows.firstMatch.frame
        XCTAssertFalse(finalFrame.isEmpty, id)
        XCTAssertTrue(finalWindow.contains(finalFrame), "Offscreen final target: " + id)
        if id.hasPrefix("reader."), node("reader.tools.scroll").exists,
           !["reader.more", "reader.back", "reader.records"].contains(id) {
            XCTAssertTrue(node("reader.tools.scroll").frame.intersection(finalWindow).contains(finalFrame),
                          "Target outside native scroll range: " + id)
        }
'''
def project(original):
    assert original.count(OLD_SCROLL) == 1
    anchor = '        capture("before-" + id)\n'
    assert original.count(anchor) == 1
    return original.replace(OLD_SCROLL, NEW_SCROLL, 1).replace(anchor, PRECONDITION + anchor, 1)
