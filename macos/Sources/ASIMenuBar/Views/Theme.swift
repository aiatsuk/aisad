import AppKit
import SwiftUI

/// Shared colors, corner radii and motion of the menu bar surfaces.
enum Theme {
    static let green = adaptive(dark: 0x30D158, light: 0x34C759)
    static let orange = adaptive(dark: 0xFF9F0A, light: 0xFF9500)
    static let red = adaptive(dark: 0xFF453A, light: 0xFF3B30)
    static let blue = adaptive(dark: 0x0A84FF, light: 0x007AFF)

    /// Tints over the system's blurred window material.
    static let panel = Color(nsColor: NSColor(name: nil) { appearance in
        isDark(appearance) ? NSColor(white: 15 / 255, alpha: 0.92) : NSColor(white: 246 / 255, alpha: 0.92)
    })
    static let popover = Color(nsColor: NSColor(name: nil) { appearance in
        isDark(appearance) ? NSColor(white: 23 / 255, alpha: 0.86) : NSColor(white: 246 / 255, alpha: 0.86)
    })

    static let fill = Color.primary.opacity(0.04)
    static let rowFill = Color.primary.opacity(0.05)
    static let hairline = Color.primary.opacity(0.08)
    static let line = Color.primary.opacity(0.1)
    static let segmentTrack = Color.primary.opacity(0.06)
    static let segmentThumb = Color(nsColor: NSColor(name: nil) { appearance in
        isDark(appearance) ? NSColor(white: 1, alpha: 0.14) : .white
    })
    static let tertiary = Color.secondary.opacity(0.84)
    static let quaternary = Color.secondary.opacity(0.67)

    static let cardRadius: CGFloat = 12
    static let motion = Animation.timingCurve(0.32, 0.72, 0, 1, duration: 0.25)

    private static func isDark(_ appearance: NSAppearance) -> Bool {
        appearance.bestMatch(from: [.darkAqua, .aqua, .accessibilityHighContrastDarkAqua,
                                    .accessibilityHighContrastAqua])?.rawValue.contains("Dark") ?? false
    }

    private static func adaptive(dark: UInt32, light: UInt32) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            let value = isDark(appearance) ? dark : light
            return NSColor(srgbRed: CGFloat(value >> 16 & 0xFF) / 255, green: CGFloat(value >> 8 & 0xFF) / 255,
                           blue: CGFloat(value & 0xFF) / 255, alpha: 1)
        })
    }
}

/// A card with the shared fill and hairline.
struct CardBackground: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(Theme.fill, in: RoundedRectangle(cornerRadius: Theme.cardRadius))
            .overlay {
                RoundedRectangle(cornerRadius: Theme.cardRadius).strokeBorder(Theme.hairline, lineWidth: 1)
            }
    }
}

extension Date {
    /// Age for labels: "just now", then "17 sec ago", without the formatter's periods.
    func ageText(now: Date) -> String {
        if now.timeIntervalSince(self) < 10 { return "just now" }
        return formatted(.relative(presentation: .numeric, unitsStyle: .abbreviated))
            .replacingOccurrences(of: ".", with: "")
    }
}
