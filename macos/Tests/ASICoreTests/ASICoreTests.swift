import Foundation
import XCTest
@testable import ASICore

final class ReportTests: XCTestCase {
    private func payload(cost: Double = 20, high: Double = 20, observed: Int = 1,
                         unpriced: Int = 0, percent: Double? = 1, budget: Double = 2000,
                         schema: Int = 1) throws -> Data {
        let periods: [[String: Any]] = ["today", "week", "month"].map { id in
            ["id": id, "known_cost_usd": cost, "cost_high_usd": high,
             "budget_usd": id == "month" ? budget : NSNull(),
             "used_percent": id == "month" ? (percent.map { $0 as Any } ?? NSNull()) : NSNull(),
             "observed_requests": observed, "unpriced_requests": unpriced,
             "resets_at": "2026-11-01T00:00:00+03:00"]
        }
        return try JSONSerialization.data(withJSONObject: [
            "schema_version": schema, "version": "1.4.3",
            "generated": "2026-10-22T12:00:00.123456+00:00",
            "timezone": "System local timezone", "periods": periods
        ])
    }

    func testDecodeCollectorContractAndCalendarDates() throws {
        let report = try MenuBarReport.decode(payload())
        XCTAssertEqual(report.periods.map(\.title), ["Today", "This week", "This month"])
        XCTAssertEqual(report.month?.budgetUsd, 2000)
        XCTAssertEqual(report.month?.amountText, "$20.00")
        XCTAssertEqual(report.month?.progress, 0.01)
        XCTAssertEqual(report.month?.resetsAt.timeIntervalSince1970, 1793480400)
    }

    func testZeroAbsentUnpricedPartialAndRanges() throws {
        let zero = try MenuBarReport.decode(payload(cost: 0, high: 0, percent: 0)).month!
        XCTAssertEqual(zero.amountText, "$0.00")
        let absent = try MenuBarReport.decode(payload(cost: 0, high: 0, observed: 0, percent: nil)).month!
        XCTAssertEqual(absent.amountText, "No data")
        let unknown = try MenuBarReport.decode(payload(cost: 0, high: 0, unpriced: 1, percent: nil)).month!
        XCTAssertEqual(unknown.amountText, "Unpriced")
        XCTAssertEqual(unknown.percentText, "—")
        let partial = try MenuBarReport.decode(payload(high: 40, observed: 2, unpriced: 1)).month!
        XCTAssertEqual(partial.amountText, "$20.00–$40.00+")
        XCTAssertEqual(partial.percentText, "1–2%+")
    }

    func testProgressCapsButOverspendPercentDoesNot() throws {
        let month = try MenuBarReport.decode(payload(cost: 2500, high: 2500, percent: 125)).month!
        XCTAssertEqual(month.progress, 1)
        XCTAssertEqual(month.percentText, "125%")
        XCTAssertEqual(month.warningLevel, 3)
    }

    func testMalformedReportsAndInvalidNumbersAreRejected() throws {
        XCTAssertThrowsError(try MenuBarReport.decode(payload(schema: 2)))
        XCTAssertThrowsError(try MenuBarReport.decode(payload(budget: 0)))
        XCTAssertThrowsError(try MenuBarReport.decode(payload(cost: -1)))
        XCTAssertThrowsError(try MenuBarReport.decode(payload(high: 10)))
        XCTAssertThrowsError(try MenuBarReport.decode(payload(unpriced: 2)))
    }

    func testWarningThresholds() throws {
        for (percent, level) in [(64.0,0),(65,1),(80,2),(100,3)] {
            let month = try MenuBarReport.decode(payload(percent: percent)).month!
            XCTAssertEqual(month.warningLevel, level)
        }
    }
}

@MainActor
final class ProcessTests: XCTestCase {
    private let directory = URL(fileURLWithPath: "/tmp", isDirectory: true)

    func testDrainsAllOutputBeforeReturning() async throws {
        let value = String(repeating: "usage", count: 8000)
        let output = try await ProcessRunner.run(executable: URL(fileURLWithPath: "/usr/bin/printf"),
                                                arguments: ["%s", value], directory: directory)
        XCTAssertEqual(String(decoding: output, as: UTF8.self), value)
    }

    func testNonzeroStatusIncludesStderr() async throws {
        do {
            _ = try await ProcessRunner.run(executable: URL(fileURLWithPath: "/bin/sh"),
                arguments: ["-c", "printf 'synthetic failure' >&2; exit 2"], directory: directory)
            XCTFail("Expected failure")
        } catch {
            XCTAssertEqual(error.localizedDescription, "synthetic failure")
        }
    }

    func testTimeoutTerminatesChild() async throws {
        do {
            _ = try await ProcessRunner.run(executable: URL(fileURLWithPath: "/bin/sleep"),
                arguments: ["10"], directory: directory, timeout: 0.05)
            XCTFail("Expected timeout")
        } catch CollectorError.timedOut {
        }
    }

    func testOutputLimitTerminatesChild() async throws {
        do {
            _ = try await ProcessRunner.run(executable: URL(fileURLWithPath: "/usr/bin/yes"),
                arguments: [], directory: directory, outputLimit: 1024)
            XCTFail("Expected output bound")
        } catch CollectorError.outputTooLarge {
        }
    }

    func testCancellationTerminatesChild() async throws {
        let task = Task {
            try await ProcessRunner.run(executable: URL(fileURLWithPath: "/bin/sleep"),
                arguments: ["10"], directory: directory)
        }
        try await Task.sleep(for: .milliseconds(50))
        task.cancel()
        do { _ = try await task.value; XCTFail("Expected cancellation") }
        catch is CancellationError {}
    }

    func testMissingExecutableIsRecoverable() async throws {
        do {
            _ = try await ProcessRunner.run(executable: URL(fileURLWithPath: "/missing/asi-test"),
                                            arguments: [], directory: directory)
            XCTFail("Expected launch error")
        } catch {
            XCTAssertFalse(error.localizedDescription.isEmpty)
        }
    }
}

@MainActor
final class CollectorIntegrationTests: XCTestCase {
    func testBundledCollectorAndSharedBudgetWithSyntheticHome() async throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("ASI client test " + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let source = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("agent_usage.py")
        // Keep the real parser/calculations, isolate discovery from personal sessions.
        let literals = try JSONSerialization.data(withJSONObject: [source.path, root.appendingPathComponent("empty home").path])
        let literal = String(decoding: literals, as: UTF8.self)
        let shim = """
        import json, runpy, sys
        source, home = json.loads(\(String(reflecting: literal)))
        sys.argv += ['--home', home]
        runpy.run_path(source, run_name='__main__')
        """
        try shim.write(to: root.appendingPathComponent("agent_usage.py"), atomically: true, encoding: .utf8)
        let output = root.appendingPathComponent("data/output")
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let initial = Data(#"{"monthly_budget_usd":3210,"forecast_enabled":true,"custom":"keep"}"#.utf8)
        try initial.write(to: output.appendingPathComponent("budget.json"))
        let client = CollectorClient(resources: root, environment: ["ASI_DATA_DIR": root.appendingPathComponent("data").path])
        let budget = try await client.budget()
        XCTAssertEqual(budget, 3210)
        let before = try await client.report()
        XCTAssertEqual(before.month?.budgetUsd, 3210)
        XCTAssertEqual(before.month?.amountText, "No data")
        XCTAssertNotNil(before.monthlyHistory)
        XCTAssertTrue(before.monthlyHistory?.points.isEmpty == true)
        // Real collector output must reach every chart, not just the cards.
        XCTAssertNotNil(before.chart(.day))
        XCTAssertNotNil(before.chart(.week))
        XCTAssertNotNil(before.chart(.month))
        try await client.saveBudget(4567)
        let after = try await client.report()
        XCTAssertEqual(after.month?.budgetUsd, 4567)
        let settings = try JSONSerialization.jsonObject(with: Data(contentsOf: output.appendingPathComponent("budget.json"))) as! [String: Any]
        XCTAssertEqual(settings["forecast_enabled"] as? Bool, true)
        XCTAssertEqual(settings["custom"] as? String, "keep")
        XCTAssertFalse(FileManager.default.fileExists(atPath: output.appendingPathComponent("sessions.sqlite").path))
        // Every dashboard open collects new local observations into the shared output.
        let firstDashboard = try await client.dashboard()
        let dashboard = firstDashboard.url
        XCTAssertEqual(dashboard, output.appendingPathComponent("dashboard.html"))
        let html = try String(contentsOf: dashboard, encoding: .utf8)
        XCTAssertTrue(html.lowercased().contains("<!doctype html>"))
        let home = root.appendingPathComponent("empty home/.claude/projects/test")
        try FileManager.default.createDirectory(at: home, withIntermediateDirectories: true)
        let timestamp = ISO8601DateFormatter().string(from: Date())
        let observation = #"{"type":"assistant","sessionId":"dashboard-refresh","timestamp":"\#(timestamp)","message":{"id":"new-usage","model":"claude-sonnet-5.5","usage":{"input_tokens":1000000,"output_tokens":100000}}}"#
        try (observation + "\n").write(to: home.appendingPathComponent("session.jsonl"),
                                       atomically: true, encoding: .utf8)
        let freshDashboard = try await client.dashboard()
        let reopened = freshDashboard.url
        XCTAssertEqual(reopened, dashboard)
        XCTAssertNotEqual(try String(contentsOf: reopened, encoding: .utf8), html)
        let snapshot = try JSONSerialization.jsonObject(with: Data(contentsOf: output.appendingPathComponent("usage.json"))) as! [String: Any]
        let summary = snapshot["summary"] as! [String: Any]
        XCTAssertEqual(summary["requests"] as? Int, 1)
        let persisted = try XCTUnwrap(snapshot["spend_summary"] as? [String: Any])
        let persistedReport = try MenuBarReport.decode(JSONSerialization.data(withJSONObject: persisted))
        XCTAssertEqual(freshDashboard.report.generated, persistedReport.generated)
        XCTAssertEqual(freshDashboard.report.month?.budgetUsd, 4567)
        XCTAssertEqual(freshDashboard.report.month?.knownCostUsd, 3)
        XCTAssertEqual(freshDashboard.report.monthlyHistory?.curves[0].points.last?.cost, 3)
        XCTAssertEqual(freshDashboard.report.monthlyHistory?.asOfDate, persistedReport.monthlyHistory?.asOfDate)
        XCTAssertNotEqual(firstDashboard.report.generated, freshDashboard.report.generated)
        XCTAssertEqual(try XCTUnwrap(summary["cost"] as? Double), 3, accuracy: 0.000001)

        // A failed recollection must report failure, preserving the last complete HTML.
        let freshHTML = try Data(contentsOf: reopened)
        try "raise SystemExit('synthetic dashboard collection failure')\n".write(
            to: root.appendingPathComponent("agent_usage.py"), atomically: true, encoding: .utf8)
        do { _ = try await client.dashboard(); XCTFail("Expected dashboard collection failure") }
        catch { XCTAssertTrue(error.localizedDescription.contains("synthetic dashboard collection failure")) }
        XCTAssertEqual(try Data(contentsOf: reopened), freshHTML)
        let unchangedBudget = try JSONSerialization.jsonObject(with: Data(contentsOf: output.appendingPathComponent("budget.json"))) as! [String: Any]
        XCTAssertEqual(unchangedBudget["monthly_budget_usd"] as? Double, 4567)
        XCTAssertEqual(unchangedBudget["custom"] as? String, "keep")
    }

    func testMissingPythonAndInvalidBudgetAreRecoverable() async throws {
        let client = CollectorClient(resources: URL(fileURLWithPath: "/missing"),
                                     environment: ["ASI_PYTHON": "/missing/python"])
        do { _ = try await client.report(); XCTFail("Expected missing Python") }
        catch CollectorError.missingPython {}
        do { try await client.saveBudget(.infinity); XCTFail("Expected invalid budget") }
        catch CollectorError.failed {}
    }
}

/// 1.x (AISAD) settings and data keep working; the app itself never moves data.
final class LegacyNameTests: XCTestCase {
    func testNewSettingWinsThenThe1xNameAndEmptyCountsAsUnset() {
        XCTAssertNil(CollectorClient.setting("PYTHON", in: [:]))
        XCTAssertEqual(CollectorClient.setting("PYTHON", in: ["AISAD_PYTHON": "/old"]), "/old")
        XCTAssertEqual(CollectorClient.setting("PYTHON", in: ["ASI_PYTHON": "/new", "AISAD_PYTHON": "/old"]), "/new")
        XCTAssertEqual(CollectorClient.setting("PYTHON", in: ["ASI_PYTHON": "", "AISAD_PYTHON": "/old"]), "/old")
        XCTAssertNil(CollectorClient.setting("PYTHON", in: ["ASI_PYTHON": "", "AISAD_PYTHON": ""]))
    }

    func testDataDirectoryPrefersNewThen1xWithoutMovingEither() throws {
        let home = FileManager.default.temporaryDirectory.appendingPathComponent("ASI data dir " + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: home) }
        let current = home.appendingPathComponent(".local/share/asi", isDirectory: true)
        let legacy = home.appendingPathComponent(".local/share/aisad", isDirectory: true)
        func resolved(_ environment: [String: String] = [:]) -> String {
            CollectorClient.dataDirectory(environment: environment, home: home).standardizedFileURL.path
        }
        // Neither exists: the new path, and nothing is created.
        XCTAssertEqual(resolved(), current.standardizedFileURL.path)
        XCTAssertFalse(FileManager.default.fileExists(atPath: current.path))
        // Only the 1.x directory exists: use it in place.
        try FileManager.default.createDirectory(at: legacy, withIntermediateDirectories: true)
        XCTAssertEqual(resolved(), legacy.standardizedFileURL.path)
        XCTAssertTrue(FileManager.default.fileExists(atPath: legacy.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: current.path))
        // Both exist: the new one wins and the old one stays untouched.
        try FileManager.default.createDirectory(at: current, withIntermediateDirectories: true)
        XCTAssertEqual(resolved(), current.standardizedFileURL.path)
        XCTAssertTrue(FileManager.default.fileExists(atPath: legacy.path))
        // Only the new one exists.
        try FileManager.default.removeItem(at: legacy)
        XCTAssertEqual(resolved(), current.standardizedFileURL.path)
        // A configured directory wins under either name.
        XCTAssertEqual(resolved(["AISAD_DATA_DIR": "/tmp/old-name"]), "/tmp/old-name")
        XCTAssertEqual(resolved(["ASI_DATA_DIR": "/tmp/new-name", "AISAD_DATA_DIR": "/tmp/old-name"]), "/tmp/new-name")
        XCTAssertEqual(resolved(["ASI_DATA_DIR": "", "AISAD_DATA_DIR": "/tmp/old-name"]), "/tmp/old-name")
    }

    func testClientUsesThe1xDataDirectoryAndPythonVariable() async throws {
        let home = FileManager.default.temporaryDirectory.appendingPathComponent("ASI client home " + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: home) }
        let legacy = home.appendingPathComponent(".local/share/aisad", isDirectory: true)
        try FileManager.default.createDirectory(at: legacy, withIntermediateDirectories: true)
        let client = CollectorClient(resources: URL(fileURLWithPath: "/missing"),
                                     environment: ["AISAD_PYTHON": "/missing/python"], home: home)
        XCTAssertEqual(client.output.standardizedFileURL.path,
                       legacy.appendingPathComponent("output").standardizedFileURL.path)
        // The 1.x Python variable is honored: a missing interpreter is reported, not replaced.
        do { _ = try await client.report(); XCTFail("Expected missing Python") }
        catch CollectorError.missingPython {}
    }
}
