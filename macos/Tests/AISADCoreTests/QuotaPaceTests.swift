import Foundation
import XCTest
@testable import AISADCore

final class QuotaPaceTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_700_000_000)
    private let day: TimeInterval = 86_400

    /// A weekly window `elapsedDays` into its period.
    private func weekly(used: Double, elapsedDays: Double, id: String = "week",
                        title: String = "Weekly") -> QuotaWindow {
        QuotaWindow(id: id, title: title, usedPercent: used,
                    resetsAt: now.addingTimeInterval((7 - elapsedDays) * day), durationMinutes: 10080)
    }

    private func provider(_ windows: [QuotaWindow], fetchedAt: Date? = nil) -> ProviderQuota {
        ProviderQuota(id: "codex", name: "Codex", plan: "Pro", source: "Synthetic",
                      fetchedAt: fetchedAt ?? now, status: "available", message: nil,
                      retryAfterSeconds: 300, windows: windows)
    }

    func testFasterThanEvenSpendIsBehindPaceAndRunsOutBeforeReset() throws {
        // Two of seven days gone, half the allowance used: even spend leaves 71.4%.
        let pace = try XCTUnwrap(QuotaPace(window: weekly(used: 50, elapsedDays: 2), at: now))
        XCTAssertEqual(pace.evenRemainingPercent, 100 * 5 / 7, accuracy: 0.001)
        XCTAssertEqual(pace.standing, .behind)
        XCTAssertEqual(pace.paceText, "21% behind pace")
        XCTAssertEqual(try XCTUnwrap(pace.runsOut).timeIntervalSince(pace.start), 4 * day, accuracy: 1)
    }

    func testSlowerSpendLastsUntilReset() throws {
        let pace = try XCTUnwrap(QuotaPace(window: weekly(used: 10, elapsedDays: 3.5), at: now))
        XCTAssertEqual(pace.standing, .ahead)
        XCTAssertEqual(pace.paceText, "40% ahead of pace")
        XCTAssertNil(pace.runsOut)
    }

    func testUnusedWindowHasNoProjectionAndEvenSpendIsOnPace() throws {
        let fresh = try XCTUnwrap(QuotaPace(window: weekly(used: 0, elapsedDays: 0.001), at: now))
        XCTAssertFalse(fresh.hasUsage)
        XCTAssertNil(fresh.runsOut)
        XCTAssertEqual(fresh.standing, .onPace)
        let even = try XCTUnwrap(QuotaPace(window: weekly(used: 50, elapsedDays: 3.5), at: now))
        XCTAssertEqual(even.paceText, "On pace")
    }

    func testWindowsWithoutResetOrDurationOrAlreadyExpiredHaveNoPace() {
        XCTAssertNil(QuotaPace(window: QuotaWindow(id: "x", title: "Credits", usedPercent: 10,
                                                   resetsAt: nil, durationMinutes: 10080), at: now))
        XCTAssertNil(QuotaPace(window: QuotaWindow(id: "x", title: "Custom", usedPercent: 10,
                                                   resetsAt: now.addingTimeInterval(day), durationMinutes: nil), at: now))
        XCTAssertNil(QuotaPace(window: weekly(used: 10, elapsedDays: 7.5), at: now))
    }

    func testHeadlineIsTheAggregateWeeklyWindowAndOthersFollowInDisplayOrder() {
        let session = QuotaWindow(id: "5h", title: "5 hours", usedPercent: 48,
                                  resetsAt: now.addingTimeInterval(3_600), durationMinutes: 300)
        let scoped = weekly(used: 0, elapsedDays: 1, id: "fable", title: "Weekly · Fable")
        let quota = provider([scoped, weekly(used: 10, elapsedDays: 1), session])
        XCTAssertEqual(quota.primaryWindow(at: now)?.id, "week")
        XCTAssertEqual(quota.secondaryWindows(at: now).map(\.id), ["5h", "fable"])
        XCTAssertEqual(session.shortTitle, "Session")
        XCTAssertEqual(scoped.shortTitle, "Weekly Fable")
    }

    func testLevelsMatchTheTileColours() {
        XCTAssertEqual(QuotaLevel(remainingPercent: 90), .healthy)
        XCTAssertEqual(QuotaLevel(remainingPercent: 73), .low)
        XCTAssertEqual(QuotaLevel(remainingPercent: 15), .critical)
    }

    func testHistoryKeepsChangedReadingsOfTheCurrentPeriodOnly() throws {
        var history = QuotaHistory()
        let window = weekly(used: 10, elapsedDays: 2)
        // A reading from the previous period, then the current one.
        history.record(provider([QuotaWindow(id: "week", title: "Weekly", usedPercent: 95,
                                             resetsAt: now.addingTimeInterval(-2.5 * day), durationMinutes: 10080)],
                                fetchedAt: now.addingTimeInterval(-3 * day)), at: now.addingTimeInterval(-3 * day))
        history.record(provider([weekly(used: 5, elapsedDays: 2)], fetchedAt: now.addingTimeInterval(-3_600)),
                       at: now.addingTimeInterval(-3_600))
        // Unchanged within ten minutes: nothing new. Older than the last sample: ignored.
        history.record(provider([weekly(used: 5, elapsedDays: 2)], fetchedAt: now.addingTimeInterval(-3_400)),
                       at: now.addingTimeInterval(-3_400))
        history.record(provider([weekly(used: 4, elapsedDays: 2)], fetchedAt: now.addingTimeInterval(-7_200)),
                       at: now.addingTimeInterval(-3_000))
        history.record(provider([window]), at: now)
        XCTAssertEqual(history.samples.count, 2, "the reading whose window reset over a day ago is pruned")
        XCTAssertEqual(history.series(provider: "codex", window: window, at: now).map(\.remainingPercent), [95, 90])

        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".json")
        defer { try? FileManager.default.removeItem(at: url) }
        try history.write(to: url)
        XCTAssertEqual(QuotaHistory.load(from: url), history)
        XCTAssertEqual(QuotaHistory.load(from: url.appendingPathExtension("missing")), QuotaHistory())
    }
}
