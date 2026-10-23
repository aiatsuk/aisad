#if DEBUG
import AISADCore
import Foundation

/// Snapshot-only adapter for the existing CLI's aggregate chart JSON.
struct MonthlyChartPreview {
    struct Report: Decodable {
        struct Period: Decodable { let from: String; let to: String; let days: Int }
        struct Series: Decodable {
            struct Day: Decodable {
                let date: String
                let costUsd: Double?
                let observations: Int
                let incomplete: Bool
            }
            let provider: String
            let basis: String
            let daily: [Day]
        }
        let asOfDate: String
        let period: Period
        let series: [Series]
    }
    enum PeriodKind: String { case current, previous }
    struct Day {
        let number: Int
        let cost: Double?
        let observations: Int
        let incomplete: Bool
    }
    struct Series: Identifiable {
        let id: PeriodKind
        let title: String
        let daily: [Day]
    }
    struct Point: Identifiable {
        let period: PeriodKind
        let day: Int
        let cost: Double
        let segment: String
        var id: String { period.rawValue + "-" + String(day) }
    }

    let report: Report
    let previousReport: Report
    let compact: Bool
    let selectedDay: Int?

    var dayCount: Int { max(report.period.days, previousReport.period.days) }
    var series: [Series] {
        [aggregate(report, period: .current), aggregate(previousReport, period: .previous)]
    }
    var points: [Point] {
        // Draw the solid current line above the dashed comparison on overlap.
        series.reversed().flatMap { series in
            var segment = 0
            var previous: Int?
            return series.daily.compactMap { day -> Point? in
                guard let cost = day.cost else {
                    previous = nil
                    return nil
                }
                if previous != day.number - 1 { segment += 1 }
                previous = day.number
                return Point(period: series.id, day: day.number, cost: cost,
                             segment: series.id.rawValue + "-" + String(segment))
            }
        }
    }
    var cumulativePoints: [Point] {
        series.reversed().flatMap { series in
            var total = 0.0
            var segment = 0
            var previous: Int?
            return series.daily.compactMap { day -> Point? in
                guard let cost = day.cost else { previous = nil; return nil }
                total += cost
                if previous != day.number - 1 { segment += 1 }
                previous = day.number
                return Point(period: series.id, day: day.number, cost: total,
                             segment: series.id.rawValue + "-cumulative-" + String(segment))
            }
        }
    }
    func cumulativeDetail(period: PeriodKind, day: Int) -> String {
        guard let series = series.first(where: { $0.id == period }),
              let point = cumulativePoints.first(where: { $0.period == period && $0.day == day }) else {
            return detail(period: period, day: day)
        }
        let incomplete = series.daily.contains { $0.number <= day && $0.observations > 0 && $0.incomplete }
        return SpendPeriod.dollars(point.cost) + (incomplete ? "+" : "")
    }

    var upperBound: Double {
        let peak = points.map(\.cost).max() ?? 0
        guard peak > 0 else { return 1 }
        let power = pow(10, floor(log10(peak)))
        return ceil(peak / power / 0.25) * power * 0.25
    }
    var hasUnpricedDays: Bool {
        series.contains { $0.daily.contains { $0.observations > 0 && $0.cost == nil } }
    }
    var hasPartialDays: Bool {
        series.contains { $0.daily.contains { $0.incomplete && $0.cost != nil } }
    }
    func detail(period: PeriodKind, day: Int) -> String {
        guard let entry = series.first(where: { $0.id == period })?.daily.first(where: { $0.number == day }),
              entry.observations > 0 else { return "No data" }
        guard let cost = entry.cost else { return "Unpriced" }
        return SpendPeriod.dollars(cost) + (entry.incomplete ? "+" : "")
    }

    private func aggregate(_ report: Report, period: PeriodKind) -> Series {
        let sources = report.series.filter {
            ["Claude", "Codex"].contains($0.provider) && $0.basis == "api_equivalent_estimate"
        }
        let daily = (1...report.period.days).map { number in
            let date = String(report.period.from.prefix(8)) + String(format: "%02d", number)
            let entries = date <= report.asOfDate
                ? sources.flatMap { $0.daily.filter { $0.date == date && $0.observations > 0 } } : []
            let costs = entries.compactMap(\.costUsd)
            return Day(number: number, cost: costs.isEmpty ? nil : costs.reduce(0, +),
                       observations: entries.reduce(0) { $0 + $1.observations },
                       incomplete: entries.contains { $0.incomplete || $0.costUsd == nil })
        }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US")
        formatter.dateFormat = "yyyy-MM-dd"
        let date = formatter.date(from: report.period.from)!
        formatter.dateFormat = "MMM"
        return Series(id: period, title: formatter.string(from: date), daily: daily)
    }

    static func fromArguments() throws -> Self? {
        let arguments = CommandLine.arguments
        guard let index = arguments.firstIndex(of: "--chart-report"),
              arguments.indices.contains(index + 1) else { return nil }
        guard let previousIndex = arguments.firstIndex(of: "--chart-previous-report"),
              arguments.indices.contains(previousIndex + 1) else { throw CollectorError.invalidReport }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        func read(_ path: String) throws -> Report {
            let report = try decoder.decode(Report.self, from: Data(contentsOf: URL(fileURLWithPath: path)))
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.timeZone = TimeZone(secondsFromGMT: 0)
            formatter.dateFormat = "yyyy-MM-dd"
            formatter.isLenient = false
            var calendar = Calendar(identifier: .gregorian)
            calendar.timeZone = formatter.timeZone
            guard let first = formatter.date(from: report.period.from),
                  formatter.string(from: first) == report.period.from,
                  calendar.component(.day, from: first) == 1,
                  calendar.range(of: .day, in: .month, for: first)?.count == report.period.days,
                  let last = calendar.date(byAdding: .day, value: report.period.days - 1, to: first),
                  formatter.string(from: last) == report.period.to,
                  let asOf = formatter.date(from: report.asOfDate),
                  formatter.string(from: asOf) == report.asOfDate,
                  report.period.from <= report.asOfDate else { throw CollectorError.invalidReport }
            guard Set(report.series.map(\.provider)).count == report.series.count else {
                throw CollectorError.invalidReport
            }
            for series in report.series {
                guard Set(series.daily.map(\.date)).count == series.daily.count else {
                    throw CollectorError.invalidReport
                }
                for day in series.daily {
                    guard day.observations >= 0,
                          day.costUsd.map({ $0.isFinite && $0 >= 0 }) ?? true,
                          day.costUsd == nil || day.observations > 0,
                          let date = formatter.date(from: day.date),
                          formatter.string(from: date) == day.date,
                          report.period.from <= day.date, day.date <= report.period.to else {
                        throw CollectorError.invalidReport
                    }
                }
            }
            return report
        }
        let report = try read(arguments[index + 1])
        let previous = try read(arguments[previousIndex + 1])
        let previousEnd = String(previous.period.to.prefix(7))
        let currentStart = String(report.period.from.prefix(7))
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        let first = formatter.date(from: report.period.from)!
        guard let prior = Calendar(identifier: .gregorian).date(byAdding: .month, value: -1, to: first),
              String(formatter.string(from: prior).prefix(7)) == previousEnd,
              previousEnd < currentStart else { throw CollectorError.invalidReport }
        let selected = arguments.firstIndex(of: "--chart-day").flatMap {
            arguments.indices.contains($0 + 1) ? Int(arguments[$0 + 1]) : nil
        }
        if let selected, !(1...max(report.period.days, previous.period.days)).contains(selected) {
            throw CollectorError.invalidReport
        }
        return Self(report: report, previousReport: previous,
                    compact: arguments.contains("--chart-compact"), selectedDay: selected)
    }
}
#endif
