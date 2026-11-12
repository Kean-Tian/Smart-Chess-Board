/*
 * SPDX-FileCopyrightText: 2021-2025 Espressif Systems (Shanghai) CO LTD
 *
 * SPDX-License-Identifier: Apache-2.0
 */
/*

 * Automatically generated file. DO NOT EDIT.

 * Espressif IoT Development Framework (ESP-IDF) 6.1.0 Configuration Header

 */
       
/* List of deprecated options */
/* Simplified memory map for the bootloader.
 * Make sure the bootloader can load into main memory without overwriting itself.
 */
MEMORY
{
  iram_seg (RWX) : org = 0x4004A000, len = 0x4000 /* SRAM part of block 12 and 13 */
  iram_loader_seg (RWX) : org = 0x4004E000, len = 0x7000 /* SRAM part of block 13, Block 14 & part of 15 */
  dram_seg (RW) : org = 0x3FFE5000, len = 0x5B00 /* Part SRAM Blocks 15 & 16, ROM static buffer starts at end of this region (reclaimed after app runs) */
}
/*  Default entry point:  */
