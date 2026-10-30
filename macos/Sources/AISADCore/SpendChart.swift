import Foundation

/// Hourly and daily aggregates behind the Day and Week charts; no session IDs or paths.
public struct PeriodCurves: Decodable, Sendable {
    public struct Bucket: Decodable, Sendable {
        public let observations: Int
        public let unpricedObservations: Int
        public let costUsd: Double?
        public let costHighUsd: Double?

        var isValid: Bool {
            guard observations >= 0, unpricedObservations >= 0, unpricedObservations <= observations else { return false }
            guard observations > unpricedObservations else { return costUsd == nil && costHighUsd == nil }
            guard let costUsd, let costHighUsd else { return false }
            return costUsd.isFinite && costHighUsd.isFinite && costUsd >= 0 && costHighUsd >= costUsd
        }
    }
    public struct Comparison: Decodable, Sendable {
        public let elapsed: Int
        public let untimedObservations: Int
        public let current: [Bucket]
        public let previous: [Bucket]

        func isValid(buckets: Int) -> Bool {
            current.count == buckets && previous.count == buckets &&
                (1...buckets).contains(elapsed) && untimedObservations >= 0 &&
                (current + previous).allSatisfy(\.isValid) &&
                current.dropFirst(elapsed).allSatisfy { $0.observations == 0 }
        }

        /// The chart and the card must describe one collection; observations
        /// without a time are the only ones a chart may leave out.
        func matches(_ period: SpendPeriod) -> Bool {
            let cost = current.reduce(0) { $0 + ($1.costUsd ?? 0) }
            let high = current.reduce(0) { $0 + ($1.costHighUsd ?? 0) }
            let observations = current.reduce(0) { $0 + $1.observations }
            guard observations + untimedObservations == period.observedRequests else { return false }
            return untimedObservations > 0 ||
                (abs(cost - period.knownCostUsd) < 0.000_001 && abs(high - period.costHighUsd) < 0.000_001)
        }
    }

    public let today: Comparison
    public let week: Comparison

    func isValid(today todayPeriod: SpendPeriod, week weekPeriod: SpendPeriod) -> Bool {
        today.isValid(buckets: 24) && week.isValid(buckets: 7) &&
            today.matches(todayPeriod) && week.matches(weekPeriod)
    }
}

/// The range shown in the spend chart card.
public enum SpendRange: String, CaseIterable, Identifiable, Sendable {
    case day, week, month

    public var id: String { rawValue }
    public var title: String { rawValue.capitalized }
    public var periodID: String {
        switch self {
        case .day: "today"
        case .week: "week"
        case .month: "month"
        }
    }
}

/// One cumulative spend comparison, whatever its range, ready for drawing.
public struct SpendChart: Sendable {
    public enum Period: String, Sendable { case current, previous }
    public struct Point: Identifiable, Sendable {
        public let period: Period
        public let position: Int
        public let cost: Double
        public let amountText: String
        public let segment: String
        public fileprivate(set) var showsMarker = false
        public var id: String { period.rawValue + "-" + String(position) }
    }
    public struct Curve: Identifiable, Sendable {
        public let id: Period
        public let title: String
        public let span: String?
        public let points: [Point]
        fileprivate let unpriced: Set<Int>

        public func detail(position: Int) -> String {
            if let point = points.first(where: { $0.position == position }) { return point.amountText }
            return unpriced.contains(position) ? "Unpriced" : "No data"
        }
    }
    public struct AxisLabel: Identifiable, Sendable {
        public let position: Double
        public let text: String
        public var id: Double { position }
    }

    public let curves: [Curve]
    public let points: [Point]
    public let domain: ClosedRange<Double>
    public let positions: ClosedRange<Int>
    public let axisLabels: [AxisLabel]
    public let hasIncompletePrices: Bool
    public let untimedObservations: Int
    private let range: SpendRange

    /// Where the current curve ends; keyboard selection starts here.
    public var latestPosition: Int {
        curves.first { $0.id == .current }?.points.last?.position ?? positions.lowerBound
    }

    public func selectionTitle(position: Int) -> String {
        switch range {
        case .day: String(format: "%d:00", position)
        case .week: Self.weekdays[max(0, min(6, position - 1))]
        case .month: "Day " + String(position)
        }
    }

    public func upperBound(budget: Double?) -> Double {
        Self.niceUpperBound(peak: max(points.map(\.cost).max() ?? 0, budget ?? 0))
    }

    public static func niceUpperBound(peak: Double) -> Double {
        guard peak > 0 else { return 1 }
        let padded = peak * 1.08
        let power = pow(10, floor(log10(padded)))
        return ceil(padded / power / 0.25) * power * 0.25
    }

    private static let weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    public init(history: MonthlySpendHistory) {
        var charted: [Curve] = []
        for curve in history.curves {
            let period: Period = curve.id == .current ? .current : .previous
            let points = curve.points.map {
                var point = Point(period: period, position: $0.day, cost: $0.cost,
                                  amountText: $0.amountText, segment: $0.segment)
                point.showsMarker = $0.showsMarker
                return point
            }
            let unpriced = curve.month.daily.filter { $0.observations > 0 && $0.costUsd == nil }.map(\.number)
            charted.append(Curve(id: period, title: curve.title, span: curve.month.from + " – " + curve.month.to,
                                 points: points, unpriced: Set(unpriced)))
        }
        curves = charted
        points = charted.reversed().flatMap(\.points)
        domain = 0.5...(Double(history.dayCount) + 0.5)
        positions = 1...history.dayCount
        axisLabels = [AxisLabel(position: 1, text: "1"),
                      AxisLabel(position: Double(history.dayCount), text: String(history.dayCount))]
        hasIncompletePrices = history.hasIncompletePrices
        untimedObservations = 0
        range = .month
    }

    public init(today: PeriodCurves.Comparison) {
        self.init(range: .day, comparison: today, titles: ("Today", "Yesterday"), origin: true,
                  domain: 0...24, labels: [.init(position: 0, text: "0:00"), .init(position: 24, text: "24:00")])
    }

    public init(week: PeriodCurves.Comparison) {
        self.init(range: .week, comparison: week, titles: ("This week", "Last week"), origin: false,
                  domain: 0.5...7.5, labels: [.init(position: 1, text: "Mon"), .init(position: 7, text: "Sun")])
    }

    private init(range: SpendRange, comparison: PeriodCurves.Comparison, titles: (String, String),
                 origin: Bool, domain: ClosedRange<Double>, labels: [AxisLabel]) {
        func curve(_ period: Period, _ title: String, _ buckets: [PeriodCurves.Bucket], elapsed: Int) -> Curve {
            guard buckets.contains(where: { $0.observations > 0 }) else {
                return Curve(id: period, title: title, span: nil, points: [], unpriced: [])
            }
            func point(_ position: Int, _ cost: Double, _ high: Double, _ lowerBound: Bool) -> Point {
                let text = SpendPeriod.dollars(cost) +
                    (high - cost > 0.000_001 ? "–" + SpendPeriod.dollars(high) : "") + (lowerBound ? "+" : "")
                return Point(period: period, position: position, cost: cost, amountText: text,
                             segment: period.rawValue)
            }
            var total = 0.0, high = 0.0, lowerBound = false
            var points = origin ? [point(0, 0, 0, false)] : []
            // Spend is cumulative, so a quiet stretch stays flat rather than breaking the line.
            for (index, bucket) in buckets.prefix(elapsed).enumerated() {
                total += bucket.costUsd ?? 0
                high += bucket.costHighUsd ?? 0
                lowerBound = lowerBound || bucket.unpricedObservations > 0
                points.append(point(index + 1, total, high, lowerBound))
            }
            points[points.count - 1].showsMarker = true
            return Curve(id: period, title: title, span: nil, points: points, unpriced: [])
        }
        let current = curve(.current, titles.0, comparison.current, elapsed: comparison.elapsed)
        let previous = curve(.previous, titles.1, comparison.previous, elapsed: comparison.previous.count)
        curves = [current, previous]
        points = previous.points + current.points
        self.domain = domain
        positions = 1...comparison.current.count
        axisLabels = labels
        hasIncompletePrices = (comparison.current + comparison.previous).contains {
            $0.unpricedObservations > 0 || ($0.costHighUsd ?? 0) - ($0.costUsd ?? 0) > 0.000_001
        }
        untimedObservations = comparison.untimedObservations
        self.range = range
    }
}
