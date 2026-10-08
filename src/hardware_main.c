#define _POSIX_C_SOURCE 200809L

#include "scb/sensor_matrix.h"

#include <errno.h>
#include <getopt.h>
#include <gpiod.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static volatile sig_atomic_t keep_running = 1;

static void stop_running(int signal_number) {
    (void)signal_number;
    keep_running = 0;
}

static void sleep_microseconds(void *context, unsigned int microseconds) {
    struct timespec delay = {
        (time_t)(microseconds / 1000000U),
        (long)(microseconds % 1000000U) * 1000L
    };
    (void)context;
    while (nanosleep(&delay, &delay) < 0 && errno == EINTR && keep_running) {
    }
}

#ifdef SCB_GPIOD_V2

typedef struct {
    struct gpiod_chip *chip;
    struct gpiod_line_request *request;
} GpiodBackend;

static void backend_close(GpiodBackend *backend) {
    if (backend->request != NULL) {
        gpiod_line_request_release(backend->request);
        backend->request = NULL;
    }
    if (backend->chip != NULL) {
        gpiod_chip_close(backend->chip);
        backend->chip = NULL;
    }
}

static int backend_open(GpiodBackend *backend, const char *chip_path,
                        const ScbSensorMatrix *matrix) {
    struct gpiod_line_settings *output_settings = NULL;
    struct gpiod_line_settings *input_settings = NULL;
    struct gpiod_line_config *line_config = NULL;
    struct gpiod_request_config *request_config = NULL;
    unsigned int outputs[3] = {
        matrix->address_pins[0], matrix->address_pins[1],
        matrix->address_pins[2]
    };
    int result = -1;
    memset(backend, 0, sizeof(*backend));
    backend->chip = gpiod_chip_open(chip_path);
    if (backend->chip == NULL) goto done;
    output_settings = gpiod_line_settings_new();
    input_settings = gpiod_line_settings_new();
    line_config = gpiod_line_config_new();
    request_config = gpiod_request_config_new();
    if (output_settings == NULL || input_settings == NULL ||
        line_config == NULL || request_config == NULL) goto done;

    if (gpiod_line_settings_set_direction(
            output_settings, GPIOD_LINE_DIRECTION_OUTPUT) < 0 ||
        gpiod_line_settings_set_output_value(
            output_settings, GPIOD_LINE_VALUE_INACTIVE) < 0 ||
        gpiod_line_config_add_line_settings(
            line_config, outputs, 3U, output_settings) < 0 ||
        gpiod_line_settings_set_direction(
            input_settings, GPIOD_LINE_DIRECTION_INPUT) < 0 ||
        gpiod_line_settings_set_bias(
            input_settings, GPIOD_LINE_BIAS_DISABLED) < 0 ||
        gpiod_line_config_add_line_settings(
            line_config, matrix->column_pins, SCB_BOARD_COLUMNS,
            input_settings) < 0) {
        goto done;
    }
    gpiod_request_config_set_consumer(request_config, "smart-chessboard");
    backend->request = gpiod_chip_request_lines(
        backend->chip, request_config, line_config);
    if (backend->request == NULL) goto done;
    result = 0;

done:
    if (request_config != NULL) gpiod_request_config_free(request_config);
    if (line_config != NULL) gpiod_line_config_free(line_config);
    if (input_settings != NULL) gpiod_line_settings_free(input_settings);
    if (output_settings != NULL) gpiod_line_settings_free(output_settings);
    if (result < 0) backend_close(backend);
    return result;
}

static int backend_write(void *context, unsigned int pin, bool high) {
    GpiodBackend *backend = context;
    return gpiod_line_request_set_value(
        backend->request, pin,
        high ? GPIOD_LINE_VALUE_ACTIVE : GPIOD_LINE_VALUE_INACTIVE);
}

static int backend_read_columns(
    void *context, const unsigned int pins[SCB_BOARD_COLUMNS],
    bool values[SCB_BOARD_COLUMNS]) {
    GpiodBackend *backend = context;
    for (size_t index = 0U; index < SCB_BOARD_COLUMNS; ++index) {
        enum gpiod_line_value value =
            gpiod_line_request_get_value(backend->request, pins[index]);
        if (value == GPIOD_LINE_VALUE_ERROR) return -1;
        values[index] = value == GPIOD_LINE_VALUE_ACTIVE;
    }
    return 0;
}

#else

typedef struct {
    struct gpiod_chip *chip;
    struct gpiod_line *outputs[3];
    struct gpiod_line *inputs[SCB_BOARD_COLUMNS];
    size_t requested_outputs;
    size_t requested_inputs;
} GpiodBackend;

static void backend_close(GpiodBackend *backend) {
    for (size_t index = 0U; index < backend->requested_inputs; ++index) {
        gpiod_line_release(backend->inputs[index]);
    }
    for (size_t index = 0U; index < backend->requested_outputs; ++index) {
        gpiod_line_release(backend->outputs[index]);
    }
    backend->requested_inputs = 0U;
    backend->requested_outputs = 0U;
    if (backend->chip != NULL) {
        gpiod_chip_close(backend->chip);
        backend->chip = NULL;
    }
}

static int backend_open(GpiodBackend *backend, const char *chip_path,
                        const ScbSensorMatrix *matrix) {
    unsigned int output_offsets[3] = {
        matrix->address_pins[0], matrix->address_pins[1],
        matrix->address_pins[2]
    };
    memset(backend, 0, sizeof(*backend));
    backend->chip = gpiod_chip_open(chip_path);
    if (backend->chip == NULL) return -1;
    for (size_t index = 0U; index < 3U; ++index) {
        backend->outputs[index] =
            gpiod_chip_get_line(backend->chip, output_offsets[index]);
        if (backend->outputs[index] == NULL ||
            gpiod_line_request_output(backend->outputs[index],
                                      "smart-chessboard", 0) < 0) {
            backend_close(backend);
            return -1;
        }
        ++backend->requested_outputs;
    }
    for (size_t index = 0U; index < SCB_BOARD_COLUMNS; ++index) {
        backend->inputs[index] =
            gpiod_chip_get_line(backend->chip, matrix->column_pins[index]);
        if (backend->inputs[index] == NULL ||
            gpiod_line_request_input(backend->inputs[index],
                                     "smart-chessboard") < 0) {
            backend_close(backend);
            return -1;
        }
        ++backend->requested_inputs;
    }
    return 0;
}

static struct gpiod_line *find_output(GpiodBackend *backend,
                                      unsigned int pin) {
    for (size_t index = 0U; index < backend->requested_outputs; ++index) {
        if (gpiod_line_offset(backend->outputs[index]) == pin) {
            return backend->outputs[index];
        }
    }
    errno = EINVAL;
    return NULL;
}

static int backend_write(void *context, unsigned int pin, bool high) {
    GpiodBackend *backend = context;
    struct gpiod_line *line = find_output(backend, pin);
    if (line == NULL) return -1;
    return gpiod_line_set_value(line, high ? 1 : 0);
}

static int backend_read_columns(
    void *context, const unsigned int pins[SCB_BOARD_COLUMNS],
    bool values[SCB_BOARD_COLUMNS]) {
    GpiodBackend *backend = context;
    for (size_t index = 0U; index < SCB_BOARD_COLUMNS; ++index) {
        int value;
        if (gpiod_line_offset(backend->inputs[index]) != pins[index]) {
            errno = EINVAL;
            return -1;
        }
        value = gpiod_line_get_value(backend->inputs[index]);
        if (value < 0) return -1;
        values[index] = value != 0;
    }
    return 0;
}

#endif

static void print_usage(const char *program) {
    printf(
        "Usage: %s [options]\n"
        "  --gpiochip PATH             GPIO chip (default /dev/gpiochip0)\n"
        "  --address-pins A0,A1,A2     74HC138 address GPIOs\n"
        "  --column-pins C1,...,C8     Eight comparator GPIOs\n"
        "  --columns-active-low        Low means occupied\n"
        "  --address-settle-us N       Decoder delay (default 10)\n"
        "  --sensor-settle-us N        Sensor delay (default 1000)\n"
        "  --poll-ms N                 Delay after each scan (default 20)\n"
        "  --debounce-reads N          Matching scans required (default 3)\n",
        program);
}

static int parse_unsigned(const char *text, unsigned int *value) {
    char *end = NULL;
    unsigned long parsed;
    errno = 0;
    parsed = strtoul(text, &end, 0);
    if (errno != 0 || end == text || *end != '\0' || parsed > 1000000UL) {
        return -1;
    }
    *value = (unsigned int)parsed;
    return 0;
}

static int parse_pin_list(const char *text, unsigned int *pins,
                          size_t expected_count) {
    char buffer[128];
    char *save = NULL;
    char *token;
    size_t count = 0U;
    if (strlen(text) >= sizeof(buffer)) return -1;
    memcpy(buffer, text, strlen(text) + 1U);
    token = strtok_r(buffer, ",", &save);
    while (token != NULL && count < expected_count) {
        if (parse_unsigned(token, &pins[count]) < 0 || pins[count] > 53U) {
            return -1;
        }
        ++count;
        token = strtok_r(NULL, ",", &save);
    }
    return count == expected_count && token == NULL ? 0 : -1;
}

int main(int argc, char **argv) {
    enum {
        OPT_GPIOCHIP = 1000,
        OPT_ADDRESS_PINS,
        OPT_COLUMN_PINS,
        OPT_ACTIVE_LOW,
        OPT_ADDRESS_SETTLE,
        OPT_SENSOR_SETTLE,
        OPT_POLL_MS,
        OPT_DEBOUNCE
    };
    static const struct option options[] = {
        {"gpiochip", required_argument, NULL, OPT_GPIOCHIP},
        {"address-pins", required_argument, NULL, OPT_ADDRESS_PINS},
        {"column-pins", required_argument, NULL, OPT_COLUMN_PINS},
        {"columns-active-low", no_argument, NULL, OPT_ACTIVE_LOW},
        {"address-settle-us", required_argument, NULL, OPT_ADDRESS_SETTLE},
        {"sensor-settle-us", required_argument, NULL, OPT_SENSOR_SETTLE},
        {"poll-ms", required_argument, NULL, OPT_POLL_MS},
        {"debounce-reads", required_argument, NULL, OPT_DEBOUNCE},
        {"help", no_argument, NULL, 'h'},
        {NULL, 0, NULL, 0}
    };
    const char *chip_path = "/dev/gpiochip0";
    unsigned int poll_ms = 20U;
    unsigned int debounce_reads = 3U;
    ScbGpioOps gpio_ops = {NULL, backend_write, backend_read_columns,
                            sleep_microseconds};
    ScbSensorMatrix matrix;
    GpiodBackend backend;
    ScbDebouncer debouncer;
    ScbMoveTracker tracker;
    bool snapshot[SCB_BOARD_SQUARES];
    bool stable[SCB_BOARD_SQUARES];
    int option;
    int exit_code = 1;

    scb_sensor_matrix_defaults(&matrix, gpio_ops);
    while ((option = getopt_long(argc, argv, "h", options, NULL)) != -1) {
        switch (option) {
            case OPT_GPIOCHIP:
                chip_path = optarg;
                break;
            case OPT_ADDRESS_PINS:
                if (parse_pin_list(optarg, matrix.address_pins, 3U) < 0) goto invalid;
                break;
            case OPT_COLUMN_PINS:
                if (parse_pin_list(optarg, matrix.column_pins,
                                   SCB_BOARD_COLUMNS) < 0) goto invalid;
                break;
            case OPT_ACTIVE_LOW:
                matrix.columns_active_low = true;
                break;
            case OPT_ADDRESS_SETTLE:
                if (parse_unsigned(optarg, &matrix.address_settle_us) < 0) goto invalid;
                break;
            case OPT_SENSOR_SETTLE:
                if (parse_unsigned(optarg, &matrix.sensor_settle_us) < 0) goto invalid;
                break;
            case OPT_POLL_MS:
                if (parse_unsigned(optarg, &poll_ms) < 0 || poll_ms == 0U) goto invalid;
                break;
            case OPT_DEBOUNCE:
                if (parse_unsigned(optarg, &debounce_reads) < 0 ||
                    debounce_reads == 0U) goto invalid;
                break;
            case 'h':
                print_usage(argv[0]);
                return 0;
            default:
                goto invalid;
        }
    }
    if (optind != argc || scb_sensor_matrix_validate(&matrix) < 0) goto invalid;
    if (backend_open(&backend, chip_path, &matrix) < 0) {
        fprintf(stderr, "Could not open GPIO lines on %s: %s\n",
                chip_path, strerror(errno));
        return 1;
    }
    matrix.gpio.context = &backend;
    if (scb_sensor_matrix_initialize(&matrix) < 0 ||
        scb_debouncer_initialize(&debouncer, debounce_reads) < 0) {
        fprintf(stderr, "Could not initialize sensor matrix: %s\n", strerror(errno));
        goto cleanup;
    }
    scb_move_tracker_initialize(&tracker);
    (void)signal(SIGINT, stop_running);
    (void)signal(SIGTERM, stop_running);
    puts("Sensor matrix initialized. Press Ctrl-C to stop.");

    while (keep_running) {
        int debounced;
        ScbBoardEvent event;
        if (scb_sensor_matrix_scan(&matrix, snapshot) < 0) {
            fprintf(stderr, "GPIO scan failed: %s\n", strerror(errno));
            goto cleanup;
        }
        debounced = scb_debouncer_update(&debouncer, snapshot, stable);
        if (debounced < 0) goto cleanup;
        if (debounced > 0) {
            if (scb_move_tracker_process(&tracker, stable, &event) < 0) goto cleanup;
            puts(event.message);
            fflush(stdout);
        }
        sleep_microseconds(NULL, poll_ms * 1000U);
    }
    exit_code = 0;

cleanup:
    backend_close(&backend);
    return exit_code;

invalid:
    fprintf(stderr, "Invalid GPIO, timing, or debounce option.\n");
    print_usage(argv[0]);
    return 2;
}
