/**
 * @file    OLEDIIC.c
 * @brief   OLED 软件 IIC 底层时序
 *
 * @note    属于 stm32-smart-car 项目（STM32F103C8T6 蓝牙循迹避障智能小车）。
 *          原作者：chenjiayou      整理与补充：yingsangmao
 *          各部分代码的具体来源与授权见仓库根目录 README.md / LICENSE。
 */

#include "delay.h"
#include "olediic.h"

void IIC_delay(void)
{
	u8 t=3;
	while(t--);
}

//起始信号
void I2C_Start(void)
{
	OLED_SDA_Set();
	OLED_SCL_Set();
	IIC_delay();
	OLED_SDA_Clr();
	IIC_delay();
	OLED_SCL_Clr();
	IIC_delay();
}

//结束信号
void I2C_Stop(void)
{
	OLED_SDA_Clr();
	OLED_SCL_Set();
	IIC_delay();
	OLED_SDA_Set();
}

//等待信号响应
void I2C_WaitAck(void) //测数据信号的电平
{
	OLED_SDA_Set();
	IIC_delay();
	OLED_SCL_Set();
	IIC_delay();
	OLED_SCL_Clr();
	IIC_delay();
}

//写入一个字节
void Send_Byte(u8 dat)
{
	u8 i;
	for(i=0;i<8;i++)
	{
		if(dat&0x80)//将dat的8位从最高位依次写入
		{
			OLED_SDA_Set();
    }
		else
		{
			OLED_SDA_Clr();
    }
		IIC_delay();
		OLED_SCL_Set();
		IIC_delay();
		OLED_SCL_Clr();//将时钟信号设置为低电平
		dat<<=1;
  }
}

