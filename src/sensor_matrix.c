#include "scb/sensor_matrix.h"

#include <errno.h>
#include <stdio.h>
#include <string.h>

static void set_invalid_argument(void) {
    errno = EINVAL;
}

void scb_sensor_matrix_defaults(ScbSensorMatrix *matrix, ScbGpioOps gpio) {
    static const unsigned int address_pins[3] = {17U, 27U, 22U};
    static const unsigned int column_pins[SCB_BOARD_COLUMNS] = {
        5U, 6U, 12U, 13U, 16U, 19U, 20U, 21U
    };
    if (matrix == NULL) return;
    memset(matrix, 0, sizeof(*matrix));
    matrix->gpio = gpio;
    memcpy(matrix->address_pins, address_pins, sizeof(address_pins));
    matrix->enable_pin = 23U;
    memcpy(matrix->column_pins, column_pins, sizeof(column_pins));
    matrix->address_settle_us = 10U;
    matrix->sensor_settle_us = 1000U;
}

int scb_sensor_matrix_validate(const ScbSensorMatrix *matrix) {
    unsigned int pins[12];
    size_t count = 0U;
    if (matrix == NULL || matrix->gpio.write == NULL ||
        matrix->gpio.read_columns == NULL || matrix->gpio.sleep_us == NULL) {
        set_invalid_argument();
        return -1;
    }
    for (size_t index = 0U; index < 3U; ++index) {
        pins[count++] = matrix->address_pins[index];
    }
    pins[count++] = matrix->enable_pin;
    for (size_t index = 0U; index < SCB_BOARD_COLUMNS; ++index) {
        pins[count++] = matrix->column_pins[index];
    }
    for (size_t left = 0U; left < count; ++left) {
        if (pins[left] > 53U) {
            set_invalid_argument();
            return -1;
        }
        for (size_t right = left + 1U; right < count; ++right) {
            if (pins[left] == pins[right]) {
                set_invalid_argument();
                return -1;
            }
        }
    }
    return 0;
}

int scb_sensor_matrix_initialize(ScbSensorMatrix *matrix) {
    if (scb_sensor_matrix_validate(matrix) < 0) return -1;
    if (matrix->gpio.write(matrix->gpio.context, matrix->enable_pin, false) < 0) {
        return -1;
    }
    for (size_t index = 0U; index < 3U; ++index) {
        if (matrix->gpio.write(matrix->gpio.context,
                               matrix->address_pins[index], false) < 0) {
            return -1;
        }
    }
    return 0;
}

void scb_sensor_matrix_disable(ScbSensorMatrix *matrix) {
    if (matrix != NULL && matrix->gpio.write != NULL) {
        (void)matrix->gpio.write(matrix->gpio.context, matrix->enable_pin, false);
    }
}

int scb_sensor_matrix_scan(ScbSensorMatrix *matrix,
                           bool occupied[SCB_BOARD_SQUARES]) {
    bool levels[SCB_BOARD_COLUMNS];
    int result = 0;
    if (occupied == NULL || scb_sensor_matrix_validate(matrix) < 0) return -1;
    memset(occupied, 0, sizeof(bool) * SCB_BOARD_SQUARES);

    for (unsigned int row = 0U; row < SCB_BOARD_ROWS; ++row) {
        if (matrix->gpio.write(matrix->gpio.context,
                               matrix->enable_pin, false) < 0) {
            result = -1;
            break;
        }
        for (unsigned int bit = 0U; bit < 3U; ++bit) {
            bool high = (row & (1U << bit)) != 0U;
            if (matrix->gpio.write(matrix->gpio.context,
                                   matrix->address_pins[bit], high) < 0) {
                result = -1;
                break;
            }
        }
        if (result < 0) break;
        matrix->gpio.sleep_us(matrix->gpio.context, matrix->address_settle_us);
        if (matrix->gpio.write(matrix->gpio.context,
                               matrix->enable_pin, true) < 0) {
            result = -1;
            break;
        }
        matrix->gpio.sleep_us(matrix->gpio.context, matrix->sensor_settle_us);
        if (matrix->gpio.read_columns(matrix->gpio.context,
                                      matrix->column_pins, levels) < 0) {
            result = -1;
            break;
        }
        for (unsigned int column = 0U; column < SCB_BOARD_COLUMNS; ++column) {
            bool detected = matrix->columns_active_low ? !levels[column] : levels[column];
            occupied[row * SCB_BOARD_COLUMNS + column] = detected;
        }
    }
    scb_sensor_matrix_disable(matrix);
    return result;
}

int scb_debouncer_initialize(ScbDebouncer *debouncer,
                             unsigned int required_reads) {
    if (debouncer == NULL || required_reads == 0U) {
        set_invalid_argument();
        return -1;
    }
    memset(debouncer, 0, sizeof(*debouncer));
    debouncer->required_reads = required_reads;
    return 0;
}

int scb_debouncer_update(ScbDebouncer *debouncer,
                         const bool snapshot[SCB_BOARD_SQUARES],
                         bool stable_snapshot[SCB_BOARD_SQUARES]) {
    size_t bytes = sizeof(bool) * SCB_BOARD_SQUARES;
    if (debouncer == NULL || snapshot == NULL || stable_snapshot == NULL ||
        debouncer->required_reads == 0U) {
        set_invalid_argument();
        return -1;
    }
    if (debouncer->has_candidate &&
        memcmp(snapshot, debouncer->candidate, bytes) == 0) {
        ++debouncer->candidate_count;
    } else {
        memcpy(debouncer->candidate, snapshot, bytes);
        debouncer->candidate_count = 1U;
        debouncer->has_candidate = true;
    }
    if (debouncer->candidate_count < debouncer->required_reads) return 0;
    if (debouncer->has_stable &&
        memcmp(snapshot, debouncer->stable, bytes) == 0) {
        return 0;
    }
    memcpy(debouncer->stable, snapshot, bytes);
    memcpy(stable_snapshot, snapshot, bytes);
    debouncer->has_stable = true;
    return 1;
}

int scb_square_index(const char *name) {
    if (name == NULL || name[0] < 'a' || name[0] > 'h' ||
        name[1] < '1' || name[1] > '8' || name[2] != '\0') {
        set_invalid_argument();
        return -1;
    }
    return (name[1] - '1') * 8 + (name[0] - 'a');
}

void scb_square_name(unsigned int index, char name[3]) {
    if (name == NULL) return;
    if (index >= SCB_BOARD_SQUARES) {
        name[0] = '?';
        name[1] = '?';
    } else {
        name[0] = (char)('a' + index % 8U);
        name[1] = (char)('1' + index / 8U);
    }
    name[2] = '\0';
}

void scb_move_tracker_initialize(ScbMoveTracker *tracker) {
    if (tracker != NULL) memset(tracker, 0, sizeof(*tracker));
}

static void event_initialize(ScbBoardEvent *event, ScbEventKind kind) {
    memset(event, 0, sizeof(*event));
    event->kind = kind;
    event->source = SCB_NO_SQUARE;
    event->destination = SCB_NO_SQUARE;
}

static bool pending_contains(const ScbMoveTracker *tracker,
                             unsigned int square) {
    for (size_t index = 0U; index < tracker->pending_count; ++index) {
        if (tracker->pending_lifts[index] == square) return true;
    }
    return false;
}

static void pending_remove(ScbMoveTracker *tracker, unsigned int square) {
    for (size_t index = 0U; index < tracker->pending_count; ++index) {
        if (tracker->pending_lifts[index] == square) {
            memmove(&tracker->pending_lifts[index],
                    &tracker->pending_lifts[index + 1U],
                    (tracker->pending_count - index - 1U) * sizeof(unsigned int));
            --tracker->pending_count;
            return;
        }
    }
}

static void format_square_list(char *output, size_t capacity, const char *prefix,
                               const unsigned int *squares, size_t count) {
    size_t used = (size_t)snprintf(output, capacity, "%s", prefix);
    for (size_t index = 0U; index < count && used < capacity; ++index) {
        char name[3];
        scb_square_name(squares[index], name);
        int written = snprintf(output + used, capacity - used, "%s%s",
                               index == 0U ? " " : ",", name);
        if (written < 0) break;
        used += (size_t)written;
    }
}

static int complete_move(ScbMoveTracker *tracker, unsigned int source,
                         unsigned int destination, ScbBoardEvent *event) {
    char source_name[3];
    char destination_name[3];
    scb_square_name(source, source_name);
    scb_square_name(destination, destination_name);
    tracker->pending_count = 0U;
    event_initialize(event, SCB_EVENT_MOVE);
    event->source = (int)source;
    event->destination = (int)destination;
    (void)snprintf(event->message, sizeof(event->message), "MOVE %s%s",
                   source_name, destination_name);
    return 0;
}

int scb_move_tracker_process(ScbMoveTracker *tracker,
                             const bool snapshot[SCB_BOARD_SQUARES],
                             ScbBoardEvent *event) {
    unsigned int removed[SCB_BOARD_SQUARES];
    unsigned int added[SCB_BOARD_SQUARES];
    size_t removed_count = 0U;
    size_t added_count = 0U;
    if (tracker == NULL || snapshot == NULL || event == NULL) {
        set_invalid_argument();
        return -1;
    }
    if (!tracker->initialized) {
        memcpy(tracker->previous, snapshot, sizeof(tracker->previous));
        tracker->initialized = true;
        event_initialize(event, SCB_EVENT_READY);
        unsigned int pieces = 0U;
        for (size_t index = 0U; index < SCB_BOARD_SQUARES; ++index) {
            if (snapshot[index]) ++pieces;
        }
        (void)snprintf(event->message, sizeof(event->message),
                       "READY %u PIECES", pieces);
        return 0;
    }

    for (unsigned int index = 0U; index < SCB_BOARD_SQUARES; ++index) {
        if (tracker->previous[index] && !snapshot[index]) {
            removed[removed_count++] = index;
        } else if (!tracker->previous[index] && snapshot[index]) {
            added[added_count++] = index;
        }
    }
    memcpy(tracker->previous, snapshot, sizeof(tracker->previous));

    for (size_t index = 0U; index < removed_count; ++index) {
        if (!pending_contains(tracker, removed[index])) {
            tracker->pending_lifts[tracker->pending_count++] = removed[index];
        }
    }

    for (size_t index = 0U; index < added_count; ++index) {
        unsigned int destination = added[index];
        if (pending_contains(tracker, destination)) {
            if (tracker->pending_count == 2U) {
                unsigned int source = tracker->pending_lifts[0] == destination
                                          ? tracker->pending_lifts[1]
                                          : tracker->pending_lifts[0];
                return complete_move(tracker, source, destination, event);
            }
            if (tracker->pending_count == 1U) {
                char name[3];
                pending_remove(tracker, destination);
                scb_square_name(destination, name);
                event_initialize(event, SCB_EVENT_PLACE);
                (void)snprintf(event->message, sizeof(event->message),
                               "RETURN %s", name);
                return 0;
            }
        } else if (tracker->pending_count == 1U) {
            return complete_move(tracker, tracker->pending_lifts[0],
                                 destination, event);
        }
    }

    if (added_count > 0U && tracker->pending_count == 0U) {
        event_initialize(event, SCB_EVENT_PLACE);
        format_square_list(event->message, sizeof(event->message),
                           "PLACE", added, added_count);
    } else if (removed_count > 0U) {
        event_initialize(event, SCB_EVENT_LIFT);
        format_square_list(event->message, sizeof(event->message),
                           "LIFT", removed, removed_count);
    } else if (tracker->pending_count > 1U) {
        event_initialize(event, SCB_EVENT_AMBIGUOUS);
        format_square_list(event->message, sizeof(event->message),
                           "WAIT PLACE", tracker->pending_lifts,
                           tracker->pending_count);
    } else if (tracker->pending_count == 1U) {
        event_initialize(event, SCB_EVENT_LIFT);
        format_square_list(event->message, sizeof(event->message),
                           "LIFT", tracker->pending_lifts, 1U);
    } else {
        unsigned int pieces = 0U;
        event_initialize(event, SCB_EVENT_READY);
        for (size_t index = 0U; index < SCB_BOARD_SQUARES; ++index) {
            if (snapshot[index]) ++pieces;
        }
        (void)snprintf(event->message, sizeof(event->message),
                       "READY %u PIECES", pieces);
    }
    return 0;
}
