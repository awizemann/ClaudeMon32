#include "AudioManager.h"
#include "../config.h"
#include <math.h>

AudioManager::AudioManager()
    : _enabled(false)
    , _volume(50)
    , _i2sInitialized(false)
{
}

void AudioManager::init()
{
    // Configure speaker enable pin
    pinMode(SPEAKER_EN, OUTPUT);
    enableSpeaker(false);

    Serial.println("[Audio] Initialized");
}

void AudioManager::configureI2S()
{
    if (_i2sInitialized) return;

    i2s_config_t i2s_config = {};
    i2s_config.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX);
    i2s_config.sample_rate = 44100;
    i2s_config.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
    i2s_config.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
    i2s_config.communication_format = I2S_COMM_FORMAT_STAND_I2S;
    i2s_config.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
    i2s_config.dma_buf_count = 4;
    i2s_config.dma_buf_len = 512;
    i2s_config.use_apll = false;
    i2s_config.tx_desc_auto_clear = true;

    i2s_pin_config_t pin_config = {};
    pin_config.bck_io_num = I2S_BCLK;
    pin_config.ws_io_num = I2S_LRCK;
    pin_config.data_out_num = I2S_DOUT;
    pin_config.data_in_num = I2S_DIN;

    esp_err_t err = i2s_driver_install(I2S_NUM_0, &i2s_config, 0, NULL);
    if (err != ESP_OK) {
        Serial.printf("[Audio] I2S install failed: %d\n", err);
        return;
    }

    err = i2s_set_pin(I2S_NUM_0, &pin_config);
    if (err != ESP_OK) {
        Serial.printf("[Audio] I2S set pin failed: %d\n", err);
        i2s_driver_uninstall(I2S_NUM_0);
        return;
    }

    _i2sInitialized = true;
    Serial.println("[Audio] I2S configured");
}

void AudioManager::setEnabled(bool enabled)
{
    _enabled = enabled;
    if (!enabled) {
        enableSpeaker(false);
        if (_i2sInitialized) {
            i2s_driver_uninstall(I2S_NUM_0);
            _i2sInitialized = false;
        }
    }
    Serial.printf("[Audio] %s\n", enabled ? "Enabled" : "Disabled");
}

void AudioManager::setVolume(int volume)
{
    _volume = constrain(volume, 0, 100);
    Serial.printf("[Audio] Volume: %d%%\n", _volume);
}

bool AudioManager::isEnabled() const
{
    return _enabled;
}

int AudioManager::getVolume() const
{
    return _volume;
}

void AudioManager::enableSpeaker(bool on)
{
    digitalWrite(SPEAKER_EN, on ? HIGH : LOW);
}

void AudioManager::generateTone(uint16_t freq, uint16_t durationMs)
{
    if (!_enabled || freq == 0) return;

    configureI2S();
    if (!_i2sInitialized) return;

    enableSpeaker(true);

    const int sampleRate = 44100;
    const int totalSamples = (sampleRate * durationMs) / 1000;
    const float volumeScale = (float)_volume / 100.0f;
    const float amplitude = 16000.0f * volumeScale;

    int16_t buffer[256];
    int samplesWritten = 0;

    while (samplesWritten < totalSamples) {
        int chunkSize = min(256, totalSamples - samplesWritten);
        for (int i = 0; i < chunkSize; i++) {
            float t = (float)(samplesWritten + i) / (float)sampleRate;
            buffer[i] = (int16_t)(amplitude * sinf(2.0f * M_PI * freq * t));
        }

        size_t bytesWritten = 0;
        i2s_write(I2S_NUM_0, buffer, chunkSize * sizeof(int16_t), &bytesWritten, portMAX_DELAY);
        samplesWritten += chunkSize;
    }

    // Brief silence to let DMA flush
    memset(buffer, 0, sizeof(buffer));
    size_t bytesWritten = 0;
    i2s_write(I2S_NUM_0, buffer, sizeof(buffer), &bytesWritten, portMAX_DELAY);

    enableSpeaker(false);
}

void AudioManager::playTone(uint16_t frequency, uint16_t durationMs)
{
    generateTone(frequency, durationMs);
}

void AudioManager::playNotification()
{
    generateTone(1000, 100);
    delay(50);
    generateTone(1500, 100);
}

void AudioManager::playSuccess()
{
    generateTone(800, 80);
    delay(40);
    generateTone(1200, 80);
    delay(40);
    generateTone(1600, 120);
}

void AudioManager::playError()
{
    generateTone(400, 200);
    delay(100);
    generateTone(300, 300);
}
