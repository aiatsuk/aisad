import Foundation

/// Two calendar months of aggregate costs; no session IDs, paths or provider credentials.
public struct MonthlySpendHistory: Decodable, Sendable {
    public enum Period: String, Sendable { case current, previous }
    public struct Day: Decodable, Sendable {
        public let date: String
        public let observations: Int
        public let unpricedObservations: Int
        public let costUsd: Double?
        public let costHighUsd: Double?
        public var number: Int { Int(date.suffix(2))! }
        public var incomplete: Bool {
            unpricedObservations > 0 || (costHighUsd ?? 0) - (costUsd ?? 0) > 0.000_001
        }
    }
    public struct Month: Decodable, Sendable {
        public let from: String
        public let to: String
        public let days: Int
        public let daily: [Day]
    }
    public struct Point: Identifiable, Sendable {
        public let period: Period
        public let day: Int
        public let cost: Double
        public let high: Double
        public let isLowerBound: Bool
        public let segment: String
        public fileprivate(set) var showsMarker = false
        public var id: String { period.rawValue + "-" + String(day) }
        public var amountText: String {
            SpendPeriod.dollars(cost) +
                (high - cost > 0.000_001 ? "–" + SpendPeriod.dollars(high) : "") +
                (isLowerBound ? "+" : "")
        }
    }
    public struct Curve: Identifiable, Sendable {
        public let id: Period
        public let title: String
        public let month: Month
        public let points: [Point]
        public func detail(day: Int) -> String {
            if let point = points.first(where: { $0.day == day }) { return point.amountText }
            guard let entry = month.daily.first(where: { $0.number == day }),
                  entry.observations > 0 else { return "No data" }
            return "Unpriced"
        }
    }

    public let schemaVersion: Int
    public let asOfDate: String
    public let current: Month
    public let previous: Month
    public let curves: [Curve]
    public let points: [Point]
    public let hasIncompletePrices: Bool
    public var dayCount: Int { max(current.days, previous.days) }

    private enum CodingKeys: String, CodingKey { case schemaVersion, asOfDate, current, previous }

    public init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try values.decode(Int.self, forKey: .schemaVersion)
        asOfDate = try values.decode(String.self, forKey: .asOfDate)
        current = try values.decode(Month.self, forKey: .current)
        previous = try values.decode(Month.self, forKey: .previous)
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.isLenient = false
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = formatter.timeZone
        guard schemaVersion == 1,
              let today = formatter.date(from: asOfDate), formatter.string(from: today) == asOfDate,
              current.from == String(asOfDate.prefix(7)) + "-01",
              let first = formatter.date(from: current.from),
              let prior = calendar.date(byAdding: .month, value: -1, to: first),
              previous.from == formatter.string(from: prior) else { throw CollectorError.invalidReport }
        for month in [current, previous] {
            guard let start = formatter.date(from: month.from),
                  formatter.string(from: start) == month.from,
                  calendar.component(.day, from: start) == 1,
                  calendar.range(of: .day, in: .month, for: start)?.count == month.days,
                  let end = calendar.date(byAdding: .day, value: month.days - 1, to: start),
                  formatter.string(from: end) == month.to, month.daily.count == month.days else {
                throw CollectorError.invalidReport
            }
            for (index, day) in month.daily.enumerated() {
                let expected = String(month.from.prefix(8)) + String(format: "%02d", index + 1)
                guard day.date == expected, day.observations >= 0,
                      day.unpricedObservations >= 0, day.unpricedObservations <= day.observations else {
                    throw CollectorError.invalidReport
                }
                if day.observations > day.unpricedObservations {
                    guard let cost = day.costUsd, let high = day.costHighUsd,
                          cost.isFinite, high.isFinite, cost >= 0, high >= cost else {
                        throw CollectorError.invalidReport
                    }
                } else if day.costUsd != nil || day.costHighUsd != nil {
                    throw CollectorError.invalidReport
                }
                if day.date > asOfDate && day.observations > 0 { throw CollectorError.invalidReport }
            }
        }
        var result: [Curve] = []
        for (kind, month) in [(Period.current, current), (.previous, previous)] {
            var total = 0.0, high = 0.0
            var lowerBound = false
            var segment = 0
            var preceding: Int?
            var points: [Point] = []
            for day in month.daily {
                lowerBound = lowerBound || day.unpricedObservations > 0
                guard let cost = day.costUsd, let upper = day.costHighUsd else {
                    preceding = nil
                    continue
                }
                total += cost
                high += upper
                guard total.isFinite, high.isFinite else { throw CollectorError.invalidReport }
                if preceding != day.number - 1 { segment += 1 }
                preceding = day.number
                points.append(Point(period: kind, day: day.number, cost: total, high: high,
                                    isLowerBound: lowerBound, segment: kind.rawValue + "-" + String(segment)))
            }
            let counts = Dictionary(grouping: points, by: \.segment).mapValues(\.count)
            for index in points.indices {
                points[index].showsMarker = index == points.count - 1 || counts[points[index].segment] == 1
            }
            let date = formatter.date(from: month.from)!
            formatter.dateFormat = "MMM"
            let title = formatter.string(from: date)
            formatter.dateFormat = "yyyy-MM-dd"
            result.append(Curve(id: kind, title: title, month: month, points: points))
        }
        curves = result
        points = result.reversed().flatMap(\.points)
        hasIncompletePrices = [current, previous].contains { $0.daily.contains(where: \.incomplete) }
    }

    public func matches(_ period: SpendPeriod) -> Bool {
        let cost = current.daily.reduce(0) { $0 + ($1.costUsd ?? 0) }
        let high = current.daily.reduce(0) { $0 + ($1.costHighUsd ?? 0) }
        return abs(cost - period.knownCostUsd) < 0.000_001 &&
            abs(high - period.costHighUsd) < 0.000_001 &&
            current.daily.reduce(0) { $0 + $1.observations } == period.observedRequests &&
            current.daily.reduce(0) { $0 + $1.unpricedObservations } == period.unpricedRequests
    }

    public func upperBound(budget: Double?) -> Double {
        let peak = max(points.map(\.cost).max() ?? 0, budget ?? 0)
        guard peak > 0 else { return 1 }
        let padded = peak * 1.08
        let power = pow(10, floor(log10(padded)))
        return ceil(padded / power / 0.25) * power * 0.25
    }
}
