import SwiftUI

struct LibraryView: View {
    @EnvironmentObject var library: LibraryStore
    @EnvironmentObject var engine: PlayerEngine
    @State private var search = ""

    private var filtered: [Track] {
        guard !search.isEmpty else { return library.tracks }
        return library.tracks.filter {
            $0.title.localizedCaseInsensitiveContains(search)
                || $0.artist.localizedCaseInsensitiveContains(search)
        }
    }

    var body: some View {
        NavigationStack {
            List {
                ForEach(filtered) { track in
                    Button {
                        engine.playQueue(library.tracks, startAt: track)
                    } label: {
                        HStack(spacing: 10) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(track.title)
                                    .font(.body)
                                    .foregroundStyle(engine.current?.id == track.id ? Color.accentColor : Color.primary)
                                Text(track.artist)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer(minLength: 8)
                            if track.hasLyrics {
                                Image(systemName: "text.bubble")
                                    .font(.caption)
                                    .foregroundStyle(.tertiary)
                            }
                            Text(TimeFormat.seconds(track.duration))
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
            .navigationTitle("曲库（\(library.tracks.count)）")
            .searchable(text: $search, prompt: "搜索歌名 / 歌手")
            .refreshable { library.refresh() }
            .overlay {
                if library.tracks.isEmpty {
                    ContentUnavailableView(
                        "还没有音乐",
                        systemImage: "music.note",
                        description: Text("用「导入」页从电脑拉取，或用数据线经 iTunes / Apple 设备把 MP3 放入 Music 文件夹")
                    )
                }
            }
        }
    }
}
