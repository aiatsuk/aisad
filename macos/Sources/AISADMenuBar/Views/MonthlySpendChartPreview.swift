#if DEBUG
import Charts
import SwiftUI

/// Native chart experiment; only the offscreen snapshot path can supply data.
struct MonthlySpendChartPreview: View {
    let preview: MonthlyChartPreview
    var showPricingNote = true
    var cumulative = false
    var budget: Double? = nil
    var height: CGFloat? = nil
    @State private var hoveredDay: Int?

    private var points: [MonthlyChartPreview.Point] {
        cumulative ? preview.cumulativePoints : preview.points
    }
    private var upperBound: Double {
        guard cumulative else { return preview.upperBound }
        let peak = max(points.map(\.cost).max() ?? 0, budget ?? 0)
        guard peak > 0 else { return 1 }
        let power = pow(10, floor(log10(peak)))
        return ceil(peak / power / 0.25) * power * 0.25
    }

    private var selectedDay: Int? { hoveredDay ?? preview.selectedDay }
    private var ticks: [Int] {
        preview.compact ? [1, preview.dayCount] : [1, 8, 15, 22, preview.dayCount]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 4) {
                if preview.compact {
                    legend
                } else {
                    Text("Daily spend").font(.system(size: 10, weight: .medium))
                }
                Spacer(minLength: 4)
                Text(selectedDay.map { "Day " + String($0) } ?? (cumulative ? "Cumulative" : "USD / day"))
                    .font(.system(size: 9.5)).foregroundStyle(.secondary).fixedSize()
            }
            if points.isEmpty {
                Text(preview.hasUnpricedDays ? "Prices unavailable for these days" : "No usage recorded in either month")
                    .font(.system(size: 10)).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: preview.compact ? 44 : 68)
            } else {
                plot
                    .frame(height: height ?? (preview.compact ? 49 : 78))
            }
            if !preview.compact { legend }
            if showPricingNote && (preview.hasUnpricedDays || preview.hasPartialDays) {
                Text(preview.hasUnpricedDays ? "Unpriced days omitted · known subtotals only" : "Known subtotals · some prices are incomplete")
                    .font(.system(size: 9)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.top, 3)
        .padding(.bottom, 2)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(cumulative
            ? "Month-to-date API-equivalent cost. Current month solid; previous month dashed."
            : "Daily total API-equivalent costs. Current month solid; previous month dashed.")
        .help(cumulative
            ? "Accumulated known Claude + Codex costs from the start of each month. Today's total is partial. Missing dates remain gaps."
            : "Claude + Codex per calendar day. Solid: current month, today so far. Dashed: full previous month, aligned by day number. Missing dates remain empty.")
    }

    private var legend: some View {
        HStack(spacing: 14) {
            ForEach(preview.series) { series in
                HStack(spacing: 4) {
                    Path { path in
                        path.move(to: CGPoint(x: 0, y: 1))
                        path.addLine(to: CGPoint(x: 9, y: 1))
                    }
                    .stroke(tint(series.id), style: StrokeStyle(
                        lineWidth: 2, lineCap: .round, dash: series.id == .previous ? [2, 2] : []))
                    .frame(width: 9, height: 2)
                    Text(series.title)
                    if let selectedDay {
                        Text(cumulative
                            ? preview.cumulativeDetail(period: series.id, day: selectedDay)
                            : preview.detail(period: series.id, day: selectedDay))
                            .monospacedDigit()
                    }
                }
            }
        }
        .font(.system(size: 9.5))
        .foregroundStyle(.secondary)
    }

    private var plot: some View {
        Chart {
            ForEach(points) { point in
                LineMark(x: .value("Day", point.day), y: .value("USD", point.cost),
                         series: .value("Segment", point.segment))
                    .foregroundStyle(tint(point.period))
                    .lineStyle(StrokeStyle(lineWidth: 1.5, lineCap: .round,
                                           dash: point.period == .previous ? [3, 2] : []))
                    .interpolationMethod(.linear)
                if point.day == selectedDay || isLast(point) || isIsolated(point) {
                    PointMark(x: .value("Day", point.day), y: .value("USD", point.cost))
                        .foregroundStyle(tint(point.period))
                        .symbolSize(point.day == selectedDay ? 22 : 10)
                }
            }
            if cumulative, let budget {
                RuleMark(y: .value("Monthly budget", budget))
                    .foregroundStyle(Color.secondary.opacity(0.7))
                    .lineStyle(StrokeStyle(lineWidth: 0.8, dash: [4, 3]))
                    .annotation(position: .top, alignment: .leading) {
                        Text("Limit " + budget.formatted(.currency(code: "USD")
                            .locale(Locale(identifier: "en_US")).precision(.fractionLength(0))))
                            .font(.system(size: 8.5)).foregroundStyle(.secondary)
                    }
            }
            if let selectedDay {
                RuleMark(x: .value("Selected day", selectedDay))
                    .foregroundStyle(.secondary.opacity(0.4))
                    .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [2, 2]))
            }
        }
        .chartLegend(.hidden)
        .chartXScale(domain: 0.5...(Double(preview.dayCount) + 0.5))
        .chartYScale(domain: 0...upperBound)
        .chartXAxis {
            AxisMarks(values: ticks) { value in
                AxisValueLabel(collisionResolution: .disabled) {
                    if let day = value.as(Int.self) {
                        Text(String(day)).font(.system(size: 8))
                    }
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
                            hoveredDay = min(preview.dayCount, max(1, Int(value.rounded())))
                        case .ended: hoveredDay = nil
                        }
                    }
            }
        }
    }

    private func tint(_ period: MonthlyChartPreview.PeriodKind) -> Color {
        period == .current ? .blue : .secondary
    }
    private func isIsolated(_ point: MonthlyChartPreview.Point) -> Bool {
        points.filter { $0.segment == point.segment }.count == 1
    }
    private func isLast(_ point: MonthlyChartPreview.Point) -> Bool {
        points.last(where: { $0.period == point.period })?.day == point.day
    }
}
#endif
