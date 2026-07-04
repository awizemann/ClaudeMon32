#ifndef API_POLLER_H
#define API_POLLER_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <vector>
#include <map>

struct APIEndpointConfig {
    String name;
    String url;
    String authToken;
    uint32_t intervalSec;
    std::map<String, String> jsonPaths;  // field -> JSONPath
    bool enabled;
};

struct APIResult {
    String field;
    String value;
};

class APIPoller {
public:
    APIPoller();

    void addEndpoint(const APIEndpointConfig& config);
    void removeEndpoint(const String& name);
    void clearEndpoints();
    void update();       // Call in loop()
    void forceUpdate();  // Force immediate poll of all endpoints

    // Get latest values
    String getValue(const String& field) const;
    const std::map<String, String>& getAllValues() const;
    bool hasNewData() const;
    void clearNewDataFlag();

private:
    void pollEndpoint(APIEndpointConfig& ep);
    String extractJsonPath(const JsonDocument& doc, const String& path);
    String resolveJsonPath(JsonVariantConst variant, const String& path);

    std::vector<APIEndpointConfig> _endpoints;
    std::map<String, String>       _values;
    std::vector<uint32_t>          _lastPollMs;
    bool                           _hasNewData;
};

#endif // API_POLLER_H
