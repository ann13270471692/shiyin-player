import Foundation

struct SyncServer: Identifiable, Hashable {
    let id: String
    let host: String
    let port: Int
    var displayName: String
}

@MainActor
final class SyncBrowser: NSObject, ObservableObject, NetServiceBrowserDelegate, NetServiceDelegate {
    @Published private(set) var servers: [SyncServer] = []
    @Published var manualHost: String = ""

    private var browser: NetServiceBrowser?
    private var resolving: Set<NetService> = []

    func start() {
        stop()
        let b = NetServiceBrowser()
        b.delegate = self
        servers = []
        b.searchForServices(ofType: "_shiyin._tcp.", inDomain: "local")
        browser = b
    }

    func stop() {
        browser?.stop()
        browser = nil
        for s in resolving { s.stop() }
        resolving = []
    }

    func addManual(_ server: SyncServer) {
        if !servers.contains(where: { $0.id == server.id }) {
            servers.append(server)
        }
    }

    // MARK: - NetServiceBrowserDelegate（非隔离回调，统一跳回 MainActor）

    nonisolated func netServiceBrowser(_ browser: NetServiceBrowser,
                                      didFind service: NetService, moreComing: Bool) {
        Task { @MainActor in
            self.resolving.insert(service)
            service.delegate = self
            service.resolve(withTimeout: 5)
        }
    }

    nonisolated func netServiceBrowser(_ browser: NetServiceBrowser,
                                       didRemove service: NetService, moreComing: Bool) {
        Task { @MainActor in
            self.servers.removeAll { $0.id == service.name }
        }
    }

    // MARK: - NetServiceDelegate

    nonisolated func netServiceDidResolveAddress(_ sender: NetService) {
        var host = sender.hostName
        if host == nil {
            // mDNS 主机名解析失败时退回第一个 IP 地址
            for addr in sender.addresses ?? [] {
                if addr.withUnsafeBytes({ $0.load(as: sa_family_t.self) }) == sa_family_t(AF_INET),
                   let sin = addr.withUnsafeBytes({ $0.baseAddress?.assumingMemoryBound(to: sockaddr_in.self) }) {
                    var buf = [CChar](repeating: 0, count: Int(INET_ADDRSTRLEN))
                    if let p = inet_ntop(AF_INET, &sin.pointee.sin_addr, &buf, socklen_t(INET_ADDRSTRLEN)) {
                        host = String(cString: p)
                        break
                    }
                }
            }
        }
        guard let host else { return }
        let server = SyncServer(id: sender.name, host: host, port: sender.port,
                                displayName: sender.name)
        Task { @MainActor in
            self.resolving.remove(sender)
            if !self.servers.contains(where: { $0.id == server.id }) {
                self.servers.append(server)
            }
        }
    }

    nonisolated func netService(_ sender: NetService,
                                didNotResolve errorDict: [String: NSNumber]) {
        Task { @MainActor in self.resolving.remove(sender) }
    }
}
