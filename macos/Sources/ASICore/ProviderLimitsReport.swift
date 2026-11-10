import Foundation

public struct ProviderLimitsReport: Decodable, Sendable {
    public let schemaVersion: Int
    public let generated: Date
    public let providers: [ProviderQuota]

    public static func decode(_ data: Data) throws -> Self {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let value = try decoder.singleValueContainer().decode(String.self)
            let format = ISO8601DateFormatter()
            format.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = format.date(from: value) { return date }
            format.formatOptions = [.withInternetDateTime]
            guard let date = format.date(from: value) else { throw CollectorError.invalidReport }
            return date
        }
        let report = try decoder.decode(Self.self, from: data)
        guard report.schemaVersion == 1,
              Set(report.providers.map(\.id)).count == report.providers.count else {
            throw CollectorError.invalidReport
        }
        for provider in report.providers {
            guard ["claude", "codex", "grok"].contains(provider.id),
                  ["available", "unavailable", "not_connected", "unsupported", "rate_limited"].contains(provider.status),
                  (15...3600).contains(provider.retryAfterSeconds),
                  Set(provider.windows.map(\.id)).count == provider.windows.count,
                  provider.status != "available" || !provider.windows.isEmpty else {
                throw CollectorError.invalidReport
            }
            for window in provider.windows {
                guard window.usedPercent.isFinite, window.usedPercent >= 0,
                      window.durationMinutes.map({ $0.isFinite && $0 > 0 }) ?? true else {
                    throw CollectorError.invalidReport
                }
            }
        }
        return report
    }
}

public struct ProviderQuota: Decodable, Identifiable, Sendable {
    public let id: String
    public let name: String
    public let plan: String?
    public let source: String
    public var fetchedAt: Date
    public var status: String
    public var message: String?
    public let retryAfterSeconds: Int
    public var windows: [QuotaWindow]

    public var isStale: Bool { status == "stale" }

    /// Only the aggregate weekly allowance belongs in the compact second line.
    public func activeWeeklyWindow(at date: Date) -> QuotaWindow? {
        displayWindows.first {
            !$0.isModelSpecific && !$0.isExpired(at: date) &&
            $0.displayDurationMinutes.map { abs($0 - 10080) <= 60 } == true
        }
    }

    /// Short-term first, then long-term; aggregate limits precede model-specific peers.
    /// Preserve source order for windows with equal priority.
    public var displayWindows: [QuotaWindow] {
        windows.enumerated().sorted { lhs, rhs in
            let left = lhs.element.displayDurationMinutes ?? .infinity
            let right = rhs.element.displayDurationMinutes ?? .infinity
            if left != right { return left < right }
            let leftScoped = lhs.element.isModelSpecific
            let rightScoped = rhs.element.isModelSpecific
            if leftScoped != rightScoped { return !leftScoped }
            return lhs.offset < rhs.offset
        }.map(\.element)
    }
}

public struct QuotaWindow: Decodable, Identifiable, Sendable {
    public let id: String
    public let title: String
    public let usedPercent: Double
    public let resetsAt: Date?
    public let durationMinutes: Double?

    /// The collector normalizes scoped windows as "Weekly · Fable", etc.
    var isModelSpecific: Bool { title.contains(" · ") }

    /// Duration is authoritative; recognized labels cover older readings without it.
    var displayDurationMinutes: Double? {
        if let durationMinutes { return durationMinutes }
        switch title.components(separatedBy: " · ").first?.lowercased() {
        case "5 hours": return 300
        case "weekly", "week": return 10080
        case "monthly", "month": return 43200
        default: return nil
        }
    }

    public var remainingPercent: Double { max(0, min(100, 100 - usedPercent)) }
    public var remainingText: String {
        remainingPercent.rounded(.down).formatted(.number.precision(.fractionLength(0))) + "% left"
    }

    public func isExpired(at date: Date) -> Bool { resetsAt.map { $0 <= date } ?? false }
}
