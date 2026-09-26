/**
 * @file    HCSR04.h
 * @brief   超声波测距接口
 *
 * @note    属于 stm32-smart-car 项目（STM32F103C8T6 蓝牙循迹避障智能小车）。
 *          原作者：chenjiayou      整理与补充：yingsangmao
 *          各部分代码的具体来源与授权见仓库根目录 README.md / LICENSE。
 */

#ifndef __HCSR04_H
#define __HCSR04_H
#include "stm32f10x.h"                  // Device header

void HCSR04_Init(void);
uint16_t HCSR04_GetValue(void);
void HCSR04_Start(void);

#endif 
