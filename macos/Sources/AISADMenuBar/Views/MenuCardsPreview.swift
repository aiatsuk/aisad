#if DEBUG
import AISADCore
import SwiftUI

/// Isolated native layout alternatives. Normal startup never constructs this view.
struct MenuCardsPreview: View {
    enum Style: String, CaseIterable, Identifiable {
        case cards, compact, cumulative
        var id: String { rawValue }
        var width: CGFloat { self == .compact ? 280 : 300 }
        var title: String {
            switch self {
            case .cards: "A · Cards · 300 pt"
            case .compact: "B · Compact · 280 pt"
            case .cumulative: "C · Cumulative · 300 pt"
            }
        }
        static var fromArguments: Self? {
            let args = CommandLine.arguments
            guard let index = args.firstIndex(of: "--card-layout"),
                  args.indices.contains(index + 1) else { return nil }
            return Self(rawValue: args[index + 1])
        }
    }

    let store: UsageStore
    let chart: MonthlyChartPreview
    let style: Style

    private var compact: Bool { style == .compact }
    private var inset: CGFloat { compact ? 8 : 10 }

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 7 : 8) {
            header
            if let report = store.report {
                HStack(alignment: .top, spacing: 6) {
                    ForEach(report.periods.filter { $0.id != "month" }) { period in
                        metricCard(period)
                            .frame(width: (style.width - 26) / 2)
                    }
                }
                if let month = report.month { monthlyCard(month) }
            }
            if let error = store.error ?? store.dashboardError {
                HStack(alignment: .top, spacing: 5) {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundStyle(.red)
                    Text("Update failed · " + error.replacingOccurrences(of: "Error: ", with: ""))
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .font(.system(size: 9.5))
                .help(error)
                .accessibilityLabel("Update failed. Showing last known values. " + error)
            }
            ProviderLimitsView(store: store.limits)
                .padding(.horizontal, 2)
                .padding(.vertical, compact ? 1 : 3)
            Divider()
            footer
        }
        .padding(.horizontal, 10)
        .padding(.top, 8)
        .padding(.bottom, 6)
        .frame(width: style.width)
        .buttonStyle(.plain)
    }

    private var header: some View {
        HStack {
            Text("AISAD").font(.system(size: 12, weight: .semibold))
            Spacer()
            Button { store.openDashboard() } label: {
                HStack(spacing: 4) {
                    Text("Dashboard")
                    Image(systemName: "arrow.up.right.square")
                }
                    .font(.system(size: 10.5, weight: .medium))
                    .padding(.horizontal, 7).padding(.vertical, 4)
                    .background(.quaternary, in: Capsule())
            }
            .accessibilityLabel("Open dashboard")
        }
        .padding(.bottom, 1)
    }

    private func metricCard(_ period: SpendPeriod) -> some View {
        VStack(alignment: .leading, spacing: compact ? 3 : 4) {
            Text(period.title)
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(.secondary)
            Text(period.amountText)
                .font(.system(size: compact ? 18 : 20, weight: .semibold))
                .monospacedDigit()
                .lineLimit(1).minimumScaleFactor(0.7)
            ViewThatFits(in: .horizontal) {
                Text(period.comparison?.text ?? "No comparison")
                    .fixedSize(horizontal: true, vertical: false)
                VStack(alignment: .leading, spacing: 1) {
                    ForEach(Array((period.comparison?.text ?? "No comparison")
                        .components(separatedBy: " · ").enumerated()), id: \.offset) { _, text in
                        Text(text).lineLimit(1).minimumScaleFactor(0.75)
                    }
                }
            }
            .font(.system(size: 9)).monospacedDigit()
            .foregroundStyle(.secondary)
            .frame(minHeight: 11, alignment: .topLeading)
            .help(period.comparison?.detail ?? "")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(inset)
        .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 8))
        .overlay {
            if !compact {
                RoundedRectangle(cornerRadius: 8)
                    .strokeBorder(Color.primary.opacity(0.07), lineWidth: 0.5)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func monthlyCard(_ month: SpendPeriod) -> some View {
        VStack(alignment: .leading, spacing: compact ? 5 : 7) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(month.title)
                        .font(.system(size: 10, weight: .medium)).foregroundStyle(.secondary)
                    Text(month.amountText)
                        .font(.system(size: compact ? 20 : 22, weight: .semibold))
                        .monospacedDigit().lineLimit(1).minimumScaleFactor(0.65)
                }
                Spacer(minLength: 4)
                if let comparison = month.comparison {
                    VStack(alignment: .trailing, spacing: 3) {
                        ForEach(Array(comparison.text.components(separatedBy: " · ").enumerated()), id: \.offset) { _, text in
                            Text(text).font(.system(size: 9.5)).monospacedDigit()
                        }
                    }
                    .foregroundStyle(.secondary)
                    .help(comparison.detail)
                    .accessibilityLabel("Change from previous month: " + comparison.text)
                }
            }
            MonthlySpendChartPreview(preview: chart, showPricingNote: false, cumulative: style == .cumulative,
                                     budget: month.budgetUsd, height: compact ? 57 : 65)
            if style == .cumulative {
                HStack(spacing: 3) {
                    Text(month.percentText)
                        .foregroundStyle(month.warningLevel >= 3 ? .red : .secondary)
                    if let budget = month.budgetUsd {
                        Text("of " + budget.formatted(.currency(code: "USD")
                            .locale(Locale(identifier: "en_US")).precision(.fractionLength(0))))
                    }
                    Spacer(minLength: 4)
                    Text(resetText(month))
                }
                .font(.system(size: 9)).monospacedDigit().foregroundStyle(.secondary)
            } else {
                BudgetAxisPreview(period: month, reset: resetText(month))
            }
            if month.unpricedRequests > 0 {
                Text("\(month.unpricedRequests) unpriced · " +
                     (month.hasPricedData ? "known subtotal" : "cost unavailable"))
                    .font(.system(size: 9)).foregroundStyle(.secondary)
            } else if chart.hasPartialDays || chart.hasUnpricedDays {
                Text("Some chart prices are incomplete")
                    .font(.system(size: 9)).foregroundStyle(.secondary)
            }
        }
        .padding(inset)
        .background((style == .cumulative ? Color.blue : Color.primary)
            .opacity(style == .cumulative ? 0.04 : 0.025), in: RoundedRectangle(cornerRadius: 9))
        .overlay {
            RoundedRectangle(cornerRadius: 9)
                .strokeBorder(Color.primary.opacity(0.08), lineWidth: 0.5)
        }
    }

    private func resetText(_ period: SpendPeriod) -> String {
        let seconds = period.resetsAt.timeIntervalSinceNow
        guard seconds > 0 else { return "reset pending" }
        return "resets " + String(Int(ceil(seconds / 86_400))) + "d"
    }

    private var footer: some View {
        HStack(spacing: 10) {
            Button {
                store.refreshNow()
                store.limits.refreshNow()
            } label: {
                if store.isRefreshing {
                    Label("Updating…", systemImage: "arrow.clockwise")
                } else {
                    Label(store.report?.generated.formatted(.relative(
                        presentation: .named, unitsStyle: .abbreviated)) ?? "Refresh",
                          systemImage: "arrow.clockwise")
                }
            }
            .accessibilityLabel("Refresh usage and provider limits")
            Spacer(minLength: 4)
            SettingsLink { Label("Budget", systemImage: "gearshape") }
            Button("Quit") { NSApp.terminate(nil) }
        }
        .font(.system(size: 10)).foregroundStyle(.secondary)
        .frame(minHeight: 20)
    }
}

private struct BudgetAxisPreview: View {
    let period: SpendPeriod
    let reset: String

    var body: some View {
        if let budget = period.budgetUsd {
            let maximum = max(budget, period.hasPricedData ? period.knownCostUsd : budget)
            let budgetFraction = budget / maximum
            let spentFraction = min(1, period.knownCostUsd / maximum)
            VStack(spacing: 3) {
                HStack(spacing: 3) {
                    Text("Budget")
                    Spacer()
                    Text(period.percentText)
                        .foregroundStyle(period.warningLevel >= 3 ? .red : .secondary)
                    Text("· " + reset)
                }
                .font(.system(size: 9)).monospacedDigit().foregroundStyle(.secondary)
                GeometryReader { geometry in
                    let width = geometry.size.width
                    ZStack(alignment: .leading) {
                        Capsule().fill(.quaternary).frame(height: 3)
                        if period.hasPricedData {
                            Capsule().fill(Color.blue).frame(width: width * spentFraction, height: 3)
                            if period.knownCostUsd > budget {
                                Rectangle().fill(Color.red.opacity(0.8))
                                    .frame(width: width * (spentFraction - budgetFraction), height: 3)
                                    .offset(x: width * budgetFraction)
                            }
                            Circle().fill(period.knownCostUsd > budget ? Color.red : Color.blue)
                                .frame(width: 4, height: 4)
                                .offset(x: min(width - 4, max(0, width * spentFraction - 2)))
                        }
                        Rectangle().fill(.secondary)
                            .frame(width: 1, height: 8)
                            .offset(x: min(width - 1, width * budgetFraction))
                    }
                    .frame(height: 8)
                    .accessibilityHidden(true)
                }
                .frame(height: 8)
                GeometryReader { geometry in
                    if budgetFraction > 0.35 {
                        Text("$0").position(x: 6, y: 5)
                    }
                    Text("Limit " + budget.formatted(.currency(code: "USD")
                        .locale(Locale(identifier: "en_US")).precision(.fractionLength(0))))
                        .fixedSize()
                        .position(x: min(geometry.size.width - 33,
                                         max(36, geometry.size.width * budgetFraction)), y: 5)
                }
                .font(.system(size: 8.5)).foregroundStyle(.secondary)
                .frame(height: 12)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Monthly budget")
            .accessibilityValue(period.amountText + " of " + SpendPeriod.dollars(budget) + ", " + period.percentText)
            .help("USD scale. The tick marks the monthly budget; the dot marks current known spend. " + reset)
        }
    }
}

struct MenuCardsComparisonPreview: View {
    let store: UsageStore
    let chart: MonthlyChartPreview

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            ForEach(MenuCardsPreview.Style.allCases) { style in
                VStack(alignment: .leading, spacing: 10) {
                    Text(style.title).font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.secondary)
                    MenuCardsPreview(store: store, chart: chart, style: style)
                        .background(.background, in: RoundedRectangle(cornerRadius: 12))
                        .overlay {
                            RoundedRectangle(cornerRadius: 12)
                                .strokeBorder(.separator, lineWidth: 0.5)
                        }
                }
            }
        }
        .padding(16)
    }
}
#endif
