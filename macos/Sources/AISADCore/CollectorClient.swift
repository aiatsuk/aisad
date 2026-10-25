import Foundation

public struct DashboardSnapshot: Sendable {
    public let url: URL
    public let report: MenuBarReport
}

public actor CollectorClient {
    public nonisolated let output: URL
    private let collector: URL
    private let python: URL?
    private let shared: SharedUsageReader

    public init(resources: URL, environment: [String: String] = ProcessInfo.processInfo.environment) {
        collector = resources.appendingPathComponent("agent_usage.py")
        let root = environment["AISAD_DATA_DIR"].map {
            URL(fileURLWithPath: ($0 as NSString).expandingTildeInPath, isDirectory: true)
        } ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".local/share/aisad")
        output = root.appendingPathComponent("output", isDirectory: true)
        shared = SharedUsageReader(output: output)
        let paths = environment["AISAD_PYTHON"].map { [$0] } ??
            ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
        python = paths.first { FileManager.default.isExecutableFile(atPath: $0) }.map(URL.init(fileURLWithPath:))
    }

    public func sharedReport(after revision: String?) async throws -> MenuBarReport? {
        try await shared.read(after: revision)
    }

    public func report() async throws -> MenuBarReport {
        try MenuBarReport.decode(await invoke(["menubar", "--json"]))
    }

    /// Recollect on every open; a failed collection leaves the previous HTML intact.
    public func dashboard() async throws -> DashboardSnapshot {
        let url = output.appendingPathComponent("dashboard.html")
        let report = try MenuBarReport.decode(await invoke(["dashboard", "--json"], timeout: 300))
        guard (try? url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true else {
            throw CollectorError.failed("The dashboard was not created. Try again.")
        }
        return DashboardSnapshot(url: url, report: report)
    }

    public func limits(providers: [String]) async throws -> ProviderLimitsReport {
        guard let python else { throw CollectorError.missingPython }
        let helper = collector.deletingLastPathComponent().appendingPathComponent("provider_limits.py")
        guard FileManager.default.fileExists(atPath: helper.path) else {
            throw CollectorError.failed("Rebuild AISAD to include the plan-limit reader.")
        }
        let data = try await ProcessRunner.run(executable: python,
            arguments: [helper.path, "--providers"] + providers,
            directory: collector.deletingLastPathComponent(), timeout: 25, terminationGrace: 0.75)
        let report = try ProviderLimitsReport.decode(data)
        guard Set(report.providers.map(\.id)) == Set(providers) else {
            throw CollectorError.invalidReport
        }
        return report
    }

    public func budget() async throws -> Double {
        struct Settings: Decodable { let monthly_budget_usd: Double }
        let data = try await invoke(["budget", "--json"])
        let value = try JSONDecoder().decode(Settings.self, from: data).monthly_budget_usd
        guard value.isFinite, value > 0 else { throw CollectorError.invalidReport }
        return value
    }

    public func saveBudget(_ value: Double) async throws {
        guard value.isFinite, value > 0 else {
            throw CollectorError.failed("Enter a positive monthly budget in USD.")
        }
        _ = try await invoke(["budget", "--set", String(value), "--json"])
    }

    private func invoke(_ arguments: [String], timeout: TimeInterval = 120) async throws -> Data {
        guard let python else { throw CollectorError.missingPython }
        guard FileManager.default.fileExists(atPath: collector.path) else { throw CollectorError.missingCollector }
        return try await ProcessRunner.run(executable: python,
            arguments: [collector.path] + arguments + ["--output", output.path],
            directory: collector.deletingLastPathComponent(), timeout: timeout)
    }
}
