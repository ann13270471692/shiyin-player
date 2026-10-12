import SwiftUI

struct LyricsView: View {
    @EnvironmentObject var engine: PlayerEngine
    @State private var lines: [LyricLine] = []
    @State private var currentIdx = -1
    @State private var loading = false
    @State private var manualUntil = Date.distantPast
    @State private var lastIdxChange = Date.distantPast

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
                        VStack(spacing: 14) {
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
                    }                    .simultaneousGesture(
                        DragGesture(minimumDistance: 12)
                            .onChanged { _ in
                                manualUntil = Date().addingTimeInterval(4)
                            }
                    )
                    .safeAreaInset(edge: .top, spacing: 0) {
                        HStack(spacing: 10) {
                            Text(String(format: "歌词偏移 %+.1fs", engine.lyricOffset))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Button("−0.5s") { engine.nudgeLyricOffset(-0.5) }
                                .font(.caption)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 5)
                                .background(.thinMaterial, in: Capsule())
                            Button("+0.5s") { engine.nudgeLyricOffset(0.5) }
                                .font(.caption)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 5)
                                .background(.thinMaterial, in: Capsule())
                            Spacer()
                        }
                        .padding(.vertical, 6)
                    }
                    .onChange(of: currentIdx) { _, new in
                        guard new >= 0, Date() >= manualUntil else { return }
                        let fast = Date().timeIntervalSince(lastIdxChange) < 0.8
                        lastIdxChange = Date()
                        if fast {
                            // 快嘴段落：行距太近，排队动画会连成整页滚动，直接对齐
                            proxy.scrollTo(new, anchor: .center)
                        } else {
                            withAnimation(.smooth(duration: 0.35)) {
                                proxy.scrollTo(new, anchor: .center)
                            }
                        }
                    }
                    .overlay(alignment: .bottom) {
                        if Date() < manualUntil {
                            Button {
                                manualUntil = .distantPast
                                if currentIdx >= 0 {
                                    withAnimation(.easeOut(duration: 0.3)) {
                                        proxy.scrollTo(currentIdx, anchor: .center)
                                    }
                                }
                            } label: {
                                Image(systemName: "location")
                                    .font(.body)
                                    .padding(11)
                                    .background(.thinMaterial, in: Circle())
                                    .shadow(radius: 3)
                            }
                            .padding(.bottom, 10)
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
        let pos = t + engine.lyricOffset
        var idx = -1
        for (i, line) in lines.enumerated() {
            if line.time <= pos + 0.15 { idx = i } else { break }
        }
        if idx != currentIdx { currentIdx = idx }
    }
}
