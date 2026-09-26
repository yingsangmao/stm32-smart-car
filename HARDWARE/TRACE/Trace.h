/**
 * @file    Trace.h
 * @brief   四路循迹接口（X1~X4 宏，低电平为检测到黑线）
 *
 * @note    属于 stm32-smart-car 项目（STM32F103C8T6 蓝牙循迹避障智能小车）。
 *          原作者：chenjiayou      整理与补充：yingsangmao
 *          各部分代码的具体来源与授权见仓库根目录 README.md / LICENSE。
 */

#ifndef __Trace_H
#define __Trace_H

#define X1 GPIO_ReadInputDataBit(GPIOB,GPIO_Pin_0)
#define X2 GPIO_ReadInputDataBit(GPIOB,GPIO_Pin_1)
#define X3 GPIO_ReadInputDataBit(GPIOB,GPIO_Pin_10)
#define X4 GPIO_ReadInputDataBit(GPIOB,GPIO_Pin_11)

void Trace_Init(void);

#endif
