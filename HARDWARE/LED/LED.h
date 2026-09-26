/**
 * @file    LED.h
 * @brief   板载 LED 驱动接口
 *
 * @note    属于 stm32-smart-car 项目（STM32F103C8T6 蓝牙循迹避障智能小车）。
 *          原作者：chenjiayou      整理与补充：yingsangmao
 *          各部分代码的具体来源与授权见仓库根目录 README.md / LICENSE。
 */

#ifndef __LED_H
#define __LED_H

void LED_Init(void);
void LED_Open(void);
void LED_Close(void);
void LED_Flash(void);

#endif
