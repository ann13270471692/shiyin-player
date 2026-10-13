import SwiftUI
import UIKit

/// 品牌色，与鸿蒙版 ACCENT (#FF9F0A) 保持一致
extension Color {
    static let brand = Color(red: 1.0, green: 0.624, blue: 0.039)
}

struct NowPlayingView: View {
    @EnvironmentObject var engine: PlayerEngine
    @State private var toastText: String?
    @State private var toastID = 0

    var body: some View {
        NavigationStack {
            Group {
                if let cur = engine.current {
                    VStack(spacing: 16) {
                        HStack(spacing: 16) {
                            ArtworkView(track: cur)
                                .frame(width: 84, height: 84)
                            VStack(alignment: .leading, spacing: 5) {
                                Text(cur.title)
                                    .font(.title3.bold())
                                    .lineLimit(1)
                                Text(cur.artist)
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        ProgressSection()
                        ControlsSection { mode in showToast(mode) }

                        LyricsView()
                    }
                    .padding(.horizontal)
                } else {
                    ContentUnavailableView(
                        "未在播放",
                        systemImage: "music.note",
                        description: Text("从曲库选一首开始")
                    )
                }
            }
            // 切换随机 / 循环后的轻量 toast：短暂显示模式名
            .overlay(alignment: .bottom) {
                if let t = toastText {
                    Text(t)
                        .font(.footnote.weight(.medium))
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .background(.ultraThinMaterial, in: Capsule())
                        .shadow(color: .black.opacity(0.15), radius: 6, y: 2)
                        .transition(.opacity)
                        .padding(.bottom, 10)
                }
            }
            .navigationTitle("播放")
        }
    }

    private func showToast(_ text: String) {
        toastID += 1
        let id = toastID
        withAnimation(.easeOut(duration: 0.2)) { toastText = text }
        Task {
            try? await Task.sleep(nanoseconds: 1_100_000_000)
            if id == toastID {
                withAnimation(.easeIn(duration: 0.25)) { toastText = nil }
            }
        }
    }
}

private struct ArtworkView: View {
    @EnvironmentObject var engine: PlayerEngine
    let track: Track

    var body: some View {
        Group {
            if let img = engine.artwork(for: track) {
                Image(uiImage: img)
                    .resizable()
                    .scaledToFit()
            } else {
                RoundedRectangle(cornerRadius: 18)
                    .fill(Color.secondary.opacity(0.15))
                    .overlay(
                        Image(systemName: "music.note")
                            .font(.system(size: 34))
                            .foregroundStyle(.secondary)
                    )
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .task(id: track.id) { await engine.loadArtworkIfNeeded(for: track) }
    }
}

private struct ProgressSection: View {
    @EnvironmentObject var engine: PlayerEngine
    @State private var dragging = false
    @State private var dragValue: Double = 0

    var body: some View {
        VStack(spacing: 4) {
            Slider(
                value: Binding(
                    get: { dragging ? dragValue : engine.currentTime },
                    set: { v in if dragging { dragValue = v } else { engine.seek(to: v) } }
                ),
                in: 0...max(engine.duration, 1),
                onEditingChanged: { started in
                    if started {
                        dragValue = engine.currentTime
                        dragging = true
                    } else {
                        engine.seek(to: dragValue)
                        dragging = false
                    }
                }
            )
            .tint(.brand)

            HStack {
                Text(TimeFormat.seconds(dragging ? dragValue : engine.currentTime))
                Spacer()
                Text("-" + TimeFormat.seconds(max(engine.duration - (dragging ? dragValue : engine.currentTime), 0)))
            }
            .font(.caption.monospacedDigit())
            .foregroundStyle(.secondary)
        }
    }
}

private struct ControlsSection: View {
    @EnvironmentObject var engine: PlayerEngine
    let onModeChange: (String) -> Void

    var body: some View {
        HStack {
            // 随机：状态直接读引擎的 @Published shuffle，点击后立刻变色并重建顺序
            Button {
                withAnimation(.snappy(duration: 0.25)) { engine.toggleShuffle() }
                UIImpactFeedbackGenerator(style: .light).impactOccurred()
                onModeChange(engine.shuffle ? "随机播放" : "顺序播放")
            } label: {
                VStack(spacing: 2) {
                    Image(systemName: "shuffle")
                        .font(.system(size: 19))
                        .foregroundStyle(engine.shuffle ? Color.brand : Color.secondary)
                        .frame(width: 44, height: 44)
                    Text(engine.shuffle ? "随机" : "顺序")
                        .font(.caption2)
                        .foregroundStyle(engine.shuffle ? Color.brand : Color.secondary)
                }
            }

            Button { engine.previous() } label: {
                Image(systemName: "backward.fill")
                    .font(.system(size: 25))
                    .frame(width: 48, height: 48)
            }

            Button { engine.togglePlay() } label: {
                Image(systemName: engine.isPlaying ? "pause.fill" : "play.fill")
                    .font(.system(size: 26))
                    .foregroundStyle(Color(.systemBackground))
                    .frame(width: 66, height: 66)
                    .background(
                        Circle()
                            .fill(Color.brand)
                            .shadow(color: Color.brand.opacity(0.30), radius: 18, y: 6)
                    )
            }

            Button { engine.next() } label: {
                Image(systemName: "forward.fill")
                    .font(.system(size: 25))
                    .frame(width: 48, height: 48)
            }

            // 循环：三态 Off → All → One，状态直接读引擎的 @Published repeatMode
            Button {
                withAnimation(.snappy(duration: 0.25)) { engine.cycleRepeat() }
                UIImpactFeedbackGenerator(style: .light).impactOccurred()
                onModeChange(repeatToastText)
            } label: {
                VStack(spacing: 2) {
                    Image(systemName: engine.repeatMode == .one ? "repeat.1" : "repeat")
                        .font(.system(size: 19))
                        .foregroundStyle(engine.repeatMode == .off ? Color.secondary : Color.brand)
                        .frame(width: 44, height: 44)
                    Text(repeatModeText)
                        .font(.caption2)
                        .foregroundStyle(engine.repeatMode == .off ? Color.secondary : Color.brand)
                }
            }
        }
        .buttonStyle(.plain)
        .foregroundStyle(.primary)
        .frame(maxWidth: .infinity)
    }

    /// 按钮下方的模式文字：循环 / 单曲 / 不循环
    private var repeatModeText: String {
        switch engine.repeatMode {
        case .off: return "不循环"
        case .all: return "循环"
        case .one: return "单曲"
        }
    }

    private var repeatToastText: String {
        switch engine.repeatMode {
        case .off: return "不循环"
        case .all: return "列表循环"
        case .one: return "单曲循环"
        }
    }
}
