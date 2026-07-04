import SwiftUI

struct WiFiSettingsView: View {
    @Environment(ConnectionManager.self) private var connectionManager
    @State private var ssid: String = ""
    @State private var password: String = ""
    @State private var sendStatus: String = ""
    @State private var isSending = false

    private var state: DeviceState {
        connectionManager.deviceState
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Current Status
                GroupBox {
                    VStack(alignment: .leading, spacing: 8) {
                        Label("Current WiFi Status", systemImage: "wifi")
                            .font(.headline)

                        HStack {
                            Text("Status")
                            Spacer()
                            Circle()
                                .fill(state.wifiConnected ? .green : .red)
                                .frame(width: 8, height: 8)
                            Text(state.wifiConnected ? "Connected" : "Disconnected")
                                .foregroundStyle(.secondary)
                        }

                        if state.wifiConnected && !state.wifiSSID.isEmpty {
                            LabeledContent("Network", value: state.wifiSSID)
                        }
                    }
                }

                // WiFi Configuration
                GroupBox {
                    VStack(alignment: .leading, spacing: 12) {
                        Label("WiFi Configuration", systemImage: "wifi.circle")
                            .font(.headline)

                        Text("Enter WiFi credentials to provision the device.")
                            .font(.callout)
                            .foregroundStyle(.secondary)

                        TextField("SSID (Network Name)", text: $ssid)
                            .textFieldStyle(.roundedBorder)

                        SecureField("Password", text: $password)
                            .textFieldStyle(.roundedBorder)

                        HStack {
                            Button {
                                guard !ssid.isEmpty else { return }
                                isSending = true
                                connectionManager.send(.setWifi(ssid: ssid, password: password))
                                sendStatus = "WiFi credentials sent to device"
                                isSending = false
                                DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                                    sendStatus = ""
                                }
                            } label: {
                                HStack {
                                    if isSending {
                                        ProgressView()
                                            .controlSize(.small)
                                    }
                                    Text("Send to Device")
                                }
                            }
                            .disabled(!connectionManager.isConnected || ssid.isEmpty)

                            if !sendStatus.isEmpty {
                                Label(sendStatus, systemImage: "checkmark.circle")
                                    .font(.caption)
                                    .foregroundStyle(.green)
                            }
                        }
                    }
                }

                if !connectionManager.isConnected {
                    Label(
                        "Connect to a device first to configure WiFi.",
                        systemImage: "exclamationmark.triangle"
                    )
                    .font(.callout)
                    .foregroundStyle(.orange)
                }

                Spacer()
            }
            .padding()
        }
        .navigationTitle("WiFi Settings")
    }
}
