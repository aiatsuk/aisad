import Foundation
import XCTest
@testable import AISADCore

final class QuotaIndicatorTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_700_000_000)

    private func window(_ id: String, used: Double, expired: Bool = false,
                        unknownReset: Bool = false) -> QuotaWindow {
        let title = ["5h": "5 hours", "week": "Weekly", "model-week": "Weekly · Fable"][id] ?? id
        let duration: Double? = ["5h": 300, "week": 10080, "model-week": 10080][id]
        return QuotaWindow(id: id, title: title, usedPercent: used,
                    resetsAt: unknownReset ? nil : now.addingTimeInterval(expired ? -1 : 3600),
                    durationMinutes: duration)
    }

    private func provider(_ windows: [QuotaWindow], status: String = "available", id: String = "claude") -> ProviderQuota {
        ProviderQuota(id: id, name: "Synthetic provider", plan: "Max", source: "Synthetic",
                      fetchedAt: now, status: status, message: nil, retryAfterSeconds: 60,
                      windows: windows)
    }

    func testRingsRepresentIndependentRemainingWindows() {
        let state = QuotaIndicatorState(provider: provider([
            window("5h", used: 16), window("week", used: 73)
        ]), refreshing: false, now: now)
        XCTAssertEqual(state.phase, .available)
        XCTAssertEqual(state.rings.map(\.id), ["5h", "week"])
        XCTAssertEqual(state.rings[0].placement, .outer)
        XCTAssertEqual(state.rings[1].placement, .inner)
        XCTAssertEqual(state.rings[0].remainingFraction!, 0.84, accuracy: 0.000001)
        XCTAssertEqual(state.rings[1].remainingFraction!, 0.27, accuracy: 0.000001)
        XCTAssertEqual(state.lowestRemainingPercent, 27)
    }

    func testUnknownDoesNotBecomeAnExhaustedQuota() {
        let missing = QuotaIndicatorState(provider: nil, refreshing: false, now: now)
        XCTAssertEqual(missing.phase, .unavailable)
        XCTAssertNil(missing.lowestRemainingPercent)
        XCTAssertTrue(missing.rings.isEmpty)
        let zero = QuotaIndicatorState(provider: provider([window("week", used: 100)]),
                                      refreshing: false, now: now)
        XCTAssertEqual(zero.phase, .available)
        XCTAssertEqual(zero.lowestRemainingPercent, 0)
        XCTAssertEqual(zero.rings.first?.remainingFraction, 0)
    }

    func testInitialLoadingAndBackgroundRefreshAreDistinct() {
        XCTAssertEqual(QuotaIndicatorState(provider: nil, refreshing: true, now: now).phase, .loading)
        let p = provider([window("week", used: 21)])
        XCTAssertEqual(QuotaIndicatorState(provider: p, refreshing: true, now: now).phase, .available)
    }

    func testExpiredWindowsNeverInventARefill() {
        let p = provider([window("5h", used: 42, expired: true)])
        let state = QuotaIndicatorState(provider: p, refreshing: false, now: now)
        XCTAssertEqual(state.phase, .expired)
        XCTAssertNil(state.rings.first?.remainingFraction)
        XCTAssertNil(state.lowestRemainingPercent)
        XCTAssertEqual(p.windows[0].remainingPercent, 58)
    }

    func testPartlyExpiredAndRateLimitedReadingsAreStale() {
        let mixed = QuotaIndicatorState(provider: provider([
            window("5h", used: 42, expired: true), window("week", used: 79)
        ]), refreshing: false, now: now)
        XCTAssertEqual(mixed.phase, .stale)
        XCTAssertNil(mixed.rings[0].remainingFraction)
        XCTAssertEqual(mixed.lowestRemainingPercent, 21)
        for status in ["stale", "rate_limited"] {
            let state = QuotaIndicatorState(provider: provider([window("week", used: 79)], status: status),
                                            refreshing: false, now: now)
            XCTAssertEqual(state.phase, .stale)
            XCTAssertEqual(state.rings[0].remainingFraction!, 0.21, accuracy: 0.000001)
        }
    }

    func testHiddenExtraWindowsStillAffectTheWarning() {
        for remaining in [0.0, 4, 21] {
            let p = provider([window("5h", used: 20), window("week", used: 40),
                              window("model-week", used: 100 - remaining)])
            let state = QuotaIndicatorState(provider: p, refreshing: false, now: now)
            XCTAssertEqual(state.rings.count, 2)
            XCTAssertEqual(state.windowCount, 3)
            XCTAssertEqual(state.lowestRemainingPercent, remaining)
            XCTAssertEqual(p.windows.count, 3, "The detail view must retain every window")
        }
    }

    func testUnknownResetAndOverusePreserveReportedSemantics() {
        let state = QuotaIndicatorState(provider: provider([
            window("credits", used: 133, unknownReset: true)
        ]), refreshing: false, now: now)
        XCTAssertEqual(state.phase, .available)
        XCTAssertEqual(state.rings[0].remainingFraction, 0)
    }

    func testPeriodHierarchyIgnoresProviderResponseOrder() {
        for id in ["claude", "codex", "grok"] {
            let p = provider([window("model-week", used: 96), window("week", used: 73),
                              window("5h", used: 16)], id: id)
            let state = QuotaIndicatorState(provider: p, refreshing: false, now: now)
            XCTAssertEqual(p.displayWindows.map(\.id), ["5h", "week", "model-week"])
            XCTAssertEqual(state.rings.map(\.id), ["5h", "week"])
            XCTAssertEqual(state.rings[0].placement, .outer)
            XCTAssertEqual(state.rings[1].placement, .inner)
            XCTAssertEqual(state.lowestRemainingPercent, 4, "Model windows still affect warnings")
        }
    }

    func testWeeklyOnlyStaysInsideWithoutInventingASession() {
        let p = provider([window("model-week", used: 4), window("week", used: 73)])
        let state = QuotaIndicatorState(provider: p, refreshing: false, now: now)
        XCTAssertEqual(state.rings.count, 1)
        XCTAssertEqual(state.rings.first?.id, "week")
        XCTAssertEqual(state.rings.first?.placement, .inner)
        XCTAssertEqual(p.displayWindows.map(\.id), ["week", "model-week"])
    }

    func testOlderReadingsWithoutDurationsKeepTheSameHierarchy() {
        let weekly = QuotaWindow(id: "secondary", title: "Weekly", usedPercent: 73,
                                 resetsAt: nil, durationMinutes: nil)
        let session = QuotaWindow(id: "primary", title: "5 hours", usedPercent: 16,
                                  resetsAt: nil, durationMinutes: nil)
        let p = provider([weekly, session])
        let state = QuotaIndicatorState(provider: p, refreshing: false, now: now)
        XCTAssertEqual(p.displayWindows.map(\.id), ["primary", "secondary"])
        XCTAssertEqual(state.rings[0].placement, .outer)
        XCTAssertEqual(state.rings[1].placement, .inner)
    }

    func testReportedDurationsSupportOtherShortAndLongTermWindows() {
        let monthly = QuotaWindow(id: "month", title: "Monthly", usedPercent: 40,
                                  resetsAt: nil, durationMinutes: 43200)
        let daily = QuotaWindow(id: "day", title: "Daily", usedPercent: 50,
                                resetsAt: nil, durationMinutes: 1440)
        let p = provider([monthly, daily])
        let state = QuotaIndicatorState(provider: p, refreshing: false, now: now)
        XCTAssertEqual(p.displayWindows.map(\.id), ["day", "month"])
        XCTAssertEqual(state.rings[0].placement, .outer)
        XCTAssertEqual(state.rings[1].placement, .inner)
    }

    func testWarningBoundariesUseRemainingQuota() {
        for remaining in [100.0, 25, 20] {
            XCTAssertEqual(QuotaIndicatorState.WarningLevel(remainingPercent: remaining), .normal)
        }
        for remaining in [19.99, 15, 10.01] {
            XCTAssertEqual(QuotaIndicatorState.WarningLevel(remainingPercent: remaining), .warning)
        }
        for remaining in [10.0, 5, 0] {
            XCTAssertEqual(QuotaIndicatorState.WarningLevel(remainingPercent: remaining), .critical)
        }
    }

    func testFableNeverReplacesMissingAggregateLimits() {
        let p = provider([window("model-week", used: 39), window("5h", used: 16)])
        let state = QuotaIndicatorState(provider: p, refreshing: false, now: now)
        XCTAssertEqual(state.rings.count, 1)
        XCTAssertEqual(state.rings.first?.id, "5h")
        XCTAssertEqual(state.rings.first?.placement, .outer)
        XCTAssertEqual(p.displayWindows.map(\.id), ["5h", "model-week"])

        let scopedOnly = provider([window("model-week", used: 39)])
        let scopedState = QuotaIndicatorState(provider: scopedOnly, refreshing: false, now: now)
        XCTAssertTrue(scopedState.rings.isEmpty, "Do not invent an aggregate ring from Fable")
        XCTAssertEqual(scopedOnly.displayWindows.count, 1, "Fable remains in the details")
    }

    func testExhaustedFableWarnsWithoutChangingHealthyAggregateRings() {
        let p = provider([window("model-week", used: 100), window("week", used: 73),
                          window("5h", used: 16)])
        let state = QuotaIndicatorState(provider: p, refreshing: false, now: now)
        XCTAssertEqual(state.phase, .available)
        XCTAssertEqual(state.rings.map(\.id), ["5h", "week"])
        XCTAssertEqual(state.rings[0].remainingFraction!, 0.84, accuracy: 0.000001)
        XCTAssertEqual(state.rings[1].remainingFraction!, 0.27, accuracy: 0.000001)
        XCTAssertEqual(state.lowestRemainingPercent, 0)
        XCTAssertEqual(QuotaIndicatorState.WarningLevel(remainingPercent: state.lowestRemainingPercent!), .critical)
        XCTAssertEqual(p.displayWindows.map(\.id), ["5h", "week", "model-week"])
        XCTAssertEqual(p.displayWindows.last?.remainingPercent, 0)
    }

    func testCompactWeeklyCaptionUsesTheAggregateForEveryProvider() {
        for id in ["claude", "codex", "grok"] {
            let p = provider([window("model-week", used: 0), window("5h", used: 16),
                              window("week", used: 73)], id: id)
            XCTAssertEqual(p.activeWeeklyWindow(at: now)?.id, "week")
            XCTAssertEqual(p.activeWeeklyWindow(at: now)?.remainingText, "27% left")
        }
        let exhausted = provider([window("week", used: 100)])
        XCTAssertEqual(exhausted.activeWeeklyWindow(at: now)?.remainingText, "0% left")
    }

    func testCompactWeeklyCaptionDoesNotInventOrSubstituteAWindow() {
        XCTAssertNil(provider([]).activeWeeklyWindow(at: now))
        XCTAssertNil(provider([window("5h", used: 16), window("model-week", used: 39)])
            .activeWeeklyWindow(at: now))
        XCTAssertNil(provider([window("week", used: 73, expired: true)])
            .activeWeeklyWindow(at: now))
        let monthly = QuotaWindow(id: "credits", title: "Monthly", usedPercent: 79,
                                  resetsAt: nil, durationMinutes: 43200)
        XCTAssertNil(provider([monthly]).activeWeeklyWindow(at: now))
        let weekly = QuotaWindow(id: "credits", title: "Weekly", usedPercent: 79,
                                 resetsAt: nil, durationMinutes: 10079.5)
        XCTAssertEqual(provider([weekly]).activeWeeklyWindow(at: now)?.remainingText, "21% left")
    }
}
