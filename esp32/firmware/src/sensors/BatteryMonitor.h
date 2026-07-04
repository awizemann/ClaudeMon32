#ifndef BATTERY_MONITOR_H
#define BATTERY_MONITOR_H

#include <Arduino.h>

class BatteryMonitor {
public:
    void init();
    float readVoltage();        // Returns battery voltage in millivolts
    uint8_t getPercent();       // Returns 0-100 charge level

private:
    static constexpr int SAMPLES = 4;
    float _readings[SAMPLES] = {};
    uint8_t _readIndex = 0;
    bool _filled = false;

    float averageVoltage();
};

#endif // BATTERY_MONITOR_H
