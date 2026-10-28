# 验证记录（2026-10-26）

ESP32-S3 / PlatformIO espressif32@6.9.0 / ESP-IDF 5.3.1 目标编译通过。

主机 CTest 五组全部通过：

1. libchess 规则适配层。
2. ESP32 便携控制核心（模拟 GPIO）。
3. 原 Python AI 原型（模拟网络响应）。
4. Pi USB 客户端（模拟串口）。
5. Pi 物理占位／规则协同（模拟局面与接口）。

控制核心另经 UndefinedBehaviorSanitizer 检查通过。
本机 AddressSanitizer 在运行时初始化失败，因此没有将其记为已通过。
主机规则库与 Python 解释器使用同一 arm64 架构，结果不是 Pi 实机运行结果。

没有连接硬件、没有烧录、没有实测波形或电机。编译通过不代表硬件部署完成。
本次输出为基础控制固件；自动归零、避障搬运和完整 GUI/Stockfish 集成不在完成范围内。

二进制及来源摘要见 `Build_Validation.json` 与 `../binaries/flash_manifest.json`。
