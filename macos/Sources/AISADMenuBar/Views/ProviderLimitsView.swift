import AISADCore
import SwiftUI
import OSLog

enum QuotaProvider: String, CaseIterable, Identifiable {
    case claude, codex, grok
    var id: String { rawValue }
    var title: String {
        switch self { case .claude: "Claude"; case .codex: "Codex"; case .grok: "Grok" }
    }
    var fullTitle: String { self == .claude ? "Claude Code" : title }
}

/// One compact provider row. Hovering does not start a collection.
struct ProviderLimitsView: View {
    let store: ProviderLimitsStore
    @State private var presentedProvider: QuotaProvider?

    var body: some View {
        TimelineView(.periodic(from: .now, by: 30)) { context in
            HStack(spacing: 8) {
                ForEach(QuotaProvider.allCases) { kind in
                    ProviderQuotaButton(kind: kind,
                        provider: store.providers.first { $0.id == kind.id },
                        refreshing: store.isRefreshing, retryAt: store.nextRefresh(for: kind.id),
                        error: store.error, now: context.date, presented: $presentedProvider)
                    if kind != .grok { Spacer(minLength: 4) }
                }
            }
        }
    }
}

private struct ProviderQuotaButton: View {
    let kind: QuotaProvider
    let provider: ProviderQuota?
    let refreshing: Bool
    let retryAt: Date?
    let error: String?
    let now: Date
    @Binding var presented: QuotaProvider?
    @State private var interaction = HoverPopoverState()
    @State private var dismissal: Task<Void, Never>?
    private let logger = Logger(subsystem: "com.aiatsuk.aisad.menubar", category: "quota-card")

    private var state: QuotaIndicatorState {
        QuotaIndicatorState(provider: provider, refreshing: refreshing, now: now)
    }
    private var isPresented: Binding<Bool> {
        Binding(get: { presented == kind }, set: { value in
            if value {
                presented = kind
            } else if presented == kind {
                presented = nil
                interaction.dismiss()
                dismissal?.cancel()
            }
        })
    }

    var body: some View {
        Button {
            dismissal?.cancel()
            interaction.pin()
            logger.notice("Quota card pinned: \(kind.rawValue, privacy: .public)")
            presented = kind
        } label: {
            HStack(spacing: 6) {
                QuotaRingsView(state: state)
                VStack(alignment: .leading, spacing: 1) {
                    Text(kind.title)
                        .font(.system(size: 10.5, weight: presented == kind ? .semibold : .regular))
                        .foregroundStyle(state.phase == .available ? .primary : .secondary)
                    let weekly = provider?.activeWeeklyWindow(at: now)
                    Text(weekly?.remainingText ?? "—")
                        .font(.system(size: 9.5))
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.vertical, 1)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(kind.fullTitle + " plan limits")
        .accessibilityValue(accessibilityValue)
        .accessibilityHint("Show all quota windows and reset times")
        .onHover { hover($0, details: false) }
        .popover(isPresented: isPresented, arrowEdge: .bottom) {
            ProviderLimitDetailsView(kind: kind, provider: provider, refreshing: refreshing,
                                     retryAt: retryAt, error: error)
                .onHover { hover($0, details: true) }
                .onAppear {
                    logger.notice("Quota card appeared: \(kind.rawValue, privacy: .public)")
                }
                .onDisappear {
                    logger.notice("Quota card disappeared: \(kind.rawValue, privacy: .public)")
                }
        }
        .onChange(of: presented) { _, value in
            if value != kind {
                interaction.dismiss()
                dismissal?.cancel()
            }
        }
        .onDisappear {
            interaction.dismiss()
            dismissal?.cancel()
            if presented == kind { presented = nil }
        }
    }

    private func hover(_ inside: Bool, details: Bool) {
        interaction.setHover(inside, area: details ? .details : .trigger)
        if inside, details {
            logger.info("Pointer entered quota card: \(kind.rawValue, privacy: .public)")
        }
        dismissal?.cancel()
        if inside {
            presented = kind
        } else if !interaction.isPinned, presented == kind {
            // Allow the pointer to cross the native popover arrow/gap.
            dismissal = Task { @MainActor in
                do { try await Task.sleep(for: .milliseconds(200)) } catch { return }
                guard !Task.isCancelled, !interaction.shouldRemainOpen else { return }
                if presented == kind { presented = nil }
            }
        }
    }

    private var accessibilityValue: String {
        guard let provider else { return refreshing ? "Reading limits" : "Limits unavailable" }
        let values = provider.displayWindows.map {
            $0.title + ": " + ($0.isExpired(at: now) ? "reset passed; refresh needed" : $0.remainingText)
        }
        let prefix = state.phase == .stale ? "Last known reading. " : ""
        return prefix + (values.isEmpty ? (provider.message ?? "Limits unavailable") : values.joined(separator: "; "))
    }
}
