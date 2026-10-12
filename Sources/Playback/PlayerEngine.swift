import Foundation
import AVFoundation
import MediaPlayer
import UIKit

enum RepeatMode: Int { case off, all, one }

@MainActor
final class PlayerEngine: ObservableObject {
    static let shared = PlayerEngine()

    @Published private(set) var current: Track?
    @Published private(set) var isPlaying = false
    @Published private(set) var currentTime: Double = 0
    @Published private(set) var duration: Double = 0
    @Published var shuffle = false
    @Published var repeatMode: RepeatMode = .off

    private let player = AVPlayer()
    private var queue: [Track] = []
    private var order: [Int] = []      // queue 下标的播放顺序
    private var orderPos = 0
    private var timeToken: Any?
    private var positionByPath: [String: Double] = [:]
    private var artworkCache: [String: UIImage] = [:]
    private var lyricsCache: [String: String] = [:]
    private let posKey = "resumePositions"

    private init() {
        positionByPath = (UserDefaults.standard.dictionary(forKey: posKey) as? [String: Double]) ?? [:]
        setupSession()
        setupRemoteCommands()
        setupNotifications()
        timeToken = player.addPeriodicTimeObserver(
            forInterval: CMTime(seconds: 0.25, preferredTimescale: 600),
            queue: .main
        ) { [weak self] t in
            let s = CMTimeGetSeconds(t)
            guard s.isFinite else { return }
            Task { @MainActor in self?.currentTime = s }
        }
    }

    deinit {
        if let token = timeToken { player.removeTimeObserver(token) }
        NotificationCenter.default.removeObserver(self)
    }

    // MARK: - Public

    func playQueue(_ tracks: [Track], startAt track: Track) {
        guard let idx = tracks.firstIndex(of: track) else { return }
        queue = tracks
        rebuildOrder()
        guard let pos = order.firstIndex(of: idx) else { return }
        orderPos = pos
        savePosition()
        loadCurrent(autoplay: true)
    }

    func togglePlay() {
        if isPlaying { pause() } else { resume() }
    }

    func resume() {
        guard player.currentItem != nil else {
            if let cur = current { playQueue(queue.isEmpty ? [cur] : queue, startAt: cur) }
            return
        }
        handlePlay()
    }

    func pause() {
        savePosition()
        player.pause()
        isPlaying = false
        updateNowPlaying()
    }

    func next() { advance(by: 1) }

    func previous() {
        if currentTime > 3 { seek(to: 0); return }
        advance(by: -1)
    }

    func seek(to seconds: Double) {
        player.seek(to: CMTime(seconds: seconds, preferredTimescale: 600))
        currentTime = seconds
        updateNowPlaying()
    }

    func orderDidChange() {
        guard !queue.isEmpty else { return }
        rebuildOrder()
        if let cur = current,
           let qi = queue.firstIndex(of: cur),
           let p = order.firstIndex(of: qi) {
            orderPos = p
        } else {
            orderPos = 0
        }
    }

    func cycleRepeat() {
        repeatMode = RepeatMode(rawValue: (repeatMode.rawValue + 1) % 3) ?? .off
    }

    func artwork(for track: Track) -> UIImage? { artworkCache[track.path] }

    func loadArtworkIfNeeded(for track: Track) async {
        guard artworkCache[track.path] == nil else { return }
        let asset = AVURLAsset(url: track.url)
        guard let meta = try? await asset.load(.commonMetadata) else { return }
        let items = AVMetadataItem.metadataItems(from: meta, filteredByIdentifier: .commonIdentifierArtwork)
        guard let data = items.first?.dataValue, let img = UIImage(data: data) else { return }
        artworkCache[track.path] = img
        if current?.path == track.path { updateNowPlaying() }
    }

    func embeddedLyrics(for track: Track) async -> String? {
        if let cached = lyricsCache[track.path] { return cached.isEmpty ? nil : cached }
        let url = track.url
        let raw = await Task.detached(priority: .utility) { ID3Parser.lyrics(from: url) }.value
        lyricsCache[track.path] = raw ?? ""
        return raw
    }

    // MARK: - Internals

    private func rebuildOrder() {
        order = Array(0..<queue.count)
        if shuffle { order.shuffle() }
    }

    private func loadCurrent(autoplay: Bool) {
        guard order.indices.contains(orderPos), orderPos < queue.count else { return }
        let qi = order[orderPos]
        guard queue.indices.contains(qi) else { return }
        let track = queue[qi]
        current = track
        let item = AVPlayerItem(url: track.url)
        player.replaceCurrentItem(with: item)
        duration = 0
        currentTime = 0

        Task {
            if let d = try? await item.load(.duration) {
                let s = CMTimeGetSeconds(d)
                if s.isFinite && s > 0 { self.duration = s }
            }
            if let saved = self.positionByPath[track.path],
               saved > 3, saved < self.duration - 5 {
                self.player.seek(to: CMTime(seconds: saved, preferredTimescale: 600))
                self.currentTime = saved
            }
        }
        Task { await self.loadArtworkIfNeeded(for: track) }

        if autoplay { handlePlay() }
    }

    private func handlePlay() {
        try? AVAudioSession.sharedInstance().setActive(true)
        player.play()
        isPlaying = true
        updateNowPlaying()
    }

    private func advance(by delta: Int) {
        guard !order.isEmpty else { return }
        orderPos += delta
        if orderPos >= order.count {
            if repeatMode == .all {
                orderPos = 0
            } else {
                savePosition()
                player.pause()
                isPlaying = false
                updateNowPlaying()
                return
            }
        } else if orderPos < 0 {
            orderPos = order.count - 1
        }
        savePosition()
        loadCurrent(autoplay: true)
    }

    private func handleEnded() {
        if let cur = current { positionByPath[cur.path] = 0 }
        if repeatMode == .one {
            player.seek(to: .zero)
            handlePlay()
            return
        }
        advance(by: 1)
    }

    private func savePosition() {
        guard let cur = current else { return }
        let t = CMTimeGetSeconds(player.currentTime())
        guard t.isFinite, t > 0 else { return }
        positionByPath[cur.path] = t
        UserDefaults.standard.set(positionByPath, forKey: posKey)
    }

    private func updateNowPlaying() {
        guard let cur = current else {
            MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
            return
        }
        var info: [String: Any] = [
            MPMediaItemPropertyTitle: cur.title,
            MPMediaItemPropertyArtist: cur.artist,
            MPMediaItemPropertyPlaybackDuration: duration,
            MPNowPlayingInfoPropertyElapsedPlaybackTime: currentTime,
            MPNowPlayingInfoPropertyPlaybackRate: isPlaying ? 1.0 : 0.0,
        ]
        if let art = artworkCache[cur.path] {
            info[MPMediaItemPropertyArtwork] = MPMediaArtwork(artworkImage: art)
        }
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
    }

    // MARK: - Session / Remote / Notifications

    private func setupSession() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playback, mode: .default)
    }

    private func setupRemoteCommands() {
        let center = MPRemoteCommandCenter.shared()
        center.playCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.handlePlay() }
            return .success
        }
        center.pauseCommand.addTarget { [weak self] _ in
            Task { @MainActor in
                self?.savePosition()
                self?.player.pause()
                self?.isPlaying = false
                self?.updateNowPlaying()
            }
            return .success
        }
        center.togglePlayPauseCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.togglePlay() }
            return .success
        }
        center.nextTrackCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.next() }
            return .success
        }
        center.previousTrackCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.previous() }
            return .success
        }
        center.changePlaybackPositionCommand.addTarget { [weak self] event in
            guard let e = event as? MPChangePlaybackPositionCommandEvent else { return .commandFailed }
            let seconds = e.positionTime
            Task { @MainActor in self?.seek(to: seconds) }
            return .success
        }
    }

    private func setupNotifications() {
        NotificationCenter.default.addObserver(
            forName: AVPlayerItem.didPlayToEndTimeNotification,
            object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in self?.handleEnded() }
        }

        NotificationCenter.default.addObserver(
            forName: AVAudioSession.interruptionNotification,
            object: nil, queue: .main
        ) { [weak self] note in
            guard let info = note.userInfo,
                  let typeValue = info[AVAudioSessionInterruptionTypeKey] as? UInt,
                  let type = AVAudioSession.InterruptionType(rawValue: typeValue)
            else { return }
            if type == .began {
                Task { @MainActor in
                    self?.savePosition()
                    self?.player.pause()
                    self?.isPlaying = false
                    self?.updateNowPlaying()
                }
            } else if let optionsValue = info[AVAudioSessionInterruptionOptionKey] as? UInt,
                      AVAudioSession.InterruptionOptions(rawValue: optionsValue).contains(.shouldResume) {
                Task { @MainActor in self?.resume() }
            }
        }

        NotificationCenter.default.addObserver(
            forName: AVAudioSession.routeChangeNotification,
            object: nil, queue: .main
        ) { [weak self] note in
            guard let info = note.userInfo,
                  let reasonValue = info[AVAudioSessionRouteChangeReasonKey] as? UInt,
                  let reason = AVAudioSession.RouteChangeReason(rawValue: reasonValue),
                  reason == .oldDeviceUnavailable
            else { return }
            Task { @MainActor in
                self?.savePosition()
                self?.player.pause()
                self?.isPlaying = false
                self?.updateNowPlaying()
            }
        }
    }
}
