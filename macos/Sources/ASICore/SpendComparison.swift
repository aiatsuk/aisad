import Foundation

public struct SpendComparison: Decodable, Sendable {
    public struct Window: Decodable, Sendable {
        public let from: Date
        public let to: Date
    }

    public struct Totals: Decodable, Sendable {
        public let knownCostUsd: Double
    }

    public let status: String
    public let label: String
    public let absoluteUsd: Double?
    public let percent: Double?
    public let current: Totals
    public let previous: Totals
    public let currentPeriod: Window
    public let previousPeriod: Window

    public var isAvailable: Bool { status == "available" || status == "zero_baseline" }

    var isValid: Bool {
        current.knownCostUsd.isFinite && current.knownCostUsd >= 0 &&
        previous.knownCostUsd.isFinite && previous.knownCostUsd >= 0 &&
        (absoluteUsd.map(\.isFinite) ?? true) && (percent.map(\.isFinite) ?? true) &&
        currentPeriod.from <= currentPeriod.to && previousPeriod.from <= previousPeriod.to &&
        (!isAvailable || absoluteUsd != nil) &&
        (status != "available" || percent != nil) &&
        (status != "zero_baseline" || percent == nil)
    }

    public var symbol: String {
        guard let absoluteUsd else { return "minus" }
        return absoluteUsd > 0 ? "arrow.up.right" : absoluteUsd < 0 ? "arrow.down.right" : "minus"
    }

    public var text: String {
        guard isAvailable, let absoluteUsd else {
            let reason = switch status {
            case "no_previous_data": "No previous data"
            case "no_current_data": "No current data"
            case "incomplete_pricing": "Incomplete prices"
            default: "Comparison unavailable"
            }
            return reason
        }
        func sign(_ value: Double) -> String { value > 0 ? "+" : value < 0 ? "−" : "" }
        var change = sign(absoluteUsd) + SpendPeriod.dollars(abs(absoluteUsd))
        if let percent {
            let amount = abs(percent).formatted(.number.precision(.fractionLength(0...1))
                .locale(Locale(identifier: "en_US")))
            change += " · " + sign(percent) + amount + "%"
        }
        return change
    }

    public var detail: String {
        func span(_ window: Window) -> String {
            window.from.formatted(date: .abbreviated, time: .shortened) + " – " +
            window.to.formatted(date: .abbreviated, time: .shortened)
        }
        return label + ". Matched local calendar windows.\n" +
            "Current: " + span(currentPeriod) + " · " + SpendPeriod.dollars(current.knownCostUsd) + "\n" +
            "Previous: " + span(previousPeriod) + " · " + SpendPeriod.dollars(previous.knownCostUsd)
    }
}
