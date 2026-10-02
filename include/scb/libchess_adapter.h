#ifndef SCB_LIBCHESS_ADAPTER_H
#define SCB_LIBCHESS_ADAPTER_H

#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
// 让这些函数保持 C 的名字，这样 main.c 才能正常调用。
extern "C" {
#endif

typedef enum {
    SCB_RULES_WHITE = 0,
    SCB_RULES_BLACK = 1
} ScbRulesSide;

// C 代码只拿着这个“棋局句柄”，不用管里面的 C++ 细节。
typedef struct ScbRulesGame ScbRulesGame;

// 创建新棋局，用完后记得销毁。
ScbRulesGame *scb_rules_create(void);
void scb_rules_destroy(ScbRulesGame *game);

// 第一个只问合不合法，第二个会真的把这一步走到棋盘上。
bool scb_rules_is_legal_move(const ScbRulesGame *game, const char *uci);
bool scb_rules_play_move(ScbRulesGame *game, const char *uci);

// 下面这些函数用来查看当前棋局状态。
ScbRulesSide scb_rules_side_to_move(const ScbRulesGame *game);
bool scb_rules_is_in_check(const ScbRulesGame *game);
bool scb_rules_is_checkmate(const ScbRulesGame *game);
bool scb_rules_is_stalemate(const ScbRulesGame *game);
bool scb_rules_is_draw(const ScbRulesGame *game);

// 需要保存或显示棋盘时，就从这里拿 FEN 或普通文本。
size_t scb_rules_fen(const ScbRulesGame *game, char *output, size_t capacity);
size_t scb_rules_board_text(const ScbRulesGame *game, char *output, size_t capacity);
size_t scb_rules_legal_moves(const ScbRulesGame *game, char *output, size_t capacity);

#ifdef __cplusplus
}
#endif

#endif
