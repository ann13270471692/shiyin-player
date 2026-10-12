import SwiftUI

@main
struct ShiyinApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}

struct ContentView: View {
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "music.note.list")
                .font(.system(size: 72))
                .foregroundStyle(.tint)
            Text("拾音")
                .font(.largeTitle.bold())
            Text("M0 · 安装链路验证成功 🎉")
                .foregroundStyle(.secondary)
        }
        .padding()
    }
}
