#ifndef AUDIO_MANAGER_H
#define AUDIO_MANAGER_H

#include <Arduino.h>
#include <driver/i2s.h>

class AudioManager {
public:
    AudioManager();

    void init();
    void setEnabled(bool enabled);
    void setVolume(int volume);  // 0-100
    bool isEnabled() const;
    int  getVolume() const;

    // Play a simple tone (frequency in Hz, duration in ms)
    void playTone(uint16_t frequency, uint16_t durationMs);

    // Play a notification beep pattern
    void playNotification();
    void playSuccess();
    void playError();

private:
    void enableSpeaker(bool on);
    void configureI2S();
    void generateTone(uint16_t freq, uint16_t durationMs);

    bool _enabled;
    int  _volume;  // 0-100
    bool _i2sInitialized;
};

#endif // AUDIO_MANAGER_H
