import SwiftUI

/// 品牌色，与鸿蒙版 ACCENT (#FF9F0A) 保持一致
extension Color {
    static let brand = Color(red: 1.0, green: 0.624, blue: 0.039)
}

struct NowPlayingView: View {
    @EnvironmentObject var engine: PlayerEngine

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
                        ControlsSection()

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
            .navigationTitle("播放")
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

    var body: some View {
        HStack {
            Button {
                engine.shuffle.toggle()
                engine.orderDidChange()
            } label: {
                Image(systemName: "shuffle")
                    .font(.system(size: 19))
                    .foregroundStyle(engine.shuffle ? Color.brand : Color.secondary)
                    .frame(width: 44, height: 44)
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

            Button { engine.cycleRepeat() } label: {
                Image(systemName: engine.repeatMode == .one ? "repeat.1" : "repeat")
                    .font(.system(size: 19))
                    .foregroundStyle(engine.repeatMode == .off ? Color.secondary : Color.brand)
                    .frame(width: 44, height: 44)
            }
        }
        .buttonStyle(.plain)
        .foregroundStyle(.primary)
        .frame(maxWidth: .infinity)
    }
}
