#include "scb_transport.h"
#include "board_pins.h"
#include "driver/uart.h"
#include "driver/usb_serial_jtag.h"
#include "sdkconfig.h"

esp_err_t scb_transport_init(void) {
#if CONFIG_SCB_LINK_UART
    /* GPIO17/18 are broken out at J6. UART0 ROM pins 43/44 are unconnected. */
    const uart_config_t config = {.baud_rate = SCB_UART_BAUD,
        .data_bits = UART_DATA_8_BITS, .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1, .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT};
    esp_err_t result = uart_param_config(UART_NUM_1, &config);
    if (result != ESP_OK) return result;
    result = uart_set_pin(UART_NUM_1, SCB_PIN_UART_TX, SCB_PIN_UART_RX,
                          UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    if (result != ESP_OK) return result;
    return uart_driver_install(UART_NUM_1, 2048, 2048, 0, NULL, 0);
#else
    /* J5 USB-B is connected directly to the S3 native USB pins. */
    usb_serial_jtag_driver_config_t config = {.tx_buffer_size = 2048, .rx_buffer_size = 2048};
    return usb_serial_jtag_driver_install(&config);
#endif
}

int scb_transport_read(void *buffer, size_t length) {
#if CONFIG_SCB_LINK_UART
    return uart_read_bytes(UART_NUM_1, buffer, length, 0);
#else
    return usb_serial_jtag_read_bytes(buffer, length, 0);
#endif
}

int scb_transport_write(const void *buffer, size_t length, TickType_t wait) {
#if CONFIG_SCB_LINK_UART
    (void)wait;
    return uart_write_bytes(UART_NUM_1, buffer, length);
#else
    /* Bounded wait: an unplugged host must not block the control task. */
    return usb_serial_jtag_write_bytes(buffer, length, wait);
#endif
}
