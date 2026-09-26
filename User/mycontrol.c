#include "stm32f10x.h"
#include "Delay.h"
#include "Trace.h"
#include "MOTOR.h"
#include "HCSR04.h"
#include "Servo.h"
#include "mycontrol.h"

void HCSR04_getData(void);


uint16_t HCSR04_M=0;  //转到中间 超声波测到的距离
uint16_t HCSR04_L=0;  //转到左边 超声波测到的距离
uint16_t HCSR04_R=0;  //转到右边 超声波测到的距离


void Avoidance(void)
{
	HCSR04_M = HCSR04_GetValue();    //单位厘米
	
	if(HCSR04_M>0&&HCSR04_M<=35)
	{
		Set_Car_Speed(0,0);	//停车
		HCSR04_getData();  //读取左右距离
		
		if(HCSR04_L>=HCSR04_R)
		{
			Set_Car_Speed(-3800,-3800);
			Delay_ms(600);
			Set_Car_Speed(0,0);
			Delay_ms(200);
			Set_Car_Speed(-4300,4300);  //左转
			Delay_ms(800);
		}
		else
		{
			Set_Car_Speed(-3800,-3800);
			Delay_ms(600);
			Set_Car_Speed(0,0);
			Delay_ms(200);
			Set_Car_Speed(4300,-4300);  //右转
			Delay_ms(800);
		}
	}
	else
	{
		Set_Car_Speed(3800,3800);  //直行
	}
	
	
}

//超声波读取前面、左边、右边的距离
void HCSR04_getData(void)
{
	Servo_SetAngle(90);
	HCSR04_M = HCSR04_GetValue();    //单位厘米
	
	Servo_SetAngle(150);
	HCSR04_L = HCSR04_GetValue();    //单位厘米
	
	Servo_SetAngle(30);
	HCSR04_R = HCSR04_GetValue();    //单位厘米
	
	Servo_SetAngle(90);
}




//寻迹任务
void Trace_task(void)
{

	//十字/岔路口直行：中间两路+恰好一侧外圈压线(四个全压线0000不算,落回急弯处理转圈找线)
	if(X1==0&&X3==0&&(X2==0||X4==0)&&(X2==1||X4==1))
	{
		Set_Car_Speed(4000,4000);
		return;
	}

	if(X1==0&&X3==0) Set_Car_Speed(4000,4000);
		
	if(X1==1&&X3==0) Set_Car_Speed(4600,0);   //右转
		
	if(X1==0&&X3==1) Set_Car_Speed(0,4600);
	
	if(X2==1&&X1==1&&X3==1&&X4==0) Set_Car_Speed(5500,0);
		
	if(X2==0&&X1==1&&X3==1&&X4==1) Set_Car_Speed(0,5500);
		
	
	//拐右直角
	if(X3==0&&X4==0)
	{
		Set_Car_Speed(0,0);  //停车一下
		Delay_ms(500);
		do
		{
			Set_Car_Speed(5200,-5200);  //原地右转
		}while(X1==0);
	}
	
	//拐左直角
	if(X2==0&&X1==0)
	{
		Set_Car_Speed(0,0);  //停车一下
		Delay_ms(500);
		do
		{
			Set_Car_Speed(-5200,5200);  //原地左转
		}while(X3==0);
	}
	
	
	//if(X2==1&&X1==1&&X3==1&&X4==1) Set_Car_Speed(4000,4000);

}


/* ==================================================================
 *   手势遥控模式（电脑摄像头 → 蓝牙串口 → STM32）
 *
 *   为什么用 TIM1 做时间基准：
 *   TIM2 舵机 PWM、TIM3 电机 PWM、TIM4 超声波 Echo 计时、
 *   SysTick 被 Delay_us 直接改写寄存器做忙等，
 *   现有资源都不能再动。TIM1 全工程未使用，这里只用它的更新中断，
 *   不配置任何输出引脚，因此不影响 PA8~PA11（PA9/PA10 还是串口）。
 *
 *   计时完全由硬件中断驱动，不依赖主循环执行速度：
 *   即使主循环被阻塞，超时判断依然准确。
 *
 *   本模式未激活时，以下所有函数都不参与电机控制，
 *   手机蓝牙遥控 / 循迹 / 避障行为与改动前完全一致。
 * ================================================================== */

static volatile u32 g_ms_tick = 0;    /* TIM1 每 1ms 加 1，独立时间基准 */
static volatile u8  g_active  = 0;    /* 1 = 处于手势遥控模式 */
static volatile u8  g_cmd     = 0x00; /* 最近一次有效的控制指令 */
static volatile u32 g_last_rx = 0;    /* 最近一次收到有效控制帧的时刻(ms) */
static u8 g_timeout = 0;              /* 1 = 已超时停车 */

/* TIM1 时间基准初始化：72MHz/(71+1)=1MHz，再计 1000 次 = 1ms */
void Gesture_Init(void)
{
	TIM_TimeBaseInitTypeDef TIM_TimeBaseInitStructure;
	NVIC_InitTypeDef NVIC_InitStructure;

	RCC_APB2PeriphClockCmd(RCC_APB2Periph_TIM1, ENABLE);

	TIM_InternalClockConfig(TIM1);
	TIM_TimeBaseInitStructure.TIM_ClockDivision = TIM_CKD_DIV1;
	TIM_TimeBaseInitStructure.TIM_CounterMode = TIM_CounterMode_Up;
	TIM_TimeBaseInitStructure.TIM_Period = 999;
	TIM_TimeBaseInitStructure.TIM_Prescaler = 71;
	TIM_TimeBaseInitStructure.TIM_RepetitionCounter = 0;  /* 高级定时器必须赋值 */
	TIM_TimeBaseInit(TIM1, &TIM_TimeBaseInitStructure);

	TIM_ClearFlag(TIM1, TIM_FLAG_Update);
	TIM_ITConfig(TIM1, TIM_IT_Update, ENABLE);

	/* 抢占优先级 2，低于 USART1 的 1，保证串口接收不被计时打断 */
	NVIC_InitStructure.NVIC_IRQChannel = TIM1_UP_IRQn;
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 2;
	NVIC_InitStructure.NVIC_IRQChannelSubPriority = 2;
	NVIC_Init(&NVIC_InitStructure);

	TIM_Cmd(TIM1, ENABLE);
}

void TIM1_UP_IRQHandler(void)
{
	if (TIM_GetITStatus(TIM1, TIM_IT_Update) != RESET)
	{
		g_ms_tick++;
		TIM_ClearITPendingBit(TIM1, TIM_IT_Update);
	}
}

/* 串口收到一个字节时调用（在 USART1 接收中断内） */
void Gesture_OnRxByte(u8 byte)
{
	if (!g_active) return;   /* 不在此模式：完全不干预原有遥控 */

	if (byte == 0x00 || byte == 0x03 || byte == 0x04)
	{
		g_cmd = byte;
		g_last_rx = g_ms_tick;   /* 刷新心跳时刻 */
	}
}

u8 Gesture_IsActive(void)   { return g_active;  }
u8 Gesture_IsTimedOut(void) { return g_timeout; }

/* 进入手势遥控模式：先停车，再等电脑的心跳帧 */
void Gesture_Enter(void)
{
	Set_Car_Speed(0, 0);
	g_active = 1;
	g_cmd = 0x00;
	g_timeout = 0;
	g_last_rx = g_ms_tick;
}

/* 退出手势遥控模式：停车，把控制权交回手机遥控/循迹/避障 */
void Gesture_Exit(void)
{
	Set_Car_Speed(0, 0);
	g_active = 0;
	g_cmd = 0x00;
	g_timeout = 0;
}

/* 主循环调用：判断心跳超时并输出电机指令 */
void Gesture_Task(void)
{
	u32 now;

	if (!g_active) return;

	now = g_ms_tick;   /* 只读一次，保证本轮判断用的是同一时刻 */

	if ((u32)(now - g_last_rx) > GESTURE_TIMEOUT_MS)
	{
		/* 电脑崩溃、蓝牙断开、电脑程序卡死都会落到这里 */
		g_timeout = 1;
		Set_Car_Speed(0, 0);
		return;
	}

	g_timeout = 0;
	switch (g_cmd)
	{
		case 0x03: Set_Car_Speed(-7200, 7200); break;   /* 左转，与手机遥控一致 */
		case 0x04: Set_Car_Speed(7200, -7200); break;   /* 右转，与手机遥控一致 */
		default:   Set_Car_Speed(0, 0);        break;   /* 0x00 停车 */
	}
}
