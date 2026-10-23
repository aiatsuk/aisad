import AISADCore
import SwiftUI
import OSLog

/// Exporting views must not register a second menu-bar scene with Control Center.
@main
enum AISADLauncher {
    @MainActor
    static func main() {
        if CommandLine.arguments.contains("--snapshot") {
            let application = NSApplication.shared
            let delegate = AppDelegate()
            application.delegate = delegate
            withExtendedLifetime(delegate) { application.run() }
        } else {
            AISADMenuBarApp.main()
        }
    }
}

struct AISADMenuBarApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @State private var isMenuInserted = true
    private let logger = Logger(subsystem: "com.aiatsuk.aisad.menubar", category: "lifecycle")

    private var menuInsertion: Binding<Bool> {
        Binding(get: { isMenuInserted }, set: { inserted in
            logger.notice("Status item insertion changed: \(inserted, privacy: .public)")
            isMenuInserted = inserted
        })
    }

    var body: some Scene {
        MenuBarExtra(isInserted: menuInsertion) {
            MenuBarView(store: delegate.store)
        } label: {
            MenuBarStatusLabel(providers: delegate.store.limits.providers,
                               images: delegate.statusLabelImages)
        }
        .menuBarExtraStyle(.window)

        Settings {
            BudgetSettingsView(store: delegate.store)
        }
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let statusLabelImages = StatusLabelImageCache()
    private var exportTask: Task<Void, Never>?
    private let logger = Logger(subsystem: "com.aiatsuk.aisad.menubar", category: "lifecycle")
    let store = UsageStore(client: CollectorClient(
        resources: Bundle.main.resourceURL ?? Bundle.main.bundleURL))

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        if let index = CommandLine.arguments.firstIndex(of: "--snapshot"),
           CommandLine.arguments.indices.contains(index + 1) {
            let directory = URL(fileURLWithPath: CommandLine.arguments[index + 1], isDirectory: true)
            exportTask = Task {
                do {
                    var preview = false
                    #if DEBUG
                    if let fixture = CommandLine.arguments.firstIndex(of: "--snapshot-fixture"),
                       CommandLine.arguments.indices.contains(fixture + 1) {
                        try SnapshotPreview.load(
                            from: URL(fileURLWithPath: CommandLine.arguments[fixture + 1]), into: store)
                        preview = true
                    }
                    #endif
                    if !preview {
                        await store.refresh()
                        await store.limits.refresh()
                    }
                    try SnapshotExporter.write(store: store, to: directory, allowEmpty: preview)
                    NSApp.terminate(nil)
                } catch {
                    FileHandle.standardError.write(Data("Snapshot failed: \(error)\n".utf8))
                    NSApp.terminate(nil)
                }
            }
        } else {
            logger.notice("AISAD starting normal menu-bar session")
            store.start()
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        logger.notice("AISAD terminating")
        exportTask?.cancel()
        store.stop()
    }
}
