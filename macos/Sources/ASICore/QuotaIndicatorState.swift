import Foundation

/// A compact quota summary. Ring values are independent windows, never an average.
public struct QuotaIndicatorState: Sendable {
    public enum Phase: Equatable, Sendable { case loading, unavailable, available, stale, expired }
    public enum WarningLevel: Equatable, Sendable {
        case normal, warning, critical

        public init(remainingPercent: Double) {
            self = remainingPercent <= 10 ? .critical : remainingPercent < 20 ? .warning : .normal
        }
    }
    public struct Ring: Identifiable, Sendable {
        public enum Placement: Sendable { case outer, inner }
        public let id: String
        public let placement: Placement
        /// Nil is unknown/expired; zero is a real exhausted quota.
        public let remainingFraction: Double?
    }

    public let phase: Phase
    public let rings: [Ring]
    public let lowestRemainingPercent: Double?
    public let windowCount: Int

    public init(provider: ProviderQuota?, refreshing: Bool, now: Date) {
        guard let provider, !provider.windows.isEmpty else {
            phase = provider == nil && refreshing ? .loading : .unavailable
            rings = []
            lowestRemainingPercent = nil
            windowCount = 0
            return
        }
        let active = provider.windows.filter { !$0.isExpired(at: now) }
        if active.isEmpty {
            phase = .expired
        } else if provider.status != "available" || active.count != provider.windows.count {
            phase = .stale
        } else {
            phase = .available
        }
        // Keep a fixed visual hierarchy even if the provider reorders its response
        // or reports only a weekly window. Other windows remain in the details.
        var selected: [Ring] = []
        for window in provider.displayWindows where !window.isModelSpecific {
            let placement: Ring.Placement = (window.displayDurationMinutes ?? 0) >= 10080 ? .inner : .outer
            guard !selected.contains(where: { $0.placement == placement }) else { continue }
            selected.append(Ring(id: window.id, placement: placement,
                remainingFraction: window.isExpired(at: now) ? nil : window.remainingPercent / 100))
        }
        rings = selected
        lowestRemainingPercent = active.map(\.remainingPercent).min()
        windowCount = provider.windows.count
    }
}
