#include <array>
#include <libchess/position.hpp>
#include <string>
#include "catch.hpp"

void valid(libchess::Position &pos, const int depth) noexcept {
    REQUIRE(pos.valid());

    if (depth == 0) {
        return;
    }

    if (!pos.in_check()) {
        const auto halfmoves = pos.halfmoves();
        const auto fullmoves = pos.fullmoves();
        const auto hash = pos.hash();
        const auto turn = pos.turn();

        pos.makenull();

#ifdef NO_HASH
        REQUIRE(hash == 0);
#else
        REQUIRE(hash != pos.calculate_hash());
        REQUIRE(pos.hash() == pos.calculate_hash());
#endif

        valid(pos, depth - 1);
        pos.undonull();

        REQUIRE(halfmoves == pos.halfmoves());
        REQUIRE(fullmoves == pos.fullmoves());
        REQUIRE(hash == pos.hash());
        REQUIRE(turn == pos.turn());
    }

    const auto moves = pos.legal_moves();
    for (const auto &move : moves) {
        const auto halfmoves = pos.halfmoves();
        const auto fullmoves = pos.fullmoves();
        const auto hash = pos.hash();
        const auto turn = pos.turn();

        pos.makemove(move);

#ifdef NO_HASH
        REQUIRE(hash == 0);
#else
        REQUIRE(hash != pos.calculate_hash());
        REQUIRE(pos.hash() == pos.calculate_hash());
#endif

        valid(pos, depth - 1);
        pos.undomove();

        REQUIRE(halfmoves == pos.halfmoves());
        REQUIRE(fullmoves == pos.fullmoves());
        REQUIRE(hash == pos.hash());
        REQUIRE(turn == pos.turn());
    }
}

TEST_CASE("Consistency") {
    const std::array<std::string, 18> fens = {{
        "startpos",
        "2rq1rk1/pp1bppbp/2np1np1/8/3NP3/1BN1BP2/PPPQ2PP/2KR3R b - - 8 11",
        "2rqr1k1/pp1bppbp/3p1np1/4n3/3NP2P/1BN1BP2/PPPQ2P1/1K1R3R b - - 0 13",
        "rnbqkbnr/ppp1pppp/8/8/3pP3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 3",
        "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1",
        "4k3/8/4r3/3pP3/8/8/8/4K3 w - d6 0 2",
        "4k3/8/8/K2pP2r/8/8/8/8 w - d6 0 1",
        "4k3/8/7r/K2pP3/8/8/8/8 w - d6 0 1",
        "5k2/8/8/1K1Pp1r1/8/8/8/8 w - e6 0 2",
        "k6b/6pp/pp1P4/1R6/5pP1/8/K6P/7B b - g3 0 19",
        "2b1k3/8/8/2Pp4/8/7K/8/8 w - d6 0 1",
        "4k3/r6K/8/2Pp4/8/8/8/8 w - d6 0 1",
        "2K1k3/8/8/2Pp4/8/7b/8/8 w - d6 0 1",
        "8/8/7k/8/2pP4/8/8/2B1K3 b - d3 0 1",
        "8/8/7k/8/2pP4/8/8/2Q1K3 b - d3 0 1",
        "8/8/8/8/2pP4/8/R6k/4K3 b - d3 0 1",
        "4k3/8/K6r/3pP3/8/8/8/8 w - d6 0 1",
        "3k1K2/8/8/3pP3/8/b7/8/8 w - d6 0 1",
    }};

    for (const auto &fen : fens) {
        INFO(fen);
        libchess::Position pos{fen};
        valid(pos, 3);
    }
}
