# PCB 接线与固件配置

依据：用户提供的 `master pcb.pdf` 与 `sensor pcb.pdf`，2026-10-26 版本。这里记录的是原理图可见网络，没有把 PDF 当作已测量的实物连接。

## ESP32-S3 GPIO

GPIO 数字不能当成裸芯片封装脚号。

| 功能 | 网络 | GPIO | 封装脚号 |
|---|---|---:|---:|
| LED 数据，先经 74AHCT1G125 | LED_IN_3V3 | 2 | 7 |
| 行地址 A0 | MUX_IN1 | 4 | 9 |
| 行地址 A1 | MUX_IN2 | 5 | 10 |
| 行地址 A2 | MUX_IN3 | 6 | 11 |
| 第 1 列 | DIG_OUT1 | 7 | 12 |
| 第 2 列 | DIG_OUT2 | 8 | 13 |
| 第 3 列 | DIG_OUT3 | 9 | 14 |
| 第 4 列 | DIG_OUT4 | 10 | 15 |
| 第 5 列 | DIG_OUT5 | 11 | 16 |
| 第 6 列 | DIG_OUT6 | 12 | 17 |
| 第 7 列 | DIG_OUT7 | 13 | 18 |
| 第 8 列 | DIG_OUT8 | 14 | 19 |
| USB D- | USB_DN | 19 | 25 |
| USB D+ | USB_DP | 20 | 26 |
| 电磁铁 MOSFET | EM_CTRL | 33 | 38 |
| X 步进脉冲 | X_STEP | 34 | 39 |
| X 方向 | X_DIR | 35 | 40 |
| Y 步进脉冲 | Y_STEP | 36 | 41 |
| Y 方向 | Y_DIR | 37 | 42 |
| 两个 A4988 的公共使能 | MOTOR_EN | 38 | 43 |

`MOTOR_EN=1` 禁用驱动，`MOTOR_EN=0` 使能。`EM_CTRL=1` 吸合，`0` 释放。
两轴 **独立 STEP、共用 ENABLE**。旧 Pi 版本的共享 STEP 算法不适用于本板，固件未使用旧 `motor_axis.c`。

## 排线 Master J4 / Sensor J1（逐脚一致）

| 排线脚 | 网络 | MCU GPIO |
|---:|---|---:|
| 1 | DIG_OUT3 | 9 |
| 2 | DIG_OUT7 | 13 |
| 3 | DIG_OUT4 | 10 |
| 4 | DIG_OUT8 | 14 |
| 5 | DIG_OUT6 | 12 |
| 6 | DIG_OUT2 | 8 |
| 7 | DIG_OUT5 | 11 |
| 8 | DIG_OUT1 | 7 |
| 9 | LED_IN（电平转换后） | 2，经缓冲 |
| 10 | GND | — |
| 11 | MUX_IN1 | 4 |
| 12 | GND | — |
| 13 | MUX_IN2 | 5 |
| 14 | +3V3 | — |
| 15 | MUX_IN3 | 6 |
| 16 | +5V | — |

特别注意：排线的 DIG_OUT 顺序不是 1、2、3……；固件按网络名映射。

## 传感与 LED

- LM339 是比较器，固件读取八路数字高低电平，不读取 ADC 数值；1.5 V 阈值由硬件产生。
- 本次传感板的比较器输出上拉到 +3V3，不能沿用旧文档中的 +5V 上拉结论。
- 默认 `LOW=occupied`；先用一颗棋子验证，必要时执行 `POLARITY HIGH`。
- 默认 Y0 为 rank 1、DIG_OUT1 为 file a。实际朝向不能单凭 PDF 确定，先核对四角。
- LED 默认 LED0=a1、蛇形接线。方向不同可修改 `board_pins.h` 的独立传感／LED 翻转参数。
- 传感扫描是逐行采样，连续三帧相同才报告稳定状态；未测量实物扫描率。
- RMT 使用 10 MHz 分辨率，GRB、MSB first，0=300/900 ns，1=900/300 ns，帧尾低电平 300 us。需要在实际 WS2812B 器件上核对波形和颜色。

## 裸芯片与存储器

本图为 ESP32-S3 裸芯片加外部 W25Q128（16 MB）Flash。固件使用 DIO、禁用 PSRAM。
GPIO33–37 已用于电磁铁和电机，因此不能换成占用这些引脚的 octal Flash/PSRAM 配置，不能直接照搬带 octal PSRAM 的开发板配置。
这项约束依据 [Espressif GPIO 文档](https://docs.espressif.com/projects/esp-idf/en/v5.3.3/esp32s3/api-reference/peripherals/gpio.html)。

## 图纸未提供的运动输入

图中未见归零开关、限位或位置反馈接到 MCU。`HOME` 因此返回 `NO_HOME_SWITCHES`。
`ORIGIN` 只记录操作员人工对准的位置，不会驱动机构归零。`DONE` 只表示指令脉冲完成，不能证明棋子到位。
X/Y 正方向、每格步数、电磁铁耦合、行驱动能力与完整机构运动均待实物验证。
