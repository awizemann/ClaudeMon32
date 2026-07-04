#include "BatteryMonitor.h"
#include "../config.h"

void BatteryMonitor::init()
{
    analogReadResolution(12);          // 0-4095
    analogSetAttenuation(ADC_11db);    // 0-3.3V range
    pinMode(BAT_ADC, INPUT);

    // Pre-fill the rolling average with an initial reading
    float initial = readVoltage();
    for (int i = 0; i < SAMPLES; i++) {
        _readings[i] = initial;
    }
    _filled = true;
    _readIndex = 0;

    Serial.printf("[Battery] Init OK, voltage=%.0f mV, percent=%d%%\n",
                  initial, getPercent());
}

float BatteryMonitor::readVoltage()
{
    // Read raw ADC value (12-bit: 0-4095 → 0-3300 mV)
    int raw = analogRead(BAT_ADC);
    float adcMv = (raw / 4095.0f) * 3300.0f;

    // Voltage divider on board is 2:1, so actual battery voltage = ADC × 2
    float batteryMv = adcMv * 2.0f;

    // Store in rolling buffer
    _readings[_readIndex] = batteryMv;
    _readIndex = (_readIndex + 1) % SAMPLES;
    if (_readIndex == 0) _filled = true;

    return batteryMv;
}

float BatteryMonitor::averageVoltage()
{
    int count = _filled ? SAMPLES : _readIndex;
    if (count == 0) return 0.0f;

    float sum = 0;
    for (int i = 0; i < count; i++) {
        sum += _readings[i];
    }
    return sum / count;
}

uint8_t BatteryMonitor::getPercent()
{
    // Take a fresh reading
    readVoltage();

    float mv = averageVoltage();

    // LiPo discharge curve approximation:
    // 4200 mV = 100%, 3000 mV = 0%
    // Piecewise linear for better accuracy:
    //   4200-3900: 100-60% (slow discharge)
    //   3900-3700: 60-30%  (moderate)
    //   3700-3500: 30-10%  (getting low)
    //   3500-3000: 10-0%   (critical)

    if (mv >= 4200) return 100;
    if (mv >= 3900) return 60 + (uint8_t)((mv - 3900) / 300.0f * 40.0f);
    if (mv >= 3700) return 30 + (uint8_t)((mv - 3700) / 200.0f * 30.0f);
    if (mv >= 3500) return 10 + (uint8_t)((mv - 3500) / 200.0f * 20.0f);
    if (mv >= 3000) return (uint8_t)((mv - 3000) / 500.0f * 10.0f);
    return 0;
}
