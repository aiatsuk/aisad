import Foundation
import XCTest
@testable import AISADCore

final class ProviderLimitsTests: XCTestCase {
    private func payload(used: Any = 79, status: String = "available", windows: Bool = true) -> [String: Any] {
        let window: [String: Any] = ["id": "credits", "title": "Weekly", "used_percent": used,
            "resets_at": "2026-10-23T04:50:00Z", "duration_minutes": 10080]
        return ["schema_version": 1, "generated": "2026-10-22T09:00:00.123Z", "providers": [[
            "id": "grok", "name": "Grok", "plan": "SuperGrok", "source": "Grok CLI",
            "fetched_at": "2026-10-22T09:00:00Z", "status": status, "message": NSNull(),
            "retry_after_seconds": 60, "windows": windows ? [window] : []
        ]]]
    }

    func testReportedRemainingAndResetAreNotCostEstimates() throws {
        let report = try ProviderLimitsReport.decode(JSONSerialization.data(withJSONObject: payload()))
        let window = try XCTUnwrap(report.providers.first?.windows.first)
        XCTAssertEqual(window.remainingPercent, 21)
        XCTAssertEqual(window.remainingText, "21% left")
        XCTAssertFalse(window.isExpired(at: report.generated))
        XCTAssertTrue(window.isExpired(at: try XCTUnwrap(window.resetsAt)))
        XCTAssertEqual(window.remainingPercent, 21, "Passing a reset must not invent a new 100% allowance")
    }

    func testOveruseClampsRemainingButPreservesReportedValue() throws {
        let report = try ProviderLimitsReport.decode(JSONSerialization.data(withJSONObject: payload(used: 110)))
        XCTAssertEqual(report.providers.first?.windows.first?.usedPercent, 110)
        XCTAssertEqual(report.providers.first?.windows.first?.remainingText, "0% left")
    }

    func testUnavailableDoesNotBecomeZeroUsage() throws {
        let report = try ProviderLimitsReport.decode(JSONSerialization.data(
            withJSONObject: payload(status: "not_connected", windows: false)))
        XCTAssertTrue(try XCTUnwrap(report.providers.first).windows.isEmpty)
        XCTAssertThrowsError(try ProviderLimitsReport.decode(JSONSerialization.data(
            withJSONObject: payload(windows: false))))
    }

    func testInvalidMeasurementsAndDuplicateProvidersAreRejected() throws {
        for value: Any in [-1, true, "42"] {
            XCTAssertThrowsError(try ProviderLimitsReport.decode(JSONSerialization.data(
                withJSONObject: payload(used: value))))
        }
        var object = payload()
        let providers = object["providers"] as! [[String: Any]]
        object["providers"] = providers + providers
        XCTAssertThrowsError(try ProviderLimitsReport.decode(JSONSerialization.data(withJSONObject: object)))
    }

    func testCancellationAllowsQuotaReaderToCleanUp() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let marker = directory.appendingPathComponent("terminated")
        let source = """
        import signal, time
        from pathlib import Path
        def done(*args):
            Path(\(String(reflecting: marker.path))).write_text("cleaned")
            raise SystemExit(0)
        signal.signal(signal.SIGTERM, done)
        time.sleep(10)
        """
        let python = ["/opt/homebrew/bin/python3", "/usr/bin/python3"].first {
            FileManager.default.isExecutableFile(atPath: $0)
        }!
        do {
            _ = try await ProcessRunner.run(executable: URL(fileURLWithPath: python),
                arguments: ["-c", source], directory: directory, timeout: 0.3, terminationGrace: 0.75)
            XCTFail("Expected timeout")
        } catch CollectorError.timedOut {}
        XCTAssertEqual(try String(contentsOf: marker, encoding: .utf8), "cleaned")
    }

    func testIgnoredTerminationStillHasHardDeadline() async throws {
        let start = Date()
        do {
            _ = try await ProcessRunner.run(executable: URL(fileURLWithPath: "/bin/sh"),
                arguments: ["-c", "trap '' TERM; exec sleep 10"],
                directory: FileManager.default.temporaryDirectory, timeout: 0.1, terminationGrace: 0.2)
            XCTFail("Expected timeout")
        } catch CollectorError.timedOut {}
        XCTAssertLessThan(Date().timeIntervalSince(start), 2)
    }
}
