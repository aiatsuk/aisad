import AISADCore
import SwiftUI

/// The selected provider's headline allowance: pace, projection and its other windows.
struct QuotaOverviewView: View {
    let kind: QuotaProvider
    let provider: ProviderQuota?
    let history: QuotaHistory
    let refreshing: Bool
    let now: Date
    @State private var selection: QuotaPaceChart.Point?
    #if DEBUG
    @Environment(\.snapshotQuotaHover) private var snapshotHover
    #endif

    private var window: QuotaWindow? { provider?.primaryWindow(at: now) }
    private var fresh: Bool { provider?.status == "available" }
    private var pace: QuotaPace? { window.flatMap { QuotaPace(window: $0, at: now) } }
    private var tint: Color { QuotaPalette.tint(remaining: window?.remainingPercent, fresh: fresh) }

    private var points: [QuotaPaceChart.Point] {
        guard let provider, let window, let pace else { return [] }
        var result = history.series(provider: provider.id, window: window, at: now)
            .map { QuotaPaceChart.Point(at: $0.at, remaining: $0.remainingPercent) }
        // The window opens full; the latest reading is always the last point.
        if result.first.map({ $0.at > pace.start }) ?? true {
            result.insert(.init(at: pace.start, remaining: 100), at: 0)
        }
        let latest = QuotaPaceChart.Point(at: min(provider.fetchedAt, now), remaining: window.remainingPercent)
        if result.last?.at != latest.at { result.append(latest) }
        return result
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            header
            if let window, let pace {
                chartHero(window: window, pace: pace)
            } else {
                unavailable
            }
            let others = provider?.secondaryWindows(at: now) ?? []
            if !others.isEmpty {
                VStack(spacing: 7) {
                    ForEach(others) { QuotaWindowRow(window: $0, now: now, fresh: fresh) }
                }
                .padding(.top, 2)
            }
        }
        .onChange(of: kind) { _, _ in selection = nil }
        #if DEBUG
        .onAppear {
            if let snapshotHover, !points.isEmpty {
                selection = points[min(points.count - 1, Int(Double(points.count - 1) * snapshotHover))]
            }
        }
        #endif
    }

    private var header: some View {
        HStack(spacing: 7) {
            ProviderMark(kind: kind, size: 15)
            Text(kind.fullTitle).font(.system(size: 13, weight: .semibold))
            if let plan = provider?.plan, !plan.isEmpty {
                Text(plan).font(.system(size: 9.5, weight: .medium)).foregroundStyle(.secondary)
                    .padding(.horizontal, 5).padding(.vertical, 1.5)
                    .background(Color.primary.opacity(0.08), in: RoundedRectangle(cornerRadius: 4))
            }
            Spacer(minLength: 6)
            Text(updatedText).font(.system(size: 10)).foregroundStyle(lastKnown ? .orange : .secondary)
                .lineLimit(1)
        }
    }

    private var updatedText: String {
        if refreshing, provider == nil { return "Reading…" }
        guard let provider, !provider.windows.isEmpty else { return "" }
        if lastKnown { return "Last reading " + relative(provider.fetchedAt) }
        return now.timeIntervalSince(provider.fetchedAt) < 60 ? "Updated just now" : "Updated " + relative(provider.fetchedAt)
    }

    /// Windows kept from an earlier reading after a failed or rate-limited refresh.
    private var lastKnown: Bool {
        guard let provider else { return false }
        return provider.status != "available" && !provider.windows.isEmpty
    }

    private func relative(_ date: Date) -> String {
        date.formatted(.relative(presentation: .named, unitsStyle: .abbreviated))
    }

    private func chartHero(window: QuotaWindow, pace: QuotaPace) -> some View {
        let shown = selection
        let shownPace = shown.map { point in
            QuotaPace.at(point.at, remaining: point.remaining, start: pace.start, end: pace.end)
        }
        return VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(percent(shown?.remaining ?? window.remainingPercent))
                            .font(.system(size: 26, weight: .bold)).monospacedDigit()
                            .contentTransition(.numericText())
                        Text(window.windowName + " left").font(.system(size: 12)).foregroundStyle(.secondary)
                    }
                    HStack(spacing: 6) {
                        if let shown {
                            Text(shown.at.formatted(.dateTime.weekday(.abbreviated).hour()))
                                .foregroundStyle(.primary)
                            Text(shownPace?.text ?? "").foregroundStyle(.secondary)
                        } else {
                            Text(pace.paceText).foregroundStyle(paceColor(pace))
                            Text(projectionText(pace, short: true)).foregroundStyle(.secondary)
                        }
                    }
                    .font(.system(size: 10.5)).monospacedDigit().lineLimit(1)
                    Text(window.windowName + " " + window.resetText(now: now))
                        .font(.system(size: 9.5)).monospacedDigit().foregroundStyle(.secondary)
                        .help("Resets " + pace.end.formatted(date: .abbreviated, time: .shortened))
                }
                Spacer(minLength: 0)
            }
            QuotaPaceChart(pace: pace, points: points, tint: tint, now: now, selection: $selection)
                .frame(height: 92)
            QuotaChartLegend(tint: tint, showsProjection: pace.hasUsage)
        }
    }

    private var unavailable: some View {
        HStack {
            Text(refreshing ? "Reading limits…" : (provider?.message ?? "Limits unavailable"))
                .font(.system(size: 11)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .frame(minHeight: 40)
    }

    private func paceColor(_ pace: QuotaPace) -> Color {
        pace.standing == .behind && fresh ? QuotaPalette.low : .secondary
    }

    private func projectionText(_ pace: QuotaPace, short: Bool) -> String {
        guard pace.hasUsage else { return "Resets " + pace.end.formatted(.dateTime.weekday(.abbreviated).hour()) }
        guard let runsOut = pace.runsOut else {
            return "Lasts until reset " + pace.end.formatted(.dateTime.weekday(.abbreviated).hour())
        }
        return "Runs out " + runsOut.formatted(short ? .dateTime.weekday(.abbreviated).hour()
                                                     : .dateTime.weekday(.abbreviated).hour().minute())
    }

    private func percent(_ value: Double) -> String {
        value.rounded(.down).formatted(.number.precision(.fractionLength(0))) + "%"
    }
}

private extension QuotaPace {
    /// Pace of a past reading, for the hover readout.
    static func at(_ date: Date, remaining: Double, start: Date, end: Date) -> (text: String, delta: Double) {
        let duration = end.timeIntervalSince(start)
        let even = duration > 0 ? 100 * (1 - min(max(date.timeIntervalSince(start) / duration, 0), 1)) : 0
        let delta = remaining - even
        let amount = abs(delta).rounded().formatted(.number.precision(.fractionLength(0))) + "%"
        let text = abs(delta) < 1 ? "On pace" : amount + (delta < 0 ? " behind pace" : " ahead of pace")
        return (text, delta)
    }
}

struct QuotaWindowRow: View {
    let window: QuotaWindow
    let now: Date
    let fresh: Bool

    var body: some View {
        let expired = window.isExpired(at: now)
        let tint = QuotaPalette.tint(remaining: expired ? nil : window.remainingPercent, fresh: fresh)
        VStack(alignment: .leading, spacing: 2) {
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
                    .font(.system(size: 11)).monospacedDigit()
                    .frame(width: 36, alignment: .trailing)
            }
            Text(expired ? "Reset passed · refresh needed" : window.resetText(now: now))
                .font(.system(size: 9.5)).monospacedDigit().foregroundStyle(.secondary)
        }
        .help(window.title + (window.resetsAt.map {
            " · resets " + $0.formatted(date: .abbreviated, time: .shortened) } ?? ""))
        .accessibilityElement(children: .combine)
    }
}

/// One tile per provider; a click opens that provider's pace popover.
struct ProviderTilesView: View {
    let store: ProviderLimitsStore
    let now: Date
    @State private var presented: QuotaProvider?

    var body: some View {
        HStack(spacing: 6) {
            ForEach(QuotaProvider.allCases) { kind in
                tile(kind, provider: store.providers.first { $0.id == kind.id })
            }
        }
    }

    private func isPresented(_ kind: QuotaProvider) -> Binding<Bool> {
        Binding(get: { presented == kind }, set: { if !$0, presented == kind { presented = nil } })
    }

    private func tile(_ kind: QuotaProvider, provider: ProviderQuota?) -> some View {
        let window = provider?.primaryWindow(at: now)
        let isSelected = presented == kind
        return Button { presented = isSelected ? nil : kind } label: {
            VStack(spacing: 4) {
                ProviderRings(kind: kind, provider: provider, refreshing: store.isRefreshing, now: now)
                Text(window.map { $0.remainingPercent.rounded(.down)
                        .formatted(.number.precision(.fractionLength(0))) + "%" } ?? "—")
                    .font(.system(size: 11, weight: isSelected ? .semibold : .regular)).monospacedDigit()
                    .foregroundStyle(window == nil ? .secondary : .primary)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 6)
            .background(isSelected ? Color.primary.opacity(0.08) : .clear, in: RoundedRectangle(cornerRadius: 9))
            .contentShape(RoundedRectangle(cornerRadius: 9))
        }
        .buttonStyle(.plain)
        .focusEffectDisabled()
        .help(kind.fullTitle + " plan limits and pace")
        .accessibilityLabel(kind.fullTitle)
        .accessibilityValue(window.map { $0.remainingText } ?? "Limits unavailable")
        .accessibilityHint("Show the weekly pace chart")
        .popover(isPresented: isPresented(kind), arrowEdge: .bottom) {
            QuotaPopover(kind: kind, store: store)
        }
    }
}

/// The pace chart for one provider; shared with offscreen snapshots.
struct QuotaPopover: View {
    let kind: QuotaProvider
    let store: ProviderLimitsStore

    var body: some View {
        TimelineView(.periodic(from: .now, by: 30)) { context in
            QuotaOverviewView(kind: kind, provider: store.providers.first { $0.id == kind.id },
                              history: store.history, refreshing: store.isRefreshing, now: context.date)
        }
        .font(.system(size: 12))
        .padding(14)
        .frame(width: 300)
    }
}
