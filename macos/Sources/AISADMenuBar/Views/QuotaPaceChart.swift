import AISADCore
import Charts
import SwiftUI

/// Remaining allowance across the current window: readings this app fetched,
/// the even-pace line and a linear projection to exhaustion or reset.
struct QuotaPaceChart: View {
    struct Point: Identifiable, Equatable {
        let at: Date
        let remaining: Double
        var id: Date { at }
    }

    let pace: QuotaPace
    let points: [Point]
    let tint: Color
    let now: Date
    @Binding var selection: Point?

    private static let dotted = StrokeStyle(lineWidth: 1.5, lineCap: .round, dash: [0.1, 2.9])

    private var current: Point { points.last ?? Point(at: now, remaining: pace.remainingPercent) }

    private var projectionEnd: Point {
        if let runsOut = pace.runsOut { return Point(at: runsOut, remaining: 0) }
        let elapsed = now.timeIntervalSince(pace.start)
        let rate = elapsed > 0 ? (100 - pace.remainingPercent) / elapsed : 0
        return Point(at: pace.end, remaining: max(0, pace.remainingPercent - rate * pace.end.timeIntervalSince(now)))
    }

    /// Equal columns across the whole window: a day each for multi-day windows,
    /// else quarters. Grid lines sit on the boundaries, the reset included, so
    /// every stretch a line crosses is labelled.
    private var columns: (step: TimeInterval, count: Int) {
        let duration = pace.end.timeIntervalSince(pace.start)
        guard duration >= 2 * 86_400 else { return (duration / 4, 4) }
        let count = Int((duration / 86_400).rounded())
        return (duration / Double(count), count)
    }

    private var boundaries: [Date] {
        (0...columns.count).map { pace.start.addingTimeInterval(Double($0) * columns.step) }
    }

    private var labelCenters: [Date] {
        (0..<columns.count).map { pace.start.addingTimeInterval((Double($0) + 0.5) * columns.step) }
    }

    private var labelFormat: Date.FormatStyle {
        columns.step >= 86_400 ? .dateTime.weekday(.abbreviated) : .dateTime.hour()
    }

    var body: some View {
        Chart {
            LineMark(x: .value("Time", pace.start), y: .value("Remaining", 100), series: .value("Series", "even"))
                .foregroundStyle(Theme.tertiary)
                .lineStyle(Self.dotted)
            LineMark(x: .value("Time", pace.end), y: .value("Remaining", 0), series: .value("Series", "even"))
                .foregroundStyle(Theme.tertiary)
                .lineStyle(Self.dotted)

            ForEach(points) { point in
                AreaMark(x: .value("Time", point.at), y: .value("Remaining", point.remaining))
                    .foregroundStyle(LinearGradient(colors: [tint.opacity(0.22), tint.opacity(0.02)],
                                                    startPoint: .top, endPoint: .bottom))
                    .interpolationMethod(.linear)
                LineMark(x: .value("Time", point.at), y: .value("Remaining", point.remaining),
                         series: .value("Series", "you"))
                    .foregroundStyle(tint)
                    .lineStyle(StrokeStyle(lineWidth: 1.7, lineCap: .round, lineJoin: .round))
                    .interpolationMethod(.linear)
            }

            if pace.hasUsage {
                LineMark(x: .value("Time", current.at), y: .value("Remaining", current.remaining),
                         series: .value("Series", "projection"))
                    .foregroundStyle(tint)
                    .lineStyle(Self.dotted)
                LineMark(x: .value("Time", projectionEnd.at), y: .value("Remaining", projectionEnd.remaining),
                         series: .value("Series", "projection"))
                    .foregroundStyle(tint)
                    .lineStyle(Self.dotted)
                if pace.runsOut != nil {
                    PointMark(x: .value("Time", projectionEnd.at), y: .value("Remaining", 0))
                        .symbol { Circle().strokeBorder(tint, lineWidth: 1.2).frame(width: 6, height: 6) }
                }
            }

            PointMark(x: .value("Time", current.at), y: .value("Remaining", current.remaining))
                .symbol { Circle().fill(tint).frame(width: 7, height: 7) }

            if let selection {
                RuleMark(x: .value("Time", selection.at))
                    .foregroundStyle(Color.primary.opacity(0.35))
                    .lineStyle(StrokeStyle(lineWidth: 1))
                PointMark(x: .value("Time", selection.at), y: .value("Remaining", selection.remaining))
                    .symbol { Circle().fill(Color(nsColor: .windowBackgroundColor)).overlay(Circle().stroke(tint, lineWidth: 1.5))
                        .frame(width: 7, height: 7) }
            }
        }
        // Inset both axes so strokes and point marks at 0%, 100% and the window
        // edges stay inside the plot, then clip anything that would still escape.
        .chartXScale(domain: pace.start...pace.end, range: .plotDimension(startPadding: 4, endPadding: 4))
        .chartYScale(domain: 0...100, range: .plotDimension(startPadding: 5, endPadding: 5))
        .chartPlotStyle { $0.clipped() }
        .chartYAxis(.hidden)
        .chartXAxis {
            AxisMarks(values: boundaries) { _ in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5)).foregroundStyle(Theme.hairline)
            }
            AxisMarks(values: labelCenters) { value in
                AxisValueLabel(anchor: .top) {
                    if let date = value.as(Date.self) {
                        // A day column is named after the day most of it covers.
                        Text(columns.step >= 86_400 ? date : date.addingTimeInterval(-columns.step / 2),
                             format: labelFormat)
                            .font(.system(size: 10)).foregroundStyle(.secondary)
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
                            guard let frame = proxy.plotFrame.map({ geometry[$0] }),
                                  let date: Date = proxy.value(atX: location.x - frame.origin.x) else { return }
                            selection = points.min { abs($0.at.timeIntervalSince(date)) < abs($1.at.timeIntervalSince(date)) }
                        case .ended:
                            selection = nil
                        }
                    }
            }
        }
        .accessibilityLabel("Remaining allowance this window")
        .accessibilityValue(pace.paceText)
    }
}

struct QuotaChartLegend: View {
    let tint: Color
    let showsProjection: Bool

    var body: some View {
        HStack(spacing: 16) {
            item("You") { Capsule().fill(tint).frame(width: 10, height: 2) }
            item("Even pace") { dots(Theme.tertiary) }
            if showsProjection { item("Projection") { dots(tint) } }
            Spacer(minLength: 0)
        }
        .font(.system(size: 10))
        .foregroundStyle(.secondary)
    }

    private func dots(_ color: Color) -> some View {
        HStack(spacing: 1.5) { ForEach(0..<3, id: \.self) { _ in Circle().fill(color).frame(width: 1.5, height: 1.5) } }
            .frame(width: 10)
    }

    private func item<Mark: View>(_ title: String, @ViewBuilder mark: () -> Mark) -> some View {
        HStack(spacing: 4) { mark(); Text(title) }
    }
}
