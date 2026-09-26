/**
 * @file    MOTOR.h
 * @brief   电机控制接口
 *
 * @note    属于 stm32-smart-car 项目（STM32F103C8T6 蓝牙循迹避障智能小车）。
 *          原作者：chenjiayou      整理与补充：yingsangmao
 *          各部分代码的具体来源与授权见仓库根目录 README.md / LICENSE。
 */

#ifndef __MOTOR_H
#define __MOTOR_H

void MOTOR_GPIO_Init(void);
void Set_Car_Speed(int Left_speed ,int Right_speed);

#endif
