import Foundation

enum WidgetType: String, Codable, CaseIterable, Identifiable {
    case text
    case number
    case clock
    case sensor
    case chart

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .text: return "Text"
        case .number: return "Number"
        case .clock: return "Clock"
        case .sensor: return "Sensor"
        case .chart: return "Chart"
        }
    }
}

enum ValueFormat: String, Codable, CaseIterable, Identifiable {
    case none = ""
    case currency = "currency"
    case percent = "percent"
    case number = "number"
    case temperature = "temperature"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .none: return "None"
        case .currency: return "Currency ($)"
        case .percent: return "Percent (%)"
        case .number: return "Number (1,000)"
        case .temperature: return "Temperature"
        }
    }
}

struct Widget: Identifiable, Codable, Equatable {
    var id: UUID = UUID()
    var type: WidgetType
    var x: Int
    var y: Int
    var width: Int
    var height: Int
    var label: String
    var dataBinding: String
    var fontSize: Int
    var valueFormat: ValueFormat = .none
    var cornerRadius: Int = 5

    static func == (lhs: Widget, rhs: Widget) -> Bool {
        lhs.id == rhs.id
    }
}

struct Layout: Identifiable, Codable {
    var id: UUID = UUID()
    var name: String
    var widgets: [Widget]
}

enum LayoutTemplate {
    // All layouts account for 14px status bar + 4px margin = y starts at 18
    // Usable area: (4, 18) to (196, 196) = 192×178

    static let singleValue = Layout(
        name: "Single Value",
        widgets: [
            Widget(
                type: .number,
                x: 4, y: 18,
                width: 192, height: 178,
                label: "Value",
                dataBinding: "api.value",
                fontSize: 48,
                valueFormat: .currency,
                cornerRadius: 6
            )
        ]
    )

    static let dualSplit = Layout(
        name: "Dual Split",
        widgets: [
            Widget(
                type: .number,
                x: 4, y: 18,
                width: 94, height: 178,
                label: "Left",
                dataBinding: "api.left",
                fontSize: 32,
                cornerRadius: 5
            ),
            Widget(
                type: .number,
                x: 102, y: 18,
                width: 94, height: 178,
                label: "Right",
                dataBinding: "api.right",
                fontSize: 32,
                cornerRadius: 5
            )
        ]
    )

    static let quadGrid = Layout(
        name: "Quad Grid",
        widgets: [
            Widget(
                type: .sensor,
                x: 4, y: 18,
                width: 94, height: 87,
                label: "Temp",
                dataBinding: "sensor.temperature",
                fontSize: 32,
                valueFormat: .temperature,
                cornerRadius: 4
            ),
            Widget(
                type: .sensor,
                x: 102, y: 18,
                width: 94, height: 87,
                label: "Humidity",
                dataBinding: "sensor.humidity",
                fontSize: 32,
                valueFormat: .percent,
                cornerRadius: 4
            ),
            Widget(
                type: .clock,
                x: 4, y: 109,
                width: 94, height: 87,
                label: "Clock",
                dataBinding: "system.time",
                fontSize: 32,
                cornerRadius: 4
            ),
            Widget(
                type: .text,
                x: 102, y: 109,
                width: 94, height: 87,
                label: "Status",
                dataBinding: "system.status",
                fontSize: 20,
                cornerRadius: 4
            )
        ]
    )

    static let all: [Layout] = [singleValue, dualSplit, quadGrid]
}
