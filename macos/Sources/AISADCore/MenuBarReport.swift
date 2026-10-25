import Foundation

public struct MenuBarReport: Decodable, Sendable {
    public let schemaVersion: Int
    public let version: String
    public let syncRevision: String?
    public let generated: Date
    public let timezone: String
    public let periods: [SpendPeriod]
    public let monthlyHistory: MonthlySpendHistory?

    public var month: SpendPeriod? { periods.first { $0.id == "month" } }

    public static func decode(_ data: Data) throws -> MenuBarReport {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let value = try decoder.singleValueContainer().decode(String.self)
            let format = ISO8601DateFormatter()
            format.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = format.date(from: value) { return date }
            format.formatOptions = [.withInternetDateTime]
            guard let date = format.date(from: value) else {
                throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath,
                                                       debugDescription: "Invalid report date."))
            }
            return date
        }
        let report = try decoder.decode(Self.self, from: data)
        guard report.schemaVersion == 1,
              report.periods.map(\.id) == ["today", "week", "month"],
              report.month?.budgetUsd != nil else {
            throw CollectorError.invalidReport
        }
        for period in report.periods {
            guard period.knownCostUsd.isFinite, period.knownCostUsd >= 0,
                  period.costHighUsd.isFinite, period.costHighUsd >= period.knownCostUsd,
                  period.observedRequests >= 0, period.unpricedRequests >= 0,
                  period.unpricedRequests <= period.observedRequests,
                  period.budgetUsd.map({ $0.isFinite && $0 > 0 }) ?? true,
                  period.usedPercent.map({ $0.isFinite && $0 >= 0 }) ?? true,
                  period.comparison?.isValid ?? true else {
                throw CollectorError.invalidReport
            }
        }
        if let history = report.monthlyHistory, let month = report.month,
           !history.matches(month) { throw CollectorError.invalidReport }
        return report
    }
}

public struct SpendPeriod: Decodable, Identifiable, Sendable {
    public let id: String
    public let knownCostUsd: Double
    public let costHighUsd: Double
    public let budgetUsd: Double?
    public let usedPercent: Double?
    public let observedRequests: Int
    public let unpricedRequests: Int
    public let resetsAt: Date
    public let comparison: SpendComparison?

    public var title: String {
        switch id {
        case "today": "Today"
        case "week": "This week"
        default: "This month"
        }
    }

    public var hasPricedData: Bool { observedRequests > unpricedRequests }
    public var hasRange: Bool { costHighUsd - knownCostUsd > 0.000_001 }
    public var isLowerBound: Bool { unpricedRequests > 0 }
    public var progress: Double { min(max((usedPercent ?? 0) / 100, 0), 1) }
    public var warningLevel: Int {
        guard hasPricedData, let percent = usedPercent else { return 0 }
        if percent >= 100 { return 3 }
        if percent >= 80 { return 2 }
        return percent >= 65 ? 1 : 0
    }

    public var amountText: String {
        guard observedRequests > 0 else { return "No data" }
        guard hasPricedData else { return "Unpriced" }
        let value = Self.dollars(knownCostUsd)
        let range = hasRange ? "–" + Self.dollars(costHighUsd) : ""
        return value + range + (isLowerBound ? "+" : "")
    }

    public var percentText: String {
        guard hasPricedData, let percent = usedPercent else { return "—" }
        let highPercent = budgetUsd.map { costHighUsd / $0 * 100 } ?? percent
        let low = percent.formatted(.number.precision(.fractionLength(0)))
        let high = highPercent.formatted(.number.precision(.fractionLength(0)))
        return low + (hasRange && high != low ? "–" + high : "") + "%" + (isLowerBound ? "+" : "")
    }

    public static func dollars(_ value: Double) -> String {
        value.formatted(.currency(code: "USD").locale(Locale(identifier: "en_US")))
    }
}

public enum CollectorError: LocalizedError, Sendable {
    case missingPython, missingCollector, invalidReport, timedOut, outputTooLarge
    case failed(String)

    public var errorDescription: String? {
        switch self {
        case .missingPython: "Python 3.9 or newer is required. Install Python, then refresh."
        case .missingCollector: "The bundled AISAD collector is missing. Rebuild the app."
        case .invalidReport: "The collector returned an unsupported usage report."
        case .timedOut: "Collection timed out. Refresh to try again."
        case .outputTooLarge: "The collector output exceeded its size limit."
        case .failed(let message): message
        }
    }
}
