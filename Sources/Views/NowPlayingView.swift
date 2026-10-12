import SwiftUI

struct NowPlayingView: View {
    @EnvironmentObject var engine: PlayerEngine

    var body: some View {
        NavigationStack {
            Group {
                if let cur = engine.current {
                    VStack(spacing: 14) {
                        ArtworkView(track: cur)
                            .frame(width: 160, height: 160)

                        VStack(spacing: 4) {
                            Text(cur.title)
                                .font(.title3.bold())
                                .multilineTextAlignment(.center)
                            Text(cur.artist)
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }

                        ProgressSection()
                        ControlsSection()

                        Divider()
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
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color.secondary.opacity(0.15))
                    .overlay(
                        Image(systemName: "music.note")
                            .font(.system(size: 64))
                            .foregroundStyle(.secondary)
                    )
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .task(id: track.id) { await engine.loadArtworkIfNeeded(for: track) }
    }
}

private struct ProgressSection: View {
    @EnvironmentObject var engine: PlayerEngine
    @State private var dragging = false
    @State private var dragValue: Double = 0

    var body: some View {
        VStack(spacing: 2) {
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
            HStack {
                Text(TimeFormat.seconds(dragging ? dragValue : engine.currentTime))
                Spacer()
                Text(TimeFormat.seconds(engine.duration))
            }
            .font(.caption.monospacedDigit())
            .foregroundStyle(.secondary)
        }
    }
}

private struct ControlsSection: View {
    @EnvironmentObject var engine: PlayerEngine

    var body: some View {
        VStack(spacing: 14) {
            HStack(spacing: 40) {
                Button { engine.previous() } label: {
                    Image(systemName: "backward.fill").font(.title2)
                }
                Button { engine.togglePlay() } label: {
                    Image(systemName: engine.isPlaying ? "pause.circle.fill" : "play.circle.fill")
                        .font(.system(size: 64))
                }
                Button { engine.next() } label: {
                    Image(systemName: "forward.fill").font(.title2)
                }
            }
            HStack(spacing: 32) {
                Button {
                    engine.shuffle.toggle()
                    engine.orderDidChange()
                } label: {
                    Label("随机", systemImage: "shuffle")
                        .font(.footnote)
                        .foregroundStyle(engine.shuffle ? Color.accentColor : Color.secondary)
                }
                Button { engine.cycleRepeat() } label: {
                    Label("循环", systemImage: engine.repeatMode == .one ? "repeat.1" : "repeat")
                        .font(.footnote)
                        .foregroundStyle(engine.repeatMode == .off ? Color.secondary : Color.accentColor)
                }
            }
        }
    }
}
