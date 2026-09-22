#include "Servo.h"
#include "Delay.h"

/*
*** TIM2  配置定时器2PWM控制SG90舵机 ***

*** PWM频率：50Hz ***

*** 接口：PA0->舵机1 ***

*** 作者：yingsangmao ***



*/
void myServo_Init(u16 arr,u16 psc)
{  
	GPIO_InitTypeDef GPIO_InitStructure;
	TIM_TimeBaseInitTypeDef  TIM_TimeBaseStructure;
	TIM_OCInitTypeDef  TIM_OCInitStructure;
	
	RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM2, ENABLE);	//使能定时器2时钟
 	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA, ENABLE);  //使能GPIO外设
	
 
   //初始化输出TIM2 通道1 PWM脉冲波形的引脚CH1->PA0
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_0; //CH1
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_PP;  //复用推挽输出
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
	GPIO_Init(GPIOA, &GPIO_InitStructure);//初始化GPIO
 
   //初始化TIM2
	TIM_TimeBaseStructure.TIM_Period = arr; //设置在下一个更新事件装入活动的自动重装载寄存器周期的值
	TIM_TimeBaseStructure.TIM_Prescaler =psc; //设置用来作为TIMx时钟频率除数的预分频值 
	TIM_TimeBaseStructure.TIM_ClockDivision = 0; //设置时钟分割:TDTS = Tck_tim
	TIM_TimeBaseStructure.TIM_CounterMode = TIM_CounterMode_Up;  //TIM向上计数模式
	TIM_TimeBaseInit(TIM2, &TIM_TimeBaseStructure); //根据TIM_TimeBaseInitStruct中指定的参数初始化TIMx的时间基数单位
	
	//初始化TIM2 Channe PWM模式	 
	TIM_OCInitStructure.TIM_OCMode = TIM_OCMode_PWM1; //选择定时器模式:TIM脉冲宽度调制模式1
 	TIM_OCInitStructure.TIM_OutputState = TIM_OutputState_Enable; //比较输出使能
	TIM_OCInitStructure.TIM_OCPolarity = TIM_OCPolarity_High; //输出极性:TIM输出比较极性高
	
	TIM_OC1Init(TIM2, &TIM_OCInitStructure);  //根据T指定的参数初始化外设TIM2 OC1
  
	TIM_OC1PreloadConfig(TIM2, TIM_OCPreload_Enable);  //使能TIM2在CCR1上的预装载寄存器
	
	TIM_Cmd(TIM2, ENABLE);  //使能TIM2
}



// 脉宽对应值（ARR=1999, PSC=719 时，对应 20ms 周期）
// 0° 对应 0.5ms -> CCR = 50
// 180° 对应 2.5ms -> CCR = 250
#define SERVO_MIN_PULSE 50
#define SERVO_MAX_PULSE 250

/**
 * @brief  设置舵机到指定角度
 * @param  angle: 目标角度，范围 0~180。超过范围会被限制到最近边界。
 */
void Servo_SetAngle(uint8_t angle)
{
    // 限幅
    if (angle > 180) {
        angle = 180;
    }
    // 线性映射角度到 CCR 值
    uint16_t pulse = SERVO_MIN_PULSE +
                     (uint32_t)(angle) * (SERVO_MAX_PULSE - SERVO_MIN_PULSE) / 180;
    // 设置比较寄存器
    TIM_SetCompare1(TIM2, pulse);
    // 给舵机一些时间动作
    Delay_ms(500);
}





