// SPDX-License-Identifier: MIT
import SwiftUI

@main
struct EXReaderHostApp: App {
    var body: some Scene {
        WindowGroup {
            HostRootView()
        }
    }
}

struct SelfTestScreen: View {
    @State private var status = "运行中…"
    @State private var detail = ""

    var body: some View {
        VStack(spacing: 12) {
            Text("EXReader 自检").font(.title2).bold()
            Text(status).accessibilityIdentifier("selftest.status")
            if !detail.isEmpty {
                Text(detail).font(.caption).foregroundColor(.secondary)
                    .accessibilityIdentifier("selftest.detail")
            }
        }
        .padding()
        .frame(minWidth: 360, minHeight: 200)
        .onAppear {
            let outcome = LegacySelfTest.run()
            status = outcome.passed ? "通过 \(outcome.checkCount) 项" : "失败"
            detail = outcome.error ?? ""
        }
    }
}
