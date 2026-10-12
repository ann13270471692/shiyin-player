import Foundation

struct RemoteFile: Codable, Identifiable, Hashable {
    let name: String
    let size: Int
    let mtime: Int
    var id: String { name }
}

private struct Manifest: Codable { let files: [RemoteFile] }

enum DownloadState: Equatable {
    case idle, running, done, failed(String)
}

@MainActor
final class SyncDownloader: ObservableObject {
    @Published private(set) var remoteFiles: [RemoteFile] = []
    @Published private(set) var progress: [String: Double] = [:]   // -1 = 失败
    @Published private(set) var localNames: Set<String> = []
    @Published private(set) var state: DownloadState = .idle

    func fetchManifest(from server: SyncServer) async {
        state = .running
        defer { if case .running = state { state = .idle } }
        guard let url = URL(string: "http://\(server.host):\(server.port)/manifest.json"),
              let (data, _) = try? await URLSession.shared.data(from: url),
              let m = try? JSONDecoder().decode(Manifest.self, from: data)
        else {
            state = .failed("无法读取文件列表：检查服务器是否在运行、IP 是否正确")
            return
        }
        remoteFiles = m.files
        let dir = LibraryStore.musicDirectory()
        localNames = Set((try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? [])
    }

    func download(_ files: [RemoteFile], from server: SyncServer) async {
        state = .running
        for f in files where !localNames.contains(f.name) {
            await downloadOne(f, server: server)
        }
        state = .done
    }

    private func downloadOne(_ f: RemoteFile, server: SyncServer) async {
        let dir = LibraryStore.musicDirectory()
        let dest = dir.appendingPathComponent(f.name)
        let tmp = URL(fileURLWithPath: dest.path + ".part")
        let fm = FileManager.default

        var start = 0
        if let attrs = try? fm.attributesOfItem(atPath: tmp.path),
           let partial = attrs[.size] as? Int {
            start = partial
        }

        let encoded = f.name.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? f.name
        guard let url = URL(string: "http://\(server.host):\(server.port)/file/\(encoded)") else {
            progress[f.name] = -1
            return
        }

        var request = URLRequest(url: url)
        if start > 0 { request.setValue("bytes=\(start)-", forHTTPHeaderField: "Range") }

        do {
            let (bytes, response) = try await URLSession.shared.bytes(for: request)
            guard let http = response as? HTTPURLResponse,
                  (200...299).contains(http.statusCode) else {
                progress[f.name] = -1
                return
            }
            let resume = start > 0 && http.statusCode == 206
            let handle: FileHandle
            if resume, let h = try? FileHandle(forWritingTo: tmp) {
                h.seekToEndOfFile()
                handle = h
            } else {
                try? fm.removeItem(at: tmp)
                fm.createFile(atPath: tmp.path, contents: nil)
                handle = try FileHandle(forWritingTo: tmp)
                start = 0
            }

            var received = start
            var buffer: [UInt8] = []
            buffer.reserveCapacity(1 << 16)
            for try await byte in bytes {
                buffer.append(byte)
                if buffer.count >= 65536 {
                    handle.write(Data(buffer))
                    received += buffer.count
                    buffer.removeAll(keepingCapacity: true)
                    progress[f.name] = min(Double(received) / Double(max(f.size, 1)), 0.99)
                }
            }
            if !buffer.isEmpty {
                handle.write(Data(buffer))
                received += buffer.count
            }
            try? handle.close()

            if received >= f.size {
                try? fm.removeItem(at: dest)
                try fm.moveItem(at: tmp, to: dest)
                progress[f.name] = 1.0
                localNames.insert(f.name)
            } else {
                progress[f.name] = -1
            }
        } catch {
            progress[f.name] = -1
        }
    }
}
