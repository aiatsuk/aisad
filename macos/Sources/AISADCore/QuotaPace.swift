import Foundation

/// Where a quota window stands against an even spend of its allowance.
/// Remaining below the even line is "behind pace": the allowance runs out early.
public struct QuotaPace: Sendable, Equatable {
    public enum Standing: Equatable, Sendable { case behind, onPace, ahead }

    public let start: Date
    public let end: Date
    public let remainingPercent: Double
    /// Remaining percent an even spend would leave at `at`.
    public let evenRemainingPercent: Double
    /// Linear projection of the average rate so far; nil when it lasts until reset.
    public let runsOut: Date?
    public let hasUsage: Bool

    public init?(window: QuotaWindow, at date: Date) {
        guard let end = window.resetsAt, let minutes = window.displayDurationMinutes,
              minutes > 0, !window.isExpired(at: date) else { return nil }
        let duration = minutes * 60
        let start = end.addingTimeInterval(-duration)
        let elapsed = min(max(date.timeIntervalSince(start), 0), duration)
        self.start = start
        self.end = end
        remainingPercent = window.remainingPercent
        evenRemainingPercent = 100 * (1 - elapsed / duration)
        let used = 100 - window.remainingPercent
        hasUsage = used > 0.05
        if hasUsage, elapsed > 0 {
            let exhausted = start.addingTimeInterval(elapsed * 100 / used)
            runsOut = exhausted < end ? max(exhausted, date) : nil
        } else {
            runsOut = nil
        }
    }

    /// Positive when more allowance remains than an even spend would leave.
    public var delta: Double { remainingPercent - evenRemainingPercent }

    public var standing: Standing {
        abs(delta) < 1 ? .onPace : delta < 0 ? .behind : .ahead
    }

    public var paceText: String {
        let amount = abs(delta).rounded().formatted(.number.precision(.fractionLength(0))) + "%"
        switch standing {
        case .onPace: return "On pace"
        case .behind: return amount + " behind pace"
        case .ahead: return amount + " ahead of pace"
        }
    }

    /// Fraction of the window elapsed at `date`, for chart and gauge markers.
    public func elapsedFraction(at date: Date) -> Double {
        let duration = end.timeIntervalSince(start)
        guard duration > 0 else { return 1 }
        return min(max(date.timeIntervalSince(start) / duration, 0), 1)
    }
}

public enum QuotaLevel: Equatable, Sendable {
    case healthy, low, critical

    public init(remainingPercent: Double) {
        self = remainingPercent >= 80 ? .healthy : remainingPercent >= 30 ? .low : .critical
    }
}

extension ProviderQuota {
    /// The headline window: the aggregate weekly allowance, else the longest aggregate one.
    public func primaryWindow(at date: Date) -> QuotaWindow? {
        if let weekly = activeWeeklyWindow(at: date) { return weekly }
        let aggregate = displayWindows.filter { !$0.isModelSpecific && !$0.isExpired(at: date) }
        return aggregate.last ?? displayWindows.first { !$0.isExpired(at: date) }
    }

    /// Every other window, in display order, for the compact rows under the headline.
    public func secondaryWindows(at date: Date) -> [QuotaWindow] {
        let primary = primaryWindow(at: date)?.id
        return displayWindows.filter { $0.id != primary }
    }
}

extension QuotaWindow {
    /// Short row labels: "5 hours" is the rolling session, scopes drop the separator.
    public var shortTitle: String {
        if displayDurationMinutes == 300, !isModelSpecific { return "Session" }
        return title.replacingOccurrences(of: " · ", with: " ")
    }

    public var windowName: String {
        switch displayDurationMinutes {
        case 300: "Session"
        case 10080: "Weekly"
        case 43200: "Monthly"
        default: title.components(separatedBy: " · ").first ?? title
        }
    }
}
