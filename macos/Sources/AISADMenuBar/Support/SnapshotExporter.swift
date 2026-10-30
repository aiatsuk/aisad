import AISADCore
import AppKit
import SwiftUI

/// Capture actual native view trees without requesting desktop recording access.
@MainActor
enum SnapshotExporter {
    private static let symbols = [
        "chart.bar.fill", "arrow.clockwise", "gearshape", "arrow.up.right.square", "arrow.up.right",
        "arrow.down.right", "minus", "exclamationmark.triangle", "clock.badge.exclamationmark",
        "checkmark.circle", "questionmark", "clock", "exclamationmark",
        "chevron.right"
    ]

    static func write(store: UsageStore, to directory: URL, allowEmpty: Bool = false) throws {
        guard allowEmpty || store.report != nil else {
            throw CollectorError.failed(store.error ?? "No report available for the snapshot.")
        }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        for symbol in symbols {
            guard NSImage(systemSymbolName: symbol, accessibilityDescription: nil) != nil else {
                throw CollectorError.failed("Unavailable SF Symbol: " + symbol)
            }
        }
        let contrast = CommandLine.arguments.contains("--snapshot-high-contrast")
        for (name, scheme) in [("light", ColorScheme.light), ("dark", ColorScheme.dark)] {
            let appearance = NSAppearance(named: contrast
                ? (scheme == .dark ? .accessibilityHighContrastDarkAqua : .accessibilityHighContrastAqua)
                : (scheme == .dark ? .darkAqua : .aqua))
            NSApp.appearance = appearance
            #if DEBUG
            let chart = try MonthlyChartPreview.fromArguments()
            let args = CommandLine.arguments
            let selectedDay = args.firstIndex(of: "--chart-day").flatMap {
                args.indices.contains($0 + 1) ? Int(args[$0 + 1]) : nil
            }
            let menu = Group {
                if let style = MenuCardsPreview.Style.fromArguments, let chart {
                    MenuCardsPreview(store: store, chart: chart, style: style)
                } else {
                    MenuBarView(store: store, chartPreview: chart)
                        .environment(\.snapshotChartDay, selectedDay)
                }
            }
            if CommandLine.arguments.contains("--card-board"), let chart {
                try capture(MenuCardsComparisonPreview(store: store, chart: chart),
                            name: "cards-comparison-" + name,
                            scheme: scheme, appearance: appearance, directory: directory)
            }
            #else
            let menu = MenuBarView(store: store)
            #endif
            try capture(menu, name: "menubar-" + name,
                        scheme: scheme, appearance: appearance, directory: directory)
            #if DEBUG
            for range in SpendRange.allCases {
                try capture(MenuBarView(store: store).environment(\.snapshotSpendRange, range)
                                .environment(\.snapshotChartDay, selectedDay),
                            name: "menubar-" + range.rawValue + "-" + name,
                            scheme: scheme, appearance: appearance, directory: directory)
            }
            for kind in QuotaProvider.allCases {
                try capture(QuotaPopover(kind: kind, store: store.limits), name: "quota-" + kind.rawValue + "-" + name,
                            scheme: scheme, appearance: appearance, directory: directory)
                try capture(QuotaPopover(kind: kind, store: store.limits).environment(\.snapshotQuotaHover, 0.6),
                            name: "quota-" + kind.rawValue + "-hover-" + name,
                            scheme: scheme, appearance: appearance, directory: directory)
            }
            #endif
            try capture(AllProvidersPanel(store: store.limits), name: "all-providers-" + name,
                        scheme: scheme, appearance: appearance, directory: directory)
            for kind in QuotaProvider.allCases {
                let provider = store.limits.providers.first { $0.id == kind.id }
                try capture(ProviderLimitDetailsView(kind: kind, provider: provider,
                            refreshing: store.limits.isRefreshing,
                            retryAt: store.limits.nextRefresh(for: kind.id), error: store.limits.error),
                            name: "limits-" + kind.id + "-" + name,
                            scheme: scheme, appearance: appearance, directory: directory)
            }
            try capture(MenuBarStatusLabel(providers: store.limits.providers, images: StatusLabelImageCache())
                            .padding(.horizontal, 6).padding(.vertical, 4).frame(height: 28),
                        name: "status-item-" + name, scheme: scheme,
                        appearance: appearance, directory: directory)
            if store.monthlyBudget != nil {
                try capture(BudgetSettingsView(store: store), name: "settings-" + name,
                            scheme: scheme, appearance: appearance, directory: directory)
            }
            try capture(symbolBoard, name: "symbols-" + name,
                        scheme: scheme, appearance: appearance, directory: directory)
        }
    }

    private static var symbolBoard: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(symbols, id: \.self) { name in
                HStack(spacing: 12) {
                    Image(systemName: name).font(.system(size: 12, weight: .regular)).frame(width: 18)
                    Image(systemName: name).font(.system(size: 16, weight: .regular)).frame(width: 22)
                    Text(name).font(.system(.caption, design: .monospaced))
                }
            }
        }
        .symbolRenderingMode(.monochrome)
        .padding(14)
    }

    private static func capture<Content: View>(
        _ content: Content, name: String, scheme: ColorScheme,
        appearance: NSAppearance?, directory: URL
    ) throws {
        let root = content
            .environment(\.colorScheme, scheme)
            .background(Color(nsColor: .windowBackgroundColor))
        let host = NSHostingView(rootView: root)
        host.appearance = appearance
        host.frame = NSRect(origin: .zero, size: host.fittingSize)
        let window = NSWindow(contentRect: host.frame, styleMask: [.borderless],
                              backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.appearance = appearance
        window.contentView = host
        window.setFrameOrigin(NSPoint(x: -10000, y: -10000))
        window.orderFront(nil)
        host.layoutSubtreeIfNeeded()
        host.displayIfNeeded()
        guard let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) else {
            throw CollectorError.failed("Could not allocate the native snapshot.")
        }
        host.cacheDisplay(in: host.bounds, to: bitmap)
        guard let png = bitmap.representation(using: .png, properties: [:]) else {
            throw CollectorError.failed("Could not render the native view.")
        }
        try png.write(to: directory.appendingPathComponent(name + ".png"))
        window.close()
    }
}
