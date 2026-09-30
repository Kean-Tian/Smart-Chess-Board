#include "scb/mcu_controller.hpp"

#include <cstdio>

namespace scb::firmware {
namespace {

void squareName(std::uint8_t square, char (&name)[3]) {
    name[0] = static_cast<char>('a' + square % 8);
    name[1] = static_cast<char>('1' + square / 8);
    name[2] = '\0';
}

} // namespace

McuController::McuController(Platform platform, bool buttonTestMode)
    : platform_(platform), buttonTestMode_(buttonTestMode) {
    if (buttonTestMode_) {
        testSquare_ = 12; // e2 is occupied in the standard starting position.
        testSensors_[testSquare_] = true;
    }
}

void McuController::loop(std::uint32_t nowMs) {
    updateButton(nowMs);
    scanSensors(nowMs);
}

bool McuController::sensorOccupied(std::uint8_t square) const {
    return square < BoardSquareCount && sensors_[square].initialized && sensors_[square].stable;
}

void McuController::updateButton(std::uint32_t nowMs) {
    if (!buttonTestMode_ || platform_.buttonPressed == nullptr) return;
    const bool rawPressed = platform_.buttonPressed(platform_.context);

    if (!buttonInitialized_) {
        buttonInitialized_ = true;
        buttonCandidate_ = rawPressed;
        buttonChangedAt_ = nowMs;
        return;
    }
    if (rawPressed != buttonCandidate_) {
        buttonCandidate_ = rawPressed;
        buttonChangedAt_ = nowMs;
    }
    if (nowMs - buttonChangedAt_ < InputDebounceMs || buttonStable_ == buttonCandidate_) return;

    buttonStable_ = buttonCandidate_;
    if (buttonStable_) {
        if (!testMovePending_) {
            testSensors_[testSquare_] = false;
            testMovePending_ = true;
        } else {
            const std::uint8_t destination = static_cast<std::uint8_t>((testSquare_ + 8) % BoardSquareCount);
            testSensors_[destination] = true;
            testSquare_ = destination;
            testMovePending_ = false;
        }
    }
}

void McuController::scanSensors(std::uint32_t nowMs) {
    for (std::uint8_t square = 0; square < BoardSquareCount; ++square) {
        const bool raw = rawSensor(square);
        DebouncedInput& input = sensors_[square];
        if (raw != input.candidate) {
            input.candidate = raw;
            input.changedAt = nowMs;
        }
        if (nowMs - input.changedAt < InputDebounceMs) continue;

        if (!input.initialized) {
            input.stable = input.candidate;
            input.initialized = true;
        } else if (input.stable != input.candidate) {
            input.stable = input.candidate;
            onSensorChanged(square, input.stable);
        }
    }
}

bool McuController::rawSensor(std::uint8_t square) const {
    if (buttonTestMode_) return testSensors_[square];
    return platform_.readHallSensor != nullptr && platform_.readHallSensor(platform_.context, square);
}

void McuController::onSensorChanged(std::uint8_t square, bool occupied) {
    sendSensorEvent(square, occupied);
    if (occupied) {
        if (pendingFrom_ >= 0 && pendingFrom_ != square) {
            sendMoveEvent(pendingFrom_, square);
            pendingFrom_ = -1;
            if (platform_.writeStatusLed != nullptr) platform_.writeStatusLed(platform_.context, false);
        }
    } else {
        pendingFrom_ = square;
        if (platform_.writeStatusLed != nullptr) platform_.writeStatusLed(platform_.context, true);
    }
}

void McuController::sendSensorEvent(std::uint8_t square, bool occupied) {
    if (platform_.sendUartLine == nullptr) return;
    char name[3];
    char line[32];
    squareName(square, name);
    std::snprintf(line, sizeof(line), "SCB1 SENSOR %s %u", name, occupied ? 1U : 0U);
    platform_.sendUartLine(platform_.context, line);
}

void McuController::sendMoveEvent(int from, std::uint8_t to) {
    if (platform_.sendUartLine == nullptr || from < 0 || from >= BoardSquareCount) return;
    char fromName[3];
    char toName[3];
    char line[32];
    squareName(static_cast<std::uint8_t>(from), fromName);
    squareName(to, toName);
    std::snprintf(line, sizeof(line), "SCB1 MOVE %s %s", fromName, toName);
    platform_.sendUartLine(platform_.context, line);
}

} // namespace scb::firmware