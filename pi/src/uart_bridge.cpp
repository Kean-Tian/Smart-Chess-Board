#include "scb/chess.hpp"

#include <cerrno>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <string_view>

#include <fcntl.h>
#include <termios.h>
#include <unistd.h>

namespace {

constexpr speed_t SerialBaudRate = B115200;

int openSerial(const char* path) {
    const int fd = open(path, O_RDWR | O_NOCTTY | O_SYNC);
    if (fd < 0) return -1;

    termios settings{};
    if (tcgetattr(fd, &settings) != 0) {
        close(fd);
        return -1;
    }
    cfmakeraw(&settings);
    cfsetispeed(&settings, SerialBaudRate);
    cfsetospeed(&settings, SerialBaudRate);
    settings.c_cflag |= CLOCAL | CREAD;
    settings.c_cflag &= ~CSTOPB;
    settings.c_cflag &= ~CRTSCTS;
    settings.c_cc[VMIN] = 1;
    settings.c_cc[VTIME] = 0;
    if (tcsetattr(fd, TCSANOW, &settings) != 0) {
        close(fd);
        return -1;
    }
    return fd;
}

bool isSquare(std::string_view square) {
    return scb::ChessGame::parseSquare(square).has_value();
}

void processLine(const std::string& line, scb::ChessGame& game) {
    std::istringstream input(line);
    std::string prefix;
    std::string kind;
    input >> prefix >> kind;
    if (prefix != "SCB1") {
        std::cerr << "Ignoring unknown serial line: " << line << '\n';
        return;
    }

    if (kind == "READY") {
        std::cout << "MCU ready: " << line << '\n';
        return;
    }
    if (kind == "SENSOR") {
        std::string square;
        int occupied = -1;
        input >> square >> occupied;
        if (!input || !isSquare(square) || (occupied != 0 && occupied != 1)) {
            std::cerr << "Malformed sensor event: " << line << '\n';
            return;
        }
        std::cout << "Sensor " << square << (occupied ? " occupied" : " empty") << '\n';
        return;
    }
    if (kind == "MOVE") {
        std::string from;
        std::string to;
        input >> from >> to;
        if (!input || !isSquare(from) || !isSquare(to)) {
            std::cerr << "Malformed move event: " << line << '\n';
            return;
        }
        const auto move = scb::ChessGame::parseUci(from + to);
        if (!move || !game.makeMove(*move)) {
            std::cerr << "MCU move rejected by chess rules: " << from << to << '\n';
            return;
        }
        std::cout << "Accepted physical move " << from << to << '\n' << game.boardText();
        if (game.isInCheck(game.sideToMove())) std::cout << "Check.\n";
        if (game.isCheckmate()) std::cout << "Checkmate.\n";
        if (game.isStalemate()) std::cout << "Stalemate.\n";
        return;
    }
    std::cerr << "Unknown SCB1 event: " << line << '\n';
}

} // namespace

int main(int argc, char** argv) {
    const char* device = argc > 1 ? argv[1] : "/dev/serial0";
    const int fd = openSerial(device);
    if (fd < 0) {
        std::cerr << "Cannot open serial device " << device << ": " << std::strerror(errno) << '\n';
        return 1;
    }
    std::cout << "Listening on " << device << " at 115200 baud. Press Ctrl+C to exit.\n";

    scb::ChessGame game;
    std::string line;
    char byte{};
    while (true) {
        const ssize_t count = read(fd, &byte, 1);
        if (count < 0) {
            if (errno == EINTR) continue;
            std::cerr << "Serial read failed: " << std::strerror(errno) << '\n';
            close(fd);
            return 1;
        }
        if (count == 0) continue;
        if (byte == '\n') {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            processLine(line, game);
            line.clear();
        } else if (line.size() < 96) {
            line.push_back(byte);
        } else {
            line.clear();
            std::cerr << "Discarded oversized serial line.\n";
        }
    }
}
