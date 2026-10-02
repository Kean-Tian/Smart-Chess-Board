#include "../include/scb/libchess_adapter.h"

#include <libchess/position.hpp>

#include <cctype>
#include <cstring>
#include <new>
#include <string>

// 真正的 libchess 棋盘藏在这里，C 文件只会看到一个指针。
struct ScbRulesGame {
    libchess::Position position{"startpos"};
};

namespace {

// 把 C++ 字符串交给 C 使用，空间不够时就直接返回失败。
size_t copy_text(const std::string &text, char *output, size_t capacity) {
    if (output == nullptr || capacity == 0 || text.size() + 1 > capacity) {
        if (output != nullptr && capacity > 0) output[0] = '\0';
        return 0;
    }
    std::memcpy(output, text.c_str(), text.size() + 1);
    return text.size();
}

char piece_character(const libchess::Position &position, int square) {
    static constexpr char symbols[] = "pnbrqk";
    const libchess::Square location{square};
    const libchess::Piece piece = position.piece_on(location);
    if (piece == libchess::Piece::None) return '.';

    // 白棋显示成大写，黑棋显示成小写，看起来更直观。
    char symbol = symbols[static_cast<int>(piece)];
    if (position.occupancy(libchess::Side::White).get(location)) {
        symbol = static_cast<char>(std::toupper(static_cast<unsigned char>(symbol)));
    }
    return symbol;
}

}  

// 从这里开始都是给 C 文件调用的接口。
extern "C" {

ScbRulesGame *scb_rules_create(void) {
    try {
        return new ScbRulesGame;
    } catch (...) {
        // 创建失败时不让异常跑进 C 代码，用空指针表示失败。
        return nullptr;
    }
}

void scb_rules_destroy(ScbRulesGame *game) {
    delete game;
}

bool scb_rules_is_legal_move(const ScbRulesGame *game, const char *uci) {
    if (game == nullptr || uci == nullptr) return false;
    try {
        // parse_move 找不到这个合法走法时会报错。
        (void)game->position.parse_move(uci);
        return true;
    } catch (...) {
        return false;
    }
}

bool scb_rules_play_move(ScbRulesGame *game, const char *uci) {
    if (game == nullptr || uci == nullptr) return false;
    try {
        // 先让 libchess 检查，确认没问题后再更新棋盘。
        const libchess::Move move = game->position.parse_move(uci);
        game->position.makemove(move);
        return true;
    } catch (...) {
        return false;
    }
}

ScbRulesSide scb_rules_side_to_move(const ScbRulesGame *game) {
    if (game == nullptr || game->position.turn() == libchess::Side::White) return SCB_RULES_WHITE;
    return SCB_RULES_BLACK;
}

bool scb_rules_is_in_check(const ScbRulesGame *game) {
    return game != nullptr && game->position.in_check();
}

bool scb_rules_is_checkmate(const ScbRulesGame *game) {
    return game != nullptr && game->position.is_checkmate();
}

bool scb_rules_is_stalemate(const ScbRulesGame *game) {
    return game != nullptr && game->position.is_stalemate();
}

bool scb_rules_is_draw(const ScbRulesGame *game) {
    return game != nullptr && game->position.is_draw();
}

size_t scb_rules_fen(const ScbRulesGame *game, char *output, size_t capacity) {
    if (game == nullptr) return 0;
    return copy_text(game->position.get_fen(), output, capacity);
}

size_t scb_rules_board_text(const ScbRulesGame *game, char *output, size_t capacity) {
    if (game == nullptr) return 0;

    std::string text;
    text.reserve(160);
    // 从第八行往下打印，就是平常看到的白方视角。
    for (int rank = 7; rank >= 0; --rank) {
        text += static_cast<char>('1' + rank);
        text += ' ';
        for (int file = 0; file < 8; ++file) {
            text += piece_character(game->position, rank * 8 + file);
            text += ' ';
        }
        text += '\n';
    }
    text += "  a b c d e f g h\n";
    text += game->position.turn() == libchess::Side::White ? "White to move\n" : "Black to move\n";
    return copy_text(text, output, capacity);
}

size_t scb_rules_legal_moves(const ScbRulesGame *game, char *output, size_t capacity) {
    if (game == nullptr) return 0;

    std::string text;
    for (const libchess::Move &move : game->position.legal_moves()) {
        if (!text.empty()) text += ' ';
        if (move.type() == libchess::MoveType::ksc) {
            text += game->position.turn() == libchess::Side::White ? "e1g1" : "e8g8";
        } else if (move.type() == libchess::MoveType::qsc) {
            text += game->position.turn() == libchess::Side::White ? "e1c1" : "e8c8";
        } else {
            text += static_cast<std::string>(move);
        }
    }
    return copy_text(text, output, capacity);
}

}  // extern "C"
