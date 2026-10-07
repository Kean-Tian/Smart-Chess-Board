#ifndef SCB_SENSOR_MATRIX_H
#define SCB_SENSOR_MATRIX_H

#include <stdbool.h>
#include <stddef.h>

#define SCB_BOARD_ROWS 8U
#define SCB_BOARD_COLUMNS 8U
#define SCB_BOARD_SQUARES 64U
#define SCB_NO_SQUARE (-1)

typedef struct {
    void *context;
    int (*write)(void *context, unsigned int pin, bool high);
    int (*read_columns)(void *context, const unsigned int pins[SCB_BOARD_COLUMNS],
                        bool values[SCB_BOARD_COLUMNS]);
    void (*sleep_us)(void *context, unsigned int microseconds);
} ScbGpioOps;

typedef struct {
    ScbGpioOps gpio;
    unsigned int address_pins[3];
    unsigned int enable_pin;
    unsigned int column_pins[SCB_BOARD_COLUMNS];
    bool columns_active_low;
    unsigned int address_settle_us;
    unsigned int sensor_settle_us;
} ScbSensorMatrix;

void scb_sensor_matrix_defaults(ScbSensorMatrix *matrix, ScbGpioOps gpio);
int scb_sensor_matrix_validate(const ScbSensorMatrix *matrix);
int scb_sensor_matrix_initialize(ScbSensorMatrix *matrix);
int scb_sensor_matrix_scan(ScbSensorMatrix *matrix,
                           bool occupied[SCB_BOARD_SQUARES]);
void scb_sensor_matrix_disable(ScbSensorMatrix *matrix);

typedef struct {
    unsigned int required_reads;
    unsigned int candidate_count;
    bool has_candidate;
    bool has_stable;
    bool candidate[SCB_BOARD_SQUARES];
    bool stable[SCB_BOARD_SQUARES];
} ScbDebouncer;

int scb_debouncer_initialize(ScbDebouncer *debouncer,
                             unsigned int required_reads);
int scb_debouncer_update(ScbDebouncer *debouncer,
                         const bool snapshot[SCB_BOARD_SQUARES],
                         bool stable_snapshot[SCB_BOARD_SQUARES]);

typedef enum {
    SCB_EVENT_READY,
    SCB_EVENT_LIFT,
    SCB_EVENT_PLACE,
    SCB_EVENT_MOVE,
    SCB_EVENT_AMBIGUOUS
} ScbEventKind;

typedef struct {
    ScbEventKind kind;
    int source;
    int destination;
    char message[96];
} ScbBoardEvent;

typedef struct {
    bool initialized;
    bool previous[SCB_BOARD_SQUARES];
    unsigned int pending_lifts[SCB_BOARD_SQUARES];
    size_t pending_count;
} ScbMoveTracker;

void scb_move_tracker_initialize(ScbMoveTracker *tracker);
int scb_move_tracker_process(ScbMoveTracker *tracker,
                             const bool snapshot[SCB_BOARD_SQUARES],
                             ScbBoardEvent *event);

int scb_square_index(const char *name);
void scb_square_name(unsigned int index, char name[3]);

#endif
