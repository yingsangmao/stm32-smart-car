#include "stm32f10x.h"                  // Device header
#include "Delay.h"
#include "LED.h"
#include "TIM3_PWM.h"
#include "MOTOR.h"
#include "OLED.h"
#include "USART1.h"
#include "Servo.h"
#include "HCSR04.h"
#include "mycontrol.h"
#include "Trace.h"


extern u8 RxData;
uint16_t HCSR04_Distance=0;  //超声波测到的距离


/**** main 主函数代码 ***

*** 原作者：chenjiayou  整理与补充：yingsangmao ***



*/
int main(void)
{
	NVIC_PriorityGroupConfig(NVIC_PriorityGroup_2);

	TIM3_PWM_Init(7199,1);   //定时器PWM模式初始化(5KHZ)，用于控制L298N电机调速
	MOTOR_GPIO_Init();       //接L298N引脚IN1到IN4，控制电机正反转
	LED_Init();              //LED灯初始化
	
	OLED_Init();          //OLED初始化
	OLED_ColorTurn(0);    //0正常显示，1 反色显示
	OLED_DisplayTurn(0);  //0正常显示 1 屏幕翻转显示
	OLED_Clear();         //清屏
	OLED_Refresh();       //更新显存到OLED(即刷新刚写入的数据,刷新屏幕)
	//OLED静态显示字符
	OLED_ShowString(0,0,"yingsangmao!",16,1);
	OLED_ShowString(0,16,"U1RX:",16,1);  //蓝牙接收到的数据
	OLED_ShowString(0,32,"SR04:",16,1);  OLED_ShowString(64,32,"cm",16,1);  //超声波数据
	OLED_ShowString(0,48,"Tra:",16,1);  //循迹灰度数据
	OLED_Refresh();             //更新显存到OLED(即刷新刚写入的数据,刷新屏幕)
	
	USART1_Init(9600); //初始化串口1，接JDY-31蓝牙模块
	Gesture_Init();    //手势遥控：TIM1 提供 1ms 独立时间基准（超时停车用）
	myServo_Init(1999,719);        //定时器2，产生PWM波，周期20ms，50HZ，控制舵机
	Servo_SetAngle(90);  //初始化舵机的角度，转到90°（正对前方）
	HCSR04_Init();      //HC-SR04超声波模块初始化
	Trace_Init();      //循迹初始化
	
 
	while(1)
	{
		/* ---- 手势遥控模式切换：0x10 进入 / 0x11 退出 ----
		   这两个字节原本未被占用，不影响手机 App 的 0x00~0x06。
		   处理完把 RxData 归零，避免同一个字节继续落到下面的 switch 重复执行 */
		if(RxData==CMD_GESTURE_ENTER)
		{
			Gesture_Enter();
			RxData = 0x00;
		}
		else if(RxData==CMD_GESTURE_EXIT)
		{
			Gesture_Exit();
			RxData = 0x00;
		}

		if(Gesture_IsActive())
		{
			/* 手势遥控模式：由电脑约 100ms 发一帧维持心跳，
			   超过 GESTURE_TIMEOUT_MS 没收到就自动停车。
			   此模式下不执行手机遥控/循迹/避障，避免抢控制权 */
			Gesture_Task();
		}
		else
		{
			/* 以下为原有手机蓝牙遥控 / 循迹 / 避障逻辑，未做改动 */
			switch(RxData)
			{
			case 0x00:
				Set_Car_Speed(0,0); //停车
				HCSR04_Distance = HCSR04_GetValue();    //单位厘米
				break;
			case 0x01:
				Set_Car_Speed(7200,7200); //直行
				break;
			case 0x02:
				Set_Car_Speed(-7200,-7200); //后退
				break;
			case 0x03:
				Set_Car_Speed(-7200,7200); //左转
				break;
			case 0x04:
				Set_Car_Speed(7200,-7200); //右转
				break;
			case 0x05:
				Avoidance();              //避障
				break;
			case 0x06:
				Trace_task();            //循迹
				break;

			}
		}
		
		
		
		OLED_ShowNum(40,16, RxData, 2,16,1);
		OLED_ShowNum(40,32, HCSR04_Distance, 3,16,1);
		OLED_ShowNum(40,48, X1, 1,16,1); OLED_ShowNum(40+16,48, X2, 1,16,1); OLED_ShowNum(40+32,48, X3, 1,16,1); OLED_ShowNum(40+48,48, X4, 1,16,1); 
		/* 手势遥控状态，显示在 U1RX 那一行的右侧（第 16 行 x=64 起）：
		   [GES] = 手势模式，正常受控中
		   [TMO] = 手势模式，但已超时停车（电脑掉线/崩溃）
		   [---] = 未进入手势模式，手机遥控/循迹/避障正常 */
		if(Gesture_IsActive())
		{
			if(Gesture_IsTimedOut()) OLED_ShowString(64,16,(u8*)"[TMO]",16,1);
			else                     OLED_ShowString(64,16,(u8*)"[GES]",16,1);
		}
		else
		{
			OLED_ShowString(64,16,(u8*)"[---]",16,1);
		}

		OLED_Refresh();             //更新显存到OLED(即刷新刚写入的数据,刷新屏幕)



	}
}

