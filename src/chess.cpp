#include "scb/chess.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <sstream>

namespace scb {
namespace {
constexpr std::uint8_t WhiteKingSide = 0x01;
constexpr std::uint8_t WhiteQueenSide = 0x02;
constexpr std::uint8_t BlackKingSide = 0x04;
constexpr std::uint8_t BlackQueenSide = 0x08;

int fileOf(int square) { return square % 8; }
int rankOf(int square) { return square / 8; }
int squareOf(int file, int rank) { return rank * 8 + file; }

bool isPromotionType(PieceType type) {
    return type == PieceType::Queen || type == PieceType::Rook ||
           type == PieceType::Bishop || type == PieceType::Knight;
}

char pieceCharacter(Piece piece) {
    char value = '?';
    switch (piece.type) {
    case PieceType::Pawn: value = 'p'; break;
    case PieceType::Knight: value = 'n'; break;
    case PieceType::Bishop: value = 'b'; break;
    case PieceType::Rook: value = 'r'; break;
    case PieceType::Queen: value = 'q'; break;
    case PieceType::King: value = 'k'; break;
    case PieceType::None: return '.';
    }
    return piece.color == Color::White ? static_cast<char>(std::toupper(value)) : value;
}
} // namespace

ChessGame::ChessGame() {
    constexpr PieceType backRank[8] = {
        PieceType::Rook, PieceType::Knight, PieceType::Bishop, PieceType::Queen,
        PieceType::King, PieceType::Bishop, PieceType::Knight, PieceType::Rook};
    for (int file = 0; file < 8; ++file) {
        state_.board[squareOf(file, 0)] = {backRank[file], Color::White};
        state_.board[squareOf(file, 1)] = {PieceType::Pawn, Color::White};
        state_.board[squareOf(file, 6)] = {PieceType::Pawn, Color::Black};
        state_.board[squareOf(file, 7)] = {backRank[file], Color::Black};
    }
}

Color ChessGame::opposite(Color color) noexcept {
    return color == Color::White ? Color::Black : Color::White;
}

bool ChessGame::inside(int file, int rank) noexcept {
    return file >= 0 && file < 8 && rank >= 0 && rank < 8;
}

Piece ChessGame::pieceAt(int square) const {
    return square >= 0 && square < 64 ? state_.board[square] : Piece{};
}

Color ChessGame::sideToMove() const noexcept { return state_.turn; }

std::optional<int> ChessGame::parseSquare(std::string_view name) {
    if (name.size() != 2 || name[0] < 'a' || name[0] > 'h' || name[1] < '1' || name[1] > '8') {
        return std::nullopt;
    }
    return squareOf(name[0] - 'a', name[1] - '1');
}

std::string ChessGame::squareName(int square) {
    if (square < 0 || square >= 64) return {};
    return {static_cast<char>('a' + fileOf(square)), static_cast<char>('1' + rankOf(square))};
}

std::optional<Move> ChessGame::parseUci(std::string_view text) {
    if (text.size() != 4 && text.size() != 5) return std::nullopt;
    const auto from = parseSquare(text.substr(0, 2));
    const auto to = parseSquare(text.substr(2, 2));
    if (!from || !to) return std::nullopt;
    PieceType promotion = PieceType::None;
    if (text.size() == 5) {
        switch (text[4]) {
        case 'q': promotion = PieceType::Queen; break;
        case 'r': promotion = PieceType::Rook; break;
        case 'b': promotion = PieceType::Bishop; break;
        case 'n': promotion = PieceType::Knight; break;
        default: return std::nullopt;
        }
    }
    return Move{*from, *to, promotion};
}

bool ChessGame::squareAttacked(const State& state, int square, Color byColor) {
    const int file = fileOf(square);
    const int rank = rankOf(square);
    const int pawnRank = rank + (byColor == Color::White ? -1 : 1);
    for (int pawnFile : {file - 1, file + 1}) {
        if (inside(pawnFile, pawnRank)) {
            const Piece piece = state.board[squareOf(pawnFile, pawnRank)];
            if (piece.type == PieceType::Pawn && piece.color == byColor) return true;
        }
    }

    constexpr int knightOffsets[8][2] = {
        {1, 2}, {2, 1}, {-1, 2}, {-2, 1}, {1, -2}, {2, -1}, {-1, -2}, {-2, -1}};
    for (const auto& offset : knightOffsets) {
        const int targetFile = file + offset[0];
        const int targetRank = rank + offset[1];
        if (inside(targetFile, targetRank)) {
            const Piece piece = state.board[squareOf(targetFile, targetRank)];
            if (piece.type == PieceType::Knight && piece.color == byColor) return true;
        }
    }

    constexpr int directions[8][2] = {
        {1, 0}, {-1, 0}, {0, 1}, {0, -1}, {1, 1}, {1, -1}, {-1, 1}, {-1, -1}};
    for (const auto& direction : directions) {
        int targetFile = file + direction[0];
        int targetRank = rank + direction[1];
        int distance = 1;
        while (inside(targetFile, targetRank)) {
            const Piece piece = state.board[squareOf(targetFile, targetRank)];
            if (piece) {
                if (piece.color == byColor &&
                    (piece.type == PieceType::Queen ||
                     (distance == 1 && piece.type == PieceType::King) ||
                     ((direction[0] == 0 || direction[1] == 0) && piece.type == PieceType::Rook) ||
                     ((direction[0] != 0 && direction[1] != 0) && piece.type == PieceType::Bishop))) return true;
                break;
            }
            targetFile += direction[0];
            targetRank += direction[1];
            ++distance;
        }
    }
    return false;
}

int ChessGame::kingSquare(const State& state, Color color) {
    for (int square = 0; square < 64; ++square) {
        const Piece piece = state.board[square];
        if (piece.type == PieceType::King && piece.color == color) return square;
    }
    return -1;
}

bool ChessGame::isInCheck(Color color) const {
    const int king = kingSquare(state_, color);
    return king >= 0 && squareAttacked(state_, king, opposite(color));
}

bool ChessGame::pseudoLegal(const State& state, const Move& move) {
    if (move.from < 0 || move.from >= 64 || move.to < 0 || move.to >= 64 || move.from == move.to) return false;
    const Piece moving = state.board[move.from];
    const Piece target = state.board[move.to];
    if (!moving || moving.color != state.turn || (target && target.color == moving.color) ||
        (target && target.type == PieceType::King)) return false;

    const int fromFile = fileOf(move.from);
    const int fromRank = rankOf(move.from);
    const int toFile = fileOf(move.to);
    const int toRank = rankOf(move.to);
    const int dx = toFile - fromFile;
    const int dy = toRank - fromRank;

    if (moving.type == PieceType::Pawn) {
        const int direction = moving.color == Color::White ? 1 : -1;
        const int startRank = moving.color == Color::White ? 1 : 6;
        const int finalRank = moving.color == Color::White ? 7 : 0;
        if (toRank == finalRank) {
            if (!isPromotionType(move.promotion)) return false;
        } else if (move.promotion != PieceType::None) return false;
        if (dx == 0 && dy == direction && !target) return true;
        if (dx == 0 && dy == 2 * direction && fromRank == startRank && !target &&
            !state.board[squareOf(fromFile, fromRank + direction)]) return true;
        if (std::abs(dx) == 1 && dy == direction) {
            if (target) return true;
            if (move.to == state.enPassant) {
                const Piece adjacent = state.board[squareOf(toFile, fromRank)];
                return adjacent.type == PieceType::Pawn && adjacent.color != moving.color;
            }
        }
        return false;
    }
    if (move.promotion != PieceType::None) return false;
    if (moving.type == PieceType::Knight) {
        return (std::abs(dx) == 1 && std::abs(dy) == 2) || (std::abs(dx) == 2 && std::abs(dy) == 1);
    }
    if (moving.type == PieceType::King && std::max(std::abs(dx), std::abs(dy)) == 1) return true;

    const bool straight = dx == 0 || dy == 0;
    const bool diagonal = std::abs(dx) == std::abs(dy);
    if ((moving.type == PieceType::Rook && !straight) ||
        (moving.type == PieceType::Bishop && !diagonal) ||
        (moving.type == PieceType::Queen && !straight && !diagonal)) return false;

    if (moving.type == PieceType::King && dy == 0 && std::abs(dx) == 2 && fromFile == 4 &&
        fromRank == (moving.color == Color::White ? 0 : 7) &&
        !squareAttacked(state, move.from, opposite(moving.color))) {
        const bool kingSide = dx > 0;
        const std::uint8_t right = moving.color == Color::White
            ? (kingSide ? WhiteKingSide : WhiteQueenSide)
            : (kingSide ? BlackKingSide : BlackQueenSide);
        const int rookFile = kingSide ? 7 : 0;
        const Piece rook = state.board[squareOf(rookFile, fromRank)];
        if (!(state.castling & right) || rook.type != PieceType::Rook || rook.color != moving.color) return false;
        const int step = kingSide ? 1 : -1;
        for (int file = fromFile + step; file != rookFile; file += step) {
            if (state.board[squareOf(file, fromRank)]) return false;
        }
        return !squareAttacked(state, squareOf(fromFile + step, fromRank), opposite(moving.color)) &&
               !squareAttacked(state, squareOf(fromFile + 2 * step, fromRank), opposite(moving.color));
    }

    if ((moving.type == PieceType::Rook || moving.type == PieceType::Bishop || moving.type == PieceType::Queen) &&
        (straight || diagonal)) {
        const int stepFile = (dx > 0) - (dx < 0);
        const int stepRank = (dy > 0) - (dy < 0);
        int file = fromFile + stepFile;
        int rank = fromRank + stepRank;
        while (file != toFile || rank != toRank) {
            if (state.board[squareOf(file, rank)]) return false;
            file += stepFile;
            rank += stepRank;
        }
        return true;
    }
    return false;
}

void ChessGame::applyUnchecked(State& state, const Move& move) {
    Piece moving = state.board[move.from];
    const int fromFile = fileOf(move.from);
    const int fromRank = rankOf(move.from);
    const int toFile = fileOf(move.to);
    const int toRank = rankOf(move.to);
    const Piece captured = state.board[move.to];

    if (moving.type == PieceType::Pawn && move.to == state.enPassant && fromFile != toFile && !captured) {
        state.board[squareOf(toFile, fromRank)] = {};
    }
    if (moving.type == PieceType::King && std::abs(toFile - fromFile) == 2) {
        const bool kingSide = toFile > fromFile;
        const int rookFrom = squareOf(kingSide ? 7 : 0, fromRank);
        const int rookTo = squareOf(kingSide ? 5 : 3, fromRank);
        state.board[rookTo] = state.board[rookFrom];
        state.board[rookFrom] = {};
    }

    state.board[move.from] = {};
    if (move.promotion != PieceType::None) moving.type = move.promotion;
    state.board[move.to] = moving;
    state.enPassant = -1;
    if (moving.type == PieceType::Pawn && std::abs(toRank - fromRank) == 2) {
        state.enPassant = squareOf(fromFile, (fromRank + toRank) / 2);
    }
    if (moving.type == PieceType::King) {
        state.castling &= moving.color == Color::White
            ? static_cast<std::uint8_t>(~(WhiteKingSide | WhiteQueenSide))
            : static_cast<std::uint8_t>(~(BlackKingSide | BlackQueenSide));
    }
    if (move.from == squareOf(0, 0) || move.to == squareOf(0, 0)) state.castling &= static_cast<std::uint8_t>(~WhiteQueenSide);
    if (move.from == squareOf(7, 0) || move.to == squareOf(7, 0)) state.castling &= static_cast<std::uint8_t>(~WhiteKingSide);
    if (move.from == squareOf(0, 7) || move.to == squareOf(0, 7)) state.castling &= static_cast<std::uint8_t>(~BlackQueenSide);
    if (move.from == squareOf(7, 7) || move.to == squareOf(7, 7)) state.castling &= static_cast<std::uint8_t>(~BlackKingSide);
    (void)captured;
    state.turn = opposite(state.turn);
}

bool ChessGame::makeMove(const Move& move) {
    if (!pseudoLegal(state_, move)) return false;
    State next = state_;
    applyUnchecked(next, move);
    const int king = kingSquare(next, state_.turn);
    if (king < 0 || squareAttacked(next, king, opposite(state_.turn))) return false;
    state_ = next;
    return true;
}

bool ChessGame::hasLegalMove() const {
    constexpr PieceType promotions[4] = {PieceType::Queen, PieceType::Rook, PieceType::Bishop, PieceType::Knight};
    for (int from = 0; from < 64; ++from) {
        const Piece piece = state_.board[from];
        if (!piece || piece.color != state_.turn) continue;
        for (int to = 0; to < 64; ++to) {
            const bool promotes = piece.type == PieceType::Pawn && rankOf(to) == (piece.color == Color::White ? 7 : 0);
            const int choices = promotes ? 4 : 1;
            for (int choice = 0; choice < choices; ++choice) {
                const Move move{from, to, promotes ? promotions[choice] : PieceType::None};
                if (!pseudoLegal(state_, move)) continue;
                State next = state_;
                applyUnchecked(next, move);
                const int king = kingSquare(next, state_.turn);
                if (king >= 0 && !squareAttacked(next, king, opposite(state_.turn))) return true;
            }
        }
    }
    return false;
}

bool ChessGame::isCheckmate() const { return isInCheck(state_.turn) && !hasLegalMove(); }
bool ChessGame::isStalemate() const { return !isInCheck(state_.turn) && !hasLegalMove(); }

std::string ChessGame::boardText() const {
    std::ostringstream output;
    for (int rank = 7; rank >= 0; --rank) {
        output << rank + 1 << ' ';
        for (int file = 0; file < 8; ++file) output << pieceCharacter(state_.board[squareOf(file, rank)]) << ' ';
        output << '\n';
    }
    output << "  a b c d e f g h\n";
    output << (state_.turn == Color::White ? "White" : "Black") << " to move\n";
    return output.str();
}

} // namespace scb
