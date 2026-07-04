#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <string>

#include "../wifi/WiFiManager.h"
#include "../display/DisplayManager.h"
#include "../audio/AudioManager.h"
#include "../api/APIPoller.h"
#include "../sensors/SensorManager.h"
#include "../storage/ConfigStore.h"

// --- Device status (read-only snapshot) ---

struct DeviceStatus {
    String chipModel;
    String macAddress;
    uint32_t freeHeap;
    bool wifiConnected;
    String wifiSSID;
    String wifiIP;
    int wifiRSSI;
    bool bleConnected;
    String firmwareVersion;
    float temperature;
    float humidity;
    bool audioEnabled;
    int audioVolume;
    bool hasLayout;
    uint8_t batteryPercent;
};

// Callback for deferred WiFi connect (must run on main loop, not BLE stack)
typedef void (*WiFiConnectCallback)(const String& ssid, const String& password);

// --- Protocol handler ---

class Protocol {
public:
    Protocol();

    // Inject dependencies
    void init(WiFiManager* wifi, DisplayManager* display, AudioManager* audio,
              APIPoller* api, SensorManager* sensor, ConfigStore* config);

    // Set callback for deferred WiFi connect
    void setWiFiConnectCallback(WiFiConnectCallback cb) { _wifiConnectCb = cb; }

    // Parse a JSON command string; returns the JSON response as a string.
    std::string handleCommand(const std::string& input, const DeviceStatus& status);

private:
    std::string handleGetStatus(const DeviceStatus& status);
    std::string handlePing();
    std::string handleSetWifi(JsonObjectConst params);
    std::string handleSetLayout(JsonObjectConst params);
    std::string handleSetUsage(JsonObjectConst params);
    std::string handleSetApi(JsonObjectConst params);
    std::string handleSetAudio(JsonObjectConst params);
    std::string handleGetConfig();
    std::string makeError(const char* message);
    std::string makeOk(const char* cmd, const char* msg);

    WiFiManager*    _wifi;
    DisplayManager* _display;
    AudioManager*   _audio;
    APIPoller*      _api;
    SensorManager*  _sensor;
    ConfigStore*    _config;
    WiFiConnectCallback _wifiConnectCb = nullptr;
};

#endif // PROTOCOL_H
