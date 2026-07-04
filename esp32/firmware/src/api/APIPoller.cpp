#include "APIPoller.h"

APIPoller::APIPoller()
    : _hasNewData(false)
{
}

void APIPoller::addEndpoint(const APIEndpointConfig& config)
{
    // Replace if exists
    for (size_t i = 0; i < _endpoints.size(); i++) {
        if (_endpoints[i].name == config.name) {
            _endpoints[i] = config;
            _lastPollMs[i] = 0;  // Force immediate poll
            return;
        }
    }
    _endpoints.push_back(config);
    _lastPollMs.push_back(0);
}

void APIPoller::removeEndpoint(const String& name)
{
    for (size_t i = 0; i < _endpoints.size(); i++) {
        if (_endpoints[i].name == name) {
            _endpoints.erase(_endpoints.begin() + i);
            _lastPollMs.erase(_lastPollMs.begin() + i);
            return;
        }
    }
}

void APIPoller::clearEndpoints()
{
    _endpoints.clear();
    _lastPollMs.clear();
    _values.clear();
}

void APIPoller::forceUpdate()
{
    // Reset all poll timers to force immediate poll on next update()
    for (size_t i = 0; i < _lastPollMs.size(); i++) {
        _lastPollMs[i] = 0;
    }
    Serial.println("[API] Forced immediate poll of all endpoints");
}

void APIPoller::update()
{
    if (WiFi.status() != WL_CONNECTED) return;

    uint32_t now = millis();
    for (size_t i = 0; i < _endpoints.size(); i++) {
        if (!_endpoints[i].enabled) continue;
        uint32_t intervalMs = _endpoints[i].intervalSec * 1000;
        if (now - _lastPollMs[i] >= intervalMs) {
            pollEndpoint(_endpoints[i]);
            _lastPollMs[i] = now;
        }
    }
}

void APIPoller::pollEndpoint(APIEndpointConfig& ep)
{
    Serial.printf("[API] Polling '%s': %s\n", ep.name.c_str(), ep.url.c_str());

    HTTPClient http;
    http.begin(ep.url);
    http.addHeader("Accept", "application/json");

    if (ep.authToken.length() > 0) {
        http.addHeader("Authorization", "Bearer " + ep.authToken);
    }

    http.setTimeout(10000);
    int httpCode = http.GET();

    if (httpCode == HTTP_CODE_OK) {
        String payload = http.getString();

        JsonDocument doc;
        DeserializationError err = deserializeJson(doc, payload);

        if (!err) {
            for (auto& pair : ep.jsonPaths) {
                String value = extractJsonPath(doc, pair.second);
                if (value.length() > 0) {
                    _values[pair.first] = value;
                    _hasNewData = true;
                    Serial.printf("[API] %s = %s\n", pair.first.c_str(), value.c_str());
                }
            }
        } else {
            Serial.printf("[API] JSON parse error: %s\n", err.c_str());
        }
    } else {
        Serial.printf("[API] HTTP error: %d\n", httpCode);
    }

    http.end();
}

String APIPoller::extractJsonPath(const JsonDocument& doc, const String& path)
{
    // Simple JSONPath-like resolver
    // Supports: $.key.subkey, $.array[0].key
    String cleanPath = path;
    if (cleanPath.startsWith("$.")) {
        cleanPath = cleanPath.substring(2);
    } else if (cleanPath.startsWith("$")) {
        cleanPath = cleanPath.substring(1);
    }

    return resolveJsonPath(doc.as<JsonVariantConst>(), cleanPath);
}

String APIPoller::resolveJsonPath(JsonVariantConst variant, const String& path)
{
    if (path.length() == 0) {
        // Terminal - convert value to string
        if (variant.is<const char*>()) {
            return String(variant.as<const char*>());
        } else if (variant.is<int>()) {
            return String(variant.as<int>());
        } else if (variant.is<float>()) {
            return String(variant.as<float>(), 2);
        } else if (variant.is<double>()) {
            return String(variant.as<double>(), 2);
        } else if (variant.is<bool>()) {
            return variant.as<bool>() ? "true" : "false";
        }
        // Try as string fallback
        String out;
        serializeJson(variant, out);
        return out;
    }

    // Find the next segment
    int dotPos = path.indexOf('.');
    int bracketPos = path.indexOf('[');

    String segment;
    String remainder;

    if (bracketPos >= 0 && (dotPos < 0 || bracketPos < dotPos)) {
        // Array index comes first
        if (bracketPos > 0) {
            // There's a key before the bracket
            segment = path.substring(0, bracketPos);
            remainder = path.substring(bracketPos);
            return resolveJsonPath(variant[segment.c_str()], remainder);
        }
        // Direct array access
        int closeBracket = path.indexOf(']');
        if (closeBracket < 0) return "";
        int index = path.substring(1, closeBracket).toInt();
        remainder = path.substring(closeBracket + 1);
        if (remainder.startsWith(".")) remainder = remainder.substring(1);
        return resolveJsonPath(variant[index], remainder);
    }

    if (dotPos >= 0) {
        segment = path.substring(0, dotPos);
        remainder = path.substring(dotPos + 1);
    } else {
        segment = path;
        remainder = "";
    }

    return resolveJsonPath(variant[segment.c_str()], remainder);
}

String APIPoller::getValue(const String& field) const
{
    auto it = _values.find(field);
    if (it != _values.end()) {
        return it->second;
    }
    return "";
}

const std::map<String, String>& APIPoller::getAllValues() const
{
    return _values;
}

bool APIPoller::hasNewData() const
{
    return _hasNewData;
}

void APIPoller::clearNewDataFlag()
{
    _hasNewData = false;
}
