/**
 * @file    OLEDIIC.h
 * @brief   软件 IIC 接口
 *
 * @note    属于 stm32-smart-car 项目（STM32F103C8T6 蓝牙循迹避障智能小车）。
 *          原作者：chenjiayou      整理与补充：yingsangmao
 *          各部分代码的具体来源与授权见仓库根目录 README.md / LICENSE。
 */

#ifndef __IIC_H
#define __IIC_H
#include "sys.h"

/****************
注意：模拟IIC时，任意IO口（除JTAG口外，都可以做SDA和SCL）
****************/
#define OLED_SCL_Clr() GPIO_ResetBits(GPIOA,GPIO_Pin_11)//SCL
#define OLED_SCL_Set() GPIO_SetBits(GPIOA,GPIO_Pin_11)

#define OLED_SDA_Clr() GPIO_ResetBits(GPIOA,GPIO_Pin_12)//AIN
#define OLED_SDA_Set() GPIO_SetBits(GPIOA,GPIO_Pin_12)

void IIC_delay(void);
void I2C_Start(void);
void I2C_Stop(void);
void I2C_WaitAck(void);
void Send_Byte(u8 dat);

#endif
