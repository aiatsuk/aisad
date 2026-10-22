import AISADCore
import SwiftUI

enum QuotaAppearance {
    static func tint(remaining: Double?, fresh: Bool, normal: Color = .primary) -> Color {
        guard fresh, let remaining else { return .secondary }
        switch QuotaIndicatorState.WarningLevel(remainingPercent: remaining) {
        case .normal: return normal
        case .warning: return .orange
        case .critical: return .red
        }
    }
}

struct QuotaRingsView: View {
    let state: QuotaIndicatorState

    var body: some View {
        ZStack {
            if state.phase == .loading {
                ProgressView().controlSize(.mini)
            } else {
                if state.rings.isEmpty {
                    Circle().stroke(.quaternary, lineWidth: 2)
                }
                ForEach(state.rings) { ring in
                    let diameter: CGFloat = ring.placement == .outer ? 20 : 14
                    Circle().stroke(.quaternary, lineWidth: 2)
                        .overlay {
                            if let fraction = ring.remainingFraction, fraction > 0 {
                                Circle().trim(from: 0, to: fraction)
                                    .stroke(QuotaAppearance.tint(remaining: fraction * 100,
                                                                fresh: state.phase == .available),
                                            style: StrokeStyle(lineWidth: 2, lineCap: .round))
                                    .rotationEffect(.degrees(-90))
                            }
                        }
                        .frame(width: diameter, height: diameter)
                }
                if let symbol = statusSymbol {
                    Image(systemName: symbol)
                        .font(.system(size: 7, weight: .semibold))
                        .foregroundStyle(QuotaAppearance.tint(remaining: state.lowestRemainingPercent,
                                                              fresh: state.phase == .available))
                }
            }
        }
        .frame(width: state.rings.count == 1 && state.rings.first?.placement == .inner ? 14 : 20,
               height: 20)
        .accessibilityHidden(true)
    }

    private var statusSymbol: String? {
        switch state.phase {
        case .loading: return nil
        case .unavailable: return "questionmark"
        case .stale, .expired: return "clock"
        case .available:
            if state.lowestRemainingPercent.map({
                QuotaIndicatorState.WarningLevel(remainingPercent: $0) != .normal
            }) == true { return "exclamationmark" }
            // Scoped readings alone must not look like exhausted aggregate limits.
            return state.rings.isEmpty ? "questionmark" : nil
        }
    }
}
