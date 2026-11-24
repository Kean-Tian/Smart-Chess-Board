#ifndef SCB_TRANSPORT_H
#define SCB_TRANSPORT_H
#include <stddef.h>
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
/* One selected transport owns the protocol: no interleaved USB/UART commands. */
esp_err_t scb_transport_init(void);
int scb_transport_read(void *buffer, size_t length);
int scb_transport_write(const void *buffer, size_t length, TickType_t wait);
#endif
