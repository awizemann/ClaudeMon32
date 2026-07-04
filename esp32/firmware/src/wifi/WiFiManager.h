#ifndef WIFI_MANAGER_H
#define WIFI_MANAGER_H

#include <Arduino.h>
#include <WiFi.h>

enum class WiFiState {
    Idle,
    Connecting,
    Connected,
    Failed
};

class WiFiManager {
public:
    WiFiManager();

    void init();
    void connect(const String& ssid, const String& password);
    void disconnect();
    void update();  // Call in loop() to manage reconnection

    bool isConnected() const;
    WiFiState getState() const;
    String getSSID() const;
    String getIP() const;
    int getRSSI() const;

private:
    WiFiState _state;
    String    _ssid;
    String    _password;
    uint32_t  _connectStartMs;
    uint32_t  _lastReconnectAttempt;
    uint8_t   _retryCount;

    static constexpr uint32_t CONNECT_TIMEOUT_MS   = 15000;
    static constexpr uint32_t RECONNECT_INTERVAL_MS = 30000;
    static constexpr uint8_t  MAX_RETRIES           = 3;
};

#endif // WIFI_MANAGER_H
