import Foundation

/// Hourly spend of one provider, used to learn its usual week. Aggregates only.
public struct SpendHours: Decodable, Sendable, Equatable {
    public let hours: [Int]
    public let costs: [Double]

    public init(hours: [Int], costs: [Double]) {
        self.hours = hours
        self.costs = costs
    }

    var isValid: Bool {
        hours.count == costs.count && costs.allSatisfy { $0.isFinite && $0 >= 0 }
    }

    fileprivate var byHour: [Int: Double] {
        Dictionary(zip(hours, costs), uniquingKeysWith: +)
    }
}

/// Where a quota window is heading from its latest reading.
///
/// A week with enough history follows the usual rhythm: spend so far, plus a typical
/// week's remainder scaled by how this week compares, converted to percent at this
/// window's own rate. Anything else projects the recent pace, which fades older
/// usage, so a quiet stretch lowers the forecast. Backtested on real spend history,
/// the blend beat the average since the window started at every point in the week.
public struct QuotaForecast: Sendable, Equatable {
    public enum Basis: Sendable, Equatable { case usualRhythm, recentPace }
    public struct Point: Sendable, Equatable {
        public let at: Date
        public let remaining: Double

        public init(at: Date, remaining: Double) {
            self.at = at
            self.remaining = remaining
        }
    }

    public let basis: Basis
    /// From the latest reading to the run-out or the reset.
    public let path: [Point]
    public let runsOut: Date?
    public var remainingAtReset: Double? { runsOut == nil ? path.last?.remaining : nil }

    private static let hour: TimeInterval = 3_600
    private static let hoursPerWeek = 168
    private static let pastWindows = 8
    private static let minimumUsed = 2.0
    /// How strongly a young window leans on the usual total rather than on itself.
    private static let priorWeight = 0.25
    private static let scaleRange = 0.4...2.5

    /// `readings` are this window's, oldest first; the last one is the current reading.
    /// Nil when there is too little to go on: saying nothing beats a confident guess.
    public init?(pace: QuotaPace, readings: [Point], spend: SpendHours?, calendar: Calendar = .current) {
        // An empty window has nothing left to forecast.
        guard let latest = readings.last, latest.remaining > 0,
              latest.remaining < 100 - Self.minimumUsed + 0.000_001 else { return nil }
        let duration = pace.end.timeIntervalSince(pace.start)
        let elapsed = latest.at.timeIntervalSince(pace.start)
        guard duration > 0, elapsed >= duration / 20, latest.at < pace.end else { return nil }
        let isLong = duration >= 2 * 86_400
        // Longer windows would need more history than the report carries.
        if isLong, duration <= 8 * 86_400, let spend, spend.isValid,
           let path = Self.usualRhythm(pace: pace, latest: latest, spend: spend, calendar: calendar) {
            basis = .usualRhythm
            self.path = path
        } else {
            basis = .recentPace
            path = Self.recentPace(pace: pace, readings: readings, latest: latest,
                                   halfLife: (isLong ? 72 : 0.5) * Self.hour)
        }
        runsOut = path.last.flatMap { $0.remaining <= 0 ? $0.at : nil }
    }

    /// Usage-weighted rate that forgets old usage, each half-life halving its weight.
    private static func recentPace(pace: QuotaPace, readings: [Point], latest: Point,
                                   halfLife: TimeInterval) -> [Point] {
        var series = readings
        if let first = series.first, first.at > pace.start {
            series.insert(Point(at: pace.start, remaining: 100), at: 0)
        }
        func fade(_ age: TimeInterval) -> Double { pow(2, -age / halfLife) }
        var rate = 0.0
        for (older, newer) in zip(series, series.dropFirst()) {
            let gap = newer.at.timeIntervalSince(older.at)
            let used = older.remaining - newer.remaining
            guard gap > 0, used > 0 else { continue }
            // A reading covers its whole gap, so a late first reading is not a burst.
            rate += used / gap * (fade(latest.at.timeIntervalSince(newer.at)) - fade(latest.at.timeIntervalSince(older.at)))
        }
        // A young window has no earlier usage to fade, so its rate must not read low.
        rate /= max(1 - fade(latest.at.timeIntervalSince(pace.start)), 0.000_001)
        let left = pace.end.timeIntervalSince(latest.at)
        guard rate * left >= latest.remaining else {
            return [latest, Point(at: pace.end, remaining: latest.remaining - rate * left)]
        }
        return [latest, Point(at: latest.at.addingTimeInterval(latest.remaining / rate), remaining: 0)]
    }

    private static func usualRhythm(pace: QuotaPace, latest: Point, spend: SpendHours,
                                    calendar: Calendar) -> [Point]? {
        let spent = spend.byHour
        let length = Int((pace.end.timeIntervalSince(pace.start) / hour).rounded())
        let firstHour = Int(floor(pace.start.timeIntervalSince1970 / hour))
        let reached = Int(floor(latest.at.timeIntervalSince1970 / hour)) - firstHour
        func total(_ from: Int, _ count: Int) -> Double {
            (from..<(from + count)).reduce(0) { $0 + (spent[$1] ?? 0) }
        }
        // Weeks line up by the hour of the week, the rhythm that actually repeats.
        let starts = (1...pastWindows).map { firstHour - $0 * length }
        let totals = starts.map { total($0, length) }
        let peak = totals.max() ?? 0
        let busy = zip(starts, totals).enumerated().filter { $0.element.1 > 0 && $0.element.1 >= peak * 0.1 }
        guard busy.count >= 2 else { return nil }
        let weighted = busy.map { (start: $0.element.0, total: $0.element.1, weight: exp(-Double($0.offset) / 3)) }
        let weightSum = weighted.reduce(0) { $0 + $1.weight }
        let usual = weighted.reduce(0) { $0 + $1.weight * $1.total } / weightSum

        func slot(_ hourNumber: Int) -> Int {
            let date = Date(timeIntervalSince1970: Double(hourNumber) * hour)
            return (calendar.isDateInWeekend(date) ? 4 : 0) + calendar.component(.hour, from: date) / 6
        }
        var slotSpend = [Double](repeating: 0, count: 8), slotHours = slotSpend
        for window in weighted {
            for offset in 0..<length {
                let index = slot(window.start + offset)
                slotSpend[index] += window.weight * (spent[window.start + offset] ?? 0)
                slotHours[index] += window.weight
            }
        }
        let profile = (0..<length).map { offset -> Double in
            let index = slot(firstHour + offset)
            return slotHours[index] > 0 ? slotSpend[index] / slotHours[index] : 0
        }
        let profileTotal = profile.reduce(0, +)
        let cost = total(firstHour, reached + 1)
        let used = 100 - latest.remaining
        guard profileTotal > 0, usual > 0, cost >= usual * 0.01, reached < length else { return nil }

        let shareDone = profile[...reached].reduce(0, +) / profileTotal
        let prior = priorWeight * usual
        let scale = min(max((cost + prior) / (shareDone * usual + prior), scaleRange.lowerBound), scaleRange.upperBound)
        let percentPerDollar = used / cost

        var path = [latest]
        var remaining = latest.remaining
        var time = latest.at
        for offset in reached..<length {
            let hourEnd = min(Date(timeIntervalSince1970: Double(firstHour + offset + 1) * hour), pace.end)
            guard hourEnd > time else { continue }
            let share = hourEnd.timeIntervalSince(time) / hour
            let usedThisHour = profile[offset] / profileTotal * usual * scale * percentPerDollar * share
            if usedThisHour > 0, usedThisHour >= remaining {
                let reachedZero = time.addingTimeInterval(hourEnd.timeIntervalSince(time) * remaining / usedThisHour)
                path.append(Point(at: reachedZero, remaining: 0))
                return path
            }
            remaining -= usedThisHour
            time = hourEnd
            path.append(Point(at: hourEnd, remaining: remaining))
        }
        return path
    }
}
