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

    private var header: some View {
        HStack(alignment: .center, spacing: 10) {
            Text("AISAD")
                .font(.system(size: 12, weight: .semibold))
                .help(appHelp)
            Spacer(minLength: 8)
            Button {
                store.openDashboard()
            } label: {
                HStack(spacing: 4) {
                    Text(store.isOpeningDashboard ? "Opening…" : "Dashboard")
                    if store.isOpeningDashboard {
                        ProgressView().controlSize(.mini).frame(width: 12, height: 12)
                    } else {
                        Image(systemName: "arrow.up.right.square")
                    }
                }
                .font(.system(size: 11, weight: .medium))
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
                .background(.quaternary, in: Capsule())
                .contentShape(Capsule())
            }
            .buttonStyle(.plain)
            .disabled(store.isBusy)
            .help("Collect current local usage and open the offline dashboard in your browser")
            .accessibilityLabel("Open dashboard")
            .keyboardShortcut("o")
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            header
            if let report = store.report {
                SpendCardsView(report: report)
                if !Calendar.current.isDateInToday(report.generated) {
                    Label("Snapshot is from a previous day", systemImage: "clock.badge.exclamationmark")
                        .font(.caption).foregroundStyle(.orange)
                }
            } else if store.isRefreshing {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Reading local usage…").foregroundStyle(.secondary)
                }.padding(.vertical, 4)
            } else {
                Text("Usage is not available yet.").foregroundStyle(.secondary)
            }
            if let error = store.dashboardError ?? store.error {
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
            ProviderLimitsView(store: store.limits)
                .padding(.horizontal, 2).padding(.vertical, 3)
            Divider()
            HStack(spacing: 10) {
                RefreshUsageButton(store: store)
                Spacer(minLength: 4)
                SettingsLink {
                    MenuActionLabel(title: "Budget", symbol: "gearshape")
                }
                .accessibilityLabel("Monthly budget")
                .disabled(store.monthlyBudget == nil)
                .help("Monthly budget…")
                .simultaneousGesture(TapGesture().onEnded {
                    NSApp.activate(ignoringOtherApps: true)
                })
                .keyboardShortcut(",")

                Button("Quit") { NSApplication.shared.terminate(nil) }
                    .font(.system(size: 10.5))
                    .keyboardShortcut("q")
            }
        }
        .font(.system(size: 12))
        .buttonStyle(.borderless)
        .padding(.horizontal, 10)
        .padding(.top, 8)
        .padding(.bottom, 6)
        .frame(width: 300)
        .onAppear { logger.notice("Usage menu appeared") }
        .onDisappear { logger.notice("Usage menu disappeared") }
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
