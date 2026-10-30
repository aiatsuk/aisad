import AISADCore
import SwiftUI
import OSLog

struct MenuBarView: View {
    let store: UsageStore
    #if DEBUG
    var chartPreview: MonthlyChartPreview? = nil
    #endif
    private let logger = Logger(subsystem: "com.aiatsuk.aisad.menubar", category: "menu")
    private var appHelp: String {
        let version = store.report?.version ?? ""
        let timezone = store.report?.timezone ?? "System local timezone"
        return ["Claude + Codex · API cost estimates", "AISAD " + version, timezone].joined(separator: "\n")
    }

    var body: some View {
        TimelineView(.periodic(from: .now, by: 30)) { context in
            content(now: context.date)
        }
        .font(.system(size: 12))
        .buttonStyle(.borderless)
        .padding(.horizontal, 8)
        .padding(.top, 16)
        .frame(width: 300)
        .background(Theme.panel)
        .onAppear { logger.notice("Usage menu appeared") }
        .onDisappear { logger.notice("Usage menu disappeared") }
    }

    private func content(now: Date) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            header
            if let report = store.report {
                SpendCardsView(report: report)
            } else if store.isRefreshing {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Reading local usage…").foregroundStyle(.secondary)
                }.padding(.vertical, 4)
            } else {
                Text("Usage is not available yet.").foregroundStyle(.secondary)
            }
            ProviderTilesView(store: store.limits, now: now)
            AllProvidersRow(store: store.limits)
            if let report = store.report, !Calendar.current.isDateInToday(report.generated) {
                Label("Spend snapshot is from a previous day", systemImage: "clock.badge.exclamationmark")
                    .font(.caption).foregroundStyle(.orange)
            }
            if let error = store.dashboardError ?? store.error ?? store.limits.error {
                Label {
                    Text("Update failed · " + error.replacingOccurrences(of: "Error: ", with: ""))
                } icon: {
                    Image(systemName: "exclamationmark.triangle").foregroundStyle(.red)
                }
                    .lineLimit(4)
                    .help(error)
                    .font(.system(size: 9.5)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
            }
            #if DEBUG
            if let chartPreview { MonthlySpendChartPreview(preview: chartPreview) }
            #endif
            footer
        }
    }

    private var header: some View {
        Text("AISAD").font(.system(size: 13, weight: .semibold))
            .frame(maxWidth: .infinity, alignment: .leading)
            .help(appHelp)
    }

    private var footer: some View {
        HStack(spacing: 0) {
            RefreshUsageButton(store: store)
            Spacer(minLength: 8)
            actions
        }
        .font(.system(size: 11))
        .foregroundStyle(.secondary)
        .lineLimit(1)
        .frame(height: 32)
        .padding(.top, -8)
        // The menu window gives its first borderless button key focus on open, and
        // focusEffectDisabled does not reach AppKit buttons; shortcuts still work.
        .focusEffectDisabled()
        .help(appHelp)
    }

    private var actions: some View {
        HStack(spacing: 16) {
            Button {
                store.openDashboard()
            } label: {
                MenuActionLabel(title: store.isOpeningDashboard ? "Opening…" : "Dashboard",
                                symbol: "arrow.up.right.square")
            }
            .disabled(store.isBusy)
            .focusable(false)
            .help("Collect current local usage and open the offline dashboard in your browser")
            .accessibilityLabel("Open dashboard")
            .keyboardShortcut("o")
            SettingsLink {
                MenuActionLabel(title: "Budget", symbol: "gearshape")
            }
            .accessibilityLabel("Monthly budget")
            .disabled(store.monthlyBudget == nil)
            .focusable(false)
            .help("Monthly budget…")
            .simultaneousGesture(TapGesture().onEnded {
                NSApp.activate(ignoringOtherApps: true)
            })
            .keyboardShortcut(",")

            Button("Quit") { NSApplication.shared.terminate(nil) }
                .fixedSize()
                .keyboardShortcut("q")
                .focusable(false)
                .padding(.trailing, 2)
        }
    }
}

/// A full-width row that opens every provider's windows beside the menu.
private struct AllProvidersRow: View {
    let store: ProviderLimitsStore
    @State private var presented = false

    var body: some View {
        Button { presented.toggle() } label: {
            HStack {
                Text("All providers").font(.system(size: 12, weight: .semibold))
                Spacer(minLength: 8)
                Image(systemName: "chevron.right").font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(Theme.tertiary)
            }
            .padding(.horizontal, 8)
            .frame(height: 28)
            .background(Theme.rowFill, in: RoundedRectangle(cornerRadius: Theme.cardRadius))
            .contentShape(RoundedRectangle(cornerRadius: Theme.cardRadius))
        }
        .buttonStyle(.plain)
        .focusEffectDisabled()
        .popover(isPresented: $presented, arrowEdge: .leading) {
            AllProvidersPanel(store: store).presentationBackground(Theme.popover)
        }
        .accessibilityHint("Show every quota window and reset time")
    }
}

private struct RefreshUsageButton: View {
    let store: UsageStore

    private var refreshing: Bool { store.isRefreshing || store.limits.isRefreshing }
    private var date: Date? { [store.report?.generated, store.limits.lastUpdated].compactMap { $0 }.min() }
    private var hasData: Bool { store.report != nil || !store.limits.providers.isEmpty }

    var body: some View {
        TimelineView(.periodic(from: .now, by: 60)) { context in
            let stale = date.map { context.date.timeIntervalSince($0) > 600 } ?? false
            Button {
                store.refreshNow()
                store.limits.refreshNow()
            } label: {
                HStack(spacing: 4) {
                    if refreshing, hasData {
                        ProgressView().controlSize(.mini).frame(width: 12, height: 12)
                    } else {
                        Image(systemName: "arrow.clockwise")
                            .font(.system(size: 11, weight: .regular))
                            .frame(width: 12, height: 12)
                    }
                    Text(refreshing && hasData ? "Updating…" : date?.ageText(now: context.date) ?? "Refresh")
                        .fixedSize()
                }
                .foregroundStyle(stale ? .orange : .secondary)
                .frame(minHeight: 20)
                .contentShape(Rectangle())
            }
            .disabled(store.isBusy || store.limits.isRefreshing)
            .focusable(false)
            .accessibilityLabel("Refresh usage and provider limits")
            .accessibilityValue(date?.formatted() ?? "Not collected yet")
            .help("Refresh usage and provider limits. Age of the oldest displayed reading." +
                  (date.map { "\nLast successful collection: " + $0.formatted() } ?? ""))
            .keyboardShortcut("r")
        }
    }
}

private struct MenuActionLabel: View {
    let title: String
    let symbol: String

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: symbol)
                .symbolRenderingMode(.monochrome)
                .font(.system(size: 11, weight: .regular))
                .frame(width: 12, height: 12)
            Text(title).fixedSize()
        }
        .frame(minHeight: 20)
        .contentShape(Rectangle())
    }
}
