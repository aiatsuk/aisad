import AISADCore
import SwiftUI

struct BudgetSettingsView: View {
    let store: UsageStore
    @State private var budgetText = ""

    private var amount: Double? {
        let separator = Locale.current.decimalSeparator ?? "."
        guard let value = Double(budgetText.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: separator, with: ".")),
              value.isFinite, value > 0 else { return nil }
        return value
    }

    private var hasChanges: Bool { amount != store.monthlyBudget }

    var body: some View {
        Form {
            Section("Monthly budget") {
                TextField("Limit in USD", text: $budgetText)
                    .textFieldStyle(.roundedBorder)
                    .disabled(store.isSaving || store.monthlyBudget == nil)
                Text("Applies to all Claude and Codex usage this calendar month.")
                    .font(.caption).foregroundStyle(.secondary)
                HStack {
                    Button("Save budget") {
                        guard let amount else { return }
                        store.save(amount)
                    }
                    .disabled(store.monthlyBudget == nil || store.isBusy || !hasChanges || amount == nil)
                    .keyboardShortcut(.defaultAction)
                    if store.isSaving {
                        ProgressView().controlSize(.small)
                    } else if store.budgetWasSaved && !hasChanges {
                        Label("Saved", systemImage: "checkmark.circle").foregroundStyle(.secondary)
                    }
                }
            }
            Section {
                Text("API cost estimates, not subscription limits. Refreshes every 5 minutes. Calendar periods use your Mac’s timezone.")
                    .font(.caption).foregroundStyle(.secondary)
                Button("Open data folder") { store.showDataFolder() }
                if let error = store.error {
                    Text(error).font(.caption).foregroundStyle(.red)
                        .textSelection(.enabled)
                }
            }
        }
        .formStyle(.grouped)
        .frame(width: 430)
        .fixedSize(horizontal: false, vertical: true)
        .onAppear { fillBudget(store.monthlyBudget) }
        .onChange(of: store.monthlyBudget) { old, new in
            if amount == old || budgetText.isEmpty { fillBudget(new) }
        }
    }

    private func fillBudget(_ value: Double?) {
        guard let value else { return }
        budgetText = value.formatted(.number.grouping(.never).precision(.fractionLength(0...2)))
    }
}
