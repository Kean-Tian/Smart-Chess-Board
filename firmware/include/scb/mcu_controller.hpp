#pragma once

#include <array>
#include <cstdint>

namespace scb::firmware {

constexpr std::uint8_t BoardSquareCount = 64;
constexpr std::uint32_t InputDebounceMs = 25;

struct Platform {
    void* context{};
    bool (*buttonPressed)(void*){};
    bool (*readHallSensor)(void*, std::uint8_t square){};
    void (*writeStatusLed)(void*, bool on){};
    void (*sendUartLine)(void*, const char* line){};
};

class McuController {
public:
    explicit McuController(Platform platform, bool buttonTestMode = false);

    void loop(std::uint32_t nowMs);
    bool sensorOccupied(std::uint8_t square) const;

private:
    struct DebouncedInput {
        bool stable{};
        bool candidate{};
        bool initialized{};
        std::uint32_t changedAt{};
    };

    Platform platform_;
    bool buttonTestMode_;
    bool buttonInitialized_{};
    bool buttonStable_{};
    bool buttonCandidate_{};
    std::uint32_t buttonChangedAt_{};
    std::uint8_t testSquare_{};
    int pendingFrom_{-1};
    std::array<DebouncedInput, BoardSquareCount> sensors_{};
    std::array<bool, BoardSquareCount> testSensors_{};

    void updateButton(std::uint32_t nowMs);
    void scanSensors(std::uint32_t nowMs);
    bool rawSensor(std::uint8_t square) const;
    void onSensorChanged(std::uint8_t square, bool occupied);
    void sendSensorEvent(std::uint8_t square, bool occupied);
    void sendMoveEvent(int from, std::uint8_t to);
};

} // namespace scb::firmware