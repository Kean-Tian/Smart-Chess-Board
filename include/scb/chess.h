#ifndef SCB_CHESS_H
#define SCB_CHESS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
    SCB_WHITE = 0,
    SCB_BLACK = 1
} ScbColor;

typedef enum {
    SCB_PIECE_NONE = 0,
    SCB_PAWN,
    SCB_KNIGHT,
    SCB_BISHOP,
    SCB_ROOK,
    SCB_QUEEN,
    SCB_KING
} ScbPieceType;

typedef struct {
    ScbPieceType type;
    ScbColor color;
} ScbPiece;

typedef struct {
    int from;
    int to;
    ScbPieceType promotion;
} ScbMove;

typedef struct {
    ScbPiece board[64];
    ScbColor turn;
    uint8_t castling;
    int en_passant;
} ScbChessGame;

void scb_chess_init(ScbChessGame *game);
bool scb_chess_make_move(ScbChessGame *game, const ScbMove *move);
bool scb_chess_is_in_check(const ScbChessGame *game, ScbColor color);
bool scb_chess_is_checkmate(const ScbChessGame *game);
bool scb_chess_is_stalemate(const ScbChessGame *game);
ScbPiece scb_chess_piece_at(const ScbChessGame *game, int square);
ScbColor scb_chess_side_to_move(const ScbChessGame *game);
bool scb_chess_parse_square(const char *name, int *square_out);
bool scb_chess_parse_uci(const char *text, ScbMove *move_out);
bool scb_chess_square_name(int square, char output[3]);
size_t scb_chess_board_text(const ScbChessGame *game, char *output, size_t capacity);

#endif

