import AISADCore
import Charts
import SwiftUI

/// Cumulative spend of one range against the range before it.
struct SpendChartView: View {
    let chart: SpendChart
    let budget: Double?
    @State private var hovered: Int?
    @State private var keyboard: Int?
    @FocusState private var focused: Bool

    #if DEBUG
    @Environment(\.snapshotChartDay) private var snapshotDay
    #endif

    private var selected: Int? {
        #if DEBUG
        hovered ?? keyboard ?? snapshotDay.map { min(chart.positions.upperBound, max(chart.positions.lowerBound, $0)) }
        #else
        hovered ?? keyboard
        #endif
    }
    private var upperBound: Double { chart.upperBound(budget: budget) }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 8) {
                HStack(spacing: 8) {
                    ForEach(chart.curves) { curve in
                        HStack(spacing: 4) {
                            Path { path in
                                path.move(to: CGPoint(x: 1, y: 1))
                                path.addLine(to: CGPoint(x: 10, y: 1))
                            }
                            .stroke(tint(curve.id), style: StrokeStyle(
                                lineWidth: curve.id == .previous ? 1.5 : 2, lineCap: .round,
                                dash: curve.id == .previous ? [3, 3] : []))
                            .frame(width: 11, height: 2)
                            // While inspecting, the value replaces the name to keep the row short.
                            Text(selected.map(curve.detail(position:)) ?? curve.title).monospacedDigit()
                        }
                        .help(curve.span ?? "")
                    }
                }
                .lineLimit(1)
                Spacer(minLength: 4)
                Text(selected.map(chart.selectionTitle(position:)) ?? "Cumulative")
                    .monospacedDigit()
                    .fixedSize()
            }
            .font(.system(size: 10)).foregroundStyle(.secondary)
            .frame(height: 12)
            if chart.points.isEmpty {
                Text(chart.untimedObservations > 0 ? "These readings have no usable time" :
                     chart.hasIncompletePrices ? "Prices unavailable for this range" : "No usage recorded in either range")
                    .font(.system(size: 10)).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 72)
            } else {
                // The top axis label is centered on its line, so it needs the legend clear of it.
                plot.frame(height: 68).padding(.top, 4)
                    .focusable().focusEffectDisabled().focused($focused)
                    .onTapGesture {
                        focused = true
                        keyboard = hovered ?? chart.latestPosition
                    }
                    .onMoveCommand { direction in
                        let position = selected ?? chart.latestPosition
                        switch direction {
                        case .left: keyboard = max(chart.positions.lowerBound, position - 1)
                        case .right: keyboard = min(chart.positions.upperBound, position + 1)
                        default: return
                        }
                        hovered = nil
                    }
                    .onExitCommand { hovered = nil; keyboard = nil; focused = false }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Cumulative API-equivalent spend")
        .accessibilityHint("Select a point with the pointer or left and right arrow keys. Escape clears the selection.")
        .help("Claude + Codex known cumulative cost. Solid: current range through collection time. " +
              "Dashed: the range before it. The latest amount is partial. " +
              "Current chart and amount use the same collection.")
    }

    private var plot: some View {
        Chart {
            ForEach(chart.points) { point in
                LineMark(x: .value("Position", point.plotX), y: .value("USD", point.cost),
                         series: .value("Segment", point.segment))
                    .foregroundStyle(tint(point.period))
                    .lineStyle(StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round,
                                           dash: point.period == .previous ? [3, 1.5] : []))
                    .interpolationMethod(.linear)
                    .accessibilityLabel((point.period == .current ? "Current" : "Previous") +
                                        ", " + chart.selectionTitle(position: point.position))
                    .accessibilityValue(point.amountText)
                if point.position == selected || point.showsMarker {
                    PointMark(x: .value("Position", point.plotX), y: .value("USD", point.cost))
                        .foregroundStyle(tint(point.period))
                        .symbolSize(point.position == selected ? 22 : 10)
                        .accessibilityHidden(true)
                }
            }
            if let budget {
                RuleMark(y: .value("Monthly budget", budget))
                    .foregroundStyle(Theme.quaternary)
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [2.75, 2]))
                    .annotation(position: .top, alignment: .leading, spacing: 1) {
                        Text("Limit " + budget.formatted(.currency(code: "USD")
                            .locale(Locale(identifier: "en_US")).precision(.fractionLength(0...2))))
                            .font(.system(size: 10)).foregroundStyle(.secondary)
                    }
                    .accessibilityLabel("Monthly budget")
                    .accessibilityValue(SpendPeriod.dollars(budget))
            }
            if let selected {
                RuleMark(x: .value("Selected", Double(selected)))
                    .foregroundStyle(Color.secondary.opacity(0.4))
                    .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [2, 2]))
                    .accessibilityHidden(true)
            }
        }
        .chartLegend(.hidden)
        .chartXScale(domain: chart.domain)
        .chartYScale(domain: 0...upperBound)
        .chartXAxis {
            AxisMarks(values: chart.axisLabels.map(\.position)) { value in
                AxisValueLabel(anchor: anchor(value.as(Double.self)), collisionResolution: .disabled) {
                    if let position = value.as(Double.self),
                       let label = chart.axisLabels.first(where: { $0.position == position }) {
                        Text(label.text).font(.system(size: 10))
                    }
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: .trailing, values: [0, upperBound]) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5)).foregroundStyle(Theme.hairline)
                AxisValueLabel {
                    if let amount = value.as(Double.self) {
                        Text(amount.formatted(.currency(code: "USD").locale(Locale(identifier: "en_US"))
                            .precision(.fractionLength(upperBound < 1 ? 2 : 0))))
                            .font(.system(size: 10)).monospacedDigit()
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
                                hovered = nil
                                return
                            }
                            let position = min(chart.positions.upperBound,
                                               max(chart.positions.lowerBound, Int(value.rounded())))
                            if hovered != position { hovered = position }
                        case .ended: hovered = nil
                        }
                    }
            }
        }
    }

    /// Labels at the very edge of the plot stay inside it.
    private func anchor(_ position: Double?) -> UnitPoint {
        if position == chart.domain.lowerBound { return .topLeading }
        if position == chart.domain.upperBound { return .topTrailing }
        return .top
    }

    private func tint(_ period: SpendChart.Period) -> Color {
        period == .current ? Theme.blue : .secondary
    }
}
