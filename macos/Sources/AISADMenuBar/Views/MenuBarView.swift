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
        .padding(.horizontal, 12)
        .padding(.top, 11)
        .padding(.bottom, 11)
        .frame(width: 300)
        .onAppear { logger.notice("Usage menu appeared") }
        .onDisappear { logger.notice("Usage menu disappeared") }
    }

    private func content(now: Date) -> some View {
        VStack(alignment: .leading, spacing: 10) {
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
        HStack(spacing: 10) {
            RefreshUsageButton(store: store)
            Spacer(minLength: 4)
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
                .font(.system(size: 10.5))
                .keyboardShortcut("q")
                .focusable(false)
        }
        // The menu window gives its first borderless button key focus on open, and
        // focusEffectDisabled does not reach AppKit buttons; shortcuts still work.
        .focusEffectDisabled()
        .help(appHelp)
    }
}

/// A full-width row that opens a detail popover.
private struct DisclosureRow<Detail: View>: View {
    let title: String
    let value: String
    var valueColor: Color = .secondary
    @ViewBuilder let detail: () -> Detail
    @State private var presented = false

    var body: some View {
        Button { presented.toggle() } label: {
            HStack(spacing: 6) {
                Text(title).font(.system(size: 11.5, weight: .medium))
                Spacer(minLength: 6)
                Text(value).font(.system(size: 11)).monospacedDigit().foregroundStyle(valueColor).lineLimit(1)
                Image(systemName: "chevron.right").font(.system(size: 9, weight: .semibold)).foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 10).padding(.vertical, 7)
            .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
            .contentShape(RoundedRectangle(cornerRadius: 8))
        }
        .buttonStyle(.plain)
        .focusEffectDisabled()
        .popover(isPresented: $presented, arrowEdge: .trailing) { detail() }
    }
}

private struct AllProvidersRow: View {
    let store: ProviderLimitsStore

    var body: some View {
        let connected = store.providers.filter { !$0.windows.isEmpty }.count
        DisclosureRow(title: "All providers",
                      value: store.providers.isEmpty ? "—" : "\(connected) of \(QuotaProvider.allCases.count) connected") {
            AllProvidersPanel(store: store)
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
                        ProgressView().controlSize(.mini).frame(width: 14, height: 14)
                    } else {
                        Image(systemName: "arrow.clockwise")
                            .font(.system(size: 12, weight: .regular))
                            .frame(width: 14, height: 14)
                    }
                    Text(refreshing && hasData ? "Updating…" :
                         date?.formatted(.relative(presentation: .named, unitsStyle: .abbreviated)) ?? "Refresh")
                        .font(.system(size: 10.5))
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
                .font(.system(size: 12, weight: .regular))
                .frame(width: 14, height: 14)
            Text(title).font(.system(size: 10.5))
        }
        .frame(minHeight: 20)
        .contentShape(Rectangle())
    }
}
