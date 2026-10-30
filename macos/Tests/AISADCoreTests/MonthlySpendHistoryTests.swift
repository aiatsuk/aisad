import Foundation
import XCTest
@testable import AISADCore

final class MonthlySpendHistoryTests: XCTestCase {
    private func month(_ start: String, _ entries: [Int: (Double?, Double?, Int, Int)] = [:]) -> [String: Any] {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = formatter.timeZone
        let count = calendar.range(of: .day, in: .month, for: formatter.date(from: start)!)!.count
        let prefix = String(start.prefix(8))
        return ["from": start, "to": prefix + String(format: "%02d", count), "days": count,
                "daily": (1...count).map { day -> [String: Any] in
                    let entry = entries[day] ?? (nil, nil, 0, 0)
                    return ["date": prefix + String(format: "%02d", day),
                            "cost_usd": entry.0.map { $0 as Any } ?? NSNull(),
                            "cost_high_usd": entry.1.map { $0 as Any } ?? NSNull(),
                            "observations": entry.2, "unpriced_observations": entry.3]
                }]
    }
    private func object(_ entries: [Int: (Double?, Double?, Int, Int)] = [:]) -> [String: Any] {
        ["schema_version": 1, "as_of_date": "2026-10-23",
         "current": month("2026-10-01", entries),
         "previous": month("2026-09-01", [1: (8,8,1,0)])]
    }
    private func decode(_ object: [String: Any]) throws -> MonthlySpendHistory {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(MonthlySpendHistory.self, from: JSONSerialization.data(withJSONObject: object))
    }

    func testCumulativeTotalsAlignDaysAndKeepGaps() throws {
        let history = try decode(object([1: (10,10,1,0),3: (5,5,1,0),4: (0,0,1,0)]))
        let curve = history.curves[0]
        XCTAssertEqual(curve.points.map(\.day), [1,3,4])
        XCTAssertEqual(curve.points.map(\.cost), [10,15,15])
        XCTAssertNotEqual(curve.points[0].segment, curve.points[1].segment)
        XCTAssertEqual(curve.points[1].segment, curve.points[2].segment)
        XCTAssertTrue(curve.points[0].showsMarker)
        XCTAssertEqual(curve.detail(day: 2), "No data")
        XCTAssertEqual(curve.detail(day: 24), "No data")
        XCTAssertEqual(history.curves[1].detail(day: 31), "No data")
        XCTAssertGreaterThan(history.upperBound(budget: 2000), 2000)
    }

    func testPriceRangesAndUnknownEarlierCostsPropagateToLaterTotals() throws {
        let history = try decode(object([1: (nil,nil,1,1),2: (5,6,2,1),3: (2,2,1,0)]))
        XCTAssertTrue(history.hasIncompletePrices)
        XCTAssertEqual(history.curves[0].detail(day: 1), "Unpriced")
        XCTAssertEqual(history.curves[0].detail(day: 2), "$5.00–$6.00+")
        XCTAssertEqual(history.curves[0].detail(day: 3), "$7.00–$8.00+")
    }

    func testObservedZeroIsNotMissingUsage() throws {
        let history = try decode(object([1: (0,0,1,0)]))
        XCTAssertEqual(history.curves[0].points.count, 1)
        XCTAssertEqual(history.curves[0].detail(day: 1), "$0.00")
        XCTAssertEqual(history.curves[0].detail(day: 2), "No data")
    }

    func testLeapMonthAndYearRollover() throws {
        let leap = try decode(["schema_version":1,"as_of_date":"2028-03-31",
                               "current":month("2028-03-01"),"previous":month("2028-02-01")])
        XCTAssertEqual(leap.previous.days,29)
        XCTAssertEqual(leap.dayCount,31)
        let rollover = try decode(["schema_version":1,"as_of_date":"2027-01-01",
                                   "current":month("2027-01-01"),"previous":month("2026-12-01")])
        XCTAssertEqual(rollover.curves.map(\.title),["Jan","Dec"])
    }

    func testMalformedCalendarsFutureDataAndPricingAreRejected() throws {
        var invalid = object()
        invalid["previous"] = month("2026-08-01")
        XCTAssertThrowsError(try decode(invalid))
        invalid = object([24:(1,1,1,0)])
        XCTAssertThrowsError(try decode(invalid))
        invalid = object([1:(2,1,1,0)])
        XCTAssertThrowsError(try decode(invalid))
        invalid = object([1:(0,0,0,0)])
        XCTAssertThrowsError(try decode(invalid))
        invalid = object()
        var current = invalid["current"] as! [String:Any]
        var days = current["daily"] as! [[String:Any]]
        days[0]["date"] = "2026-10-02"
        current["daily"] = days
        invalid["current"] = current
        XCTAssertThrowsError(try decode(invalid))
    }

    func testHistoryThatDoesNotMatchMonthlyCardCostsOnlyTheChart() throws {
        let periods: [[String: Any]] = ["today","week","month"].map { id in
            ["id":id,"known_cost_usd":20,"cost_high_usd":20,
             "budget_usd":id == "month" ? 2000 : NSNull(),
             "used_percent":id == "month" ? 1 : NSNull(),
             "observed_requests":1,"unpriced_requests":0,"resets_at":"2026-11-01T00:00:00Z"]
        }
        var payload: [String:Any] = ["schema_version":1,"version":"test","generated":"2026-10-23T12:00:00Z",
                                    "timezone":"UTC","periods":periods,"monthly_history":object([1:(10,10,1,0)])]
        let mismatched = try MenuBarReport.decode(JSONSerialization.data(withJSONObject: payload))
        XCTAssertNil(mismatched.monthlyHistory)
        XCTAssertEqual(mismatched.month?.knownCostUsd, 20)
        payload["monthly_history"] = object([1:(20,20,1,0)])
        XCTAssertNotNil(try MenuBarReport.decode(JSONSerialization.data(withJSONObject: payload)).monthlyHistory)
        payload.removeValue(forKey:"monthly_history")
        XCTAssertNil(try MenuBarReport.decode(JSONSerialization.data(withJSONObject: payload)).monthlyHistory)
    }
}
