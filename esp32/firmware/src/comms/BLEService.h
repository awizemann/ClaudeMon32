#ifndef BLE_SERVICE_H
#define BLE_SERVICE_H

#include <NimBLEDevice.h>
#include <string>

typedef void (*BLEDataCallback)(const std::string& data);

class BLEComm : public NimBLEServerCallbacks,
                public NimBLECharacteristicCallbacks {
public:
    BLEComm();

    void init(const char* deviceName, BLEDataCallback onData);
    void startAdvertising();
    void sendData(const std::string& data);
    bool isConnected() const;

    // NimBLEServerCallbacks
    void onConnect(NimBLEServer* pServer, NimBLEConnInfo& connInfo) override;
    void onDisconnect(NimBLEServer* pServer, NimBLEConnInfo& connInfo, int reason) override;

    // NimBLECharacteristicCallbacks
    void onWrite(NimBLECharacteristic* pCharacteristic, NimBLEConnInfo& connInfo) override;

private:
    NimBLEServer*         _pServer;
    NimBLECharacteristic* _pTxChar;
    NimBLECharacteristic* _pRxChar;
    bool                  _connected;
    BLEDataCallback       _onDataCallback;
    std::string           _rxBuffer;  // Accumulates chunks until \n delimiter
};

#endif // BLE_SERVICE_H
