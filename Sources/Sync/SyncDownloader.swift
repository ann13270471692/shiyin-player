import Foundation

struct RemoteFile: Codable, Identifiable, Hashable {
    let name: String
    let size: Int
    let mtime: Int
    var id: String { name }
}

private struct Manifest: Codable { let files: [RemoteFile] }

enum DownloadState: Equatable {
    case idle, running, done, cancelled, failed(String)
}

@MainActor
final class SyncDownloader: ObservableObject {
    @Published private(set) var remoteFiles: [RemoteFile] = []
    @Published private(set) var progress: [String: Double] = [:]   // -1 = 失败
    @Published private(set) var localNames: Set<String> = []
    @Published private(set) var state: DownloadState = .idle
    @Published private var cancelRequested = false

    private lazy var session: URLSession = {
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest = 60
        cfg.timeoutIntervalForResource = 900
        cfg.waitsForConnectivity = true
        cfg.shouldUseExtendedBackgroundIdleMode = true
        return URLSession(configuration: cfg)
    }()

    func rescanLocal() {
        let dir = LibraryStore.musicDirectory()
        localNames = Set((try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? [])
    }

    func cancel() { cancelRequested = true }

    func fetchManifest(from server: SyncServer) async {
        state = .running
        defer { if case .running = state { state = .idle } }
        guard let url = URL(string: "http://\(server.host):\(server.port)/manifest.json"),
              let (data, _) = try? await session.data(from: url),
              let m = try? JSONDecoder().decode(Manifest.self, from: data)
        else {
            state = .failed("无法读取文件列表：检查服务器是否在运行、IP 是否正确")
            return
        }
        remoteFiles = m.files
        rescanLocal()
    }

    func download(_ files: [RemoteFile], from server: SyncServer) async {
        state = .running
        cancelRequested = false
        for f in files where !localNames.contains(f.name) {
            if cancelRequested { break }
            await downloadOne(f, server: server)
        }
        state = cancelRequested ? .cancelled : .done
    }

    // 非隔离：网络与文件写入跑在协作线程池，不阻塞 UI；
    // 对 @Published 的更新统一跳回 MainActor。
    nonisolated private func downloadOne(_ f: RemoteFile, server: SyncServer) async {
        await setProgress(0.05, for: f.name)
        for attempt in 1...3 {
            let ok = await downloadAttempt(f, server: server)
            if ok { return }
            let stop: Bool = await MainActor.run { self.cancelRequested }
            if stop { break }
            try? await Task.sleep(nanoseconds: UInt64(attempt) * 800_000_000)
        }
        await setProgress(-1, for: f.name)
    }

    nonisolated private func downloadAttempt(_ f: RemoteFile, server: SyncServer) async -> Bool {
        let dir = await MainActor.run { LibraryStore.musicDirectory() }
        let dest = dir.appendingPathComponent(f.name)
        let tmp = URL(fileURLWithPath: dest.path + ".part")
        let fm = FileManager.default

        var start = 0
        if let attrs = try? fm.attributesOfItem(atPath: tmp.path),
           let partial = attrs[.size] as? Int {
            start = partial
        }
        if start > f.size {
            try? fm.removeItem(at: tmp)
            start = 0
        }

        let encoded = f.name.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? f.name
        guard let url = URL(string: "http://\(server.host):\(server.port)/file/\(encoded)") else {
            return false
        }

        var request = URLRequest(url: url)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        if start > 0 { request.setValue("bytes=\(start)-", forHTTPHeaderField: "Range") }

        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse,
                  (200...299).contains(http.statusCode) else {
                return false
            }
            let resume = start > 0 && http.statusCode == 206
            if resume {
                if let h = try? FileHandle(forWritingTo: tmp) {
                    h.seekToEndOfFile()
                    h.write(data)
                    try? h.close()
                } else {
                    return false
                }
            } else {
                try data.write(to: tmp, options: .atomic)
            }

            let attrs = try? fm.attributesOfItem(atPath: tmp.path)
            let total = (attrs?[.size] as? Int) ?? 0
            if total >= f.size {
                try? fm.removeItem(at: dest)
                try fm.moveItem(at: tmp, to: dest)
                await MainActor.run {
                    self.progress[f.name] = 1.0
                    self.localNames.insert(f.name)
                }
                return true
            }
            return false
        } catch {
            return false
        }
    }

    nonisolated private func setProgress(_ v: Double, for name: String) async {
        await MainActor.run { self.progress[name] = v }
    }
}
