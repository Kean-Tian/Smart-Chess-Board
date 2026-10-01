#ifndef SCB_LIBCHESS_ADAPTER_H
#define SCB_LIBCHESS_ADAPTER_H

#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    SCB_RULES_WHITE = 0,
    SCB_RULES_BLACK = 1
} ScbRulesSide;

typedef struct ScbRulesGame ScbRulesGame;

ScbRulesGame *scb_rules_create(void);
void scb_rules_destroy(ScbRulesGame *game);

bool scb_rules_is_legal_move(const ScbRulesGame *game, const char *uci);
bool scb_rules_play_move(ScbRulesGame *game, const char *uci);

ScbRulesSide scb_rules_side_to_move(const ScbRulesGame *game);
bool scb_rules_is_in_check(const ScbRulesGame *game);
bool scb_rules_is_checkmate(const ScbRulesGame *game);
bool scb_rules_is_stalemate(const ScbRulesGame *game);
bool scb_rules_is_draw(const ScbRulesGame *game);

size_t scb_rules_fen(const ScbRulesGame *game, char *output, size_t capacity);
size_t scb_rules_board_text(const ScbRulesGame *game, char *output, size_t capacity);
size_t scb_rules_legal_moves(const ScbRulesGame *game, char *output, size_t capacity);

#ifdef __cplusplus
}
#endif

#endif
