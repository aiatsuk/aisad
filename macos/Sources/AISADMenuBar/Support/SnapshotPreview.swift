#if DEBUG
import AISADCore
import Foundation
import SwiftUI

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
        var history = QuotaHistory()
        if let payload = object["quota_history"], !(payload is NSNull) {
            let file = FileManager.default.temporaryDirectory.appendingPathComponent("aisad-preview-history.json")
            try JSONSerialization.data(withJSONObject: payload).write(to: file)
            history = QuotaHistory.load(from: file)
        }
        if let payload = object["limits"], !(payload is NSNull) {
            let limits = try ProviderLimitsReport.decode(JSONSerialization.data(withJSONObject: payload))
            store.limits.showPreview(report: limits, history: history,
                                     refreshing: object["limits_refreshing"] as? Bool ?? false)
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
private struct SnapshotQuotaHoverKey: EnvironmentKey {
    static let defaultValue: Double? = nil
}
private struct SnapshotChartDayKey: EnvironmentKey {
    static let defaultValue: Int? = nil
}
private struct SnapshotSpendRangeKey: EnvironmentKey {
    static let defaultValue: SpendRange? = nil
}
extension EnvironmentValues {
    /// Fraction of the pace-chart history to show as hovered in offscreen snapshots.
    var snapshotQuotaHover: Double? {
        get { self[SnapshotQuotaHoverKey.self] }
        set { self[SnapshotQuotaHoverKey.self] = newValue }
    }
    var snapshotChartDay: Int? {
        get { self[SnapshotChartDayKey.self] }
        set { self[SnapshotChartDayKey.self] = newValue }
    }
    /// The spend chart range to draw in offscreen snapshots.
    var snapshotSpendRange: SpendRange? {
        get { self[SnapshotSpendRangeKey.self] }
        set { self[SnapshotSpendRangeKey.self] = newValue }
    }
}
#endif
