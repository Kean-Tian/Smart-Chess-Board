#include "scb/chess.hpp"

#include <iostream>
#include <string>

int main() {
    scb::ChessGame game;
    std::cout << "Smart Chessboard rules prototype. Enter UCI moves (e2e4), or 'quit'.\n";
    std::cout << game.boardText();

    std::string input;
    while (std::cout << "> " && std::cin >> input) {
        if (input == "quit") break;
        const auto move = scb::ChessGame::parseUci(input);
        if (!move || !game.makeMove(*move)) {
            std::cout << "Illegal move. Use a legal UCI move, e.g. e2e4 or e7e8q.\n";
            continue;
        }
        std::cout << game.boardText();
        if (game.isCheckmate()) {
            std::cout << "Checkmate. " << (game.sideToMove() == scb::Color::White ? "Black" : "White")
                      << " wins.\n";
            break;
        }
        if (game.isStalemate()) {
            std::cout << "Stalemate.\n";
            break;
        }
        if (game.isInCheck(game.sideToMove())) std::cout << "Check.\n";
    }
}
