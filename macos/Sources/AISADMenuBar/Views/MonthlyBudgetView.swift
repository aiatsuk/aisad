import AISADCore
import SwiftUI

struct MonthlyBudgetView: View {
    let period: SpendPeriod

    private var tint: Color {
        switch period.warningLevel {
        case 3: .red
        case 1, 2: .orange
        default: .accentColor
        }
    }

    var body: some View {
        if let budget = period.budgetUsd {
            VStack(alignment: .leading, spacing: 4) {
                TimelineView(.periodic(from: .now, by: 60)) { context in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text("Limit " + budget.formatted(
                            .currency(code: "USD").locale(Locale(identifier: "en_US"))
                                .precision(.fractionLength(0...2))))
                        Spacer(minLength: 4)
                        HStack(spacing: 3) {
                            Text(period.percentText)
                                .foregroundStyle(period.warningLevel >= 3 ? .red : .secondary)
                            Text("· " + resetText(at: context.date))
                        }
                        .fixedSize()
                    }
                    .font(.caption2)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
                }
                Gauge(value: period.progress) { EmptyView() }
                    .gaugeStyle(BudgetGaugeStyle(tint: tint))
                    .accessibilityLabel("Monthly budget")
                    .accessibilityValue(period.amountText + " of " + SpendPeriod.dollars(budget) +
                                        ", " + period.percentText)
            }
            .help((period.warningLevel >= 3 ? "Monthly limit reached. " : "") +
                  "Resets " + period.resetsAt.formatted(date: .abbreviated, time: .shortened))
        }
    }

    private func resetText(at now: Date) -> String {
        let seconds = period.resetsAt.timeIntervalSince(now)
        guard seconds > 0 else { return "reset pending" }
        let unit: (TimeInterval, String) = seconds >= 86_400 ? (86_400, "d") :
            seconds >= 3_600 ? (3_600, "h") : (60, "m")
        return "resets " + String(Int(ceil(seconds / unit.0))) + unit.1
    }
}

private struct BudgetGaugeStyle: GaugeStyle {
    let tint: Color

    func makeBody(configuration: Configuration) -> some View {
        GeometryReader { geometry in
            Capsule()
                .fill(.quaternary)
                .overlay(alignment: .leading) {
                    Capsule()
                        .fill(tint)
                        .frame(width: geometry.size.width * configuration.value)
                }
                .overlay {
                    Capsule().strokeBorder(.primary.opacity(0.08), lineWidth: 0.5)
                }
        }
        .frame(height: 6)
    }
}
