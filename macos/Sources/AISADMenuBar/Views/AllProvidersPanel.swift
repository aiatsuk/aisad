import AISADCore
import SwiftUI

/// Every provider's windows in one place; shared with offscreen snapshots.
struct AllProvidersPanel: View {
    let store: ProviderLimitsStore

    var body: some View {
        TimelineView(.periodic(from: .now, by: 30)) { context in
            VStack(alignment: .leading, spacing: 16) {
                ForEach(QuotaProvider.allCases) { kind in
                    section(kind, provider: store.providers.first { $0.id == kind.id }, now: context.date)
                    if kind != QuotaProvider.allCases.last { Theme.line.frame(height: 1) }
                }
            }
            .padding(16)
            .frame(width: 296)
        }
    }

    private func section(_ kind: QuotaProvider, provider: ProviderQuota?, now: Date) -> some View {
        let fresh = provider?.status == "available"
        return VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                ProviderMark(kind: kind)
                Text(provider?.name ?? kind.fullTitle).font(.system(size: 13, weight: .semibold))
                if let plan = provider?.plan, !plan.isEmpty { PlanBadge(plan: plan) }
                Spacer(minLength: 6)
                if store.isRefreshing, provider == nil {
                    ProgressView().controlSize(.mini)
                } else if let provider {
                    Text(freshness(provider, now: now))
                        .font(.system(size: 10))
                        .foregroundStyle(!provider.windows.isEmpty && !fresh ? .orange : .secondary)
                        .help(provider.source + "\n" + provider.fetchedAt.formatted())
                }
            }
            if let provider, !provider.windows.isEmpty {
                ForEach(provider.displayWindows) { window in
                    QuotaWindowRow(window: window, now: now, fresh: fresh)
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

    private func freshness(_ provider: ProviderQuota, now: Date) -> String {
        guard !provider.windows.isEmpty else { return "Not connected" }
        let age = provider.fetchedAt.ageText(now: now)
        return (provider.status == "available" ? "Updated " : "Last reading ") + age
    }
}
