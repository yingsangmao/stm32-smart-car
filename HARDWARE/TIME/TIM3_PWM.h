/**
 * @file    TIM3_PWM.h
 * @brief   TIM3 PWM 接口
 *
 * @note    属于 stm32-smart-car 项目（STM32F103C8T6 蓝牙循迹避障智能小车）。
 *          原作者：chenjiayou      整理与补充：yingsangmao
 *          各部分代码的具体来源与授权见仓库根目录 README.md / LICENSE。
 */

#ifndef __TIM3_PWM_H
#define __TIM3_PWM_H	
#include "sys.h"

void TIM1_Getsample_Int(u16 arr,u16 psc);
void TIM3_PWM_Init(u16 arr,u16 psc);

#endif
