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

// Usage screen: STALE banner appears when the host stops pushing
static constexpr uint32_t USAGE_STALE_MS = 10UL * 60UL * 1000UL;
static bool lastUsageStale = false;

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
    // Flash a blank frame first to wipe ghosting left by whatever was on
    // screen before the reboot, then draw the real boot screen.
    display.clear();
    display.fullRefresh();

    display.clear();

    // Title
    const char* title = "CLAUDEMON";
    display.drawTextBold((200 - display.textWidth(title, 2) - 1) / 2, 14, title, 2);
    display.drawCenteredText(34, "USAGE MONITOR", 1);

    // --- Mascot: a little usage critter ---
    // Antennae
    display.fillRect(84, 50, 5, 5, true);
    display.fillRect(111, 50, 5, 5, true);
    display.drawLine(86, 55, 86, 62);
    display.drawLine(113, 55, 113, 62);

    // Body
    display.fillRoundRect(60, 62, 80, 64, 14, true);

    // Eyes (white cutouts)
    display.fillRect(78, 78, 10, 16, false);
    display.fillRect(112, 78, 10, 16, false);

    // Smile
    display.fillRect(94, 100, 12, 3, false);

    // Belly gauge: white pill with a black fill bar (its "usage")
    display.fillRoundRect(72, 108, 56, 13, 4, false);
    display.fillRect(75, 111, 27, 7, true);

    // Feet
    display.fillRoundRect(72, 126, 16, 8, 3, true);
    display.fillRoundRect(112, 126, 16, 8, 3, true);

    // Footer
    display.drawLine(30, 150, 170, 150);
    display.drawCenteredText(160, "V" FIRMWARE_VER, 1);
    display.drawCenteredText(178, "WAITING FOR HOST", 1);

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
    // Default USB-CDC RX buffer is 256 bytes; a multi-account set_usage line
    // (~500 bytes) arrives as one burst and would drop its tail (and newline).
    // Must be called before Serial.begin().
    Serial.setRxBufferSize(SERIAL_BUF_MAX);
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

    // Update display with initial data after short delay. Without a layout,
    // the boot screen (which already says "WAITING FOR HOST") stays up until
    // the first set_usage push arrives.
    delay(1000);
    if (display.hasLayout()) {
        updateDisplay();
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

    // Usage mode takes priority: the screen is redrawn by set_usage on each
    // push; here we only re-render when the staleness state flips, so the
    // STALE banner appears/disappears without burning refreshes on identical
    // content.
    if (display.hasUsage()) {
        if (display.consumePendingUsageRender()) {
            // Fresh push (render deferred from the protocol handler)
            lastUsageStale = false;
            display.renderUsageScreen(false);
        } else {
            bool stale = display.usageIsStale(USAGE_STALE_MS);
            if (stale != lastUsageStale) {
                lastUsageStale = stale;
                // stale->fresh only happens via a push (handled above);
                // only the fresh->stale flip needs a render here.
                if (stale) {
                    display.renderUsageScreen(true);
                }
            }
        }
        lastDisplayUpdate = millis();
    } else if (shouldUpdate) {
        if (display.hasLayout()) {
            updateDisplay();
        } else {
            // No layout, no usage: the boot screen is static — leave it be.
            lastDisplayUpdate = millis();
        }
    }

    delay(10);
}
