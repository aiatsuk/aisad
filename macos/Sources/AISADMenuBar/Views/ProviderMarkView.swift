import AISADCore
import SwiftUI

enum QuotaPalette {
    static let healthy = Theme.green
    static let low = Theme.orange
    static let critical = Theme.red

    /// Stale or expired readings never look healthy.
    static func tint(remaining: Double?, fresh: Bool = true) -> Color {
        guard fresh, let remaining else { return .secondary }
        switch QuotaLevel(remainingPercent: remaining) {
        case .healthy: return healthy
        case .low: return low
        case .critical: return critical
        }
    }
}

/// Simple drawn marks on a 14-point grid; the app ships no third-party logos.
struct ProviderMark: View {
    let kind: QuotaProvider
    var size: CGFloat = 14

    private var scale: CGFloat { size / 14 }

    var body: some View {
        Group {
            switch kind {
            case .claude:
                Asterisk()
                    .stroke(Color(red: 0.8, green: 0.49, blue: 0.37),
                            style: StrokeStyle(lineWidth: 1.5 * scale, lineCap: .round))
            case .codex:
                Circle()
                    .fill(Color(red: 0.41, green: 0.49, blue: 0.95))
                    .overlay {
                        TerminalPrompt()
                            .stroke(.white, style: StrokeStyle(lineWidth: 1.1 * scale, lineCap: .round, lineJoin: .round))
                    }
            case .grok:
                SlashedCircle()
                    .stroke(.primary, style: StrokeStyle(lineWidth: 1.5 * scale, lineCap: .round))
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

private struct Asterisk: Shape {
    func path(in rect: CGRect) -> Path {
        let unit = rect.width / 14
        var path = Path()
        for (from, to) in [(CGPoint(x: 7, y: 1), CGPoint(x: 7, y: 13)), (CGPoint(x: 1, y: 7), CGPoint(x: 13, y: 7)),
                           (CGPoint(x: 2.8, y: 2.8), CGPoint(x: 11.2, y: 11.2)),
                           (CGPoint(x: 2.8, y: 11.2), CGPoint(x: 11.2, y: 2.8))] {
            path.move(to: CGPoint(x: from.x * unit, y: from.y * unit))
            path.addLine(to: CGPoint(x: to.x * unit, y: to.y * unit))
        }
        return path
    }
}

private struct TerminalPrompt: Shape {
    func path(in rect: CGRect) -> Path {
        let unit = rect.width / 14
        var path = Path()
        path.move(to: CGPoint(x: 4.2 * unit, y: 5 * unit))
        path.addLine(to: CGPoint(x: 6.2 * unit, y: 7 * unit))
        path.addLine(to: CGPoint(x: 4.2 * unit, y: 9 * unit))
        path.move(to: CGPoint(x: 7.4 * unit, y: 9.4 * unit))
        path.addLine(to: CGPoint(x: 10 * unit, y: 9.4 * unit))
        return path
    }
}

/// One path, so the slash can never be dropped from the circle.
private struct SlashedCircle: Shape {
    func path(in rect: CGRect) -> Path {
        let unit = rect.width / 14
        var path = Path(ellipseIn: CGRect(x: 2.4 * unit, y: 2.4 * unit, width: 9.2 * unit, height: 9.2 * unit))
        path.move(to: CGPoint(x: 1.8 * unit, y: 12.2 * unit))
        path.addLine(to: CGPoint(x: 12.2 * unit, y: 1.8 * unit))
        return path
    }
}

/// Concentric remaining-allowance rings: the short window outside, running clockwise
/// from the top; the weekly one inside, ending at the top so its used part leads.
struct ProviderRings: View {
    let kind: QuotaProvider
    let provider: ProviderQuota?
    let refreshing: Bool
    let now: Date

    private static let lineWidth: CGFloat = 3
    private static let outerRadius: CGFloat = 16.75
    private static let innerRadius: CGFloat = 12

    private var markSize: CGFloat {
        switch kind {
        case .claude: 12.8
        case .codex: 15
        case .grok: 14
        }
    }

    var body: some View {
        let state = QuotaIndicatorState(provider: provider, refreshing: refreshing, now: now)
        let fresh = state.phase == .available
        ZStack {
            Circle().stroke(Theme.line, lineWidth: Self.lineWidth)
                .frame(width: Self.outerRadius * 2, height: Self.outerRadius * 2)
            ForEach(state.rings) { item in
                // A provider with one window draws it as the outer ring.
                let outer = item.placement == .outer || state.rings.count == 1
                arc(fraction: item.remainingFraction, fromTop: outer,
                    tint: QuotaPalette.tint(remaining: item.remainingFraction.map { $0 * 100 }, fresh: fresh),
                    radius: outer ? Self.outerRadius : Self.innerRadius)
            }
            if state.phase == .loading {
                ProgressView().controlSize(.mini)
            } else {
                ProviderMark(kind: kind, size: markSize)
            }
        }
        .frame(width: 37, height: 37)
    }

    @ViewBuilder
    private func arc(fraction: Double?, fromTop: Bool, tint: Color, radius: CGFloat) -> some View {
        if let fraction, fraction > 0 {
            let filled = min(fraction, 1)
            Circle().trim(from: fromTop ? 0 : 1 - filled, to: fromTop ? filled : 1)
                .stroke(tint, style: StrokeStyle(lineWidth: Self.lineWidth, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .frame(width: radius * 2, height: radius * 2)
        }
    }
}
