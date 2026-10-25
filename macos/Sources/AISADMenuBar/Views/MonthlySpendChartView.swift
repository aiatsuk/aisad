import AISADCore
import Charts
import SwiftUI

struct MonthlySpendChartView: View {
    let history: MonthlySpendHistory
    let budget: Double?
    @State private var hoveredDay: Int?
    @State private var keyboardDay: Int?
    @FocusState private var focused: Bool

    #if DEBUG
    @Environment(\.snapshotChartDay) private var snapshotDay
    #endif

    private var selectedDay: Int? {
        #if DEBUG
        hoveredDay ?? keyboardDay ?? snapshotDay.map { min(history.dayCount, max(1, $0)) }
        #else
        hoveredDay ?? keyboardDay
        #endif
    }
    private var upperBound: Double { history.upperBound(budget: budget) }

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 4) {
                HStack(spacing: 12) {
                    ForEach(history.curves) { curve in
                        HStack(spacing: 4) {
                            Path { path in
                                path.move(to: CGPoint(x: 0, y: 1))
                                path.addLine(to: CGPoint(x: 9, y: 1))
                            }
                            .stroke(tint(curve.id), style: StrokeStyle(
                                lineWidth: 2, lineCap: .round, dash: curve.id == .previous ? [2, 2] : []))
                            .frame(width: 9, height: 2)
                            Text(curve.title)
                            if let selectedDay {
                                Text(curve.detail(day: selectedDay)).monospacedDigit()
                            }
                        }
                        .help(curve.month.from + " – " + curve.month.to)
                    }
                }
                .lineLimit(1).minimumScaleFactor(0.8)
                Spacer(minLength: 4)
                Text(selectedDay.map { "Day " + String($0) } ?? "Cumulative")
                    .fixedSize()
            }
            .font(.system(size: 9.5)).foregroundStyle(.secondary)
            if history.points.isEmpty {
                Text(history.hasIncompletePrices ? "Prices unavailable for these days" : "No usage recorded in either month")
                    .font(.system(size: 10)).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 65)
            } else {
                plot.frame(height: 65)
                    .focusable().focusEffectDisabled().focused($focused)
                    .onTapGesture {
                        focused = true
                        keyboardDay = hoveredDay ?? Int(history.asOfDate.suffix(2))
                    }
                    .onMoveCommand { direction in
                        let day = selectedDay ?? Int(history.asOfDate.suffix(2)) ?? 1
                        switch direction {
                        case .left: keyboardDay = max(1, day - 1)
                        case .right: keyboardDay = min(history.dayCount, day + 1)
                        default: return
                        }
                        hoveredDay = nil
                    }
                    .onExitCommand { hoveredDay = nil; keyboardDay = nil; focused = false }
            }
        }
        .padding(.top, 3).padding(.bottom, 2)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Monthly cumulative API-equivalent spend")
        .accessibilityHint("Select a day with the pointer or left and right arrow keys. Escape clears the selection.")
        .help("Claude + Codex known cumulative cost. Solid: current month through collection time. " +
              "Dashed: previous month, through the end of each day. Today's amount is partial. " +
              "Missing days stay empty. Current chart and amount use the same collection.")
    }

    private var plot: some View {
        Chart {
            ForEach(history.points) { point in
                LineMark(x: .value("Day", point.day), y: .value("USD", point.cost),
                         series: .value("Segment", point.segment))
                    .foregroundStyle(tint(point.period))
                    .lineStyle(StrokeStyle(lineWidth: 1.5, lineCap: .round,
                                           dash: point.period == .previous ? [3, 2] : []))
                    .interpolationMethod(.linear)
                    .accessibilityLabel((point.period == .current ? "Current month" : "Previous month") +
                                        ", day " + String(point.day))
                    .accessibilityValue(point.amountText)
                if point.day == selectedDay || point.showsMarker {
                    PointMark(x: .value("Day", point.day), y: .value("USD", point.cost))
                        .foregroundStyle(tint(point.period))
                        .symbolSize(point.day == selectedDay ? 22 : 10)
                        .accessibilityHidden(true)
                }
            }
            if let budget {
                RuleMark(y: .value("Monthly budget", budget))
                    .foregroundStyle(Color.secondary.opacity(0.7))
                    .lineStyle(StrokeStyle(lineWidth: 0.8, dash: [4, 3]))
                    .annotation(position: .top, alignment: .leading) {
                        Text("Limit " + budget.formatted(.currency(code: "USD")
                            .locale(Locale(identifier: "en_US")).precision(.fractionLength(0...2))))
                            .font(.system(size: 8.5)).foregroundStyle(.secondary)
                    }
                    .accessibilityLabel("Monthly budget")
                    .accessibilityValue(SpendPeriod.dollars(budget))
            }
            if let selectedDay {
                RuleMark(x: .value("Selected day", selectedDay))
                    .foregroundStyle(Color.secondary.opacity(0.4))
                    .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [2, 2]))
                    .accessibilityHidden(true)
            }
        }
        .chartLegend(.hidden)
        .chartXScale(domain: 0.5...(Double(history.dayCount) + 0.5))
        .chartYScale(domain: 0...upperBound)
        .chartXAxis {
            AxisMarks(values: [1, history.dayCount]) { value in
                AxisValueLabel(collisionResolution: .disabled) {
                    if let day = value.as(Int.self) { Text(String(day)).font(.system(size: 8)) }
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: .trailing, values: [0, upperBound]) { value in
                AxisGridLine().foregroundStyle(Color.secondary.opacity(0.15))
                AxisValueLabel {
                    if let amount = value.as(Double.self) {
                        Text(amount.formatted(.currency(code: "USD").locale(Locale(identifier: "en_US"))
                            .precision(.fractionLength(upperBound < 1 ? 2 : 0))))
                            .font(.system(size: 8)).monospacedDigit()
                    }
                }
            }
        }
        .chartOverlay { proxy in
            GeometryReader { geometry in
                Rectangle().fill(.clear).contentShape(Rectangle())
                    .onContinuousHover { phase in
                        switch phase {
                        case .active(let location):
                            guard let anchor = proxy.plotFrame else { return }
                            let frame = geometry[anchor]
                            guard frame.contains(location),
                                  let value: Double = proxy.value(atX: location.x - frame.minX) else {
                                hoveredDay = nil
                                return
                            }
                            let day = min(history.dayCount, max(1, Int(value.rounded())))
                            if hoveredDay != day { hoveredDay = day }
                        case .ended: hoveredDay = nil
                        }
                    }
            }
        }
    }

    private func tint(_ period: MonthlySpendHistory.Period) -> Color {
        period == .current ? .blue : .secondary
    }
}
