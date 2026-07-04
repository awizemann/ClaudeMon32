import SwiftUI

/// Wrapper that pulls ObservableObject instances out of the @Observable
/// ConnectionManager and passes them to the content view via @ObservedObject,
/// bridging the two observation systems so @Published changes trigger re-renders.
struct DeviceListView: View {
    @Environment(ConnectionManager.self) private var connectionManager

    var body: some View {
        DeviceListContent(
            connectionManager: connectionManager,
            ble: connectionManager.bleManager,
            usb: connectionManager.usbManager
        )
    }
}

private struct DeviceListContent: View {
    let connectionManager: ConnectionManager
    @ObservedObject var ble: BLEManager
    @ObservedObject var usb: USBSerialManager

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                connectionStatusBanner

                // BLE Section
                GroupBox {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Label("Bluetooth Devices", systemImage: "antenna.radiowaves.left.and.right")
                                .font(.headline)
                            Spacer()
                            if ble.isScanning {
                                ProgressView()
                                    .controlSize(.small)
                            }
                            Button(ble.isScanning ? "Stop" : "Scan") {
                                if ble.isScanning {
                                    ble.stopScan()
                                } else {
                                    ble.startScan()
                                }
                            }
                        }

                        if ble.bluetoothState != .poweredOn {
                            Label("Bluetooth is not available", systemImage: "exclamationmark.triangle")
                                .foregroundStyle(.orange)
                                .font(.callout)
                        }

                        if ble.discoveredDevices.isEmpty && !ble.isScanning {
                            Text("No devices found. Tap Scan to search.")
                                .foregroundStyle(.secondary)
                                .font(.callout)
                        }

                        ForEach(ble.discoveredDevices) { device in
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(device.name)
                                        .font(.body.weight(.medium))
                                    Text("RSSI: \(device.rssi) dBm")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                signalIcon(rssi: device.rssi)
                                if ble.connectedPeripheral?.identifier == device.peripheral.identifier {
                                    Button("Disconnect") {
                                        ble.disconnect()
                                    }
                                    .tint(.red)
                                } else {
                                    Button("Connect") {
                                        ble.connect(device.peripheral)
                                    }
                                }
                            }
                            .padding(.vertical, 4)
                            Divider()
                        }
                    }
                }

                // USB Section
                GroupBox {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Label("USB Serial Ports", systemImage: "cable.connector")
                                .font(.headline)
                            Spacer()
                            Button("Refresh") {
                                usb.scanPorts()
                            }
                        }

                        if usb.availablePorts.isEmpty {
                            Text("No USB serial devices detected.")
                                .foregroundStyle(.secondary)
                                .font(.callout)
                        }

                        ForEach(usb.availablePorts, id: \.self) { port in
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(port.split(separator: "/").last.map(String.init) ?? port)
                                        .font(.body.weight(.medium))
                                    Text(port)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                if usb.connectedPort == port {
                                    Button("Disconnect") {
                                        usb.close()
                                    }
                                    .tint(.red)
                                } else {
                                    Button("Connect") {
                                        _ = usb.open(port: port)
                                    }
                                }
                            }
                            .padding(.vertical, 4)
                            Divider()
                        }
                    }
                }
            }
            .padding()
        }
        .navigationTitle("Devices")
    }

    private var connectionStatusBanner: some View {
        HStack {
            Circle()
                .fill(connectionManager.isConnected ? .green : .red)
                .frame(width: 10, height: 10)
            Text(connectionManager.isConnected
                 ? "Connected via \(connectionManager.activeTransport)"
                 : "Disconnected")
                .font(.callout.weight(.medium))
            Spacer()
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(connectionManager.isConnected
                      ? Color.green.opacity(0.1)
                      : Color.red.opacity(0.1))
        )
    }

    private func signalIcon(rssi: Int) -> some View {
        let level: String
        if rssi > -50 {
            level = "wifi"
        } else if rssi > -70 {
            level = "wifi"
        } else {
            level = "wifi.exclamationmark"
        }
        return Image(systemName: level)
            .foregroundStyle(rssi > -70 ? .green : .orange)
    }
}
