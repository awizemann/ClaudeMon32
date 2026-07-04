import SwiftUI

enum SidebarItem: String, CaseIterable, Identifiable {
    case devices = "Devices"
    case dashboard = "Dashboard"
    case display = "Display"
    case api = "API"
    case settings = "Settings"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .devices: return "antenna.radiowaves.left.and.right"
        case .dashboard: return "gauge.with.dots.needle.33percent"
        case .display: return "rectangle.on.rectangle"
        case .api: return "cloud"
        case .settings: return "gearshape"
        }
    }

    var section: SidebarSection {
        switch self {
        case .devices: return .connection
        case .dashboard: return .monitoring
        case .display: return .configuration
        case .api: return .configuration
        case .settings: return .configuration
        }
    }
}

enum SidebarSection: String, CaseIterable {
    case connection = "Connection"
    case monitoring = "Monitoring"
    case configuration = "Configuration"

    var items: [SidebarItem] {
        SidebarItem.allCases.filter { $0.section == self }
    }
}

struct ContentView: View {
    @Environment(ConnectionManager.self) private var connectionManager
    @State private var selectedItem: SidebarItem? = .devices

    var body: some View {
        NavigationSplitView {
            List(selection: $selectedItem) {
                ForEach(SidebarSection.allCases, id: \.self) { section in
                    Section(section.rawValue) {
                        ForEach(section.items) { item in
                            Label(item.rawValue, systemImage: item.icon)
                                .tag(item)
                        }
                    }
                }
            }
            .listStyle(.sidebar)
            .navigationSplitViewColumnWidth(min: 180, ideal: 200)
            .safeAreaInset(edge: .bottom) {
                connectionFooter
                    .padding(12)
            }
        } detail: {
            switch selectedItem {
            case .devices:
                DeviceListView()
            case .dashboard:
                DashboardView()
            case .display:
                LayoutEditorView()
            case .api:
                APIListView()
            case .settings:
                WiFiSettingsView()
            case nil:
                Text("Select an item from the sidebar")
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var connectionFooter: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(connectionManager.isConnected ? .green : .red)
                .frame(width: 8, height: 8)
            Text(connectionManager.isConnected
                 ? connectionManager.activeTransport
                 : "Disconnected")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }
}
