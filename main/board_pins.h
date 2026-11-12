#pragma once
/*
 * Pin map for the ESP32-S2-Saola-1 prototype.
 * Avoided on purpose: GPIO0/45/46 (boot strapping), GPIO18 (on-board RGB LED),
 * GPIO19/20 (USB D-/D+), GPIO26-32 (flash/PSRAM bus).
 * When moving to the custom ESP32-S3 board, only this file should change.
 */
#include "driver/gpio.h"

#define PIN_X_STEP   GPIO_NUM_5
#define PIN_X_DIR    GPIO_NUM_4
#define PIN_Y_STEP   GPIO_NUM_6
#define PIN_Y_DIR    GPIO_NUM_7
#define PIN_MOTOR_EN GPIO_NUM_8   /* shared /ENABLE of both A4988s, active LOW */

/* Flip if an axis moves the wrong way (or swap one coil pair on the motor). */
#define X_INVERT_DIR false
#define Y_INVERT_DIR false
