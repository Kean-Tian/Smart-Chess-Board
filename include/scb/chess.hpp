#pragma once

#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace scb {

enum class Color : std::uint8_t { White, Black };
enum class PieceType : std::uint8_t { None, Pawn, Knight, Bishop, Rook, Queen, King };

struct Piece {
    PieceType type{PieceType::None};
    Color color{Color::White};
    explicit operator bool() const noexcept { return type != PieceType::None; }
};

struct Move {
    int from{-1};
    int to{-1};
    PieceType promotion{PieceType::None};
};

class ChessGame {
public:
    ChessGame();
    bool makeMove(const Move& move);
    bool isInCheck(Color color) const;
    bool isCheckmate() const;
    bool isStalemate() const;
    Piece pieceAt(int square) const;
    Color sideToMove() const noexcept;
    std::string boardText() const;

    static std::optional<int> parseSquare(std::string_view name);
    static std::optional<Move> parseUci(std::string_view text);
    static std::string squareName(int square);

private:
    struct State {
        std::array<Piece, 64> board{};
        Color turn{Color::White};
        std::uint8_t castling{0x0f};
        int enPassant{-1};
    };

    State state_{};
    static Color opposite(Color color) noexcept;
    static bool inside(int file, int rank) noexcept;
    static bool squareAttacked(const State& state, int square, Color byColor);
    static int kingSquare(const State& state, Color color);
    static void applyUnchecked(State& state, const Move& move);
    static bool pseudoLegal(const State& state, const Move& move);
    bool hasLegalMove() const;
};

} // namespace scb
