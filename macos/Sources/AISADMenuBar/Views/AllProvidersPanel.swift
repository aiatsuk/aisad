import AISADCore
import SwiftUI

/// Every provider's windows in one place; shared with offscreen snapshots.
struct AllProvidersPanel: View {
    let store: ProviderLimitsStore

    var body: some View {
        TimelineView(.periodic(from: .now, by: 30)) { context in
            VStack(alignment: .leading, spacing: 12) {
                ForEach(QuotaProvider.allCases) { kind in
                    section(kind, provider: store.providers.first { $0.id == kind.id }, now: context.date)
                    if kind != QuotaProvider.allCases.last { Divider() }
                }
            }
            .padding(14)
            .frame(width: 296)
        }
    }

    private func section(_ kind: QuotaProvider, provider: ProviderQuota?, now: Date) -> some View {
        let fresh = provider?.status == "available"
        return VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 7) {
                ProviderMark(kind: kind, size: 14)
                Text(provider?.name ?? kind.fullTitle).font(.system(size: 12.5, weight: .semibold))
                if let plan = provider?.plan, !plan.isEmpty {
                    Text(plan).font(.system(size: 9.5, weight: .medium)).foregroundStyle(.secondary)
                        .padding(.horizontal, 5).padding(.vertical, 1.5)
                        .background(Color.primary.opacity(0.08), in: RoundedRectangle(cornerRadius: 4))
                }
                Spacer(minLength: 6)
                if store.isRefreshing, provider == nil {
                    ProgressView().controlSize(.mini)
                } else if let provider {
                    Text(freshness(provider))
                        .font(.system(size: 10))
                        .foregroundStyle(!provider.windows.isEmpty && !fresh ? .orange : .secondary)
                        .help(provider.source + "\n" + provider.fetchedAt.formatted())
                }
            }
            if let provider, !provider.windows.isEmpty {
                ForEach(provider.displayWindows) { window in
                    row(window, fresh: fresh, now: now)
                }
            } else {
                Text(provider?.message ?? store.error ??
                     (store.isRefreshing ? "Reading plan limits…" : "No reading yet. Use Refresh to collect limits."))
                    .font(.system(size: 11)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if provider?.status == "rate_limited", let retryAt = store.nextRefresh(for: kind.id), retryAt > now {
                Text("Refresh available " + retryAt.formatted(.relative(presentation: .named, unitsStyle: .abbreviated)))
                    .font(.system(size: 10)).foregroundStyle(.secondary)
            }
        }
    }

    private func row(_ window: QuotaWindow, fresh: Bool, now: Date) -> some View {
        let expired = window.isExpired(at: now)
        let tint = QuotaPalette.tint(remaining: expired ? nil : window.remainingPercent, fresh: fresh)
        return VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 8) {
                Text(window.shortTitle).font(.system(size: 11)).lineLimit(1)
                Spacer(minLength: 6)
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.primary.opacity(0.1))
                    if !expired {
                        Capsule().fill(tint).frame(width: 56 * window.remainingPercent / 100)
                    }
                }
                .frame(width: 56, height: 3)
                Text(expired ? "reset" : window.remainingPercent.rounded(.down)
                        .formatted(.number.precision(.fractionLength(0))) + "%")
                    .font(.system(size: 11, weight: .medium)).monospacedDigit()
                    .frame(width: 36, alignment: .trailing)
            }
            Text(expired ? "Reset passed · refresh needed" : window.resetText(now: now))
                .font(.system(size: 9.5)).monospacedDigit().foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(window.title)
        .accessibilityValue((fresh ? "" : "Last known: ") + (expired ? "Reset has passed" : window.remainingText) +
                            ", " + window.resetText(now: now))
    }

    private func freshness(_ provider: ProviderQuota) -> String {
        guard !provider.windows.isEmpty else { return "Not connected" }
        let age = provider.fetchedAt.formatted(.relative(presentation: .named, unitsStyle: .abbreviated))
        return (provider.status == "available" ? "Updated " : "Last reading ") + age
    }
}
