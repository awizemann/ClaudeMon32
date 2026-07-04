#include "WiFiManager.h"

WiFiManager::WiFiManager()
    : _state(WiFiState::Idle)
    , _connectStartMs(0)
    , _lastReconnectAttempt(0)
    , _retryCount(0)
{
}

void WiFiManager::init()
{
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
}

void WiFiManager::connect(const String& ssid, const String& password)
{
    _ssid = ssid;
    _password = password;
    _retryCount = 0;
    _state = WiFiState::Connecting;
    _connectStartMs = millis();

    Serial.printf("[WiFi] Connecting to '%s'...\n", ssid.c_str());
    WiFi.disconnect(true);
    delay(100);
    WiFi.begin(ssid.c_str(), password.c_str());
}

void WiFiManager::disconnect()
{
    WiFi.disconnect(true);
    _state = WiFiState::Idle;
    _ssid = "";
    _password = "";
    Serial.println("[WiFi] Disconnected");
}

void WiFiManager::update()
{
    switch (_state) {
    case WiFiState::Connecting:
        if (WiFi.status() == WL_CONNECTED) {
            _state = WiFiState::Connected;
            _retryCount = 0;
            Serial.printf("[WiFi] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
        } else if (millis() - _connectStartMs > CONNECT_TIMEOUT_MS) {
            _retryCount++;
            if (_retryCount < MAX_RETRIES) {
                Serial.printf("[WiFi] Timeout, retry %d/%d\n", _retryCount, MAX_RETRIES);
                WiFi.disconnect(true);
                delay(100);
                WiFi.begin(_ssid.c_str(), _password.c_str());
                _connectStartMs = millis();
            } else {
                Serial.println("[WiFi] Connection failed after retries");
                _state = WiFiState::Failed;
            }
        }
        break;

    case WiFiState::Connected:
        if (WiFi.status() != WL_CONNECTED) {
            Serial.println("[WiFi] Connection lost, reconnecting...");
            _state = WiFiState::Connecting;
            _connectStartMs = millis();
            _retryCount = 0;
            WiFi.begin(_ssid.c_str(), _password.c_str());
        }
        break;

    case WiFiState::Failed:
        // Allow manual retry via new connect() call
        // Or auto-retry after interval
        if (_ssid.length() > 0 && millis() - _connectStartMs > RECONNECT_INTERVAL_MS) {
            Serial.println("[WiFi] Auto-retry...");
            _retryCount = 0;
            _state = WiFiState::Connecting;
            _connectStartMs = millis();
            WiFi.begin(_ssid.c_str(), _password.c_str());
        }
        break;

    case WiFiState::Idle:
    default:
        break;
    }
}

bool WiFiManager::isConnected() const
{
    return WiFi.status() == WL_CONNECTED;
}

WiFiState WiFiManager::getState() const
{
    return _state;
}

String WiFiManager::getSSID() const
{
    return _ssid;
}

String WiFiManager::getIP() const
{
    if (WiFi.status() == WL_CONNECTED) {
        return WiFi.localIP().toString();
    }
    return "";
}

int WiFiManager::getRSSI() const
{
    if (WiFi.status() == WL_CONNECTED) {
        return WiFi.RSSI();
    }
    return 0;
}
