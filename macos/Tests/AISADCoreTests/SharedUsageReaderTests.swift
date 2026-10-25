import Foundation
import XCTest
@testable import AISADCore

final class SharedUsageReaderTests: XCTestCase {
    func testPythonPublicationReachesNativeReaderWithoutCollecting() async throws {
        let output = FileManager.default.temporaryDirectory.appendingPathComponent("AISAD shared " + UUID().uuidString)
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: output) }
        let source = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("agent_usage.py")
        let script = """
        import importlib.util,sys
        spec=importlib.util.spec_from_file_location('collector',sys.argv[1])
        a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
        output,cost,revision=sys.argv[2],float(sys.argv[3]),sys.argv[4]
        args=a.parser().parse_args(['menubar','--output',output])
        row=dict(date='2026-10-23',cost=cost,cost_high=cost,ts=1792756800)
        snapshot=dict(version='test',generated='2026-10-23T12:00:00Z',
            as_of_date='2026-10-23',timezone='System local timezone',rows=[],request_stats=[row])
        a.publish_shared_usage(snapshot,args,revision.zfill(20))
        """
        func publish(_ cost: Int, _ revision: Int) async throws {
            _ = try await ProcessRunner.run(executable: URL(fileURLWithPath: "/usr/bin/python3"),
                arguments: ["-B", "-c", script, source.path, output.path, String(cost), String(revision)],
                directory: output, timeout: 10)
        }
        let reader = SharedUsageReader(output: output)
        try await publish(10, 10)
        let first = try await reader.read(after: nil)
        XCTAssertEqual(first?.month?.knownCostUsd, 10)
        let revision = try XCTUnwrap(first?.syncRevision)
        let unchanged = try await reader.read(after: revision)
        XCTAssertNil(unchanged)
        try await publish(2, 2)
        let older = try await reader.read(after: revision)
        XCTAssertNil(older)
        try await publish(30, 30)
        let newer = try await reader.read(after: revision)
        XCTAssertEqual(newer?.month?.knownCostUsd, 30)
        XCTAssertGreaterThan(try XCTUnwrap(newer?.syncRevision), revision)
        let path = output.appendingPathComponent("usage-live.js")
        let valid = try Data(contentsOf: path)
        try Data("{broken".utf8).write(to: path, options: .atomic)
        do { _ = try await reader.read(after: revision); XCTFail("Expected malformed report") }
        catch {}
        try valid.write(to: path, options: .atomic)
        let recovered = try await reader.read(after: revision)
        XCTAssertEqual(recovered?.month?.knownCostUsd, 30)
    }
}
