import AISADCore
import AppKit
import Observation
import OSLog

@MainActor @Observable
final class UsageStore {
    private(set) var report: MenuBarReport?
    private(set) var monthlyBudget: Double?
    private(set) var error: String?
    private(set) var dashboardError: String?
    private(set) var isOpeningDashboard = false
    private(set) var isRefreshing = false
    private(set) var isSaving = false
    private(set) var budgetWasSaved = false
    let limits: ProviderLimitsStore
    private let client: CollectorClient
    private let logger = Logger(subsystem: "com.aiatsuk.aisad.menubar", category: "usage-sync")
    private var refreshTask: Task<Void, Never>?
    private var syncTask: Task<Void, Never>?
    private var operationTask: Task<Void, Never>?

    init(client: CollectorClient) {
        self.client = client
        limits = ProviderLimitsStore(client: client)
    }

    var isBusy: Bool { isRefreshing || isSaving || isOpeningDashboard }
    var menuTitle: String {
        guard let today = report?.periods.first(where: { $0.id == "today" }),
              today.hasPricedData else { return "AISAD" }
        let amount = today.knownCostUsd.rounded(.towardZero).formatted(
            .currency(code: "USD").locale(Locale(identifier: "en_US"))
                .precision(.fractionLength(0)).grouping(.never)
        )
        return amount + (today.isLowerBound ? "+" : "")
    }

    func start() {
        limits.start()
        guard refreshTask == nil else { return }
        syncTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.readSharedReport()
                do { try await Task.sleep(for: .seconds(1)) }
                catch { break }
            }
        }
        refreshTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                do { try await Task.sleep(for: .seconds(300)) }
                catch { break }
            }
        }
    }

    func stop() {
        limits.stop()
        syncTask?.cancel()
        syncTask = nil
        refreshTask?.cancel()
        refreshTask = nil
        operationTask?.cancel()
        operationTask = nil
    }

    func refreshNow() {
        guard !isBusy else { return }
        operationTask?.cancel()
        operationTask = Task { [weak self] in await self?.refresh() }
    }

    func openDashboard() {
        guard !isBusy else { return }
        isOpeningDashboard = true
        dashboardError = nil
        operationTask = Task { [weak self] in
            guard let self else { return }
            defer { self.isOpeningDashboard = false }
            do {
                let snapshot = try await self.client.dashboard()
                try Task.checkCancellation()
                self.apply(snapshot.report)
                guard NSWorkspace.shared.open(snapshot.url) else {
                    throw CollectorError.failed("No browser could open the offline dashboard.")
                }
            } catch is CancellationError {
            } catch {
                self.dashboardError = "Could not open dashboard: " + error.localizedDescription
            }
        }
    }

    func save(_ value: Double) {
        guard !isBusy else { return }
        operationTask?.cancel()
        operationTask = Task { [weak self] in _ = await self?.saveBudget(value) }
    }

    func refresh() async {
        guard !isBusy else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        do {
            monthlyBudget = try await client.budget()
            let value = try await client.report()
            try Task.checkCancellation()
            apply(value)
        } catch is CancellationError {
        } catch { self.error = error.localizedDescription }
    }

    func saveBudget(_ value: Double) async -> Bool {
        guard !isBusy else { return false }
        isSaving = true
        budgetWasSaved = false
        defer { isSaving = false }
        do {
            try await client.saveBudget(value)
            monthlyBudget = value
            budgetWasSaved = true
            do {
                apply(try await client.report())
            } catch {
                self.error = "Budget saved. Usage refresh failed: " + error.localizedDescription
            }
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    @discardableResult
    private func apply(_ value: MenuBarReport) -> Bool {
        if let current = report?.syncRevision, let next = value.syncRevision, next < current { return false }
        report = value
        monthlyBudget = value.month?.budgetUsd
        error = nil
        return true
    }

    private func readSharedReport() async {
        guard !Task.isCancelled else { return }
        if let value = try? await client.sharedReport(after: report?.syncRevision) {
            guard !Task.isCancelled else { return }
            if apply(value) {
                logger.info("Shared usage applied revision=\(value.syncRevision ?? "unknown", privacy: .public)")
            }
        }
    }

    func showDataFolder() { NSWorkspace.shared.open(client.output) }
}


#if DEBUG
extension UsageStore {
    func showPreview(report: MenuBarReport?, error: String? = nil, refreshing: Bool = false,
                     saving: Bool = false, saved: Bool = false, openingDashboard: Bool = false) {
        stop()
        self.report = report
        monthlyBudget = report?.month?.budgetUsd
        self.error = error
        isRefreshing = refreshing
        isSaving = saving
        budgetWasSaved = saved
        isOpeningDashboard = openingDashboard
    }
}
#endif
