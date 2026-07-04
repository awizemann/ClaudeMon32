#include "BLEService.h"
#include "../config.h"

BLEComm::BLEComm()
    : _pServer(nullptr)
    , _pTxChar(nullptr)
    , _pRxChar(nullptr)
    , _connected(false)
    , _onDataCallback(nullptr)
{
}

void BLEComm::init(const char* deviceName, BLEDataCallback onData)
{
    _onDataCallback = onData;

    NimBLEDevice::init(deviceName);
    NimBLEDevice::setPower(ESP_PWR_LVL_P9);
    // Request large MTU — macOS typically negotiates 185-512
    NimBLEDevice::setMTU(517);

    _pServer = NimBLEDevice::createServer();
    _pServer->setCallbacks(this);

    NimBLEService* pService = _pServer->createService(BLE_NUS_SERVICE_UUID);

    // TX characteristic — notify to central
    _pTxChar = pService->createCharacteristic(
        BLE_NUS_TX_UUID,
        NIMBLE_PROPERTY::NOTIFY
    );

    // RX characteristic — write from central
    _pRxChar = pService->createCharacteristic(
        BLE_NUS_RX_UUID,
        NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_NR
    );
    _pRxChar->setCallbacks(this);

    pService->start();
    _pServer->start();
}

void BLEComm::startAdvertising()
{
    NimBLEAdvertising* pAdvertising = NimBLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(BLE_NUS_SERVICE_UUID);
    pAdvertising->setName(DEVICE_NAME);
    pAdvertising->start();
}

void BLEComm::sendData(const std::string& data)
{
    if (!_connected || _pTxChar == nullptr) return;

    // Append \n as message delimiter so the receiver knows
    // when reassembly is complete (matches serial framing).
    std::string framed = data + "\n";

    // Use a conservative chunk size that works with any MTU.
    // BLE minimum MTU is 23 → max notification payload is 20 bytes.
    // We use 20 to guarantee delivery regardless of negotiated MTU.
    const size_t chunkSize = 20;
    size_t offset = 0;

    while (offset < framed.length()) {
        size_t len = std::min(chunkSize, framed.length() - offset);

        // CRITICAL: pass the data directly to notify() so it snapshots
        // the bytes immediately, rather than using setValue() + notify()
        // which reads the stored value at transmission time (race condition).
        _pTxChar->notify(
            reinterpret_cast<const uint8_t*>(framed.c_str() + offset),
            len
        );
        offset += len;

        // Wait between chunks — the BLE connection interval on macOS is
        // typically 15-30ms. We must wait at least one interval so the
        // stack can transmit each notification before we queue the next.
        if (offset < framed.length()) {
            delay(30);
        }
    }
}

bool BLEComm::isConnected() const
{
    return _connected;
}

void BLEComm::onConnect(NimBLEServer* pServer, NimBLEConnInfo& connInfo)
{
    _connected = true;
    Serial.println("[BLE] Client connected");
}

void BLEComm::onDisconnect(NimBLEServer* pServer, NimBLEConnInfo& connInfo, int reason)
{
    _connected = false;
    Serial.println("[BLE] Client disconnected");
    startAdvertising();
}

void BLEComm::onWrite(NimBLECharacteristic* pCharacteristic, NimBLEConnInfo& connInfo)
{
    std::string value = pCharacteristic->getValue();
    if (value.length() == 0) return;

    // Accumulate chunks — the macOS app may split large commands
    // across multiple BLE writes. We use '\n' as the message delimiter.
    _rxBuffer += value;

    // Process all complete messages (delimited by \n)
    size_t pos;
    while ((pos = _rxBuffer.find('\n')) != std::string::npos) {
        std::string message = _rxBuffer.substr(0, pos);
        _rxBuffer.erase(0, pos + 1);

        if (message.length() > 0 && _onDataCallback != nullptr) {
            Serial.printf("[BLE RX] Complete message: %d bytes\n", message.length());
            _onDataCallback(message);
        }
    }

    // Also try to process if buffer looks like complete JSON without \n
    // (backward compatibility with older app versions)
    if (_rxBuffer.length() > 0 && _rxBuffer.front() == '{' && _rxBuffer.back() == '}') {
        // Count braces to check for complete JSON
        int depth = 0;
        bool complete = false;
        for (char c : _rxBuffer) {
            if (c == '{') depth++;
            else if (c == '}') depth--;
            if (depth == 0) { complete = true; break; }
        }
        if (complete && _onDataCallback != nullptr) {
            Serial.printf("[BLE RX] Complete JSON (no delim): %d bytes\n", _rxBuffer.length());
            _onDataCallback(_rxBuffer);
            _rxBuffer.clear();
        }
    }

    // Safety: prevent buffer from growing unbounded
    if (_rxBuffer.length() > 4096) {
        Serial.println("[BLE RX] Buffer overflow, clearing");
        _rxBuffer.clear();
    }
}
