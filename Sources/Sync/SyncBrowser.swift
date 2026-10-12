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
        guard let host = sender.hostName else { return }
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
