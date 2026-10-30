import AISADCore
import SwiftUI

struct SpendCardsView: View {
    let report: MenuBarReport
    @AppStorage("spendChartRange") private var storedRange = SpendRange.week.rawValue
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    #if DEBUG
    @Environment(\.snapshotSpendRange) private var snapshotRange
    #endif

    private var range: SpendRange {
        #if DEBUG
        if let snapshotRange { return snapshotRange }
        #endif
        return SpendRange(rawValue: storedRange) ?? .week
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 8) {
                ForEach(report.periods.filter { $0.id != "month" }) { metricCard($0) }
            }
            if let period = report.period(range) { chartCard(period) }
        }
    }

    private func metricCard(_ period: SpendPeriod) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(period.title).font(.system(size: 11, weight: .medium)).foregroundStyle(.secondary)
            Text(period.compactAmountText).font(.system(size: 22, weight: .bold))
                .monospacedDigit().lineLimit(1).minimumScaleFactor(0.65)
            ViewThatFits(in: .horizontal) {
                Text(period.comparison?.text ?? "No comparison").fixedSize()
                VStack(alignment: .leading, spacing: 1) {
                    ForEach(Array((period.comparison?.text ?? "No comparison")
                        .components(separatedBy: " · ").enumerated()), id: \.offset) { _, text in
                        Text(text).lineLimit(1).minimumScaleFactor(0.75)
                    }
                }
            }
            .font(.system(size: 10)).monospacedDigit().foregroundStyle(.secondary)
            .frame(minHeight: 13, alignment: .topLeading)
            .help(period.comparison?.detail ?? "")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(8)
        .modifier(CardBackground())
        .accessibilityElement(children: .combine)
        .help((period.hasRange ? period.amountText + "\n" : "") + (period.unpricedRequests > 0
              ? "\(period.unpricedRequests) unpriced observations. Known subtotal only."
              : "Estimated API-equivalent cost, not an invoice."))
    }

    private func chartCard(_ period: SpendPeriod) -> some View {
        let chart = report.chart(range)
        return VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    rangePicker.fixedSize()
                    Text(period.compactAmountText).font(.system(size: 22, weight: .bold))
                        .monospacedDigit().lineLimit(1).minimumScaleFactor(0.65)
                        .contentTransition(.numericText(value: period.knownCostUsd))
                        .help(period.hasRange ? period.amountText : "")
                }
                .layoutPriority(1)
                Spacer(minLength: 4)
                if let comparison = period.comparison {
                    VStack(alignment: .trailing, spacing: 2) {
                        ForEach(Array(comparison.text.components(separatedBy: " · ").enumerated()), id: \.offset) { _, text in
                            Text(text).font(.system(size: 11)).monospacedDigit()
                                .contentTransition(.numericText(value: comparison.absoluteUsd ?? 0))
                        }
                    }
                    .foregroundStyle(.secondary)
                    .help(comparison.detail)
                    .accessibilityLabel("Change from previous period: " + comparison.text)
                }
            }
            Group {
                if let chart {
                    SpendChartView(chart: chart, budget: range == .month ? period.budgetUsd : nil)
                } else {
                    Text("Chart available after refresh")
                        .font(.system(size: 10)).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, minHeight: 86)
                }
            }
            .padding(.top, 4)
            // Hours, weekdays and dates are different axes, so the chart is replaced, not morphed.
            .id(range)
            .transition(.opacity)
            Spacer(minLength: 0)
            footer(period, chart: chart)
        }
        .padding(8)
        .frame(minHeight: 171, alignment: .top)
        .modifier(CardBackground())
        .animation(reduceMotion ? nil : Theme.motion, value: range)
    }

    private var rangePicker: some View {
        HStack(spacing: 2) {
            ForEach(SpendRange.allCases) { option in
                Button {
                    storedRange = option.rawValue
                    if let period = report.period(option) {
                        AccessibilityNotification.Announcement(option.title + ": " + period.compactAmountText).post()
                    }
                } label: {
                    Text(option.title).font(.system(size: 10, weight: .medium))
                        .foregroundStyle(option == range ? .primary : .secondary)
                        .frame(height: 14)
                        .padding(.horizontal, 8)
                        .background(option == range ? Theme.segmentThumb : .clear,
                                    in: RoundedRectangle(cornerRadius: 4))
                        .contentShape(RoundedRectangle(cornerRadius: 4))
                }
                .buttonStyle(.plain)
                .focusable(false)
                .accessibilityAddTraits(option == range ? .isSelected : [])
            }
        }
        .padding(2)
        .background(Theme.segmentTrack, in: RoundedRectangle(cornerRadius: 6))
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Period")
    }

    @ViewBuilder
    private func footer(_ period: SpendPeriod, chart: SpendChart?) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            if let budget = period.budgetUsd {
                TimelineView(.periodic(from: .now, by: 60)) { context in
                    HStack(spacing: 4) {
                        Text(period.percentText)
                            .fontWeight(period.warningLevel >= 3 ? .semibold : .regular)
                            .foregroundStyle(period.warningLevel >= 3 ? Theme.red : .secondary)
                        Text("of " + budget.formatted(.currency(code: "USD")
                            .locale(Locale(identifier: "en_US")).precision(.fractionLength(0...2))))
                        if let note = shortNote(period, chart: chart) { Text("· " + note) }
                        Spacer(minLength: 4)
                        Text(resetText(period, at: context.date))
                    }
                }
                .help("Monthly API-equivalent budget. Resets " +
                      period.resetsAt.formatted(date: .abbreviated, time: .shortened) +
                      (note(period, chart: chart).map { "\n" + $0 } ?? ""))
            } else if let note = note(period, chart: chart) {
                Text(note)
            }
        }
        .font(.system(size: 11)).monospacedDigit().foregroundStyle(.secondary)
        .lineLimit(1).minimumScaleFactor(0.8)
    }

    /// Shares the budget line, so the card keeps its height across ranges.
    private func shortNote(_ period: SpendPeriod, chart: SpendChart?) -> String? {
        if period.unpricedRequests > 0 { return "\(period.unpricedRequests) unpriced" }
        return chart?.hasIncompletePrices == true ? "partial prices" : nil
    }

    private func note(_ period: SpendPeriod, chart: SpendChart?) -> String? {
        if period.unpricedRequests > 0 {
            return "\(period.unpricedRequests) unpriced · " + (period.hasPricedData ? "known subtotal" : "cost unavailable")
        }
        if let untimed = chart?.untimedObservations, untimed > 0 { return "\(untimed) readings have no time" }
        return chart?.hasIncompletePrices == true ? "Some chart prices are incomplete" : nil
    }

    private func resetText(_ period: SpendPeriod, at now: Date) -> String {
        let seconds = period.resetsAt.timeIntervalSince(now)
        guard seconds > 0 else { return "reset pending" }
        let unit: (TimeInterval, String) = seconds >= 86_400 ? (86_400, "d") :
            seconds >= 3_600 ? (3_600, "h") : (60, "m")
        return "resets " + String(Int(ceil(seconds / unit.0))) + unit.1
    }
}
