import Foundation
import XCTest
@testable import AISADCore

final class SpendChartTests: XCTestCase {
    private func bucket(_ cost: Double?, observations: Int = 1, unpriced: Int = 0, high: Double? = nil) -> [String: Any] {
        ["observations": cost == nil && unpriced == 0 ? 0 : observations, "unpriced_observations": unpriced,
         "cost_usd": cost ?? NSNull(), "cost_high_usd": high ?? cost ?? NSNull()]
    }

    private func comparison(_ current: [Int: Double], previous: [Int: Double] = [:], count: Int,
                            elapsed: Int, untimed: Int = 0, elapsedHours: Double? = nil) -> [String: Any] {
        ["elapsed": elapsed, "untimed_observations": untimed, "elapsed_hours": elapsedHours ?? NSNull(),
         "current": (0..<count).map { bucket(current[$0]) },
         "previous": (0..<count).map { bucket(previous[$0]) }]
    }

    private func period(_ id: String, cost: Double, observations: Int, unpriced: Int = 0) -> [String: Any] {
        var value: [String: Any] = ["id": id, "known_cost_usd": cost, "cost_high_usd": cost,
                                    "budget_usd": NSNull(), "used_percent": NSNull(),
                                    "observed_requests": observations, "unpriced_requests": unpriced,
                                    "resets_at": "2026-11-01T00:00:00Z"]
        if id == "month" { value["budget_usd"] = 100 }
        return value
    }

    private func decode(today: [String: Any], week: [String: Any], todayCost: Double = 5, weekCost: Double = 8,
                        todayUnpriced: Int = 0) throws -> MenuBarReport {
        try decode(curves: ["today": today, "week": week], todayCost: todayCost, weekCost: weekCost,
                   todayUnpriced: todayUnpriced)
    }

    private func decode(curves: Any, history: Any? = nil, todayCost: Double = 5, weekCost: Double = 8,
                        todayUnpriced: Int = 0) throws -> MenuBarReport {
        let periods = [period("today", cost: todayCost, observations: 2, unpriced: todayUnpriced),
                       period("week", cost: weekCost, observations: 2),
                       period("month", cost: 8, observations: 2)]
        var payload: [String: Any] = ["schema_version": 1, "version": "test", "generated": "2026-10-28T12:00:00Z",
                                      "timezone": "UTC", "periods": periods, "period_curves": curves]
        if let history { payload["monthly_history"] = history }
        return try MenuBarReport.decode(JSONSerialization.data(withJSONObject: payload))
    }

    func testDayCurveStartsAtZeroCarriesQuietHoursAndStopsNow() throws {
        let report = try decode(today: comparison([2: 2, 5: 3], previous: [23: 4], count: 24, elapsed: 8),
                                week: comparison([0: 3, 2: 5], previous: [6: 9], count: 7, elapsed: 3))
        let chart = try XCTUnwrap(report.chart(.day))
        let current = try XCTUnwrap(chart.curves.first { $0.id == .current })
        XCTAssertEqual(current.points.map(\.position), Array(0...8))
        XCTAssertEqual(current.points.map(\.cost), [0, 0, 0, 2, 2, 2, 5, 5, 5])
        XCTAssertEqual(current.points.filter(\.showsMarker).map(\.position), [8])
        XCTAssertEqual(chart.latestPosition, 8)
        XCTAssertEqual(chart.curves.last?.points.last?.position, 24)
        XCTAssertEqual(chart.selectionTitle(position: 14), "14:00")
        XCTAssertEqual(chart.axisLabels.map(\.text), ["0:00", "24:00"])
    }

    func testWeekCurveRunsMondayToElapsedDayAndPreviousRunsTheWholeWeek() throws {
        let report = try decode(today: comparison([2: 2, 5: 3], count: 24, elapsed: 8),
                                week: comparison([0: 3, 2: 5], previous: [6: 9], count: 7, elapsed: 3))
        let chart = try XCTUnwrap(report.chart(.week))
        XCTAssertEqual(chart.curves.first?.points.map(\.cost), [3, 3, 8])
        XCTAssertEqual(chart.curves.last?.points.count, 7)
        XCTAssertEqual(chart.selectionTitle(position: 3), "Wed")
        XCTAssertEqual(chart.selectionTitle(position: 7), "Sun")
    }

    func testEmptyComparisonDrawsNoCurveInsteadOfAFlatLine() throws {
        let report = try decode(today: comparison([2: 2, 5: 3], count: 24, elapsed: 8),
                                week: comparison([0: 3, 2: 5], count: 7, elapsed: 3))
        let chart = try XCTUnwrap(report.chart(.week))
        XCTAssertEqual(chart.curves.last?.points.count, 0)
    }

    func testChartMustMatchItsCardUnlessObservationsHaveNoTime() throws {
        let week = comparison([0: 3, 2: 5], count: 7, elapsed: 3)
        XCTAssertNil(try decode(today: comparison([2: 2, 5: 3], count: 24, elapsed: 8), week: week,
                                todayCost: 6).periodCurves)
        let untimed = comparison([2: 2], count: 24, elapsed: 8, untimed: 1)
        XCTAssertEqual(try decode(today: untimed, week: week).periodCurves?.today.untimedObservations, 1)
        XCTAssertNil(try decode(today: comparison([2: 2], count: 24, elapsed: 8, untimed: 2), week: week).periodCurves)
    }

    func testMalformedCurvesCostOnlyTheChartsNotTheReport() throws {
        let today = comparison([2: 2, 5: 3], count: 24, elapsed: 8)
        let week = comparison([0: 3, 2: 5], count: 7, elapsed: 3)
        var broken = today
        var buckets = today["current"] as! [[String: Any]]
        buckets[2]["cost_high_usd"] = 1.0
        broken["current"] = buckets
        for bad in [comparison([2: 2, 5: 3], count: 23, elapsed: 8),
                    comparison([2: 2, 5: 3], count: 24, elapsed: 0),
                    comparison([2: 2, 5: 3], count: 24, elapsed: 25),
                    // A future bucket with spend means the chart ran ahead of its collection.
                    comparison([2: 2, 5: 3], count: 24, elapsed: 3),
                    broken] {
            let report = try decode(today: bad, week: week)
            XCTAssertNil(report.periodCurves)
            XCTAssertEqual(report.period(.day)?.amountText, "$5.00")
            XCTAssertNil(report.chart(.day))
        }
    }

    func testChartsOfAnotherShapeCostOnlyTheCharts() throws {
        let week = comparison([0: 3, 2: 5], count: 7, elapsed: 3)
        var textCost = comparison([2: 2, 5: 3], count: 24, elapsed: 8)
        var buckets = textCost["current"] as! [[String: Any]]
        buckets[2]["cost_usd"] = "2.0"
        textCost["current"] = buckets
        var missingKey = comparison([2: 2, 5: 3], count: 24, elapsed: 8)
        missingKey.removeValue(forKey: "untimed_observations")
        for curves: Any in [["today": "bad", "week": "bad"], "bad", ["today": textCost, "week": week],
                            ["today": missingKey, "week": week]] {
            let report = try decode(curves: curves)
            XCTAssertNil(report.periodCurves)
            XCTAssertEqual(report.period(.day)?.amountText, "$5.00")
        }
        let badHistory: [String: Any] = ["schema_version": 1, "as_of_date": "not-a-date"]
        let report = try decode(curves: ["today": comparison([2: 2, 5: 3], count: 24, elapsed: 8), "week": week],
                                history: badHistory)
        XCTAssertNil(report.monthlyHistory)
        XCTAssertNotNil(report.periodCurves)
    }

    func testTodaysLineEndsAtCollectionNotTheNextHour() throws {
        let week = comparison([0: 3, 2: 5], count: 7, elapsed: 3)
        let report = try decode(today: comparison([2: 2, 5: 3], count: 24, elapsed: 8, elapsedHours: 7.5), week: week)
        let current = try XCTUnwrap(report.chart(.day)?.curves.first)
        XCTAssertEqual(current.points.last?.position, 8)
        XCTAssertEqual(current.points.last?.plotX, 7.5)
        XCTAssertEqual(current.points.first?.plotX, 0)
        let outside = try decode(today: comparison([2: 2, 5: 3], count: 24, elapsed: 8, elapsedHours: 2), week: week)
        XCTAssertEqual(outside.chart(.day)?.curves.first?.points.last?.plotX, 8)
    }

    func testCurvesMustAgreeWithTheCardOnUnpricedCounts() throws {
        var today = comparison([2: 5], count: 24, elapsed: 8)
        var buckets = today["current"] as! [[String: Any]]
        buckets[2]["observations"] = 2
        buckets[2]["unpriced_observations"] = 1
        today["current"] = buckets
        let week = comparison([0: 3, 2: 5], count: 7, elapsed: 3)
        XCTAssertNil(try decode(today: today, week: week).periodCurves)
        XCTAssertNotNil(try decode(today: today, week: week, todayUnpriced: 1).periodCurves)
    }

    func testRangeWithOnlyUnpricedUsageDrawsNoLine() throws {
        var today = comparison([:], count: 24, elapsed: 8)
        var buckets = today["current"] as! [[String: Any]]
        buckets[3] = bucket(nil, observations: 2, unpriced: 2)
        today["current"] = buckets
        let report = try decode(today: today, week: comparison([0: 3, 2: 5], count: 7, elapsed: 3),
                                todayCost: 0, todayUnpriced: 2)
        let chart = try XCTUnwrap(report.chart(.day))
        XCTAssertTrue(chart.points.isEmpty)
        XCTAssertTrue(chart.hasIncompletePrices)
        XCTAssertEqual(chart.curves.first?.detail(position: 4), "Unpriced")
        XCTAssertEqual(chart.curves.first?.detail(position: 5), "No data")
    }

    func testOlderCollectorLeavesDayAndWeekChartsEmpty() throws {
        let periods = [period("today", cost: 0, observations: 0), period("week", cost: 0, observations: 0),
                       period("month", cost: 0, observations: 0)]
        let payload: [String: Any] = ["schema_version": 1, "version": "old", "generated": "2026-10-28T12:00:00Z",
                                      "timezone": "UTC", "periods": periods]
        let report = try MenuBarReport.decode(JSONSerialization.data(withJSONObject: payload))
        XCTAssertNil(report.chart(.day))
        XCTAssertNil(report.chart(.week))
        XCTAssertNil(report.chart(.month))
    }

    func testPartialPricesAreFlagged() throws {
        var today = comparison([2: 2, 5: 3], count: 24, elapsed: 8)
        var buckets = today["current"] as! [[String: Any]]
        buckets[2] = bucket(2, high: 4)
        today["current"] = buckets
        let periods = [["id": "today", "known_cost_usd": 5.0, "cost_high_usd": 7.0, "budget_usd": NSNull(),
                        "used_percent": NSNull(), "observed_requests": 2, "unpriced_requests": 0,
                        "resets_at": "2026-11-01T00:00:00Z"] as [String: Any],
                       period("week", cost: 8, observations: 2), period("month", cost: 8, observations: 2)]
        let payload: [String: Any] = ["schema_version": 1, "version": "test", "generated": "2026-10-28T12:00:00Z",
                                      "timezone": "UTC", "periods": periods,
                                      "period_curves": ["today": today,
                                                        "week": comparison([0: 3, 2: 5], count: 7, elapsed: 3)]]
        let report = try MenuBarReport.decode(JSONSerialization.data(withJSONObject: payload))
        let chart = try XCTUnwrap(report.chart(.day))
        XCTAssertTrue(chart.hasIncompletePrices)
        XCTAssertEqual(chart.curves.first?.points.last?.amountText, "$5.00–$7.00")
        // The legend keeps one amount, so two curves always fit beside each other.
        XCTAssertEqual(chart.curves.first?.detail(position: 8), "$5.00+")
        XCTAssertEqual(chart.curves.first?.detail(position: 3), "$2.00+")
        XCTAssertEqual(chart.curves.first?.detail(position: 9), "No data")
        XCTAssertEqual(report.period(.day)?.amountText, "$5.00–$7.00")
        XCTAssertEqual(report.period(.day)?.compactAmountText, "$5.00+")
        XCTAssertEqual(report.period(.week)?.compactAmountText, "$8.00")
    }
}
