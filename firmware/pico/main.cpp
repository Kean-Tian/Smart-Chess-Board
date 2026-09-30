#include "scb/mcu_controller.hpp"

#include "hardware/gpio.h"
#include "hardware/uart.h"
#include "pico/stdlib.h"

#include <cstdio>

namespace {

uart_inst_t* const BoardUart = uart0;
constexpr std::uint32_t UartBaudRate = 115200;
constexpr std::uint ButtonPin = 2;
constexpr std::uint TxPin = PICO_DEFAULT_UART_TX_PIN;
constexpr std::uint RxPin = PICO_DEFAULT_UART_RX_PIN;
constexpr std::uint LedPin = PICO_DEFAULT_LED_PIN;

bool buttonPressed(void*) {
    return !gpio_get(ButtonPin);
}

bool readHallSensor(void*, std::uint8_t) {
    return false;
}

void writeStatusLed(void*, bool on) {
    gpio_put(LedPin, on);
}

void sendUartLine(void*, const char* line) {
    uart_puts(BoardUart, line);
    uart_puts(BoardUart, "\r\n");
}

} // namespace

int main() {
    uart_init(BoardUart, UartBaudRate);
    gpio_set_function(TxPin, GPIO_FUNC_UART);
    gpio_set_function(RxPin, GPIO_FUNC_UART);
    uart_set_format(BoardUart, 8, 1, UART_PARITY_NONE);
    uart_set_fifo_enabled(BoardUart, true);

    gpio_init(ButtonPin);
    gpio_set_dir(ButtonPin, GPIO_IN);
    gpio_pull_up(ButtonPin);

    gpio_init(LedPin);
    gpio_set_dir(LedPin, GPIO_OUT);
    gpio_put(LedPin, false);

    scb::firmware::Platform platform{
        nullptr,
        buttonPressed,
        readHallSensor,
        writeStatusLed,
        sendUartLine};
    scb::firmware::McuController controller(platform, true);

    sendUartLine(nullptr, "SCB1 READY PICO2 BUTTON_TEST");
    while (true) {
        controller.loop(to_ms_since_boot(get_absolute_time()));
        tight_loop_contents();
    }
}
