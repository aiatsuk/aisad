#if DEBUG
import AISADCore
import Foundation

/// Isolated visual-QA inputs. Normal app startup always uses the live collector.
@MainActor
enum SnapshotPreview {
    static func load(from url: URL, into store: UsageStore) throws {
        let object = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any]
        guard let object else { throw CollectorError.invalidReport }
        let report: MenuBarReport?
        if let payload = object["report"], !(payload is NSNull) {
            report = try MenuBarReport.decode(JSONSerialization.data(withJSONObject: payload))
        } else {
            report = nil
        }
        if let payload = object["limits"], !(payload is NSNull) {
            let limits = try ProviderLimitsReport.decode(JSONSerialization.data(withJSONObject: payload))
            store.limits.showPreview(report: limits, refreshing: object["limits_refreshing"] as? Bool ?? false)
        } else {
            store.limits.showPreview(report: nil, refreshing: object["limits_refreshing"] as? Bool ?? false)
        }
        store.showPreview(report: report, error: object["error"] as? String,
                          refreshing: object["refreshing"] as? Bool ?? false,
                          saving: object["saving"] as? Bool ?? false,
                          saved: object["saved"] as? Bool ?? false,
                          openingDashboard: object["opening_dashboard"] as? Bool ?? false)
    }
}
#endif
