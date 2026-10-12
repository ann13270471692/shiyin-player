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
        .onChange(of: engine.outputLatency) { _, _ in
            updateIndex(at: engine.currentTime)
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

    /// 制作信息 / 版权水印 / 空行：这些不是唱出来的词，不参与高亮
    static func nonVocal(_ s: String) -> Bool {
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
        if t.isEmpty { return true }
        let pat = "作词|作曲|编曲|制作人|出品|发行|录音|混音|母带|和声|监制|统筹|总监|版权|厂牌|经纪|宣传|文案|"
            + "封面|设计|摄影|吉他|贝斯|鼓手|弦乐|提琴|铜管|钢琴|合成|Program|Engineer|Studio|Label|Recorded|"
            + "Mixed|Master|Written|Arrang|未经许可|翻唱|禁止|ISRC|OPI|PBM|SPD|OP\\s*[:：]"
        if t.range(of: pat, options: .regularExpression) != nil { return true }
        // (间奏) (主歌) (副歌) (桥段) 这类段落标记也不是唱出来的
        if (t.hasPrefix("(") || t.hasPrefix("（")) && (t.hasSuffix(")") || t.hasSuffix("）")) { return true }
        // "XX ：YY" 这种标签行（如 "音乐项目总监：代诗琪"）
        return t.range(of: "^\\S{1,8}\\s*[:：]\\s*\\S", options: .regularExpression) != nil
    }

    private func updateIndex(at t: Double) {
        guard !lines.isEmpty else { return }
        let pos = engine.lyricPosition
        var idx = -1
        for (i, line) in lines.enumerated() {
            if line.time > pos { break }
            if !Self.nonVocal(line.text) { idx = i }
        }
        if idx != currentIdx { currentIdx = idx }
    }
}
