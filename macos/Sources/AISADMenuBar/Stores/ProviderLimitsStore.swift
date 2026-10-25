import AISADCore
import Foundation
import Observation
import OSLog

@MainActor @Observable
final class ProviderLimitsStore {
    private(set) var providers: [ProviderQuota] = []
    private(set) var isRefreshing = false
    private(set) var error: String?
    private let client: CollectorClient
    private let logger = Logger(subsystem: "com.aiatsuk.aisad.menubar", category: "limits")
    private var nextAttempt: [String: Date] = [:]
    private var refreshTask: Task<Void, Never>?
    private var manualTask: Task<Void, Never>?

    init(client: CollectorClient) { self.client = client }

    var lastUpdated: Date? {
        providers.filter { !$0.windows.isEmpty }.map(\.fetchedAt).min()
    }

    func nextRefresh(for providerID: String) -> Date? { nextAttempt[providerID] }

    func start() {
        guard refreshTask == nil else { return }
        refreshTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                do { try await Task.sleep(for: .seconds(15)) }
                catch { break }
            }
        }
    }

    func stop() {
        refreshTask?.cancel()
        refreshTask = nil
        manualTask?.cancel()
        manualTask = nil
    }

    func refreshNow() {
        guard !isRefreshing else { return }
        manualTask = Task { [weak self] in await self?.refresh(force: true) }
    }

    func refresh(force: Bool = false) async {
        guard !isRefreshing else { return }
        let now = Date()
        let ids = ["claude", "codex", "grok"].filter { id in
            // A manual refresh may retry ordinary failures, but respects provider cooldowns.
            let limited = providers.first { $0.id == id }?.status == "rate_limited"
            return (force && !limited) || (nextAttempt[id] ?? .distantPast) <= now
        }
        guard !ids.isEmpty else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        do {
            let report = try await client.limits(providers: ids)
            try Task.checkCancellation()
            for var provider in report.providers {
                nextAttempt[provider.id] = Date().addingTimeInterval(Double(provider.retryAfterSeconds))
                if provider.status != "available", provider.status != "not_connected",
                   let old = providers.first(where: { $0.id == provider.id }), !old.windows.isEmpty {
                    provider.windows = old.windows
                    provider.fetchedAt = old.fetchedAt
                    // Keep rate_limited so manual Refresh cannot bypass Retry-After.
                    if provider.status != "rate_limited" { provider.status = "stale" }
                }
                providers.removeAll { $0.id == provider.id }
                providers.append(provider)
            }
            let order = ["claude", "codex", "grok"]
            providers.sort { order.firstIndex(of: $0.id)! < order.firstIndex(of: $1.id)! }
            logger.notice("Quota refresh completed for \(report.providers.count, privacy: .public) providers")
            error = nil
        } catch is CancellationError {
        } catch {
            self.error = "Could not refresh provider limits. Try again."
            for index in providers.indices {
                if !providers[index].windows.isEmpty { providers[index].status = "stale" }
            }
            for id in ids { nextAttempt[id] = Date().addingTimeInterval(60) }
        }
    }
}

#if DEBUG
extension ProviderLimitsStore {
    func showPreview(report: ProviderLimitsReport?, refreshing: Bool = false) {
        stop()
        providers = report?.providers ?? []
        nextAttempt = Dictionary(uniqueKeysWithValues: providers.map {
            ($0.id, (report?.generated ?? .now).addingTimeInterval(Double($0.retryAfterSeconds)))
        })
        isRefreshing = refreshing
    }
}
#endif
