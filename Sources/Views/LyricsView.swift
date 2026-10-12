import SwiftUI

struct LyricsView: View {
    @EnvironmentObject var engine: PlayerEngine
    @State private var lines: [LyricLine] = []
    @State private var currentIdx = -1
    @State private var loading = false

    var body: some View {
        Group {
            if lines.isEmpty {
                VStack {
                    Spacer()
                    Text(loading ? "歌词加载中…" : "暂无歌词")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Spacer()
                }
                .frame(maxWidth: .infinity)
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 14) {
                            ForEach(Array(lines.enumerated()), id: \.element.id) { i, line in
                                Text(line.text)
                                    .font(i == currentIdx ? .title3.bold() : .body)
                                    .foregroundStyle(i == currentIdx ? Color.primary : Color.secondary.opacity(0.5))
                                    .multilineTextAlignment(.center)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 4)
                                    .id(i)
                                    .onTapGesture { engine.seek(to: line.time) }
                            }
                            Color.clear.frame(height: 100)
                        }
                        .padding(.horizontal)
                        .padding(.top, 100)
                    }
                    .onChange(of: currentIdx) { _, new in
                        guard new >= 0 else { return }
                        withAnimation(.easeOut(duration: 0.3)) {
                            proxy.scrollTo(new, anchor: .center)
                        }
                    }
                }
            }
        }
        .frame(maxHeight: .infinity)
        .task(id: engine.current?.path) {
            await loadLyrics()
        }
        .onChange(of: engine.currentTime) { _, t in
            updateIndex(at: t)
        }
    }

    private func loadLyrics() async {
        lines = []
        currentIdx = -1
        guard let cur = engine.current else { return }
        loading = true
        defer { loading = false }

        var raw: String?
        if let lrcURL = cur.lyricsURL,
           let s = try? String(contentsOf: lrcURL, encoding: .utf8) {
            raw = s
        }
        if raw == nil || (raw ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            raw = await engine.embeddedLyrics(for: cur)
        }
        let parsed = LRCParser.parse(raw ?? "")
        lines = parsed
        updateIndex(at: engine.currentTime)
    }

    private func updateIndex(at t: Double) {
        guard !lines.isEmpty else { return }
        var idx = -1
        for (i, line) in lines.enumerated() {
            if line.time <= t + 0.15 { idx = i } else { break }
        }
        if idx != currentIdx { currentIdx = idx }
    }
}
