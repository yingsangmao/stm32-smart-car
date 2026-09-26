/**
 * @file    MOTOR.c
 * @brief   L298N 电机驱动：左右轮转速与正反转控制
 *
 * @note    属于 stm32-smart-car 项目（STM32F103C8T6 蓝牙循迹避障智能小车）。
 *          原作者：chenjiayou      整理与补充：yingsangmao
 *          各部分代码的具体来源与授权见仓库根目录 README.md / LICENSE。
 */

#include "stm32f10x.h"
#include "Delay.h"
#include "TIM3_PWM.h"

void MOTOR_GPIO_Init(void)
{
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB, ENABLE);
	
	GPIO_InitTypeDef GPIO_InitStructure;
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_5|GPIO_Pin_6|GPIO_Pin_7|GPIO_Pin_8;  //依次接L298N  IN1,IN2,IN3,IN4
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
	GPIO_Init(GPIOB, &GPIO_InitStructure);
}	

/*
	函数功能：控制两侧电机的速度和正反转

	参数说明：
	* 范围：-7200到7200  【注意：参数"正负"表示电机不同的转向】
	* 参数1：Left_speed   控制左侧电机转速和方向
	* 参数2：Right_speed  控制右侧电机转速和方向
				
*/
void Set_Car_Speed(int Left_speed ,int Right_speed)
{
	//左侧电机
	if(Left_speed>0)
	{
		TIM_SetCompare2(TIM3,Left_speed);  //PA7
		GPIO_SetBits(GPIOB, GPIO_Pin_7);
		GPIO_ResetBits(GPIOB, GPIO_Pin_8);
	}
	else if(Left_speed<0)
	{
		TIM_SetCompare2(TIM3,-Left_speed);  //PA7
		GPIO_ResetBits(GPIOB, GPIO_Pin_7);
		GPIO_SetBits(GPIOB, GPIO_Pin_8);
	}
	else
	{
		TIM_SetCompare2(TIM3,0);            //PA7
		GPIO_SetBits(GPIOB, GPIO_Pin_7);
		GPIO_SetBits(GPIOB, GPIO_Pin_8);
	}
	
	
	//右侧电机
	if(Right_speed>0)
	{
		TIM_SetCompare1(TIM3,Right_speed);  //PA6
		GPIO_SetBits(GPIOB, GPIO_Pin_5);
		GPIO_ResetBits(GPIOB, GPIO_Pin_6);
	}
	else if(Right_speed<0)
	{
		TIM_SetCompare1(TIM3,-Right_speed);  //PA6
		GPIO_ResetBits(GPIOB, GPIO_Pin_5);
		GPIO_SetBits(GPIOB, GPIO_Pin_6);
	}
	else
	{
		TIM_SetCompare1(TIM3,0);  					//PA6
		GPIO_SetBits(GPIOB, GPIO_Pin_5);
		GPIO_SetBits(GPIOB, GPIO_Pin_6);
	}
	
	
}
