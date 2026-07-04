import Foundation
import CoreBluetooth
import Combine

// Nordic UART Service UUIDs
private let nusServiceUUID = CBUUID(string: "6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
private let nusRXCharUUID  = CBUUID(string: "6E400002-B5A3-F393-E0A9-E50E24DCCA9E")
private let nusTXCharUUID  = CBUUID(string: "6E400003-B5A3-F393-E0A9-E50E24DCCA9E")

struct DiscoveredDevice: Identifiable {
    let id: UUID
    let peripheral: CBPeripheral
    let name: String
    var rssi: Int
}

final class BLEManager: NSObject, ObservableObject {
    @Published var isScanning = false
    @Published var discoveredDevices: [DiscoveredDevice] = []
    @Published var connectedPeripheral: CBPeripheral?
    @Published var isConnected = false
    @Published var bluetoothState: CBManagerState = .unknown

    var onDataReceived: ((String) -> Void)?

    private var centralManager: CBCentralManager!
    private var rxCharacteristic: CBCharacteristic?
    private var txCharacteristic: CBCharacteristic?

    override init() {
        super.init()
        centralManager = CBCentralManager(delegate: self, queue: nil)
    }

    func startScan() {
        guard centralManager.state == .poweredOn else { return }
        discoveredDevices.removeAll()
        isScanning = true
        centralManager.scanForPeripherals(
            withServices: [nusServiceUUID],
            options: [CBCentralManagerScanOptionAllowDuplicatesKey: false]
        )
    }

    func stopScan() {
        centralManager.stopScan()
        isScanning = false
    }

    func connect(_ peripheral: CBPeripheral) {
        stopScan()
        centralManager.connect(peripheral, options: nil)
    }

    func disconnect() {
        if let peripheral = connectedPeripheral {
            centralManager.cancelPeripheralConnection(peripheral)
        }
    }

    func send(_ string: String) {
        guard let peripheral = connectedPeripheral,
              let rx = rxCharacteristic,
              let payload = (string + "\n").data(using: .utf8) else { return }

        // Use .withResponse MTU — typically 512 bytes, enough for most commands
        let mtu = peripheral.maximumWriteValueLength(for: .withResponse)
        let chunkSize = max(mtu, 20)

        var offset = 0
        while offset < payload.count {
            let end = min(offset + chunkSize, payload.count)
            let chunk = payload.subdata(in: offset..<end)
            peripheral.writeValue(chunk, for: rx, type: .withResponse)
            offset = end
        }
    }
}

// MARK: - CBCentralManagerDelegate

extension BLEManager: CBCentralManagerDelegate {
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        bluetoothState = central.state
        if central.state != .poweredOn {
            isScanning = false
        }
    }

    func centralManager(
        _ central: CBCentralManager,
        didDiscover peripheral: CBPeripheral,
        advertisementData: [String: Any],
        rssi RSSI: NSNumber
    ) {
        let name = peripheral.name
            ?? advertisementData[CBAdvertisementDataLocalNameKey] as? String
            ?? "Unknown"

        if let index = discoveredDevices.firstIndex(where: { $0.peripheral.identifier == peripheral.identifier }) {
            discoveredDevices[index].rssi = RSSI.intValue
        } else {
            let device = DiscoveredDevice(
                id: peripheral.identifier,
                peripheral: peripheral,
                name: name,
                rssi: RSSI.intValue
            )
            discoveredDevices.append(device)
        }
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        connectedPeripheral = peripheral
        isConnected = true
        peripheral.delegate = self
        peripheral.discoverServices([nusServiceUUID])
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        if peripheral.identifier == connectedPeripheral?.identifier {
            connectedPeripheral = nil
            isConnected = false
            rxCharacteristic = nil
            txCharacteristic = nil
        }
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        connectedPeripheral = nil
        isConnected = false
    }
}

// MARK: - CBPeripheralDelegate

extension BLEManager: CBPeripheralDelegate {
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard let services = peripheral.services else { return }
        for service in services where service.uuid == nusServiceUUID {
            peripheral.discoverCharacteristics([nusRXCharUUID, nusTXCharUUID], for: service)
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        guard let characteristics = service.characteristics else { return }
        for char in characteristics {
            switch char.uuid {
            case nusRXCharUUID:
                rxCharacteristic = char
            case nusTXCharUUID:
                txCharacteristic = char
                peripheral.setNotifyValue(true, for: char)
            default:
                break
            }
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        guard characteristic.uuid == nusTXCharUUID,
              let data = characteristic.value,
              let text = String(data: data, encoding: .utf8) else { return }
        DispatchQueue.main.async { [weak self] in
            self?.onDataReceived?(text)
        }
    }
}
