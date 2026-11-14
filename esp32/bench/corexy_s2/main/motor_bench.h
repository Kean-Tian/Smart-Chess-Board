#ifndef SCB_MOTOR_BENCH_H
#define SCB_MOTOR_BENCH_H
#include "scb/motor_control.h"
#include <stddef.h>

#define SCB_BENCH_LINE_CAPACITY 128U
#define SCB_BENCH_POLL_US 1000U
#define SCB_BENCH_LINK_TIMEOUT_US INT64_C(2000000)
#define SCB_BENCH_MOVE_TIMEOUT_US INT64_C(30000000)
typedef struct {
    ScbMotor motor;
    ScbMotorIo io;
    ScbMotorPins pins;
    ScbMotorConfig config;
    void *emit_ctx;
    void (*emit)(void *, const char *);
    unsigned configured, move_id;
    bool ping_seen, discard;
    int64_t last_ping_us, move_started_us;
    char line[SCB_BENCH_LINE_CAPACITY];
    size_t length;
} ScbMotorBench;
void scb_motor_bench_init(ScbMotorBench *, ScbMotorIo, ScbMotorPins,
                         void (*emit)(void *, const char *), void *emit_ctx);
void scb_motor_bench_feed(ScbMotorBench *, const void *, size_t, int64_t now_us);
void scb_motor_bench_tick(ScbMotorBench *, int64_t now_us);
#endif
