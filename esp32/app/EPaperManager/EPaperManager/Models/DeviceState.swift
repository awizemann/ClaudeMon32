import Foundation

enum ConnectionType: String, Codable {
    case none
    case ble
    case usb
    case both
}

@Observable
final class DeviceState {
    var connectionType: ConnectionType = .none
    var isConnected: Bool = false
    var chipModel: String = ""
    var macAddress: String = ""
    var firmwareVersion: String = ""
    var freeHeap: Int = 0
    var wifiConnected: Bool = false
    var wifiSSID: String = ""
    var wifiIP: String = ""
    var wifiRSSI: Int = 0
    var bleConnected: Bool = false
    var temperature: Double = 0.0
    var humidity: Double = 0.0
    var audioEnabled: Bool = false
    var audioVolume: Int = 50
    var hasLayout: Bool = false
    var batteryPercent: Int = 0

    // Last response metadata
    var lastCommand: String = ""
    var lastMessage: String = ""

    func update(from response: DeviceResponse) {
        lastCommand = response.cmd ?? lastCommand
        lastMessage = response.msg ?? ""

        guard let data = response.data else { return }

        chipModel       = data.chip ?? chipModel
        macAddress      = data.mac ?? macAddress
        firmwareVersion = data.fwVersion ?? firmwareVersion
        freeHeap        = data.freeHeap ?? freeHeap
        wifiConnected   = data.wifi ?? wifiConnected
        wifiSSID        = data.wifiSsid ?? wifiSSID
        wifiIP          = data.wifiIp ?? wifiIP
        wifiRSSI        = data.wifiRssi ?? wifiRSSI
        bleConnected    = data.ble ?? bleConnected
        temperature     = data.temperature ?? temperature
        humidity        = data.humidity ?? humidity
        audioEnabled    = data.audioEnabled ?? audioEnabled
        audioVolume     = data.audioVolume ?? audioVolume
        hasLayout       = data.hasLayout ?? hasLayout
        batteryPercent  = data.batteryPercent ?? batteryPercent
    }

    func reset() {
        connectionType = .none
        isConnected = false
        chipModel = ""
        macAddress = ""
        firmwareVersion = ""
        freeHeap = 0
        wifiConnected = false
        wifiSSID = ""
        wifiIP = ""
        wifiRSSI = 0
        bleConnected = false
        temperature = 0.0
        humidity = 0.0
        audioEnabled = false
        audioVolume = 50
        hasLayout = false
        batteryPercent = 0
        lastCommand = ""
        lastMessage = ""
    }
}
