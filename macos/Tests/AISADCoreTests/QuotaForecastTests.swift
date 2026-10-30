import Foundation
import XCTest
@testable import AISADCore

final class QuotaForecastTests: XCTestCase {
    private let hour: TimeInterval = 3_600
    private let day: TimeInterval = 86_400
    private var calendar: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        return calendar
    }
    /// Monday 2026-10-26 00:00 UTC, so weeks start on a whole hour.
    private let weekStart = Date(timeIntervalSince1970: 1_792_972_800)

    private func point(_ days: Double, _ remaining: Double) -> QuotaForecast.Point {
        .init(at: weekStart.addingTimeInterval(days * day), remaining: remaining)
    }

    private func pace(used: Double, atDays days: Double, duration: TimeInterval? = nil) throws -> QuotaPace {
        let duration = duration ?? 7 * day
        let window = QuotaWindow(id: "w", title: "Weekly", usedPercent: used,
                                 resetsAt: weekStart.addingTimeInterval(duration), durationMinutes: duration / 60)
        return try XCTUnwrap(QuotaPace(window: window, at: weekStart.addingTimeInterval(days * day)))
    }

    /// `perHour(week, hourOfWeek)` for `weeks` past windows; week 0 is the current one.
    private func spend(weeks: Int, currentHours: Int, perHour: (Int, Int) -> Double) -> SpendHours {
        var hours: [Int] = [], costs: [Double] = []
        let first = Int(weekStart.timeIntervalSince1970 / hour)
        for week in stride(from: weeks, through: 0, by: -1) {
            for offset in 0..<(week == 0 ? currentHours : 168) {
                let cost = perHour(week, offset)
                if cost > 0 { hours.append(first - week * 168 + offset); costs.append(cost) }
            }
        }
        return SpendHours(hours: hours, costs: costs)
    }

    func testBurstThenQuietNoLongerProjectsTheBurst() throws {
        // 20% gone in the first half day, then nothing for two and a half days.
        let readings = [point(0, 100), point(0.5, 80), point(3, 80)]
        let forecast = try XCTUnwrap(QuotaForecast(pace: pace(used: 20, atDays: 3), readings: readings, spend: nil))
        XCTAssertEqual(forecast.basis, .recentPace)
        XCTAssertNil(forecast.runsOut)
        // The plain average would use 47% by reset, leaving 33%.
        XCTAssertGreaterThan(try XCTUnwrap(forecast.remainingAtReset), 50)
    }

    func testSteadyUsageMatchesTheAverageRate() throws {
        let readings = (0...6).map { point(Double($0) * 0.5, 100 - Double($0) * 10) }
        let forecast = try XCTUnwrap(QuotaForecast(pace: pace(used: 60, atDays: 3), readings: readings, spend: nil))
        XCTAssertEqual(try XCTUnwrap(forecast.runsOut).timeIntervalSince(weekStart), 5 * day, accuracy: 60)
        XCTAssertEqual(forecast.path.last?.remaining, 0)
    }

    func testFirstReadingLateInTheWindowIsNotABurst() throws {
        // The app started on day 3: all it knows is the average so far.
        let forecast = try XCTUnwrap(QuotaForecast(pace: pace(used: 30, atDays: 3), readings: [point(3, 70)], spend: nil))
        XCTAssertEqual(forecast.path.first?.at, point(3, 70).at)
        XCTAssertEqual(try XCTUnwrap(forecast.remainingAtReset), 30, accuracy: 0.5)
    }

    func testRecentSurgeLowersTheForecastWithoutPanic() throws {
        let readings = [point(0, 100), point(2, 95), point(2.9, 94), point(3, 70)]
        let forecast = try XCTUnwrap(QuotaForecast(pace: pace(used: 30, atDays: 3), readings: readings, spend: nil))
        // The plain average would leave 30% at reset; a weekly window weighs days, not one burst.
        let left = try XCTUnwrap(forecast.remainingAtReset)
        XCTAssertLessThan(left, 30)
        XCTAssertGreaterThan(left, 10)
    }

    func testFiveHourWindowFollowsTheLastHalfHour() throws {
        let hourDays = 1.0 / 24
        let readings = [point(0, 100), point(hourDays, 90), point(2 * hourDays, 90), point(2.5 * hourDays, 50)]
        let forecast = try XCTUnwrap(QuotaForecast(pace: pace(used: 50, atDays: 2.5 * hourDays, duration: 5 * hour),
                                                   readings: readings, spend: nil))
        XCTAssertEqual(forecast.basis, .recentPace)
        // The average of 20% an hour would last exactly to the reset; the last half hour will not.
        XCTAssertLessThan(try XCTUnwrap(forecast.runsOut).timeIntervalSince(weekStart), 4 * hour)
    }

    func testSaysNothingWithTooLittleToGoOn() throws {
        XCTAssertNil(QuotaForecast(pace: try pace(used: 1, atDays: 3), readings: [point(3, 99)], spend: nil))
        XCTAssertNil(QuotaForecast(pace: try pace(used: 20, atDays: 0.2), readings: [point(0.2, 80)], spend: nil))
        XCTAssertNil(QuotaForecast(pace: try pace(used: 20, atDays: 3), readings: [], spend: nil))
    }

    func testEmptyWindowHasNoForecast() throws {
        let readings = [point(0, 100), point(2, 50), point(3.9, 0)]
        XCTAssertNil(QuotaForecast(pace: try pace(used: 100, atDays: 4), readings: readings, spend: nil))
        let history = spend(weeks: 3, currentHours: 96) { _, offset in offset % 24 < 8 ? 10 : 0 }
        XCTAssertNil(QuotaForecast(pace: try pace(used: 100, atDays: 4), readings: readings, spend: history,
                                   calendar: calendar))
    }

    func testAQuietHourNeverDividesByZero() throws {
        // Hours with no usual spend ahead of a nearly empty window.
        let history = spend(weeks: 3, currentHours: 96) { _, offset in offset % 24 < 8 ? 10 : 0 }
        let forecast = try XCTUnwrap(QuotaForecast(pace: pace(used: 99.99, atDays: 4.5),
                                                   readings: [point(4.5, 0.01)], spend: history, calendar: calendar))
        XCTAssertTrue(forecast.path.allSatisfy { $0.at.timeIntervalSince1970.isFinite && $0.remaining.isFinite })
        XCTAssertEqual(Set(forecast.path.map(\.at)).count, forecast.path.count)
    }

    func testWindowsLongerThanTheHistoryUseRecentPace() throws {
        let history = spend(weeks: 3, currentHours: 240) { _, _ in 10 }
        let forecast = try XCTUnwrap(QuotaForecast(pace: pace(used: 30, atDays: 10, duration: 30 * day),
                                                   readings: [point(10, 70)], spend: history, calendar: calendar))
        XCTAssertEqual(forecast.basis, .recentPace)
    }

    func testAWindowStartingMidHourCountsItsLatestHour() throws {
        // Start 30 minutes past the hour; the current partial hour must count as spent.
        let start = weekStart.addingTimeInterval(1_800)
        let window = QuotaWindow(id: "w", title: "Weekly", usedPercent: 25,
                                 resetsAt: start.addingTimeInterval(7 * day), durationMinutes: 10_080)
        let time = start.addingTimeInterval(42 * hour)
        let usedPace = try XCTUnwrap(QuotaPace(window: window, at: time))
        let history = spend(weeks: 3, currentHours: 43) { _, _ in 10 }
        let forecast = try XCTUnwrap(QuotaForecast(pace: usedPace, readings: [.init(at: time, remaining: 75)],
                                                   spend: history, calendar: calendar))
        XCTAssertEqual(forecast.basis, .usualRhythm)
        XCTAssertEqual(try XCTUnwrap(forecast.path.last).remaining, 0, accuracy: 3)
    }

    func testReportCarriesUsageHoursAndLosesOnlyThemWhenMalformed() throws {
        func report(_ usage: Any) throws -> MenuBarReport {
            let periods: [[String: Any]] = ["today", "week", "month"].map { id in
                ["id": id, "known_cost_usd": 0, "cost_high_usd": 0, "budget_usd": id == "month" ? 100 : NSNull(),
                 "used_percent": NSNull(), "observed_requests": 0, "unpriced_requests": 0,
                 "resets_at": "2026-11-01T00:00:00Z"]
            }
            let payload: [String: Any] = ["schema_version": 1, "version": "test", "generated": "2026-10-28T12:00:00Z",
                                          "timezone": "UTC", "periods": periods, "usage_hours": usage]
            return try MenuBarReport.decode(JSONSerialization.data(withJSONObject: payload))
        }
        let good = try report(["claude": ["hours": [1, 2], "costs": [0.5, 1.5]]])
        XCTAssertEqual(good.usageHours?["claude"], SpendHours(hours: [1, 2], costs: [0.5, 1.5]))
        let bad = try report("bad")
        XCTAssertNil(bad.usageHours)
        XCTAssertNotNil(bad.month)
    }

    func testTypicalWeekDecidesOnceThereIsHistory() throws {
        // Three weeks of $10 an hour; this week is on the same course at 25% used.
        let history = spend(weeks: 3, currentHours: 42) { _, _ in 10 }
        let forecast = try XCTUnwrap(QuotaForecast(pace: pace(used: 25, atDays: 1.75),
                                                   readings: [point(1.75, 75)], spend: history, calendar: calendar))
        XCTAssertEqual(forecast.basis, .usualRhythm)
        // On the usual course, the allowance lands near empty right at the reset.
        XCTAssertEqual(try XCTUnwrap(forecast.path.last).remaining, 0, accuracy: 3)
        XCTAssertGreaterThan(try XCTUnwrap(forecast.path.last).at, point(6.8, 0).at)
    }

    func testHeavierWeekScalesTheRemainderUp() throws {
        // Same habits, but this week spends four times as fast: it must run out early.
        let history = spend(weeks: 3, currentHours: 24) { week, _ in week == 0 ? 40 : 10 }
        let forecast = try XCTUnwrap(QuotaForecast(pace: pace(used: 30, atDays: 1),
                                                   readings: [point(1, 70)], spend: history, calendar: calendar))
        XCTAssertEqual(forecast.basis, .usualRhythm)
        XCTAssertLessThan(try XCTUnwrap(forecast.runsOut).timeIntervalSince(weekStart), 7 * day)
    }

    func testQuietWeekendsFlattenTheLine() throws {
        // Weekdays only: from Friday evening the forecast should stop falling.
        let weekdays = spend(weeks: 3, currentHours: 96) { _, offset in offset < 120 ? 10 : 0 }
        let forecast = try XCTUnwrap(QuotaForecast(pace: pace(used: 40, atDays: 4),
                                                   readings: [point(4, 60)], spend: weekdays, calendar: calendar))
        let saturday = try XCTUnwrap(forecast.path.first { $0.at >= point(5.5, 0).at })
        XCTAssertEqual(saturday.remaining, try XCTUnwrap(forecast.remainingAtReset), accuracy: 0.001)
        XCTAssertEqual(try XCTUnwrap(forecast.remainingAtReset), 50, accuracy: 1)
    }

    func testFallsBackWithoutEnoughBusyWeeks() throws {
        let oneWeek = spend(weeks: 1, currentHours: 24) { _, _ in 10 }
        let forecast = try XCTUnwrap(QuotaForecast(pace: pace(used: 30, atDays: 1),
                                                   readings: [point(1, 70)], spend: oneWeek, calendar: calendar))
        XCTAssertEqual(forecast.basis, .recentPace)
        // A near-idle week among busy ones does not count as history.
        let idle = spend(weeks: 3, currentHours: 24) { week, _ in week == 3 ? 10 : week == 0 ? 10 : 0.01 }
        let second = try XCTUnwrap(QuotaForecast(pace: pace(used: 30, atDays: 1),
                                                 readings: [point(1, 70)], spend: idle, calendar: calendar))
        XCTAssertEqual(second.basis, .recentPace)
    }

    func testUnusableSpendFallsBackRatherThanFailing() throws {
        let readings = [point(1, 70)]
        let usedPace = try pace(used: 30, atDays: 1)
        let mismatched = SpendHours(hours: [1, 2], costs: [1])
        let negative = SpendHours(hours: [1], costs: [-1])
        XCTAssertEqual(QuotaForecast(pace: usedPace, readings: readings, spend: mismatched)?.basis, .recentPace)
        XCTAssertEqual(QuotaForecast(pace: usedPace, readings: readings, spend: negative)?.basis, .recentPace)
        // No spend logged this week although quota was used, so its dollars cannot convert.
        let silent = spend(weeks: 3, currentHours: 0) { _, _ in 10 }
        XCTAssertEqual(QuotaForecast(pace: usedPace, readings: readings, spend: silent, calendar: calendar)?.basis,
                       .recentPace)
    }

    func testPathStaysInsideTheWindowAndNeverRises() throws {
        let history = spend(weeks: 8, currentHours: 60) { week, offset in Double((week + offset) % 7) }
        let forecast = try XCTUnwrap(QuotaForecast(pace: pace(used: 35, atDays: 2.5),
                                                   readings: [point(2.5, 65)], spend: history, calendar: calendar))
        XCTAssertEqual(forecast.path.first?.at, point(2.5, 0).at)
        for (older, newer) in zip(forecast.path, forecast.path.dropFirst()) {
            XCTAssertLessThanOrEqual(newer.remaining, older.remaining)
            XCTAssertGreaterThanOrEqual(newer.remaining, 0)
            XCTAssertGreaterThan(newer.at, older.at)
            XCTAssertLessThanOrEqual(newer.at, point(7, 0).at)
        }
    }
}
