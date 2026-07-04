import SwiftUI

struct DashboardView: View {
    @Environment(ConnectionManager.self) private var connectionManager

    var body: some View {
        DashboardContent(
            connectionManager: connectionManager,
            usb: connectionManager.usbManager
        )
    }
}

private struct DashboardContent: View {
    let connectionManager: ConnectionManager
    @ObservedObject var usb: USBSerialManager
    @State private var showPingResponse = false

    private var state: DeviceState {
        connectionManager.deviceState
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if !connectionManager.isConnected {
                    disconnectedBanner
                } else {
                    deviceInfoSection
                    connectivitySection
                    sensorSection
                    audioSection
                    actionsSection
                    debugSection
                }
            }
            .padding()
        }
        .navigationTitle("Dashboard")
        .onAppear {
            if connectionManager.isConnected {
                connectionManager.requestStatus()
            }
        }
        .onChange(of: connectionManager.isConnected) { _, connected in
            if connected {
                connectionManager.requestStatus()
            }
        }
    }

    private var disconnectedBanner: some View {
        VStack(spacing: 12) {
            Image(systemName: "antenna.radiowaves.left.and.right.slash")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            Text("No Device Connected")
                .font(.title2.weight(.medium))
            Text("Connect to a device using the Devices tab.")
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, minHeight: 200)
    }

    private var deviceInfoSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                Label("Device Info", systemImage: "cpu")
                    .font(.headline)

                LabeledContent("Chip", value: state.chipModel.isEmpty ? "--" : state.chipModel)
                LabeledContent("MAC", value: state.macAddress.isEmpty ? "--" : state.macAddress)
                LabeledContent("Firmware", value: state.firmwareVersion.isEmpty ? "--" : state.firmwareVersion)
                LabeledContent("Free Heap", value: state.freeHeap > 0 ? formatBytes(state.freeHeap) : "--")
                LabeledContent("Transport", value: connectionManager.activeTransport)
                LabeledContent("Display Layout", value: state.hasLayout ? "Configured" : "None")
                HStack {
                    Text("Battery")
                    Spacer()
                    if state.batteryPercent > 0 {
                        Image(systemName: batteryIconName(state.batteryPercent))
                            .foregroundStyle(state.batteryPercent <= 15 ? .red : .primary)
                        Text("\(state.batteryPercent)%")
                            .foregroundStyle(state.batteryPercent <= 15 ? .red : .primary)
                    } else {
                        Text("--")
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private var connectivitySection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                Label("Connectivity", systemImage: "network")
                    .font(.headline)

                HStack {
                    Text("WiFi")
                    Spacer()
                    Circle()
                        .fill(state.wifiConnected ? .green : .red)
                        .frame(width: 8, height: 8)
                    Text(state.wifiConnected ? "Connected" : "Disconnected")
                        .foregroundStyle(.secondary)
                }

                if state.wifiConnected {
                    if !state.wifiSSID.isEmpty {
                        LabeledContent("SSID", value: state.wifiSSID)
                    }
                    if !state.wifiIP.isEmpty {
                        LabeledContent("IP Address", value: state.wifiIP)
                    }
                    if state.wifiRSSI != 0 {
                        LabeledContent("Signal", value: "\(state.wifiRSSI) dBm")
                    }
                }

                HStack {
                    Text("BLE")
                    Spacer()
                    Circle()
                        .fill(state.bleConnected ? .green : .gray)
                        .frame(width: 8, height: 8)
                    Text(state.bleConnected ? "Connected" : "Not connected")
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private var sensorSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                Label("Sensors", systemImage: "thermometer.medium")
                    .font(.headline)

                HStack(spacing: 20) {
                    VStack {
                        Text(String(format: "%.1f\u{00B0}C", state.temperature))
                            .font(.system(size: 36, weight: .medium, design: .rounded))
                        Text("Temperature")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)

                    Divider()
                        .frame(height: 50)

                    VStack {
                        Text(String(format: "%.1f%%", state.humidity))
                            .font(.system(size: 36, weight: .medium, design: .rounded))
                        Text("Humidity")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                }
                .padding(.vertical, 8)
            }
        }
    }

    private var audioSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                Label("Audio", systemImage: "speaker.wave.2")
                    .font(.headline)

                HStack {
                    Text("Speaker")
                    Spacer()
                    Circle()
                        .fill(state.audioEnabled ? .green : .gray)
                        .frame(width: 8, height: 8)
                    Text(state.audioEnabled ? "Enabled" : "Disabled")
                        .foregroundStyle(.secondary)
                }

                if state.audioEnabled {
                    LabeledContent("Volume", value: "\(state.audioVolume)%")
                }

                HStack {
                    Button("Enable") {
                        connectionManager.send(.setAudio(enabled: true, volume: state.audioVolume))
                    }
                    .disabled(state.audioEnabled)

                    Button("Disable") {
                        connectionManager.send(.setAudio(enabled: false, volume: state.audioVolume))
                    }
                    .disabled(!state.audioEnabled)

                    Spacer()

                    Stepper("Vol: \(state.audioVolume)%", value: Binding(
                        get: { state.audioVolume },
                        set: { newVal in
                            connectionManager.send(.setAudio(enabled: state.audioEnabled, volume: newVal))
                        }
                    ), in: 0...100, step: 10)
                    .frame(width: 180)
                }
            }
        }
    }

    private var actionsSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                Label("Actions", systemImage: "bolt.fill")
                    .font(.headline)

                HStack {
                    Button("Refresh Status") {
                        connectionManager.requestStatus()
                    }

                    Button("Ping") {
                        connectionManager.sendPing()
                        showPingResponse = true
                    }
                }

                // Always show last response and raw data for diagnostics
                VStack(alignment: .leading, spacing: 4) {
                    Text("Received \(connectionManager.receiveCount) message(s)")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    if !connectionManager.lastResponse.isEmpty {
                        Text("Last JSON:")
                            .font(.caption.weight(.medium))
                        Text(connectionManager.lastResponse.prefix(300))
                            .font(.caption2.monospaced())
                            .foregroundStyle(.secondary)
                            .lineLimit(4)
                    }

                    if !connectionManager.lastRawReceived.isEmpty {
                        Text("Last raw:")
                            .font(.caption.weight(.medium))
                        Text(connectionManager.lastRawReceived.prefix(200))
                            .font(.caption2.monospaced())
                            .foregroundStyle(.orange)
                            .lineLimit(3)
                    }
                }
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(nsColor: .controlBackgroundColor))
                .clipShape(RoundedRectangle(cornerRadius: 6))

                if !connectionManager.lastError.isEmpty {
                    Label(connectionManager.lastError, systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            }
        }
    }

    private var debugSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                Label("Debug", systemImage: "ladybug")
                    .font(.headline)

                LabeledContent("Read thread", value: usb.readThreadAlive ? "alive" : "DEAD")
                LabeledContent("Total bytes read", value: "\(usb.totalBytesRead)")
                LabeledContent("Read errors", value: "\(usb.readErrors)")

                Text("Parse Log:")
                    .font(.caption.weight(.medium))
                ScrollView {
                    Text(connectionManager.parseLog)
                        .font(.caption2.monospaced())
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 200)
                .padding(6)
                .background(Color.black.opacity(0.05))
                .clipShape(RoundedRectangle(cornerRadius: 4))

                if !usb.debugLog.isEmpty {
                    Text("USB Log:")
                        .font(.caption.weight(.medium))
                    Text(usb.debugLog)
                        .font(.caption2.monospaced())
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(6)
                        .background(Color.black.opacity(0.05))
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                }
            }
        }
    }

    private func batteryIconName(_ percent: Int) -> String {
        switch percent {
        case 0...10: return "battery.0"
        case 11...37: return "battery.25"
        case 38...62: return "battery.50"
        case 63...87: return "battery.75"
        default: return "battery.100"
        }
    }

    private func formatBytes(_ bytes: Int) -> String {
        if bytes >= 1024 * 1024 {
            return String(format: "%.1f MB", Double(bytes) / 1_048_576)
        } else if bytes >= 1024 {
            return String(format: "%.1f KB", Double(bytes) / 1024)
        }
        return "\(bytes) B"
    }
}
