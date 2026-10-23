import Foundation
import Darwin

/// Runs argv directly, drains both pipes, bounds output/time and owns cancellation.
public enum ProcessRunner {
    public static func run(executable: URL, arguments: [String], directory: URL,
                           timeout: TimeInterval = 120, outputLimit: Int = 1_048_576,
                           terminationGrace: TimeInterval = 0) async throws -> Data {
        let job = ProcessJob(outputLimit: outputLimit, terminationGrace: terminationGrace)
        return try await withTaskCancellationHandler {
            try Task.checkCancellation()
            return try await withCheckedThrowingContinuation { continuation in
                job.start(executable: executable, arguments: arguments, directory: directory,
                          timeout: timeout, continuation: continuation)
            }
        } onCancel: {
            job.cancel()
        }
    }
}

private final class ProcessJob: @unchecked Sendable {
    private let lock = NSLock()
    private let process = Process()
    private let stdout = Pipe()
    private let stderr = Pipe()
    private let readers = DispatchGroup()
    private let outputLimit: Int
    private let terminationGrace: TimeInterval
    private var output = Data()
    private var errors = Data()
    private var failure: (any Error)?
    private var continuation: CheckedContinuation<Data, any Error>?
    private var watchdog: DispatchWorkItem?
    private var completed = false

    init(outputLimit: Int, terminationGrace: TimeInterval) {
        self.outputLimit = outputLimit
        self.terminationGrace = max(0, min(terminationGrace, 1))
    }

    func start(executable: URL, arguments: [String], directory: URL, timeout: TimeInterval,
               continuation: CheckedContinuation<Data, any Error>) {
        lock.lock()
        self.continuation = continuation
        if let failure {
            completed = true
            lock.unlock()
            continuation.resume(throwing: failure)
            return
        }
        process.executableURL = executable
        process.arguments = arguments
        process.currentDirectoryURL = directory
        process.standardInput = FileHandle.nullDevice
        process.standardOutput = stdout
        process.standardError = stderr
        readers.enter()
        readers.enter()
        process.terminationHandler = { [self] _ in readers.wait(); finish() }
        do {
            try process.run()
            try? stdout.fileHandleForWriting.close()
            try? stderr.fileHandleForWriting.close()
            DispatchQueue.global().async { [self] in read(stdout.fileHandleForReading, isError: false) }
            DispatchQueue.global().async { [self] in read(stderr.fileHandleForReading, isError: true) }
            let watchdog = DispatchWorkItem { [weak self] in self?.abort(CollectorError.timedOut) }
            self.watchdog = watchdog
            DispatchQueue.global().asyncAfter(deadline: .now() + timeout, execute: watchdog)
            lock.unlock()
        } catch {
            self.continuation = nil
            completed = true
            process.terminationHandler = nil
            readers.leave()
            readers.leave()
            lock.unlock()
            continuation.resume(throwing: error)
        }
    }

    func cancel() { abort(CancellationError()) }

    private func abort(_ error: any Error) {
        lock.lock()
        guard !completed else { lock.unlock(); return }
        if failure == nil { failure = error }
        if process.isRunning {
            terminateLocked()
        }
        lock.unlock()
    }

    private func terminateLocked() {
        guard terminationGrace > 0 else {
            kill(process.processIdentifier, SIGKILL)
            return
        }
        // The quota reader handles TERM by cleaning up its own CLI process groups.
        kill(process.processIdentifier, SIGTERM)
        DispatchQueue.global().asyncAfter(deadline: .now() + terminationGrace) { [weak self] in
            guard let self else { return }
            self.lock.lock()
            defer { self.lock.unlock() }
            if !self.completed, self.process.isRunning {
                kill(self.process.processIdentifier, SIGKILL)
            }
        }
    }

    private func receive(_ data: Data, isError: Bool) {
        guard !data.isEmpty else { return }
        lock.lock()
        if isError {
            if errors.count + data.count <= 16_384 { errors.append(data) }
        } else if output.count + data.count <= outputLimit {
            output.append(data)
        } else {
            if failure == nil { failure = CollectorError.outputTooLarge }
            if process.isRunning { terminateLocked() }
        }
        lock.unlock()
    }

    private func read(_ handle: FileHandle, isError: Bool) {
        defer { readers.leave(); try? handle.close() }
        do {
            while let data = try handle.read(upToCount: 8192), !data.isEmpty {
                receive(data, isError: isError)
            }
        } catch { abort(error) }
    }

    private func finish() {
        lock.lock()
        guard !completed else { lock.unlock(); return }
        completed = true
        process.terminationHandler = nil
        watchdog?.cancel()
        let continuation = self.continuation
        self.continuation = nil
        let failure = failure
        let output = output
        let detail = String(decoding: errors.prefix(4096), as: UTF8.self)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let status = process.terminationStatus
        lock.unlock()
        if let failure { continuation?.resume(throwing: failure) }
        else if status != 0 {
            continuation?.resume(throwing: CollectorError.failed(
                detail.isEmpty ? "Collection failed (exit \(status)). Refresh to retry." : detail))
        } else { continuation?.resume(returning: output) }
    }
}
