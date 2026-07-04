import Foundation

// MARK: - Command Types

enum DeviceCommand: Encodable {
    case getStatus
    case ping
    case getConfig
    case setWifi(ssid: String, password: String)
    case setLayout(Layout)
    case setAPI(APIEndpoint)
    case setAudio(enabled: Bool, volume: Int)

    private enum CodingKeys: String, CodingKey {
        case cmd, params
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)

        switch self {
        case .getStatus:
            try container.encode("get_status", forKey: .cmd)
        case .ping:
            try container.encode("ping", forKey: .cmd)
        case .getConfig:
            try container.encode("get_config", forKey: .cmd)
        case .setWifi(let ssid, let password):
            try container.encode("set_wifi", forKey: .cmd)
            try container.encode(["ssid": ssid, "password": password], forKey: .params)
        case .setLayout(let layout):
            try container.encode("set_layout", forKey: .cmd)
            try container.encode(LayoutParams(layout: layout), forKey: .params)
        case .setAPI(let endpoint):
            try container.encode("set_api", forKey: .cmd)
            try container.encode(APIParams(endpoint: endpoint), forKey: .params)
        case .setAudio(let enabled, let volume):
            try container.encode("set_audio", forKey: .cmd)
            try container.encode(["enabled": AnyCodable(enabled), "volume": AnyCodable(volume)], forKey: .params)
        }
    }
}

// MARK: - Encoding Helpers

private struct LayoutParams: Encodable {
    let layout: Layout

    private enum CodingKeys: String, CodingKey {
        case name, widgets
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(layout.name, forKey: .name)
        try container.encode(layout.widgets.map { WidgetParam(widget: $0) }, forKey: .widgets)
    }
}

private struct WidgetParam: Encodable {
    let widget: Widget

    private enum CodingKeys: String, CodingKey {
        case type, x, y, width, height, label, dataBinding, fontSize
        case valueFormat, cornerRadius
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(widget.type.rawValue, forKey: .type)
        try container.encode(widget.x, forKey: .x)
        try container.encode(widget.y, forKey: .y)
        try container.encode(widget.width, forKey: .width)
        try container.encode(widget.height, forKey: .height)
        try container.encode(widget.label, forKey: .label)
        try container.encode(widget.dataBinding, forKey: .dataBinding)
        try container.encode(widget.fontSize, forKey: .fontSize)
        try container.encode(widget.valueFormat.rawValue, forKey: .valueFormat)
        try container.encode(widget.cornerRadius, forKey: .cornerRadius)
    }
}

private struct APIParams: Encodable {
    let endpoint: APIEndpoint

    private enum CodingKeys: String, CodingKey {
        case name, url, authToken, pollIntervalSeconds, jsonPaths, enabled
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(endpoint.name, forKey: .name)
        try container.encode(endpoint.url, forKey: .url)
        try container.encode(endpoint.authToken, forKey: .authToken)
        try container.encode(endpoint.pollIntervalSeconds, forKey: .pollIntervalSeconds)
        try container.encode(endpoint.jsonPaths, forKey: .jsonPaths)
        try container.encode(endpoint.enabled, forKey: .enabled)
    }
}

// Simple type-erased Codable wrapper
private struct AnyCodable: Encodable {
    private let _encode: (Encoder) throws -> Void

    init<T: Encodable>(_ value: T) {
        _encode = { try value.encode(to: $0) }
    }

    func encode(to encoder: Encoder) throws {
        try _encode(encoder)
    }
}

// MARK: - Response Types

struct DeviceResponse: Codable {
    let status: String?
    let cmd: String?
    let msg: String?
    let data: StatusData?
}

struct StatusData: Codable {
    let chip: String?
    let mac: String?
    let freeHeap: Int?
    let wifi: Bool?
    let wifiSsid: String?
    let wifiIp: String?
    let wifiRssi: Int?
    let ble: Bool?
    let fwVersion: String?
    let temperature: Double?
    let humidity: Double?
    let audioEnabled: Bool?
    let audioVolume: Int?
    let hasLayout: Bool?
    let batteryPercent: Int?

    enum CodingKeys: String, CodingKey {
        case chip, mac, wifi, ble, temperature, humidity
        case freeHeap = "free_heap"
        case wifiSsid = "wifi_ssid"
        case wifiIp = "wifi_ip"
        case wifiRssi = "wifi_rssi"
        case fwVersion = "fw_version"
        case audioEnabled = "audio_enabled"
        case audioVolume = "audio_volume"
        case hasLayout = "has_layout"
        case batteryPercent = "battery_percent"
    }
}

// MARK: - Protocol Encoder/Decoder

struct DeviceProtocol {
    private static let encoder: JSONEncoder = {
        let enc = JSONEncoder()
        enc.outputFormatting = [] // compact JSON for BLE
        return enc
    }()

    private static let decoder: JSONDecoder = {
        let dec = JSONDecoder()
        return dec
    }()

    static func encode(_ command: DeviceCommand) -> String? {
        guard let data = try? encoder.encode(command),
              let json = String(data: data, encoding: .utf8) else {
            return nil
        }
        return json
    }

    static func decode(_ json: String) -> DeviceResponse? {
        guard let data = json.data(using: .utf8) else {
            print("[Protocol] Failed to convert to UTF-8 data")
            return nil
        }
        do {
            return try decoder.decode(DeviceResponse.self, from: data)
        } catch {
            print("[Protocol] Decode error: \(error)")
            print("[Protocol] Raw JSON: \(json.prefix(200))")
            return nil
        }
    }

    static func decodeAndUpdate(_ json: String, state: DeviceState) {
        guard let response = decode(json) else { return }
        state.update(from: response)
    }
}
