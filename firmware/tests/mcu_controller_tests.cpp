#include "scb/mcu_controller.hpp"

#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string_view>

namespace {

struct FakeBoard {
    bool button{};
    std::array<bool, scb::firmware::BoardSquareCount> halls{};
    std::array<std::array<char, 32>, 8> messages{};
    int messageCount{};
    bool led{};

    static bool readButton(void* context) { return static_cast<FakeBoard*>(context)->button; }
    static bool readHall(void* context, std::uint8_t square) {
        return static_cast<FakeBoard*>(context)->halls[square];
    }
    static void writeLed(void* context, bool on) { static_cast<FakeBoard*>(context)->led = on; }
    static void sendLine(void* context, const char* line) {
        auto& board = *static_cast<FakeBoard*>(context);
        if (board.messageCount < static_cast<int>(board.messages.size())) {
            std::strncpy(board.messages[board.messageCount].data(), line,
                         board.messages[board.messageCount].size() - 1);
            ++board.messageCount;
        }
    }

    scb::firmware::Platform platform() {
        return {this, readButton, readHall, writeLed, sendLine};
    }
};

void require(bool condition, std::string_view message) {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}

bool contains(const FakeBoard& board, std::string_view expected) {
    for (int i = 0; i < board.messageCount; ++i) {
        if (board.messages[i].data() == expected) return true;
    }
    return false;
}

} // namespace

int main() {
    using namespace scb::firmware;
    FakeBoard board;
    board.halls[12] = true; // e2 is occupied in the starting position.
    McuController controller(board.platform());

    for (std::uint32_t time = 0; time <= 30; time += 5) controller.loop(time);
    require(controller.sensorOccupied(12), "debounce initial Hall sensor state");
    require(board.messageCount == 0, "do not report initial board calibration as a move");

    board.halls[12] = false;
    for (std::uint32_t time = 40; time <= 70; time += 5) controller.loop(time);
    require(board.led, "light status LED while a piece is lifted");
    board.halls[28] = true; // e4 becomes occupied.
    for (std::uint32_t time = 80; time <= 110; time += 5) controller.loop(time);
    require(contains(board, "SCB1 SENSOR e2 0"), "report debounced sensor change over UART");
    require(contains(board, "SCB1 MOVE e2 e4"), "report a completed physical move over UART");
    require(!board.led, "turn off status LED after a move is completed");

    FakeBoard buttonBoard;
    McuController buttonController(buttonBoard.platform(), true);
    for (std::uint32_t time = 0; time <= 30; time += 5) buttonController.loop(time);
    buttonBoard.button = true;
    for (std::uint32_t time = 35; time <= 70; time += 5) buttonController.loop(time);
    for (std::uint32_t time = 75; time <= 105; time += 5) buttonController.loop(time);
    require(contains(buttonBoard, "SCB1 SENSOR a1 1"), "button test mode simulates the first Hall input");

    std::cout << "All MCU controller tests passed.\n";
}