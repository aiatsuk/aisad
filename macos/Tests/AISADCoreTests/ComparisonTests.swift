import Foundation
import XCTest
@testable import AISADCore

final class ComparisonTests: XCTestCase {
    private func comparison(status: String = "available", delta: Double? = -20,
                            percent: Double? = -40) throws -> SpendComparison {
        let object: [String: Any] = [
            "status": status, "label": "vs yesterday",
            "absolute_usd": delta.map { $0 as Any } ?? NSNull(),
            "percent": percent.map { $0 as Any } ?? NSNull(),
            "current": ["known_cost_usd": 30],
            "previous": ["known_cost_usd": 50],
            "current_period": ["from": "2026-10-22T00:00:00+03:00", "to": "2026-10-22T12:00:00+03:00"],
            "previous_period": ["from": "2026-10-21T00:00:00+03:00", "to": "2026-10-21T12:00:00+03:00"]
        ]
        let period: [String: Any] = [
            "known_cost_usd": 30, "cost_high_usd": 30, "unpriced_requests": 0,
            "observed_requests": 1, "resets_at": "2026-11-01T00:00:00+03:00",
            "used_percent": 1.5, "comparison": object
        ]
        let periods = ["today", "week", "month"].map { id in
            period.merging(["id": id, "budget_usd": id == "month" ? 2000 : NSNull()]) { _, new in new }
        }
        let data = try JSONSerialization.data(withJSONObject: [
            "schema_version": 1, "version": "1.4.3", "generated": "2026-10-22T09:00:00Z",
            "timezone": "Europe/Moscow", "periods": periods
        ])
        let report = try MenuBarReport.decode(data)
        return try XCTUnwrap(report.month?.comparison)
    }

    func testSignedChangesAndExactWindows() throws {
        let down = try comparison()
        XCTAssertEqual(down.text, "−$20.00 · −40%")
        XCTAssertEqual(down.symbol, "arrow.down.right")
        XCTAssertTrue(down.detail.contains("vs yesterday"))
        XCTAssertTrue(down.detail.contains("$30.00"))
        XCTAssertTrue(down.detail.contains("$50.00"))
        XCTAssertEqual(down.currentPeriod.to.timeIntervalSince(down.currentPeriod.from), 12 * 3600)
        let up = try comparison(delta: 10, percent: 20)
        XCTAssertEqual(up.text, "+$10.00 · +20%")
        XCTAssertEqual(up.symbol, "arrow.up.right")
    }

    func testZeroBaselineShowsDollarsWithoutInfinitePercent() throws {
        let change = try comparison(status: "zero_baseline", delta: 10, percent: nil)
        XCTAssertEqual(change.text, "+$10.00")
        XCTAssertTrue(change.isAvailable)
        let unchanged = try comparison(delta: 0, percent: 0)
        XCTAssertEqual(unchanged.text, "$0.00 · 0%")
        XCTAssertEqual(unchanged.symbol, "minus")
    }

    func testUnavailableComparisonDoesNotShowInventedZero() throws {
        let missing = try comparison(status: "no_previous_data", delta: nil, percent: nil)
        XCTAssertEqual(missing.text, "No previous data")
        XCTAssertFalse(missing.isAvailable)
        let partial = try comparison(status: "incomplete_pricing", delta: nil, percent: nil)
        XCTAssertEqual(partial.text, "Incomplete prices")
    }

    func testMalformedAvailableDeltaRejected() {
        XCTAssertThrowsError(try comparison(delta: nil))
        XCTAssertThrowsError(try comparison(percent: nil))
        XCTAssertThrowsError(try comparison(status: "zero_baseline", percent: 2))
    }
}
