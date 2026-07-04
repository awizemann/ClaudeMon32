import Foundation
import IOKit
import IOKit.serial

final class USBSerialManager: ObservableObject {
    @Published var availablePorts: [String] = []
    @Published var isConnected = false
    @Published var connectedPort: String = ""

    // Debug state
    @Published var debugLog: String = ""
    @Published var readThreadAlive = false
    @Published var totalBytesRead: Int = 0
    @Published var readErrors: Int = 0

    var onDataReceived: ((String) -> Void)?

    private var fileDescriptor: Int32 = -1
    private var readThread: Thread?
    private var shouldRead = false
    private var portScanTimer: Timer?

    init() {
        startPortScanning()
    }

    deinit {
        stopPortScanning()
        close()
    }

    private func log(_ msg: String) {
        print("[USB] \(msg)")
        DispatchQueue.main.async {
            self.debugLog += msg + "\n"
            if self.debugLog.count > 800 {
                self.debugLog = String(self.debugLog.suffix(800))
            }
        }
    }

    // MARK: - Port Discovery

    func startPortScanning() {
        scanPorts()
        portScanTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            self?.scanPorts()
        }
    }

    func stopPortScanning() {
        portScanTimer?.invalidate()
        portScanTimer = nil
    }

    func scanPorts() {
        let fileManager = FileManager.default
        do {
            let devContents = try fileManager.contentsOfDirectory(atPath: "/dev")
            let modems = devContents
                .filter { $0.hasPrefix("cu.usbmodem") || $0.hasPrefix("cu.usbserial") || $0.hasPrefix("cu.SLAB") }
                .map { "/dev/\($0)" }
                .sorted()
            DispatchQueue.main.async {
                self.availablePorts = modems
            }
        } catch {
            DispatchQueue.main.async {
                self.availablePorts = []
            }
        }
    }

    // MARK: - Connection

    func open(port: String, baudRate: speed_t = 115200) -> Bool {
        guard fileDescriptor == -1 else {
            log("open: already open")
            return false
        }

        log("Opening \(port)...")

        fileDescriptor = Darwin.open(port, O_RDWR | O_NOCTTY | O_NONBLOCK)
        guard fileDescriptor != -1 else {
            log("open failed: errno=\(errno)")
            return false
        }
        log("Opened fd=\(fileDescriptor)")

        // Raw mode configuration
        var options = termios()
        tcgetattr(fileDescriptor, &options)

        // Clear all flags for raw mode
        options.c_iflag = 0
        options.c_oflag = 0
        options.c_lflag = 0
        options.c_cflag = UInt(CS8 | CREAD | CLOCAL)

        cfsetispeed(&options, baudRate)
        cfsetospeed(&options, baudRate)

        // Non-blocking reads: return immediately
        options.c_cc.16 = 0  // VMIN
        options.c_cc.17 = 0  // VTIME

        let setResult = tcsetattr(fileDescriptor, TCSANOW, &options)
        log("tcsetattr result=\(setResult)")

        // Flush stale kernel buffers
        tcflush(fileDescriptor, TCIOFLUSH)

        // Keep O_NONBLOCK — we use poll() in the read loop
        shouldRead = true
        startReadThread()

        DispatchQueue.main.async {
            self.isConnected = true
            self.connectedPort = port
        }
        log("Connected")
        return true
    }

    func close() {
        log("Closing...")
        shouldRead = false
        readThread = nil

        if fileDescriptor != -1 {
            Darwin.close(fileDescriptor)
            fileDescriptor = -1
        }

        DispatchQueue.main.async {
            self.isConnected = false
            self.connectedPort = ""
            self.readThreadAlive = false
        }
    }

    // MARK: - Data Transfer

    func send(_ string: String) {
        guard fileDescriptor != -1,
              let data = (string + "\n").data(using: .utf8) else {
            log("send: fd invalid or encode failed")
            return
        }

        var totalWritten = 0
        data.withUnsafeBytes { buffer in
            guard let pointer = buffer.baseAddress else { return }
            totalWritten = write(fileDescriptor, pointer, data.count)
        }

        if totalWritten < 0 {
            log("write failed: errno=\(errno) (\(String(cString: strerror(errno))))")
        } else {
            log("Sent \(totalWritten) bytes: \(string.prefix(80))")
        }

        tcdrain(fileDescriptor)
    }

    // MARK: - Read Thread

    private func startReadThread() {
        let thread = Thread { [weak self] in
            self?.readLoop()
        }
        thread.name = "USBSerialRead"
        thread.qualityOfService = .userInitiated
        readThread = thread
        thread.start()
    }

    private func readLoop() {
        let fd = fileDescriptor
        log("readLoop started, fd=\(fd)")
        DispatchQueue.main.async { self.readThreadAlive = true }

        var buffer = [UInt8](repeating: 0, count: 2048)
        var accumulated = ""
        var loopCount = 0

        while shouldRead && fileDescriptor != -1 {
            // Use poll() — much simpler than select() in Swift, no fd_set issues
            var pfd = pollfd(fd: fd, events: Int16(POLLIN), revents: 0)
            let pollResult = poll(&pfd, 1, 200)  // 200ms timeout

            if pollResult < 0 {
                let err = errno
                if err == EINTR { continue }
                log("poll error: errno=\(err) (\(String(cString: strerror(err))))")
                DispatchQueue.main.async { [weak self] in self?.readErrors += 1 }
                break
            }

            if pollResult == 0 {
                continue  // timeout, no data
            }

            // Check for errors on the fd
            if pfd.revents & Int16(POLLHUP | POLLERR | POLLNVAL) != 0 {
                log("poll: device error/hangup (revents=\(pfd.revents))")
                DispatchQueue.main.async { [weak self] in
                    self?.readErrors += 1
                    self?.close()
                }
                break
            }

            // Data available
            loopCount += 1
            let bytesRead = read(fd, &buffer, buffer.count)

            if bytesRead > 0 {
                DispatchQueue.main.async { self.totalBytesRead += bytesRead }

                if loopCount <= 30 || loopCount % 50 == 0 {
                    log("read \(bytesRead) bytes (#\(loopCount))")
                }

                if let chunk = String(bytes: buffer[0..<bytesRead], encoding: .utf8) {
                    accumulated += chunk

                    while let newlineRange = accumulated.range(of: "\n") {
                        let line = String(accumulated[accumulated.startIndex..<newlineRange.lowerBound])
                            .trimmingCharacters(in: .init(charactersIn: "\r"))
                        accumulated = String(accumulated[newlineRange.upperBound...])
                        if !line.isEmpty {
                            let finalLine = line
                            if loopCount <= 30 {
                                log("Line: \(finalLine.prefix(100))")
                            }
                            DispatchQueue.main.async { [weak self] in
                                self?.onDataReceived?(finalLine)
                            }
                        }
                    }
                } else {
                    log("UTF-8 decode failed for \(bytesRead) bytes")
                }
            } else if bytesRead == 0 {
                continue
            } else {
                let err = errno
                if err == EAGAIN || err == EINTR { continue }
                log("read error: errno=\(err) (\(String(cString: strerror(err))))")
                DispatchQueue.main.async { [weak self] in
                    self?.readErrors += 1
                    self?.close()
                }
                break
            }
        }

        log("readLoop exited (loops=\(loopCount))")
        DispatchQueue.main.async { self.readThreadAlive = false }
    }
}
