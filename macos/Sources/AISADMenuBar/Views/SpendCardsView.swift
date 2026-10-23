import AISADCore
import SwiftUI

struct SpendCardsView: View {
    let report: MenuBarReport

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 6) {
                ForEach(report.periods.filter { $0.id != "month" }) { period in
                    metricCard(period).frame(width: 137)
                }
            }
            if let month = report.month { monthlyCard(month) }
        }
    }

    private func metricCard(_ period: SpendPeriod) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(period.title).font(.system(size: 10, weight: .medium)).foregroundStyle(.secondary)
            Text(period.amountText).font(.system(size: 20, weight: .semibold))
                .monospacedDigit().lineLimit(2).minimumScaleFactor(0.7)
            ViewThatFits(in: .horizontal) {
                Text(period.comparison?.text ?? "No comparison").fixedSize()
                VStack(alignment: .leading, spacing: 1) {
                    ForEach(Array((period.comparison?.text ?? "No comparison")
                        .components(separatedBy: " · ").enumerated()), id: \.offset) { _, text in
                        Text(text).lineLimit(1).minimumScaleFactor(0.75)
                    }
                }
            }
            .font(.system(size: 9)).monospacedDigit().foregroundStyle(.secondary)
            .frame(minHeight: 11, alignment: .topLeading)
            .help(period.comparison?.detail ?? "")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 8))
        .overlay {
            RoundedRectangle(cornerRadius: 8).strokeBorder(Color.primary.opacity(0.07), lineWidth: 0.5)
        }
        .accessibilityElement(children: .combine)
        .help(period.unpricedRequests > 0
              ? "\(period.unpricedRequests) unpriced observations. Known subtotal only."
              : "Estimated API-equivalent cost, not an invoice.")
    }

    private func monthlyCard(_ month: SpendPeriod) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(month.title).font(.system(size: 10, weight: .medium)).foregroundStyle(.secondary)
                    Text(month.amountText).font(.system(size: 22, weight: .semibold))
                        .monospacedDigit().lineLimit(2).minimumScaleFactor(0.65)
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
            if let history = report.monthlyHistory {
                MonthlySpendChartView(history: history, budget: month.budgetUsd)
            } else {
                Text("Chart available after refresh")
                    .font(.system(size: 10)).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 65)
            }
            TimelineView(.periodic(from: .now, by: 60)) { context in
                HStack(spacing: 3) {
                    Text(month.percentText)
                        .foregroundStyle(month.warningLevel >= 3 ? .red : .secondary)
                    if let budget = month.budgetUsd {
                        Text("of " + budget.formatted(.currency(code: "USD")
                            .locale(Locale(identifier: "en_US")).precision(.fractionLength(0...2))))
                    }
                    Spacer(minLength: 4)
                    Text(resetText(month, at: context.date))
                }
                .font(.system(size: 9)).monospacedDigit().foregroundStyle(.secondary)
            }
            .help("Monthly API-equivalent budget. Resets " +
                  month.resetsAt.formatted(date: .abbreviated, time: .shortened))
            if month.unpricedRequests > 0 {
                Text("\(month.unpricedRequests) unpriced · " +
                     (month.hasPricedData ? "known subtotal" : "cost unavailable"))
                    .font(.system(size: 9)).foregroundStyle(.secondary)
            } else if report.monthlyHistory?.hasIncompletePrices == true {
                Text("Some chart prices are incomplete")
                    .font(.system(size: 9)).foregroundStyle(.secondary)
            }
        }
        .padding(10)
        .background(Color.blue.opacity(0.04), in: RoundedRectangle(cornerRadius: 9))
        .overlay {
            RoundedRectangle(cornerRadius: 9).strokeBorder(Color.primary.opacity(0.08), lineWidth: 0.5)
        }
    }

    private func resetText(_ period: SpendPeriod, at now: Date) -> String {
        let seconds = period.resetsAt.timeIntervalSince(now)
        guard seconds > 0 else { return "reset pending" }
        let unit: (TimeInterval, String) = seconds >= 86_400 ? (86_400, "d") :
            seconds >= 3_600 ? (3_600, "h") : (60, "m")
        return "resets " + String(Int(ceil(seconds / unit.0))) + unit.1
    }
}
