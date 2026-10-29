import AISADCore
import SwiftUI

enum QuotaPalette {
    static let healthy = Color(red: 0.36, green: 0.74, blue: 0.47)
    static let low = Color(red: 0.92, green: 0.63, blue: 0.29)
    static let critical = Color(red: 0.91, green: 0.36, blue: 0.32)

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

/// Simple drawn marks of one optical size; the app ships no third-party logos.
struct ProviderMark: View {
    let kind: QuotaProvider
    var size: CGFloat = 14

    var body: some View {
        Group {
            switch kind {
            case .claude:
                Starburst(rays: 10)
                    .fill(Color(red: 0.85, green: 0.47, blue: 0.34))
            case .codex:
                Circle()
                    .fill(LinearGradient(colors: [Color(red: 0.47, green: 0.42, blue: 0.98),
                                                  Color(red: 0.27, green: 0.55, blue: 0.98)],
                                         startPoint: .topLeading, endPoint: .bottomTrailing))
                    .overlay {
                        Text(">_").font(.system(size: size * 0.42, weight: .heavy, design: .monospaced))
                            .foregroundStyle(.white)
                    }
            case .grok:
                SlashedCircle()
                    .stroke(.primary, style: StrokeStyle(lineWidth: max(1.2, size * 0.12), lineCap: .round))
                    .padding(size * 0.06)
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

private struct Starburst: Shape {
    let rays: Int

    func path(in rect: CGRect) -> Path {
        var path = Path()
        let center = CGPoint(x: rect.midX, y: rect.midY)
        let outer = min(rect.width, rect.height) / 2
        let inner = outer * 0.3
        for index in 0..<rays * 2 {
            let angle = Double(index) * .pi / Double(rays) - .pi / 2
            let radius = index.isMultiple(of: 2) ? outer : inner
            let point = CGPoint(x: center.x + radius * cos(angle), y: center.y + radius * sin(angle))
            index == 0 ? path.move(to: point) : path.addLine(to: point)
        }
        path.closeSubpath()
        return path
    }
}

/// One path, so the slash can never be dropped from the circle.
private struct SlashedCircle: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path(ellipseIn: rect.insetBy(dx: rect.width * 0.14, dy: rect.height * 0.14))
        path.move(to: CGPoint(x: rect.maxX - rect.width * 0.08, y: rect.minY + rect.height * 0.08))
        path.addLine(to: CGPoint(x: rect.minX + rect.width * 0.08, y: rect.maxY - rect.height * 0.08))
        return path
    }
}

/// Concentric remaining-allowance rings: the short window outside, the weekly one inside.
struct ProviderRings: View {
    let kind: QuotaProvider
    let provider: ProviderQuota?
    let refreshing: Bool
    let now: Date
    var diameter: CGFloat = 36

    private static let lineWidth: CGFloat = 2.5
    private static let gap: CGFloat = 2

    var body: some View {
        let state = QuotaIndicatorState(provider: provider, refreshing: refreshing, now: now)
        let fresh = state.phase == .available
        ZStack {
            if state.rings.isEmpty {
                ring(fraction: nil, tint: .secondary, diameter: diameter)
            }
            ForEach(state.rings) { item in
                // A provider with one window draws it as the outer ring.
                let outer = item.placement == .outer || state.rings.count == 1
                ring(fraction: item.remainingFraction,
                     tint: QuotaPalette.tint(remaining: item.remainingFraction.map { $0 * 100 }, fresh: fresh),
                     diameter: outer ? diameter : diameter - 2 * (Self.lineWidth + Self.gap))
            }
            if state.phase == .loading {
                ProgressView().controlSize(.mini)
            } else {
                ProviderMark(kind: kind, size: 15)
            }
        }
        .frame(width: diameter, height: diameter)
    }

    private func ring(fraction: Double?, tint: Color, diameter: CGFloat) -> some View {
        Circle().stroke(Color.primary.opacity(0.12), lineWidth: Self.lineWidth)
            .overlay {
                if let fraction, fraction > 0 {
                    Circle().trim(from: 0, to: min(fraction, 1))
                        .stroke(tint, style: StrokeStyle(lineWidth: Self.lineWidth, lineCap: .round))
                        .rotationEffect(.degrees(-90))
                }
            }
            .frame(width: diameter - Self.lineWidth, height: diameter - Self.lineWidth)
    }
}
