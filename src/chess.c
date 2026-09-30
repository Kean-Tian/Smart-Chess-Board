#include "../include/scb/chess.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum {
    WHITE_KING_SIDE = 0x01,
    WHITE_QUEEN_SIDE = 0x02,
    BLACK_KING_SIDE = 0x04,
    BLACK_QUEEN_SIDE = 0x08
};

static int file_of(int square) { return square % 8; }
static int rank_of(int square) { return square / 8; }
static int square_of(int file, int rank) { return rank * 8 + file; }
static ScbColor opposite(ScbColor color) { return color == SCB_WHITE ? SCB_BLACK : SCB_WHITE; }
static bool inside(int file, int rank) { return file >= 0 && file < 8 && rank >= 0 && rank < 8; }

static bool is_promotion_type(ScbPieceType type) {
    return type == SCB_QUEEN || type == SCB_ROOK || type == SCB_BISHOP || type == SCB_KNIGHT;
}

void scb_chess_init(ScbChessGame *game) {
    static const ScbPieceType back_rank[8] = {
        SCB_ROOK, SCB_KNIGHT, SCB_BISHOP, SCB_QUEEN,
        SCB_KING, SCB_BISHOP, SCB_KNIGHT, SCB_ROOK
    };
    if (game == NULL) return;
    memset(game, 0, sizeof(*game));
    for (int file = 0; file < 8; ++file) {
        game->board[square_of(file, 0)] = (ScbPiece){back_rank[file], SCB_WHITE};
        game->board[square_of(file, 1)] = (ScbPiece){SCB_PAWN, SCB_WHITE};
        game->board[square_of(file, 6)] = (ScbPiece){SCB_PAWN, SCB_BLACK};
        game->board[square_of(file, 7)] = (ScbPiece){back_rank[file], SCB_BLACK};
    }
    game->turn = SCB_WHITE;
    game->castling = 0x0f;
    game->en_passant = -1;
}

ScbPiece scb_chess_piece_at(const ScbChessGame *game, int square) {
    const ScbPiece empty = {SCB_PIECE_NONE, SCB_WHITE};
    if (game == NULL || square < 0 || square >= 64) return empty;
    return game->board[square];
}

ScbColor scb_chess_side_to_move(const ScbChessGame *game) {
    return game == NULL ? SCB_WHITE : game->turn;
}

bool scb_chess_parse_square(const char *name, int *square_out) {
    if (name == NULL || square_out == NULL || strlen(name) != 2 || name[0] < 'a' || name[0] > 'h' ||
        name[1] < '1' || name[1] > '8' || name[2] != '\0') return false;
    *square_out = square_of(name[0] - 'a', name[1] - '1');
    return true;
}

bool scb_chess_square_name(int square, char output[3]) {
    if (square < 0 || square >= 64 || output == NULL) return false;
    output[0] = (char)('a' + file_of(square));
    output[1] = (char)('1' + rank_of(square));
    output[2] = '\0';
    return true;
}

bool scb_chess_parse_uci(const char *text, ScbMove *move_out) {
    size_t length;
    int from;
    int to;
    ScbPieceType promotion = SCB_PIECE_NONE;
    char from_name[3];
    char to_name[3];
    if (text == NULL || move_out == NULL) return false;
    length = strlen(text);
    if (length != 4 && length != 5) return false;
    memcpy(from_name, text, 2);
    from_name[2] = '\0';
    memcpy(to_name, text + 2, 2);
    to_name[2] = '\0';
    if (!scb_chess_parse_square(from_name, &from) || !scb_chess_parse_square(to_name, &to)) return false;
    if (length == 5) {
        switch (text[4]) {
        case 'q': promotion = SCB_QUEEN; break;
        case 'r': promotion = SCB_ROOK; break;
        case 'b': promotion = SCB_BISHOP; break;
        case 'n': promotion = SCB_KNIGHT; break;
        default: return false;
        }
    }
    *move_out = (ScbMove){from, to, promotion};
    return true;
}

static bool square_attacked(const ScbChessGame *game, int square, ScbColor by_color) {
    const int file = file_of(square);
    const int rank = rank_of(square);
    const int pawn_rank = rank + (by_color == SCB_WHITE ? -1 : 1);
    for (int pawn_file = file - 1; pawn_file <= file + 1; pawn_file += 2) {
        if (inside(pawn_file, pawn_rank)) {
            ScbPiece piece = game->board[square_of(pawn_file, pawn_rank)];
            if (piece.type == SCB_PAWN && piece.color == by_color) return true;
        }
    }

    static const int knight_offsets[8][2] = {
        {1, 2}, {2, 1}, {-1, 2}, {-2, 1}, {1, -2}, {2, -1}, {-1, -2}, {-2, -1}
    };
    for (int index = 0; index < 8; ++index) {
        int target_file = file + knight_offsets[index][0];
        int target_rank = rank + knight_offsets[index][1];
        if (inside(target_file, target_rank)) {
            ScbPiece piece = game->board[square_of(target_file, target_rank)];
            if (piece.type == SCB_KNIGHT && piece.color == by_color) return true;
        }
    }

    static const int directions[8][2] = {
        {1, 0}, {-1, 0}, {0, 1}, {0, -1}, {1, 1}, {1, -1}, {-1, 1}, {-1, -1}
    };
    for (int direction = 0; direction < 8; ++direction) {
        int target_file = file + directions[direction][0];
        int target_rank = rank + directions[direction][1];
        int distance = 1;
        while (inside(target_file, target_rank)) {
            ScbPiece piece = game->board[square_of(target_file, target_rank)];
            if (piece.type != SCB_PIECE_NONE) {
                if (piece.color == by_color &&
                    (piece.type == SCB_QUEEN ||
                     (distance == 1 && piece.type == SCB_KING) ||
                     ((directions[direction][0] == 0 || directions[direction][1] == 0) && piece.type == SCB_ROOK) ||
                     ((directions[direction][0] != 0 && directions[direction][1] != 0) && piece.type == SCB_BISHOP))) return true;
                break;
            }
            target_file += directions[direction][0];
            target_rank += directions[direction][1];
            ++distance;
        }
    }
    return false;
}

static int king_square(const ScbChessGame *game, ScbColor color) {
    for (int square = 0; square < 64; ++square) {
        ScbPiece piece = game->board[square];
        if (piece.type == SCB_KING && piece.color == color) return square;
    }
    return -1;
}

bool scb_chess_is_in_check(const ScbChessGame *game, ScbColor color) {
    int king;
    if (game == NULL) return false;
    king = king_square(game, color);
    return king >= 0 && square_attacked(game, king, opposite(color));
}

static bool pseudo_legal(const ScbChessGame *game, const ScbMove *move) {
    ScbPiece moving;
    ScbPiece target;
    int from_file, from_rank, to_file, to_rank, dx, dy;
    bool straight, diagonal;
    if (move->from < 0 || move->from >= 64 || move->to < 0 || move->to >= 64 || move->from == move->to) return false;
    moving = game->board[move->from];
    target = game->board[move->to];
    if (moving.type == SCB_PIECE_NONE || moving.color != game->turn ||
        (target.type != SCB_PIECE_NONE && target.color == moving.color) || target.type == SCB_KING) return false;
    from_file = file_of(move->from); from_rank = rank_of(move->from);
    to_file = file_of(move->to); to_rank = rank_of(move->to);
    dx = to_file - from_file; dy = to_rank - from_rank;

    if (moving.type == SCB_PAWN) {
        int direction = moving.color == SCB_WHITE ? 1 : -1;
        int start_rank = moving.color == SCB_WHITE ? 1 : 6;
        int final_rank = moving.color == SCB_WHITE ? 7 : 0;
        if (to_rank == final_rank) {
            if (!is_promotion_type(move->promotion)) return false;
        } else if (move->promotion != SCB_PIECE_NONE) return false;
        if (dx == 0 && dy == direction && target.type == SCB_PIECE_NONE) return true;
        if (dx == 0 && dy == 2 * direction && from_rank == start_rank && target.type == SCB_PIECE_NONE &&
            game->board[square_of(from_file, from_rank + direction)].type == SCB_PIECE_NONE) return true;
        if (abs(dx) == 1 && dy == direction) {
            if (target.type != SCB_PIECE_NONE) return true;
            if (move->to == game->en_passant) {
                ScbPiece adjacent = game->board[square_of(to_file, from_rank)];
                return adjacent.type == SCB_PAWN && adjacent.color != moving.color;
            }
        }
        return false;
    }
    if (move->promotion != SCB_PIECE_NONE) return false;
    if (moving.type == SCB_KNIGHT) return (abs(dx) == 1 && abs(dy) == 2) || (abs(dx) == 2 && abs(dy) == 1);
    if (moving.type == SCB_KING && (abs(dx) <= 1 && abs(dy) <= 1)) return dx != 0 || dy != 0;

    straight = dx == 0 || dy == 0;
    diagonal = abs(dx) == abs(dy);
    if ((moving.type == SCB_ROOK && !straight) || (moving.type == SCB_BISHOP && !diagonal) ||
        (moving.type == SCB_QUEEN && !straight && !diagonal)) return false;

    if (moving.type == SCB_KING && dy == 0 && abs(dx) == 2 && from_file == 4 &&
        from_rank == (moving.color == SCB_WHITE ? 0 : 7) && !square_attacked(game, move->from, opposite(moving.color))) {
        bool king_side = dx > 0;
        uint8_t right = moving.color == SCB_WHITE
            ? (king_side ? WHITE_KING_SIDE : WHITE_QUEEN_SIDE)
            : (king_side ? BLACK_KING_SIDE : BLACK_QUEEN_SIDE);
        int rook_file = king_side ? 7 : 0;
        ScbPiece rook = game->board[square_of(rook_file, from_rank)];
        int step = king_side ? 1 : -1;
        if ((game->castling & right) == 0 || rook.type != SCB_ROOK || rook.color != moving.color) return false;
        for (int file = from_file + step; file != rook_file; file += step) {
            if (game->board[square_of(file, from_rank)].type != SCB_PIECE_NONE) return false;
        }
        return !square_attacked(game, square_of(from_file + step, from_rank), opposite(moving.color)) &&
               !square_attacked(game, square_of(from_file + 2 * step, from_rank), opposite(moving.color));
    }

    if ((moving.type == SCB_ROOK || moving.type == SCB_BISHOP || moving.type == SCB_QUEEN) && (straight || diagonal)) {
        int step_file = (dx > 0) - (dx < 0);
        int step_rank = (dy > 0) - (dy < 0);
        int file = from_file + step_file;
        int rank = from_rank + step_rank;
        while (file != to_file || rank != to_rank) {
            if (game->board[square_of(file, rank)].type != SCB_PIECE_NONE) return false;
            file += step_file;
            rank += step_rank;
        }
        return true;
    }
    return false;
}

static void apply_unchecked(ScbChessGame *game, const ScbMove *move) {
    ScbPiece moving = game->board[move->from];
    int from_file = file_of(move->from), from_rank = rank_of(move->from);
    int to_file = file_of(move->to), to_rank = rank_of(move->to);
    if (moving.type == SCB_PAWN && move->to == game->en_passant && from_file != to_file &&
        game->board[move->to].type == SCB_PIECE_NONE) {
        game->board[square_of(to_file, from_rank)] = (ScbPiece){SCB_PIECE_NONE, SCB_WHITE};
    }
    if (moving.type == SCB_KING && abs(to_file - from_file) == 2) {
        bool king_side = to_file > from_file;
        int rook_from = square_of(king_side ? 7 : 0, from_rank);
        int rook_to = square_of(king_side ? 5 : 3, from_rank);
        game->board[rook_to] = game->board[rook_from];
        game->board[rook_from] = (ScbPiece){SCB_PIECE_NONE, SCB_WHITE};
    }
    game->board[move->from] = (ScbPiece){SCB_PIECE_NONE, SCB_WHITE};
    if (move->promotion != SCB_PIECE_NONE) moving.type = move->promotion;
    game->board[move->to] = moving;
    game->en_passant = -1;
    if (moving.type == SCB_PAWN && abs(to_rank - from_rank) == 2) game->en_passant = square_of(from_file, (from_rank + to_rank) / 2);
    if (moving.type == SCB_KING) {
        game->castling &= moving.color == SCB_WHITE
            ? (uint8_t)~(WHITE_KING_SIDE | WHITE_QUEEN_SIDE)
            : (uint8_t)~(BLACK_KING_SIDE | BLACK_QUEEN_SIDE);
    }
    if (move->from == square_of(0, 0) || move->to == square_of(0, 0)) game->castling &= (uint8_t)~WHITE_QUEEN_SIDE;
    if (move->from == square_of(7, 0) || move->to == square_of(7, 0)) game->castling &= (uint8_t)~WHITE_KING_SIDE;
    if (move->from == square_of(0, 7) || move->to == square_of(0, 7)) game->castling &= (uint8_t)~BLACK_QUEEN_SIDE;
    if (move->from == square_of(7, 7) || move->to == square_of(7, 7)) game->castling &= (uint8_t)~BLACK_KING_SIDE;
    game->turn = opposite(game->turn);
}

bool scb_chess_make_move(ScbChessGame *game, const ScbMove *move) {
    ScbChessGame next;
    int king;
    if (game == NULL || move == NULL || !pseudo_legal(game, move)) return false;
    next = *game;
    apply_unchecked(&next, move);
    king = king_square(&next, game->turn);
    if (king < 0 || square_attacked(&next, king, opposite(game->turn))) return false;
    *game = next;
    return true;
}

static bool has_legal_move(const ScbChessGame *game) {
    static const ScbPieceType promotions[4] = {SCB_QUEEN, SCB_ROOK, SCB_BISHOP, SCB_KNIGHT};
    for (int from = 0; from < 64; ++from) {
        ScbPiece piece = game->board[from];
        if (piece.type == SCB_PIECE_NONE || piece.color != game->turn) continue;
        for (int to = 0; to < 64; ++to) {
            bool promotes = piece.type == SCB_PAWN && rank_of(to) == (piece.color == SCB_WHITE ? 7 : 0);
            int choices = promotes ? 4 : 1;
            for (int choice = 0; choice < choices; ++choice) {
                ScbMove move = {from, to, promotes ? promotions[choice] : SCB_PIECE_NONE};
                ScbChessGame next;
                int king;
                if (!pseudo_legal(game, &move)) continue;
                next = *game;
                apply_unchecked(&next, &move);
                king = king_square(&next, game->turn);
                if (king >= 0 && !square_attacked(&next, king, opposite(game->turn))) return true;
            }
        }
    }
    return false;
}

bool scb_chess_is_checkmate(const ScbChessGame *game) {
    return game != NULL && scb_chess_is_in_check(game, game->turn) && !has_legal_move(game);
}

bool scb_chess_is_stalemate(const ScbChessGame *game) {
    return game != NULL && !scb_chess_is_in_check(game, game->turn) && !has_legal_move(game);
}

static char piece_character(ScbPiece piece) {
    static const char symbols[] = ".pnbrqk";
    char value;
    if (piece.type < SCB_PAWN || piece.type > SCB_KING) return '.';
    value = symbols[piece.type];
    return piece.color == SCB_WHITE ? (char)toupper((unsigned char)value) : value;
}

size_t scb_chess_board_text(const ScbChessGame *game, char *output, size_t capacity) {
    size_t used = 0;
    if (game == NULL || output == NULL || capacity == 0) return 0;
    output[0] = '\0';
    for (int rank = 7; rank >= 0; --rank) {
        int written = snprintf(output + used, capacity - used, "%d ", rank + 1);
        if (written < 0 || (size_t)written >= capacity - used) return used;
        used += (size_t)written;
        for (int file = 0; file < 8; ++file) {
            written = snprintf(output + used, capacity - used, "%c ", piece_character(game->board[square_of(file, rank)]));
            if (written < 0 || (size_t)written >= capacity - used) return used;
            used += (size_t)written;
        }
        written = snprintf(output + used, capacity - used, "\n");
        if (written < 0 || (size_t)written >= capacity - used) return used;
        used += (size_t)written;
    }
    {
        int written = snprintf(output + used, capacity - used, "  a b c d e f g h\n%s to move\n",
                               game->turn == SCB_WHITE ? "White" : "Black");
        if (written > 0 && (size_t)written < capacity - used) used += (size_t)written;
    }
    return used;
}
