import SwiftUI

struct LayoutEditorView: View {
    @Environment(ConnectionManager.self) private var connectionManager
    @State private var currentLayout = LayoutTemplate.singleValue
    @State private var selectedWidgetID: UUID?
    @State private var showAddWidget = false
    @State private var pushStatus: String = ""

    // Canvas scale: 200x200 device pixels displayed at 400x400
    private let canvasScale: CGFloat = 2.0
    private let deviceWidth: CGFloat = 200
    private let deviceHeight: CGFloat = 200

    var body: some View {
        HSplitView {
            // Left: Canvas
            VStack(spacing: 12) {
                Text("Display Preview")
                    .font(.headline)

                ZStack {
                    // E-ink background
                    Rectangle()
                        .fill(Color(white: 0.85))
                        .frame(
                            width: deviceWidth * canvasScale,
                            height: deviceHeight * canvasScale
                        )
                        .border(Color.gray, width: 1)

                    // Status bar mockup
                    statusBarView

                    // Widgets
                    ForEach(currentLayout.widgets) { widget in
                        widgetView(widget)
                            .onTapGesture {
                                selectedWidgetID = widget.id
                            }
                    }
                }
                .frame(
                    width: deviceWidth * canvasScale,
                    height: deviceHeight * canvasScale
                )
                .clipShape(Rectangle())

                HStack {
                    Button("Push to Device") {
                        connectionManager.send(.setLayout(currentLayout))
                        pushStatus = "Layout sent!"
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                            pushStatus = ""
                        }
                    }
                    .disabled(!connectionManager.isConnected)

                    if !pushStatus.isEmpty {
                        Text(pushStatus)
                            .font(.caption)
                            .foregroundStyle(.green)
                    }
                }

                Spacer()
            }
            .padding()
            .frame(minWidth: 450)

            // Right: Properties
            VStack(alignment: .leading, spacing: 16) {
                templatePicker

                Divider()

                if let widgetID = selectedWidgetID,
                   let index = currentLayout.widgets.firstIndex(where: { $0.id == widgetID }) {
                    widgetEditor(index: index)
                } else {
                    Text("Select a widget to edit its properties")
                        .foregroundStyle(.secondary)
                        .frame(maxHeight: .infinity)
                }
            }
            .padding()
            .frame(minWidth: 250, idealWidth: 280)
        }
        .navigationTitle("Layout Editor")
    }

    // MARK: - Template Picker

    private var templatePicker: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Templates")
                .font(.headline)

            ForEach(LayoutTemplate.all) { template in
                Button {
                    currentLayout = template
                    selectedWidgetID = nil
                } label: {
                    HStack {
                        Text(template.name)
                        Spacer()
                        Text("\(template.widgets.count) widgets")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .buttonStyle(.bordered)
            }
        }
    }

    // MARK: - Widget View

    // MARK: - Status Bar Mockup

    private var statusBarView: some View {
        ZStack {
            Rectangle()
                .fill(Color.black)
                .frame(width: deviceWidth * canvasScale, height: 14 * canvasScale)

            HStack(spacing: 4) {
                // Left: WiFi + BLE grouped
                Image(systemName: "wifi")
                    .font(.system(size: 10 * canvasScale * 0.5))
                    .foregroundStyle(.white)
                Image(systemName: "antenna.radiowaves.left.and.right")
                    .font(.system(size: 9 * canvasScale * 0.5))
                    .foregroundStyle(.white)

                Spacer()

                // Right: Battery
                Image(systemName: "battery.75")
                    .font(.system(size: 12 * canvasScale * 0.5))
                    .foregroundStyle(.white)
            }
            .padding(.horizontal, 6)
            .frame(width: deviceWidth * canvasScale)
        }
        .position(x: deviceWidth * canvasScale / 2, y: 7 * canvasScale)
    }

    private func widgetView(_ widget: Widget) -> some View {
        let isSelected = widget.id == selectedWidgetID
        let radius = CGFloat(widget.cornerRadius) * canvasScale
        return ZStack {
            RoundedRectangle(cornerRadius: radius)
                .stroke(isSelected ? Color.blue : Color.black, lineWidth: isSelected ? 2 : 1)
                .background(
                    RoundedRectangle(cornerRadius: radius)
                        .fill(Color.white.opacity(0.5))
                )

            VStack(spacing: 2) {
                Text(widget.label)
                    .font(.system(size: 10 * canvasScale * 0.4, weight: .medium))
                    .foregroundStyle(.secondary)

                Text(sampleValue(for: widget))
                    .font(.system(size: CGFloat(widget.fontSize) * canvasScale * 0.3, weight: .semibold, design: .rounded))
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)

                Text(widget.valueFormat.displayName)
                    .font(.system(size: 7 * canvasScale * 0.3))
                    .foregroundStyle(.tertiary)
            }
            .padding(4)
        }
        .frame(
            width: CGFloat(widget.width) * canvasScale,
            height: CGFloat(widget.height) * canvasScale
        )
        .position(
            x: (CGFloat(widget.x) + CGFloat(widget.width) / 2) * canvasScale,
            y: (CGFloat(widget.y) + CGFloat(widget.height) / 2) * canvasScale
        )
    }

    private func sampleValue(for widget: Widget) -> String {
        switch widget.valueFormat {
        case .currency: return "$87,432"
        case .percent: return "72.4%"
        case .number: return "1,234"
        case .temperature: return "72.3F"
        case .none:
            switch widget.type {
            case .clock: return "14:30"
            case .sensor: return "22.5"
            default: return "Value"
            }
        }
    }

    // MARK: - Widget Editor

    private func widgetEditor(index: Int) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Widget Properties")
                .font(.headline)

            LabeledContent("Type") {
                Picker("", selection: $currentLayout.widgets[index].type) {
                    ForEach(WidgetType.allCases) { wtype in
                        Text(wtype.displayName).tag(wtype)
                    }
                }
                .labelsHidden()
            }

            TextField("Label", text: $currentLayout.widgets[index].label)
            TextField("Data Binding", text: $currentLayout.widgets[index].dataBinding)

            GroupBox("Position & Size") {
                VStack(spacing: 8) {
                    HStack {
                        Text("X")
                            .frame(width: 30)
                        TextField("", value: $currentLayout.widgets[index].x, format: .number)
                            .textFieldStyle(.roundedBorder)
                        Text("Y")
                            .frame(width: 30)
                        TextField("", value: $currentLayout.widgets[index].y, format: .number)
                            .textFieldStyle(.roundedBorder)
                    }
                    HStack {
                        Text("W")
                            .frame(width: 30)
                        TextField("", value: $currentLayout.widgets[index].width, format: .number)
                            .textFieldStyle(.roundedBorder)
                        Text("H")
                            .frame(width: 30)
                        TextField("", value: $currentLayout.widgets[index].height, format: .number)
                            .textFieldStyle(.roundedBorder)
                    }
                }
            }

            LabeledContent("Font Size") {
                TextField("", value: $currentLayout.widgets[index].fontSize, format: .number)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 60)
            }

            LabeledContent("Value Format") {
                Picker("", selection: $currentLayout.widgets[index].valueFormat) {
                    ForEach(ValueFormat.allCases) { fmt in
                        Text(fmt.displayName).tag(fmt)
                    }
                }
                .labelsHidden()
            }

            LabeledContent("Corner Radius") {
                HStack {
                    Slider(
                        value: Binding(
                            get: { Double(currentLayout.widgets[index].cornerRadius) },
                            set: { currentLayout.widgets[index].cornerRadius = Int($0) }
                        ),
                        in: 0...12,
                        step: 1
                    )
                    Text("\(currentLayout.widgets[index].cornerRadius)")
                        .frame(width: 24)
                        .monospacedDigit()
                }
            }

            Spacer()

            Button("Remove Widget", role: .destructive) {
                currentLayout.widgets.remove(at: index)
                selectedWidgetID = nil
            }
        }
    }
}
