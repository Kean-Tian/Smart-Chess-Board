# MCU–Pi USB 协议 v1

ESP32-S3 内建 USB Serial/JTAG，USB-B 连接 Pi。Pi 通常出现 `/dev/ttyACM0`；macOS 使用实际 `/dev/cu.usbmodem...` 名称。115200 是串口客户端设置，USB 传输并不是 UART 位速率。

## 帧格式

- ASCII，每行以 LF 结束，允许 CRLF。
- `@42 STATUS`：可选非负请求 ID，范围 0..2147483647；不带 `@ID` 时 ID=0。
- 请求行含前缀最多 127 字节。溢出或含非 ASCII 控制字节时，丢弃整行直至 LF，防止尾部被误当作另一条命令。
- 回复：`ACK 42 COMMAND`、`ERR 42 REASON`、`DONE 42 MOTION`。
- `STATUS` 直接回复 `STATUS 42 armed=0 moving=0 magnet=0 origin=0 steps=0`。
- 主动事件：`BOARD <16位HEX>`、`EVENT ...`、`FAULT ...`、`HELLO SCB_ESP32S3 1`。
- BOARD/RAW 的 bit0=a1，bit63=h8。BOARD 是去抖后的完整帧，RAW 是最近完成扫描的完整原始帧。
- TX 队列满时只丢整帧，不截断拼接；客户端可能超时。读状态可以重新查询，**运动请求不能自动重试**。

## 命令

| 请求 | 行为 |
|---|---|
| `PING` | 更新心跳。只有 PING 更新链路保活计时 |
| `STATUS` | 返回使能、运动、电磁铁、人工参考、每格步数 |
| `SCAN` | 报告稳定 BOARD；尚无稳定帧时 `NOT_READY` |
| `RAW` | 报告最近完整 RAW 帧 |
| `POLARITY LOW` / `HIGH` | 占位极性，重新建立去抖与事件基线 |
| `LED e4 0 20 0` | 设置指定格子的 RGB（每通道 0..255），其他格保留 |
| `LED_CLEAR` | 全部清零 |
| `MARK e2 e4 LEGAL` | 清屏，源格蓝、目标格绿 |
| `MARK e2 e5 ILLEGAL` | 清屏，源格和目标格红 |
| `SET_STEPS n` | 每格完整步数 1..2000，清除旧坐标参考；无默认校准值 |
| `ORIGIN a1` | 记录当前人工对准的格心，不移动机构 |
| `ARM` | 允许运动／电磁铁，必须先收到新鲜 PING |
| `DISARM` / `STOP` | 禁止运动、释放电磁铁、禁用电机，清除坐标参考 |
| `GOTO e2` | 电磁铁关闭，按已知坐标移到源格；需 ARM、校准、人工参考 |
| `MOVE e2 e4` | 当前必须已对准 e2；吸合、等待、先 X 后 Y、释放 |
| `JOG X 20` / `JOG Y -20` | 台架相对步进，范围 ±1..1000，需 ARM；清除绝对参考 |
| `MAGNET ON` / `OFF` | 手动电磁铁开关，ON 需 ARM；运动中不允许改单独开关 |
| `HOME` | 返回 `NO_HOME_SWITCHES`，不执行伪归零 |

MOVE/GOTO/JOG 先返回 `ACK id MOTION`，结束返回 `DONE id MOTION`；中断则为 `ERR id ...`。DONE 表示已发出步进脉冲，**不是棋子成功移动确认**。必须另查 BOARD 比较物理局面。

## 时序与边界

- Pi 客户端每 0.5 秒发 PING；MCU 2 秒无心跳后关闭输出并清除参考。断线检测依赖这个超时，不声称即时检测拔线。
- 默认电磁铁连续 ON 上限 5 秒，运动上限 30 秒；重复 ON 不会重置连续通电计时。
- 默认每个轴最大调度速率约 100 steps/s；使用非阻塞软件调度，一次只推进一轴。任务延迟会降低实际速率，不会补发脉冲突发。
- `MOVE` 仅为基础先 X 后 Y 搬运，没有碰撞路径规划、吃子移出路线、闭环位置反馈或归零。
- `JOG` 用于机构台架校准，位置未知时也可使用，因此软件无法判断机构是否靠近机械边界。
- 电磁铁工作期间的占位变化只作为 BOARD 数据，不能直接当成人类走法。运动结束后重新建立传感事件基线。
- `EVENT MOVE e2e4` 是候选移动，不包含合法性判断。多格同时变化报告 `AMBIGUOUS`，由 Pi 决定如何处理。

## Pi 接入

`pi5/app/scb_link.py` 提供独立读取线程、请求 ID 匹配、异步事件队列和心跳。运动超时会发 STOP，不会重新发送 MOVE。
`pi5/app/board_game.py` 把候选走法接回现有 libchess 规则库，同时比较完整占位。非法走法不更新逻辑局面，必须恢复后才能继续。
易位、多格同时变化、传感事件不明确时可人工输入 `commit <uci>`；升变必须明确 q/r/b/n。该示例是本地规则控制台，不是完整 GUI 或 Stockfish 应用。

## 使用示例

先运行 Pi 客户端，使心跳持续工作。然后逐条输入：

```text
STATUS
SCAN
LED a1 20 0 0
LED_CLEAR
SET_STEPS 200
ORIGIN a1
ARM
GOTO e2
MOVE e2 e4
STOP
```

`200` 只是语法示例，不能当作这套机构的实测每格步数。GOTO/MOVE 只能在已确认步数、方向、人工参考、机构路径和电磁铁工作条件后使用。
