#ifndef SENSOR_MANAGER_H
#define SENSOR_MANAGER_H

#include <Arduino.h>
#include <Wire.h>
#include "../config.h"

class SensorManager {
public:
    SensorManager();

    bool init(TwoWire& wire);
    void update();  // Call periodically to refresh readings

    float getTemperature() const;
    float getHumidity() const;
    bool  isAvailable() const;

private:
    bool readSHTC3();
    bool wakeup();
    void sleep();

    TwoWire* _wire;
    float    _temperature;
    float    _humidity;
    bool     _available;
    uint32_t _lastReadMs;

    static constexpr uint8_t  SHTC3_ADDR = I2C_SHTC3_ADDR;
    static constexpr uint32_t READ_INTERVAL_MS = 5000;
};

#endif // SENSOR_MANAGER_H
