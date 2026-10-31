
    func test08F08ScrollMetrics() {
        search("")
        _ = ready("")
        let options = XCTMeasureOptions()
        options.iterationCount = 5
        options.invocationOptions = [.manuallyStop]
        measure(metrics: [XCTOSSignpostMetric.scrollingAndDecelerationMetric,
                          XCTMemoryMetric(application: app)], options: options) {
            for _ in 0..<10 { scroll(previous: false) }
            stopMeasuring()
            for _ in 0..<10 { scroll(previous: true) }
            _ = ready("")
        }
        record("f08-scroll-metrics", ready(""))
    }
