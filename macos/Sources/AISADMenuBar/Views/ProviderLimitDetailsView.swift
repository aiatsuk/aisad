import AISADCore
import SwiftUI

/// Content shared by the native popover and offscreen layout verification.
struct ProviderLimitDetailsView: View {
    let kind: QuotaProvider
    let provider: ProviderQuota?
    let refreshing: Bool
    let retryAt: Date?
    let error: String?

    var body: some View {
        TimelineView(.periodic(from: .now, by: 30)) { context in
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .firstTextBaseline) {
                    Text(provider?.name ?? kind.fullTitle).font(.callout.weight(.semibold))
                    Spacer(minLength: 8)
                    if let plan = provider?.plan {
                        Text(plan).font(.caption).foregroundStyle(.secondary)
                    }
                }
                if let provider, !provider.windows.isEmpty {
                    if provider.windows.count > 8 {
                        ScrollView { windows(provider, now: context.date) }.frame(height: 240)
                    } else {
                        windows(provider, now: context.date)
                    }
                    if let message = provider.message ?? error {
                        Text(message).font(.caption).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    } else if provider.status != "available" {
                        Text("Showing the last known reading.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                } else {
                    HStack(spacing: 8) {
                        if refreshing { ProgressView().controlSize(.mini) }
                        Text(provider?.message ?? error ??
                             (refreshing ? "Reading plan limits…" : "No reading yet. Use Refresh to collect limits."))
                            .font(.caption).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                if provider?.status == "rate_limited", let retryAt, retryAt > context.date {
                    Text("Refresh available " + retryAt.formatted(
                        .relative(presentation: .named, unitsStyle: .abbreviated)))
                        .font(.caption2).foregroundStyle(.secondary)
                }
                if let provider {
                    Divider()
                    HStack(spacing: 6) {
                        Text(freshness(provider))
                            .font(.caption2).foregroundStyle(.secondary)
                        Spacer(minLength: 0)
                        if refreshing, !provider.windows.isEmpty {
                            ProgressView().controlSize(.mini)
                                .accessibilityLabel("Updating limits")
                        }
                    }
                    .help(provider.source + "\n" + provider.fetchedAt.formatted())
                }
            }
            .padding(14)
            .frame(width: 304)
        }
    }

    private func windows(_ provider: ProviderQuota, now: Date) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(provider.displayWindows) { window in
                QuotaDetailRow(window: window, fresh: provider.status == "available", now: now)
            }
        }
    }

    private func freshness(_ provider: ProviderQuota) -> String {
        let prefix = provider.windows.isEmpty ? "Checked " :
            provider.status == "available" ? "Updated " : "Last known · "
        return prefix + provider.fetchedAt.formatted(
            .relative(presentation: .named, unitsStyle: .abbreviated))
    }
}

private struct QuotaDetailRow: View {
    let window: QuotaWindow
    let fresh: Bool
    let now: Date

    private var expired: Bool { window.isExpired(at: now) }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 4) {
            Text(window.title)
                .font(.caption)
                .lineLimit(2)
                .help(window.title)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            Text(expired ? "Reset passed" : window.remainingText)
                .font(.caption.weight(.medium))
                .foregroundStyle(QuotaAppearance.tint(remaining: window.remainingPercent,
                                                       fresh: fresh && !expired))
                .fixedSize()
            if !expired {
                Text("· " + resetText)
                    .font(.caption2).foregroundStyle(.secondary)
                    .fixedSize()
            }
        }
        .monospacedDigit()
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(window.title)
        .accessibilityValue((fresh ? "" : "Last known: ") +
            (expired ? "Reset has passed; refresh needed" : window.remainingText) +
            (window.resetsAt.map { ". Resets " + $0.formatted() } ?? ". Reset time unknown"))
        .help(window.resetsAt.map { "Resets " + $0.formatted() } ?? "Reset time was not reported")
    }

    private var resetText: String { window.resetText(now: now) }
}

extension QuotaWindow {
    /// "resets in 2h 10m" within a day, a weekday within a week, else a date.
    func resetText(now: Date) -> String {
        guard let reset = resetsAt else { return "reset unknown" }
        let seconds = reset.timeIntervalSince(now)
        if seconds <= 0 { return "reset passed" }
        if seconds < 86_400 {
            let minutes = Int((seconds / 60).rounded(.up))
            return "resets in " + (minutes >= 60 ? "\(minutes / 60)h \(minutes % 60)m" : "\(minutes)m")
        }
        if reset.timeIntervalSince(now) < 7 * 86400 {
            return "resets " + reset.formatted(.dateTime.weekday(.abbreviated).hour().minute())
        }
        return "resets " + reset.formatted(.dateTime.month(.abbreviated).day().hour().minute())
    }
}
