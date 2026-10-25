// SPDX-License-Identifier: MIT
#if EXR_APPLE_PAGE_THEME
import SwiftUI

func hostPageThemeColor(_ value: UInt32) -> Color {
    Color(.sRGB, red: Double(value >> 24) / 255,
          green: Double((value >> 16) & 255) / 255,
          blue: Double((value >> 8) & 255) / 255,
          opacity: Double(value & 255) / 255)
}

struct HostPageThemeSheet: View {
    @ObservedObject var model: HostReaderModel
    @Environment(\.presentationMode) private var presentation
    var body: some View {
        VStack(spacing: 12) {
            Text("阅读主题").font(.headline).accessibilityAddTraits(.isHeader)
            ScrollView {
                VStack(spacing: 8) {
                    ForEach(HostPageThemeChoice.allCases, id: \.rawValue) { choice in
                        Button { model.changePageTheme(choice) } label: {
                            HStack {
                                Text(choice.title)
                                Spacer()
                                if choice == model.pageThemeChoice { Image(systemName: "checkmark") }
                            }.padding(10).frame(minHeight: 44).contentShape(Rectangle())
                        }.buttonStyle(.plain).disabled(model.busy)
                            .accessibilityIdentifier("theme.choice.\(choice.rawValue)")
                            .accessibilityValue(choice == model.pageThemeChoice ? "已选" : "")
                    }
                }
            }
            Text(model.current?.isFixed == true ? "PDF 和漫画保留原书色彩。" : "图片和书中的背景保留原样。")
                .font(.caption).foregroundColor(.secondary)
            Text(model.statusText).font(.caption).accessibilityIdentifier("theme.status")
#if EXR_APPLE_HOST_REVIEW
            if model.showsTestFixtures {
                Text(model.pageThemeObservation).font(.system(size: 5)).lineLimit(1)
                    .accessibilityIdentifier("theme.bitmap")
                Button("请求系统外观检查") { model.requestPageThemeSystemReview() }
                    .accessibilityIdentifier("theme.system-review")
            }
#endif
            Button("关闭") { presentation.wrappedValue.dismiss() }.buttonStyle(.bordered)
                .accessibilityIdentifier("theme.close")
        }.padding().frame(minWidth: 280, minHeight: 280)
    }
}
#endif
