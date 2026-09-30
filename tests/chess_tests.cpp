#include "scb/chess.hpp"

#include <cstdlib>
#include <iostream>
#include <string_view>

namespace {

void require(bool condition, std::string_view message) {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}

bool play(scb::ChessGame& game, std::string_view uci) {
    const auto move = scb::ChessGame::parseUci(uci);
    return move && game.makeMove(*move);
}

} // namespace

int main() {
    scb::ChessGame game;
    require(play(game, "e2e4"), "accept initial pawn move");
    require(!play(game, "d2d4"), "reject out-of-turn move");
    require(play(game, "e7e5"), "accept black pawn move after white move");

    scb::ChessGame blockedRook;
    require(!play(blockedRook, "a1a3"), "reject rook move through own pawn");

    scb::ChessGame foolsMate;
    require(play(foolsMate, "f2f3"), "Fool's mate move 1");
    require(play(foolsMate, "e7e5"), "Fool's mate move 2");
    require(play(foolsMate, "g2g4"), "Fool's mate move 3");
    require(play(foolsMate, "d8h4"), "Fool's mate move 4");
    require(foolsMate.isInCheck(scb::Color::White), "detect check");
    require(foolsMate.isCheckmate(), "detect checkmate");

        scb::ChessGame enPassant;
        require(play(enPassant, "e2e4"), "en passant setup 1");
        require(play(enPassant, "a7a6"), "en passant setup 2");
        require(play(enPassant, "e4e5"), "en passant setup 3");
        require(play(enPassant, "d7d5"), "en passant setup 4");
        require(play(enPassant, "e5d6"), "allow en passant capture");
        require(enPassant.pieceAt(*scb::ChessGame::parseSquare("d5")).type == scb::PieceType::None,
            "remove en passant captured pawn");

        scb::ChessGame castling;
        for (const auto move : {"e2e4", "e7e5", "g1f3", "b8c6", "f1e2", "g8f6", "e1g1"}) {
        require(play(castling, move), "allow legal kingside castling sequence");
        }
        require(castling.pieceAt(*scb::ChessGame::parseSquare("g1")).type == scb::PieceType::King,
            "move king during castling");
        require(castling.pieceAt(*scb::ChessGame::parseSquare("f1")).type == scb::PieceType::Rook,
            "move rook during castling");

    require(scb::ChessGame::parseUci("a7a8q").has_value(), "parse promotion UCI move");
    require(!scb::ChessGame::parseUci("i2i4"), "reject invalid square name");
    std::cout << "All chess core tests passed.\n";
}
