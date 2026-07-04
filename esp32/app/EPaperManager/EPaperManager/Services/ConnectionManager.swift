import Foundation
import Combine

@Observable
final class ConnectionManager {
    let bleManager = BLEManager()
    let usbManager = USBSerialManager()
    let deviceState = DeviceState()

    // Stored properties — bridged from @Published via Combine so @Observable tracks them
    var isConnected: Bool = false
    var activeTransport: String = "None"

    var lastResponse: String = ""
    var lastError: String = ""

    // Debug
    var lastRawReceived: String = ""
    var receiveCount: Int = 0
    var parseLog: String = ""

    private var cancellables = Set<AnyCancellable>()
    private var receiveBuffer = ""

    init() {
        setupCallbacks()
        observeConnectionState()
    }

    private func plog(_ msg: String) {
        print("[CM] \(msg)")
        parseLog += msg + "\n"
        if parseLog.count > 1000 {
            parseLog = String(parseLog.suffix(1000))
        }
    }

    // MARK: - Send Commands

    func send(_ command: DeviceCommand) {
        guard let json = DeviceProtocol.encode(command) else {
            lastError = "Failed to encode command"
            return
        }
        lastError = ""
        plog("TX: \(json.prefix(80))")
        sendRaw(json)
    }

    func sendRaw(_ string: String) {
        if bleManager.isConnected {
            bleManager.send(string)
        } else if usbManager.isConnected {
            usbManager.send(string)
        } else {
            lastError = "No active connection"
        }
    }

    func requestStatus() {
        send(.getStatus)
    }

    func sendPing() {
        send(.ping)
    }

    // MARK: - Receive

    private func setupCallbacks() {
        bleManager.onDataReceived = { [weak self] data in
            self?.handleReceived(data, source: "BLE")
        }

        usbManager.onDataReceived = { [weak self] data in
            self?.handleReceived(data, source: "USB")
        }
    }

    private func handleReceived(_ data: String, source: String) {
        receiveCount += 1
        lastRawReceived = data
        plog("RX[\(source)] #\(receiveCount) len=\(data.count): \(data.prefix(60))...")

        receiveBuffer += data
        plog("Buffer len=\(receiveBuffer.count)")

        // Split on newlines (USB sends \n-terminated lines)
        while let newlineRange = receiveBuffer.range(of: "\n") {
            let line = String(receiveBuffer[receiveBuffer.startIndex..<newlineRange.lowerBound])
                .trimmingCharacters(in: .whitespacesAndNewlines)
            receiveBuffer = String(receiveBuffer[newlineRange.upperBound...])
            if !line.isEmpty { tryProcessLine(line) }
        }

        // Try to extract complete JSON from remaining buffer
        let trimmed = receiveBuffer.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            receiveBuffer = ""
            return
        }

        // Check if buffer contains at least one complete JSON object
        // by counting brace depth
        if trimmed.hasPrefix("{") {
            var depth = 0
            var hasComplete = false
            for c in trimmed {
                if c == "{" { depth += 1 }
                else if c == "}" {
                    depth -= 1
                    if depth == 0 { hasComplete = true; break }
                }
            }

            if hasComplete {
                plog("Complete JSON found in buffer, processing...")
                let objects = splitJSONObjects(trimmed)
                plog("Split into \(objects.count) object(s)")
                for (i, obj) in objects.enumerated() {
                    plog("  obj[\(i)] len=\(obj.count): \(obj.prefix(60))...")
                    if let response = DeviceProtocol.decode(obj) {
                        lastResponse = obj
                        deviceState.update(from: response)
                        plog("  -> decoded OK, cmd=\(response.cmd ?? "nil"), has data=\(response.data != nil)")
                    } else {
                        plog("  -> decode FAILED")
                    }
                }
                // Remove the processed portion, keep any trailing partial
                let processedLength = objects.reduce(0) { $0 + $1.count }
                if processedLength >= trimmed.count {
                    receiveBuffer = ""
                } else {
                    receiveBuffer = String(trimmed.suffix(trimmed.count - processedLength))
                }
            } else {
                plog("Partial JSON, waiting for more data...")
                // Keep buffer as-is for next chunk
            }
        } else {
            // Doesn't start with { — non-JSON debug line, discard
            plog("Discarding non-JSON: \(trimmed.prefix(60))")
            receiveBuffer = ""
        }
    }

    @discardableResult
    private func tryProcessLine(_ line: String) -> Bool {
        let clean = line.trimmingCharacters(in: .whitespacesAndNewlines)
        guard clean.hasPrefix("{") else {
            plog("Line not JSON: \(clean.prefix(60))")
            return false
        }

        let objects = splitJSONObjects(clean)
        var anySuccess = false
        for obj in objects {
            if let response = DeviceProtocol.decode(obj) {
                lastResponse = obj
                deviceState.update(from: response)
                plog("Parsed line OK: cmd=\(response.cmd ?? "nil")")
                anySuccess = true
            }
        }
        return anySuccess
    }

    /// Splits `{"a":1}{"b":2}` into `["{"a":1}", "{"b":2}"]`
    private func splitJSONObjects(_ input: String) -> [String] {
        var objects: [String] = []
        var depth = 0
        var start = input.startIndex

        for i in input.indices {
            let c = input[i]
            if c == "{" {
                if depth == 0 { start = i }
                depth += 1
            } else if c == "}" {
                depth -= 1
                if depth == 0 {
                    let obj = String(input[start...i])
                    objects.append(obj)
                }
            }
        }
        return objects
    }

    // MARK: - Connection State

    private func observeConnectionState() {
        bleManager.$isConnected
            .combineLatest(usbManager.$isConnected)
            .receive(on: DispatchQueue.main)
            .sink { [weak self] bleConnected, usbConnected in
                guard let self else { return }
                let wasConnected = self.isConnected
                let nowConnected = bleConnected || usbConnected

                self.isConnected = nowConnected

                if bleConnected && usbConnected {
                    self.activeTransport = "BLE + USB"
                    self.deviceState.connectionType = .both
                } else if bleConnected {
                    self.activeTransport = "BLE"
                    self.deviceState.connectionType = .ble
                } else if usbConnected {
                    self.activeTransport = "USB"
                    self.deviceState.connectionType = .usb
                } else {
                    self.activeTransport = "None"
                    self.deviceState.connectionType = .none
                    self.deviceState.reset()
                }

                self.deviceState.isConnected = nowConnected

                if !wasConnected && nowConnected {
                    self.receiveBuffer = ""
                    self.receiveCount = 0
                    self.parseLog = ""
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                        self.requestStatus()
                    }
                }
            }
            .store(in: &cancellables)
    }
}
