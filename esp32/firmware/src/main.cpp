#include <Arduino.h>
#include <Wire.h>

#include "config.h"
#include "display/DisplayManager.h"
#include "comms/BLEService.h"
#include "comms/Protocol.h"
#include "wifi/WiFiManager.h"
#include "sensors/SensorManager.h"
#include "sensors/BatteryMonitor.h"
#include "audio/AudioManager.h"
#include "api/APIPoller.h"
#include "storage/ConfigStore.h"

// --- Globals ---

static DisplayManager display;
static BLEComm        ble;
static Protocol       protocol;
static WiFiManager    wifi;
static SensorManager  sensor;
static BatteryMonitor battery;
static AudioManager   audio;
static APIPoller      apiPoller;
static ConfigStore    configStore;
static String         serialBuffer;
static constexpr size_t SERIAL_BUF_MAX = 2048;

static uint32_t lastDisplayUpdate = 0;
static constexpr uint32_t DISPLAY_UPDATE_INTERVAL = 30000; // 30s for e-ink
static constexpr uint32_t DISPLAY_UPDATE_FAST     = 5000;  // 5s during first minute
static bool     wasWiFiConnected  = false;
static uint32_t bootTime          = 0;

// Deferred WiFi connect — BLE callbacks have limited stack,
// so WiFi.begin() must run from the main Arduino loop.
static volatile bool     pendingWiFiConnect = false;
static String            pendingWiFiSSID;
static String            pendingWiFiPass;

// --- Helpers ---

static DeviceStatus getDeviceStatus()
{
    DeviceStatus s;
    s.chipModel       = ESP.getChipModel();
    s.freeHeap        = ESP.getFreeHeap();
    s.wifiConnected   = wifi.isConnected();
    s.wifiSSID        = wifi.getSSID();
    s.wifiIP          = wifi.getIP();
    s.wifiRSSI        = wifi.getRSSI();
    s.bleConnected    = ble.isConnected();
    s.firmwareVersion = FIRMWARE_VER;
    s.temperature     = sensor.getTemperature();
    s.humidity        = sensor.getHumidity();
    s.audioEnabled    = audio.isEnabled();
    s.audioVolume     = audio.getVolume();
    s.hasLayout       = display.hasLayout();
    s.batteryPercent  = battery.getPercent();

    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_BT);
    char macStr[18];
    snprintf(macStr, sizeof(macStr), "%02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    s.macAddress = macStr;

    return s;
}

enum class CommandSource { Serial, BLE };

static void processCommand(const std::string& input, CommandSource source)
{
    DeviceStatus status = getDeviceStatus();
    std::string response = protocol.handleCommand(input, status);

    switch (source) {
    case CommandSource::BLE:
        ble.sendData(response);
        break;
    case CommandSource::Serial:
        Serial.println(response.c_str());
        break;
    }
}

// --- BLE receive callback ---

static void onBLEData(const std::string& data)
{
    Serial.print("[BLE RX] ");
    Serial.println(data.c_str());
    processCommand(data, CommandSource::BLE);
}

// --- Boot screen ---

static void showBootScreen()
{
    display.clear();

    // Modern boot screen with rounded frame
    display.drawRoundRect(8, 8, 184, 184, 8);

    display.drawCenteredText(35, "EPAPER MANAGER", 1);
    display.drawLine(30, 48, 170, 48);

    // Version in large font
    display.drawCenteredTextLarge(65, 100, "0.2.0");

    display.drawCenteredText(100, "CUSTOM FIRMWARE", 1);
    display.drawLine(30, 115, 170, 115);

    // Status icons preview
    display.drawCenteredText(135, "WIFI + BLE", 1);
    display.drawCenteredText(160, "READY", 2);

    display.fullRefresh();
}

// --- Rebuild display data from all sources ---

static std::map<String, String> gatherDisplayData()
{
    std::map<String, String> data;

    // Sensor data
    if (sensor.isAvailable()) {
        data["sensor.temperature"] = String(sensor.getTemperature(), 1);
        data["sensor.humidity"]    = String(sensor.getHumidity(), 1);
    }

    // Battery
    data["battery"] = String(battery.getPercent());

    // System data
    data["system.status"] = wifi.isConnected() ? "Online" : "Offline";
    unsigned long sec = millis() / 1000;
    char timeBuf[8];
    snprintf(timeBuf, sizeof(timeBuf), "%02lu:%02lu", (sec / 3600) % 24, (sec / 60) % 60);
    data["system.time"] = timeBuf;
    data["system.heap"] = String(ESP.getFreeHeap() / 1024) + "KB";

    // API data
    const auto& apiValues = apiPoller.getAllValues();
    bool firstValue = true;
    for (const auto& kv : apiValues) {
        data["api." + kv.first] = kv.second;
        // Also store without prefix for direct bindings
        data[kv.first] = kv.second;

        // Map first API value to generic "api.value" for simple templates
        if (firstValue) {
            data["api.value"] = kv.second;
            firstValue = false;
        }
    }

    return data;
}

static void updateDisplay()
{
    if (!display.hasLayout()) return;

    auto data = gatherDisplayData();
    display.renderLayout(data, wifi.isConnected(), ble.isConnected(), battery.getPercent());
    lastDisplayUpdate = millis();
}

// --- Arduino entry points ---

void setup()
{
    Serial.begin(115200);
    serialBuffer.reserve(512);
    delay(1000);  // Let USB-CDC settle
    Serial.println();
    Serial.println("=========================");
    Serial.print(DEVICE_NAME);
    Serial.print(" v");
    Serial.println(FIRMWARE_VER);
    Serial.println("=========================");
    Serial.flush();

    // Initialize config store
    Serial.println("[INIT] Config store...");
    Serial.flush();
    configStore.init();

    // Initialize display
    Serial.println("[INIT] Display...");
    Serial.flush();
    display.init();
    Serial.println("[INIT] Display init returned, drawing boot screen...");
    Serial.flush();
    showBootScreen();
    Serial.println("[INIT] Boot screen done");
    Serial.flush();

    // Initialize I2C for sensors
    Serial.println("[INIT] I2C bus...");
    Wire.begin(I2C_SDA, I2C_SCL);

    // Initialize sensors
    Serial.println("[INIT] Sensors...");
    sensor.init(Wire);

    // Initialize battery monitor
    Serial.println("[INIT] Battery monitor...");
    battery.init();

    // Initialize audio
    Serial.println("[INIT] Audio...");
    audio.init();

    // Load saved audio config
    {
        bool audioEn;
        int audioVol;
        configStore.loadAudio(audioEn, audioVol);
        audio.setEnabled(audioEn);
        audio.setVolume(audioVol);
    }

    // Initialize WiFi
    Serial.println("[INIT] WiFi...");
    wifi.init();

    // Auto-connect to saved WiFi
    {
        String ssid, password;
        configStore.loadWiFi(ssid, password);
        if (ssid.length() > 0) {
            Serial.printf("[INIT] WiFi config found: SSID='%s' (pass=%d chars)\n",
                          ssid.c_str(), password.length());
            wifi.connect(ssid, password);
        } else {
            Serial.println("[INIT] No saved WiFi config");
        }
    }

    // Load saved API endpoints
    {
        auto endpoints = configStore.loadAPIEndpoints();
        Serial.printf("[INIT] Loaded %d API endpoint(s) from NVS\n", endpoints.size());
        for (const auto& ep : endpoints) {
            apiPoller.addEndpoint(ep);
            Serial.printf("[INIT]   -> '%s' url=%s enabled=%s interval=%ds\n",
                          ep.name.c_str(), ep.url.c_str(),
                          ep.enabled ? "yes" : "no", ep.intervalSec);
        }
    }

    // Load saved layout
    {
        String layoutJson = configStore.loadLayout();
        if (layoutJson.length() > 0) {
            Serial.printf("[INIT] Layout JSON found (%d bytes)\n", layoutJson.length());
            LayoutDef layout;
            if (display.parseLayoutJson(layoutJson, layout)) {
                display.setLayout(layout);
                Serial.printf("[INIT] Layout applied: '%s' (%d widgets)\n",
                              layout.name.c_str(), layout.widgets.size());
            } else {
                Serial.println("[INIT] Layout parse FAILED");
            }
        } else {
            Serial.println("[INIT] No saved layout");
        }
    }

    // Initialize protocol with dependencies
    protocol.init(&wifi, &display, &audio, &apiPoller, &sensor, &configStore);

    // Deferred WiFi connect — runs on main loop, not BLE stack
    protocol.setWiFiConnectCallback([](const String& ssid, const String& password) {
        pendingWiFiSSID = ssid;
        pendingWiFiPass = password;
        pendingWiFiConnect = true;
        Serial.printf("[Main] WiFi connect deferred: '%s'\n", ssid.c_str());
    });

    // Initialize BLE
    Serial.println("[INIT] BLE...");
    ble.init(DEVICE_NAME, onBLEData);
    ble.startAdvertising();
    Serial.println("[INIT] BLE advertising started");

    // Boot complete
    bootTime = millis();
    Serial.println("[INIT] Ready. Send JSON commands over BLE or Serial.");

    if (audio.isEnabled()) {
        audio.playSuccess();
    }

    // Update display with initial data after short delay
    delay(1000);
    if (display.hasLayout()) {
        updateDisplay();
    } else {
        // Show a default status screen
        display.clear();
        display.renderStatusBar(wifi.isConnected(), ble.isConnected(), battery.getPercent());
        display.drawCenteredText(60, DEVICE_NAME, 1);
        display.drawLine(30, 75, 170, 75);

        if (sensor.isAvailable()) {
            char tempBuf[16], humBuf[16];
            snprintf(tempBuf, sizeof(tempBuf), "%.1fC", sensor.getTemperature());
            snprintf(humBuf, sizeof(humBuf), "%.1f%%", sensor.getHumidity());
            display.renderTextWidget(10, 90, 88, 60, "Temp", tempBuf, 4);
            display.renderTextWidget(102, 90, 88, 60, "Humid", humBuf, 4);
        }

        display.drawCenteredText(175, "Ready", 1);
        display.fullRefresh();
    }
}

void loop()
{
    // Process serial input (USB CDC) - read all available bytes
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            if (serialBuffer.length() > 0) {
                processCommand(std::string(serialBuffer.c_str()), CommandSource::Serial);
                serialBuffer = "";
                serialBuffer.reserve(512);
            }
        } else if (serialBuffer.length() < SERIAL_BUF_MAX) {
            serialBuffer += c;
        }
    }

    // Process deferred WiFi connect (set from BLE callback)
    if (pendingWiFiConnect) {
        pendingWiFiConnect = false;
        Serial.printf("[Main] Deferred WiFi connect to '%s'\n", pendingWiFiSSID.c_str());
        wifi.connect(pendingWiFiSSID, pendingWiFiPass);
    }

    // Update subsystems
    wifi.update();
    sensor.update();
    apiPoller.update();

    // Detect WiFi state changes
    bool nowWiFiConnected = wifi.isConnected();
    if (nowWiFiConnected && !wasWiFiConnected) {
        Serial.printf("[Main] WiFi connected! IP: %s\n", wifi.getIP().c_str());
        // Force immediate API poll now that we have internet
        apiPoller.forceUpdate();
    }
    wasWiFiConnected = nowWiFiConnected;

    // Update display — faster during first 60s, then normal interval
    bool shouldUpdate = false;
    uint32_t elapsed = millis() - bootTime;
    uint32_t interval = (elapsed < 60000) ? DISPLAY_UPDATE_FAST : DISPLAY_UPDATE_INTERVAL;

    if (millis() - lastDisplayUpdate >= interval) {
        shouldUpdate = true;
    }

    // API data changed — always update immediately
    if (apiPoller.hasNewData()) {
        shouldUpdate = true;
        apiPoller.clearNewDataFlag();
    }

    if (shouldUpdate) {
        if (display.hasLayout()) {
            updateDisplay();
        } else {
            // Refresh default status screen
            display.clear();
            display.renderStatusBar(wifi.isConnected(), ble.isConnected(), battery.getPercent());
            display.drawCenteredText(60, DEVICE_NAME, 1);
            display.drawLine(30, 75, 170, 75);
            if (sensor.isAvailable()) {
                char tempBuf[16], humBuf[16];
                snprintf(tempBuf, sizeof(tempBuf), "%.1fC", sensor.getTemperature());
                snprintf(humBuf, sizeof(humBuf), "%.1f%%", sensor.getHumidity());
                display.renderTextWidget(10, 90, 88, 60, "Temp", tempBuf);
                display.renderTextWidget(102, 90, 88, 60, "Humid", humBuf);
            }
            display.drawCenteredText(175, wifi.isConnected() ? wifi.getIP().c_str() : "Offline", 1);
            display.fullRefresh();
            lastDisplayUpdate = millis();
        }
    }

    delay(10);
}
