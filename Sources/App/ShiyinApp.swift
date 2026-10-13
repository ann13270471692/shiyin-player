import SwiftUI

@main
struct ShiyinApp: App {
    @StateObject private var library = LibraryStore()
    @StateObject private var engine = PlayerEngine.shared
    // 下载器共享给曲库页：删除手机副本后要清掉它的「已下载」记录
    @StateObject private var downloader = SyncDownloader()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(library)
                .environmentObject(engine)
                .environmentObject(downloader)
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
