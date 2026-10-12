import SwiftUI

@main
struct ShiyinApp: App {
    @StateObject private var library = LibraryStore()
    @StateObject private var engine = PlayerEngine.shared

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(library)
                .environmentObject(engine)
                .onAppear { library.refresh() }
        }
    }
}

struct RootView: View {
    var body: some View {
        TabView {
            LibraryView()
                .tabItem { Label("曲库", systemImage: "music.note.list") }
            NowPlayingView()
                .tabItem { Label("播放", systemImage: "play.circle") }
            ImportView()
                .tabItem { Label("导入", systemImage: "wifi") }
        }
    }
}
