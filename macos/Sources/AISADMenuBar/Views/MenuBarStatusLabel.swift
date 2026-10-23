import AISADCore
import AppKit
import SwiftUI
import OSLog

/// App-owned image identity stays stable while the displayed quotas are unchanged.
@MainActor
final class StatusLabelImageCache {
    private var lines: [String] = []
    private var cachedImage: NSImage?
    private let logger = Logger(subsystem: "com.aiatsuk.aisad.menubar", category: "status-label")

    func image(claude: String, codex: String) -> NSImage {
        let next = ["claude: " + claude, "codex: " + codex]
        if next == lines, let cachedImage { return cachedImage }

        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 9, weight: .medium),
            .foregroundColor: NSColor.black
        ]
        let text = next.map { $0 as NSString }
        let width = ceil(text.map { $0.size(withAttributes: attributes).width }.max() ?? 1) + 2
        let image = NSImage(size: NSSize(width: width, height: 20), flipped: true) { _ in
            for (index, line) in text.enumerated() {
                line.draw(at: NSPoint(x: 1, y: CGFloat(index) * 10), withAttributes: attributes)
            }
            return true
        }
        image.isTemplate = true
        lines = next
        cachedImage = image
        logger.notice("Status label image updated: \(width, privacy: .public) x 20")
        return image
    }
}

/// Keep MenuBarExtra's label a simple image; no nested SwiftUI rendering during launch.
struct MenuBarStatusLabel: View {
    let providers: [ProviderQuota]
    let images: StatusLabelImageCache

    var body: some View {
        let claude = weeklyRemaining("claude", at: .now)
        let codex = weeklyRemaining("codex", at: .now)
        Image(nsImage: images.image(claude: claude, codex: codex))
            .renderingMode(.template)
            .accessibilityLabel("AISAD weekly remaining: Claude " + claude + ", Codex " + codex)
            .help("AISAD · weekly remaining\nClaude: " + claude + "\nCodex: " + codex +
                "\n~ Last known reading · — unavailable or reset passed")
    }

    private func weeklyRemaining(_ id: String, at date: Date) -> String {
        guard let provider = providers.first(where: { $0.id == id }),
              let weekly = provider.activeWeeklyWindow(at: date) else { return "—" }
        let percent = weekly.remainingPercent.rounded(.down).formatted(
            .number.precision(.fractionLength(0)).locale(Locale(identifier: "en_US")))
        return (provider.status == "available" ? "" : "~") + percent + "%"
    }
}
