import AISADCore
import SwiftUI

struct SpendPeriodView: View {
    let period: SpendPeriod

    private var spendAmount: some View {
        Text(period.amountText)
            .font(.system(size: 13, weight: .semibold))
            .monospacedDigit()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(period.title).fixedSize()
                    Spacer(minLength: 4)
                    spendAmount.fixedSize(horizontal: true, vertical: false)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(period.title)
                    spendAmount
                        .frame(maxWidth: .infinity, alignment: .trailing)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if let comparison = period.comparison,
               !(period.unpricedRequests > 0 && comparison.status == "incomplete_pricing") {
                Text(comparison.text)
                    .font(.system(size: 10))
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .trailing)
                    .fixedSize(horizontal: false, vertical: true)
                    .help(comparison.detail)
                    .accessibilityLabel("Change from previous period: " + comparison.text)
                    .accessibilityHint(comparison.detail)
            }
            if period.budgetUsd != nil {
                MonthlyBudgetView(period: period)
                    .padding(.top, 3)
            }
            if period.unpricedRequests > 0 {
                Text((period.hasPricedData ? "Subtotal · " : "") +
                     "\(period.unpricedRequests) unpriced" +
                     (period.comparison?.isAvailable == false ? " · no comparison" : ""))
                    .font(.caption).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .trailing)
                    .fixedSize(horizontal: false, vertical: true)
                    .help("Unpriced usage observations: \(period.unpricedRequests). " +
                          "The amount excludes unknown costs; an exact comparison is unavailable.")
            }
        }
        .accessibilityElement(children: .combine)
    }
}
