import SwiftUI

struct APIListView: View {
    @Environment(ConnectionManager.self) private var connectionManager
    @State private var endpoints: [APIEndpoint] = []
    @State private var selectedEndpointID: UUID?
    @State private var showAddSheet = false
    @State private var pushStatus: String = ""

    var body: some View {
        HSplitView {
            // Left: List
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("API Endpoints")
                        .font(.headline)
                    Spacer()
                    Menu {
                        Button("Custom Endpoint") {
                            let endpoint = APIEndpoint(
                                name: "New Endpoint",
                                url: "https://",
                                headers: ["Accept": "application/json"],
                                authToken: "",
                                pollIntervalSeconds: 60,
                                jsonPaths: [:],
                                enabled: false
                            )
                            endpoints.append(endpoint)
                            selectedEndpointID = endpoint.id
                        }
                        Divider()
                        ForEach(APITemplate.all) { template in
                            Button(template.name) {
                                var newEndpoint = template
                                newEndpoint.id = UUID()
                                endpoints.append(newEndpoint)
                                selectedEndpointID = newEndpoint.id
                            }
                        }
                    } label: {
                        Label("Add", systemImage: "plus")
                    }
                }

                List(selection: $selectedEndpointID) {
                    ForEach($endpoints) { $endpoint in
                        HStack {
                            VStack(alignment: .leading) {
                                Text(endpoint.name)
                                    .font(.body.weight(.medium))
                                Text(endpoint.url)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                            Spacer()
                            Toggle("", isOn: $endpoint.enabled)
                                .labelsHidden()
                        }
                        .tag(endpoint.id)
                    }
                    .onDelete { indexSet in
                        endpoints.remove(atOffsets: indexSet)
                    }
                }

                HStack {
                    Button("Push All to Device") {
                        let enabled = endpoints.filter(\.enabled)
                        for endpoint in enabled {
                            connectionManager.send(.setAPI(endpoint))
                        }
                        pushStatus = "Sent \(enabled.count) endpoint(s)"
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                            pushStatus = ""
                        }
                    }
                    .disabled(!connectionManager.isConnected || endpoints.filter(\.enabled).isEmpty)

                    if !pushStatus.isEmpty {
                        Text(pushStatus)
                            .font(.caption)
                            .foregroundStyle(.green)
                    }
                }
            }
            .padding()
            .frame(minWidth: 300)

            // Right: Editor
            if let id = selectedEndpointID,
               let index = endpoints.firstIndex(where: { $0.id == id }) {
                endpointEditor(index: index)
            } else {
                VStack {
                    Text("Select an endpoint to edit")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .navigationTitle("API Configuration")
    }

    private func endpointEditor(index: Int) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Endpoint Settings")
                    .font(.headline)

                TextField("Name", text: $endpoints[index].name)
                    .textFieldStyle(.roundedBorder)

                TextField("URL", text: $endpoints[index].url)
                    .textFieldStyle(.roundedBorder)

                TextField("Auth Token", text: $endpoints[index].authToken)
                    .textFieldStyle(.roundedBorder)

                LabeledContent("Poll Interval (sec)") {
                    TextField("", value: $endpoints[index].pollIntervalSeconds, format: .number)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 80)
                }

                Toggle("Enabled", isOn: $endpoints[index].enabled)

                GroupBox("JSON Path Mappings") {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(Array(endpoints[index].jsonPaths.keys.sorted()), id: \.self) { key in
                            HStack {
                                Text(key)
                                    .frame(width: 100, alignment: .leading)
                                    .font(.caption.monospaced())
                                Text(endpoints[index].jsonPaths[key] ?? "")
                                    .font(.caption.monospaced())
                                    .foregroundStyle(.secondary)
                                Spacer()
                                Button {
                                    endpoints[index].jsonPaths.removeValue(forKey: key)
                                } label: {
                                    Image(systemName: "minus.circle")
                                }
                                .buttonStyle(.borderless)
                            }
                        }

                        AddJSONPathRow { field, path in
                            endpoints[index].jsonPaths[field] = path
                        }
                    }
                }

                Spacer()

                Button("Push to Device") {
                    connectionManager.send(.setAPI(endpoints[index]))
                    pushStatus = "Sent!"
                }
                .disabled(!connectionManager.isConnected)

                Button("Delete Endpoint", role: .destructive) {
                    endpoints.remove(at: index)
                    selectedEndpointID = nil
                }
            }
            .padding()
        }
        .frame(minWidth: 300)
    }
}

private struct AddJSONPathRow: View {
    @State private var field = ""
    @State private var path = ""
    var onAdd: (String, String) -> Void

    var body: some View {
        HStack {
            TextField("Field", text: $field)
                .textFieldStyle(.roundedBorder)
                .frame(width: 100)
            TextField("JSON Path", text: $path)
                .textFieldStyle(.roundedBorder)
            Button {
                guard !field.isEmpty, !path.isEmpty else { return }
                onAdd(field, path)
                field = ""
                path = ""
            } label: {
                Image(systemName: "plus.circle")
            }
            .buttonStyle(.borderless)
            .disabled(field.isEmpty || path.isEmpty)
        }
    }
}
