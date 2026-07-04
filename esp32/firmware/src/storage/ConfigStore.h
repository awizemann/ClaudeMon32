#ifndef CONFIG_STORE_H
#define CONFIG_STORE_H

#include <Arduino.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include "../api/APIPoller.h"

struct StoredConfig {
    // WiFi
    String wifiSSID;
    String wifiPassword;

    // Audio
    bool   audioEnabled;
    int    audioVolume;

    // Layout JSON (serialized)
    String layoutJson;

    // API endpoints JSON (serialized)
    String apiJson;
};

class ConfigStore {
public:
    ConfigStore();

    void init();

    // WiFi
    void saveWiFi(const String& ssid, const String& password);
    void loadWiFi(String& ssid, String& password);

    // Audio
    void saveAudio(bool enabled, int volume);
    void loadAudio(bool& enabled, int& volume);

    // Layout
    void saveLayout(const String& layoutJson);
    String loadLayout();

    // API endpoints
    void saveAPIEndpoints(const std::vector<APIEndpointConfig>& endpoints);
    std::vector<APIEndpointConfig> loadAPIEndpoints();

    // Check if config exists
    bool hasWiFiConfig();

private:
    Preferences _prefs;
};

#endif // CONFIG_STORE_H
