#ifndef SCB_MOTOR_CONTROL_H
#define SCB_MOTOR_CONTROL_H
#include <stdbool.h>
#include <stdint.h>

/* Board-independent, single-owner API. Pins are supplied by the caller.
 * No GPIO configuration, magnet control, heap allocation or background tasks.
 * Call tick from a periodic task; it never waits or emits catch-up bursts.
 */
#define SCB_MOTOR_EDGE_US 5U
#define SCB_MOTOR_POSITION_LIMIT INT64_C(1000000000)

typedef enum {
    SCB_MOTOR_OK, SCB_MOTOR_CONFIG, SCB_MOTOR_BUSY, SCB_MOTOR_DISABLED,
    SCB_MOTOR_REFERENCE, SCB_MOTOR_LIMIT, SCB_MOTOR_GPIO, SCB_MOTOR_TIME
} ScbMotorResult;

typedef struct {
    unsigned step[2], dir[2], enable; /* A=X driver, B=Y driver; EN active LOW. */
} ScbMotorPins;
typedef struct {
    void *ctx;
    bool (*write)(void *, unsigned pin, bool high);
} ScbMotorIo;
typedef struct {
    /* Signed CoreXY mapping, including motor order and electrical DIR polarity:
     * A = steps_per_mm[0] * (map[0][0]*X + map[0][1]*Y), likewise B.
     * Every coefficient must explicitly be +1 or -1; rows must be orthogonal.
     * There is deliberately no default mapping or mechanical calibration.
     */
    int map[2][2];
    double steps_per_mm[2]; /* Full steps with MS1/MS2/MS3 grounded. */
    double min_mm[2], max_mm[2];
    double speed_mm_s, acceleration_mm_s2;
    uint32_t poll_period_us; /* Caller schedule; caps event rate at 1/(2*period). */
} ScbMotorConfig;

typedef struct {
    ScbMotorIo io;
    ScbMotorPins pins;
    ScbMotorConfig config;
    bool initialized, enabled, referenced, moving, high[2], faulted;
    int64_t position[2], target[2]; /* Emitted motor steps relative to reference. */
    int sign[2];
    uint32_t magnitude[2], error[2], total, emitted;
    double reference_mm[2];
    double event_acceleration, peak_rate, accel_time, accel_distance, duration;
    int64_t last_tick_us, rise_at_us, fall_at_us, low_until_us;
} ScbMotor;

/* init first disables EN and clears STEP, including for invalid calibration.
 * Do not reinitialize a live instance: stop first. Hardware pins must already
 * be configured as outputs with EN preloaded HIGH by the board's startup code.
 */
ScbMotorResult scb_motor_init(ScbMotor *, ScbMotorIo, ScbMotorPins,
                            const ScbMotorConfig *, int64_t now_us);
ScbMotorResult scb_motor_enable(ScbMotor *);
/* Immediate stop/disable, always invalidates reference (coils lose holding torque). */
ScbMotorResult scb_motor_stop(ScbMotor *);
/* Explicit manual alignment, or a position supplied by separately verified homing. */
ScbMotorResult scb_motor_reference(ScbMotor *, double x_mm, double y_mm);
ScbMotorResult scb_motor_position(const ScbMotor *, double *x_mm, double *y_mm);
ScbMotorResult scb_motor_profile(ScbMotor *, double speed_mm_s, double acceleration_mm_s2);
ScbMotorResult scb_motor_move_to(ScbMotor *, double x_mm, double y_mm, int64_t now_us);
/* Relative A/B motor steps for independent-driver tests; still requires reference
 * and checks Cartesian limits. A-only movement moves BOTH CoreXY coordinates.
 */
ScbMotorResult scb_motor_move_motors(ScbMotor *, int32_t a_steps, int32_t b_steps, int64_t now_us);
ScbMotorResult scb_motor_tick(ScbMotor *, int64_t now_us);
const char *scb_motor_result_name(ScbMotorResult);
#endif
