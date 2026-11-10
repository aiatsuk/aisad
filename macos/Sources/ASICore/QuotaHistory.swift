import Foundation

/// Quota readings this app has already fetched, kept so the pace chart can draw
/// the current window. Percentages and times only; nothing is requested for it.
public struct QuotaHistory: Codable, Sendable, Equatable {
    public struct Sample: Codable, Sendable, Equatable {
        public let provider: String
        public let window: String
        public let at: Date
        public let usedPercent: Double
        public let resetsAt: Date?

        public init(provider: String, window: String, at: Date, usedPercent: Double, resetsAt: Date?) {
            self.provider = provider; self.window = window; self.at = at
            self.usedPercent = usedPercent; self.resetsAt = resetsAt
        }

        public var remainingPercent: Double { max(0, min(100, 100 - usedPercent)) }
    }

    /// Long enough to compare forecasts with how past windows really ended.
    public static let retention: TimeInterval = 8 * 7 * 86_400
    /// Per window, so a busy short window cannot push out a long one.
    public static let limit = 2500
    public private(set) var samples: [Sample]

    public init(samples: [Sample] = []) { self.samples = samples }

    /// Add one reading per window. An unchanged value within ten minutes adds nothing.
    /// Finished windows thin to one reading an hour and are dropped after `retention`.
    public mutating func record(_ provider: ProviderQuota, at date: Date) {
        for window in provider.windows where !window.isExpired(at: date) {
            let sample = Sample(provider: provider.id, window: window.id, at: provider.fetchedAt,
                                usedPercent: window.usedPercent, resetsAt: window.resetsAt)
            let last = samples.last { $0.provider == sample.provider && $0.window == sample.window }
            if let last, last.at >= sample.at { continue }
            if let last, last.usedPercent == sample.usedPercent,
               sample.at.timeIntervalSince(last.at) < 600 { continue }
            samples.append(sample)
        }
        prune(at: date)
    }

    private mutating func prune(at date: Date) {
        let horizon = date.addingTimeInterval(-Self.retention)
        let current = samples.filter { ($0.resetsAt ?? $0.at.addingTimeInterval(8 * 86_400)) >= horizon }
        // Reset times drift by seconds between readings, so periods group by the hour.
        func period(_ sample: Sample) -> String {
            let reset = sample.resetsAt.map { Int(($0.timeIntervalSince1970 / 3_600).rounded()) } ?? 0
            return sample.provider + "/" + sample.window + "/" + String(reset)
        }
        var finalIndex: [String: Int] = [:]
        for (index, sample) in current.enumerated() { finalIndex[period(sample)] = index }
        var lastKept: [String: Date] = [:]
        var kept: [Sample] = []
        for (index, sample) in current.enumerated() {
            let key = period(sample)
            let finished = sample.resetsAt.map { $0 <= date } ?? false
            // The final reading is how the window really ended, so it always stays.
            if finished, finalIndex[key] != index, let last = lastKept[key],
               sample.at.timeIntervalSince(last) < 3_600 { continue }
            lastKept[key] = sample.at
            kept.append(sample)
        }
        var counts: [String: Int] = [:]
        samples = kept.reversed().filter { sample in
            let key = sample.provider + "/" + sample.window
            counts[key, default: 0] += 1
            return counts[key, default: 0] <= Self.limit
        }.reversed()
    }

    /// Readings of one window inside its current period, oldest first.
    public func series(provider: String, window: QuotaWindow, at date: Date) -> [Sample] {
        guard let pace = QuotaPace(window: window, at: date) else { return [] }
        return samples.filter {
            $0.provider == provider && $0.window == window.id &&
            $0.at >= pace.start && $0.at <= date &&
            ($0.resetsAt.map { abs($0.timeIntervalSince(pace.end)) < 3_600 } ?? true)
        }.sorted { $0.at < $1.at }
    }

    public static func load(from url: URL) -> QuotaHistory {
        guard let data = try? Data(contentsOf: url),
              let history = try? decoder.decode(QuotaHistory.self, from: data) else { return QuotaHistory() }
        return history
    }

    public func write(to url: URL) throws {
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(),
                                                withIntermediateDirectories: true)
        try Self.encoder.encode(self).write(to: url, options: [.atomic])
    }

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }()

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()
}
