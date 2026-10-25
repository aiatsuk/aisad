import Foundation

/// Follows committed reports only. A missing or malformed file never replaces a
/// consumer's last successful reading and never starts another collection.
public actor SharedUsageReader {
    private let url: URL
    private var signature: String?

    public init(output: URL) { url = output.appendingPathComponent("usage-live.js") }

    public func read(after revision: String?) throws -> MenuBarReport? {
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        let current = String(describing: attributes[.systemFileNumber]) + ":" +
            String(describing: attributes[.size]) + ":" +
            String(describing: attributes[.modificationDate])
        guard signature != current else { return nil }
        let text = try String(contentsOf: url, encoding: .utf8)
        let prefix = "globalThis.aisadLiveRevision?.("
        guard text.hasPrefix(prefix), text.hasSuffix(");"),
              let data = String(text.dropFirst(prefix.count).dropLast(2)).data(using: .utf8),
              let commit = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              commit["schema_version"] as? Int == 1,
              let revisionValue = commit["revision"] as? String,
              let encoded = commit["report_base64"] as? String,
              let reportData = Data(base64Encoded: encoded) else { throw CollectorError.invalidReport }
        let report = try MenuBarReport.decode(reportData)
        guard report.syncRevision == revisionValue else { throw CollectorError.invalidReport }
        guard let next = report.syncRevision, next.count == 20,
              next.allSatisfy(\.isNumber) else { return nil }
        signature = current
        if let revision, next <= revision { return nil }
        return report
    }
}
