#include "SensorManager.h"

SensorManager::SensorManager()
    : _wire(nullptr)
    , _temperature(0.0f)
    , _humidity(0.0f)
    , _available(false)
    , _lastReadMs(0)
{
}

bool SensorManager::init(TwoWire& wire)
{
    _wire = &wire;

    // Check if SHTC3 is on the bus
    _wire->beginTransmission(SHTC3_ADDR);
    uint8_t err = _wire->endTransmission();
    if (err != 0) {
        Serial.println("[Sensor] SHTC3 not found on I2C bus");
        _available = false;
        return false;
    }

    _available = true;
    Serial.println("[Sensor] SHTC3 found");

    // Do initial read
    readSHTC3();
    return true;
}

void SensorManager::update()
{
    if (!_available) return;
    if (millis() - _lastReadMs < READ_INTERVAL_MS) return;

    readSHTC3();
    _lastReadMs = millis();
}

float SensorManager::getTemperature() const
{
    return _temperature;
}

float SensorManager::getHumidity() const
{
    return _humidity;
}

bool SensorManager::isAvailable() const
{
    return _available;
}

bool SensorManager::wakeup()
{
    // SHTC3 wakeup command: 0x3517
    _wire->beginTransmission(SHTC3_ADDR);
    _wire->write(0x35);
    _wire->write(0x17);
    return _wire->endTransmission() == 0;
}

void SensorManager::sleep()
{
    // SHTC3 sleep command: 0xB098
    _wire->beginTransmission(SHTC3_ADDR);
    _wire->write(0xB0);
    _wire->write(0x98);
    _wire->endTransmission();
}

bool SensorManager::readSHTC3()
{
    if (!wakeup()) {
        Serial.println("[Sensor] SHTC3 wakeup failed");
        return false;
    }
    delayMicroseconds(300);  // Wakeup time

    // Measure T first, normal mode, clock stretching: 0x7CA2
    _wire->beginTransmission(SHTC3_ADDR);
    _wire->write(0x7C);
    _wire->write(0xA2);
    if (_wire->endTransmission() != 0) {
        Serial.println("[Sensor] SHTC3 measure command failed");
        return false;
    }

    delay(15);  // Measurement time for normal mode

    uint8_t data[6];
    _wire->requestFrom(SHTC3_ADDR, (uint8_t)6);
    if (_wire->available() < 6) {
        Serial.println("[Sensor] SHTC3 read failed - insufficient data");
        return false;
    }

    for (int i = 0; i < 6; i++) {
        data[i] = _wire->read();
    }

    // Parse temperature (first 2 bytes + CRC)
    uint16_t rawTemp = (data[0] << 8) | data[1];
    // CRC check skipped for simplicity (data[2])

    // Parse humidity (next 2 bytes + CRC)
    uint16_t rawHum = (data[3] << 8) | data[4];
    // CRC check skipped for simplicity (data[5])

    _temperature = -45.0f + 175.0f * ((float)rawTemp / 65535.0f);
    _humidity    = 100.0f * ((float)rawHum / 65535.0f);

    // Clamp humidity
    if (_humidity > 100.0f) _humidity = 100.0f;
    if (_humidity < 0.0f)   _humidity = 0.0f;

    sleep();
    return true;
}
