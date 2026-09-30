#include "../include/scb/chess.h"

#include <stdio.h>
#include <stdlib.h>

static void require(bool condition, const char *message) {
    if (!condition) {
        fprintf(stderr, "FAIL: %s\n", message);
        exit(1);
    }
}

static bool play(ScbChessGame *game, const char *uci) {
    ScbMove move;
    return scb_chess_parse_uci(uci, &move) && scb_chess_make_move(game, &move);
}

int main(void) {
    ScbChessGame game;
    scb_chess_init(&game);
    require(play(&game, "e2e4"), "accept initial pawn move");
    require(!play(&game, "d2d4"), "reject out-of-turn move");
    require(play(&game, "e7e5"), "accept black pawn move after white move");

    ScbChessGame blocked_rook;
    scb_chess_init(&blocked_rook);
    require(!play(&blocked_rook, "a1a3"), "reject rook move through own pawn");

    ScbChessGame fools_mate;
    scb_chess_init(&fools_mate);
    require(play(&fools_mate, "f2f3"), "Fool's mate move 1");
    require(play(&fools_mate, "e7e5"), "Fool's mate move 2");
    require(play(&fools_mate, "g2g4"), "Fool's mate move 3");
    require(play(&fools_mate, "d8h4"), "Fool's mate move 4");
    require(scb_chess_is_in_check(&fools_mate, SCB_WHITE), "detect check");
    require(scb_chess_is_checkmate(&fools_mate), "detect checkmate");

    ScbChessGame en_passant;
    scb_chess_init(&en_passant);
    require(play(&en_passant, "e2e4"), "en passant setup 1");
    require(play(&en_passant, "a7a6"), "en passant setup 2");
    require(play(&en_passant, "e4e5"), "en passant setup 3");
    require(play(&en_passant, "d7d5"), "en passant setup 4");
    require(play(&en_passant, "e5d6"), "allow en passant capture");
    int square = -1;
    require(scb_chess_parse_square("d5", &square), "parse captured en passant square");
    require(scb_chess_piece_at(&en_passant, square).type == SCB_PIECE_NONE, "remove en passant captured pawn");

    ScbChessGame castling;
    scb_chess_init(&castling);
    const char *castle_moves[] = {"e2e4", "e7e5", "g1f3", "b8c6", "f1e2", "g8f6", "e1g1"};
    for (size_t index = 0; index < sizeof(castle_moves) / sizeof(castle_moves[0]); ++index) {
        require(play(&castling, castle_moves[index]), "allow legal kingside castling sequence");
    }
    int king_square = -1;
    int rook_square = -1;
    require(scb_chess_parse_square("g1", &king_square), "parse castled king square");
    require(scb_chess_parse_square("f1", &rook_square), "parse castled rook square");
    require(scb_chess_piece_at(&castling, king_square).type == SCB_KING, "move king during castling");
    require(scb_chess_piece_at(&castling, rook_square).type == SCB_ROOK, "move rook during castling");

    ScbMove promotion;
    require(scb_chess_parse_uci("a7a8q", &promotion), "parse promotion UCI move");
    require(!scb_chess_parse_uci("i2i4", &promotion), "reject invalid square name");
    require(!scb_chess_parse_square("a", &square), "reject short square name safely");
    puts("All chess core tests passed.");
    return 0;
}
