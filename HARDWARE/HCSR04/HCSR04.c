/**
 * @file    HCSR04.c
 * @brief   HC-SR04 超声波测距（Trig=PA4，Echo=PA5，TIM4 计 Echo 高电平时间）
 *
 * @note    属于 stm32-smart-car 项目（STM32F103C8T6 蓝牙循迹避障智能小车）。
 *          原作者：chenjiayou      整理与补充：yingsangmao
 *          各部分代码的具体来源与授权见仓库根目录 README.md / LICENSE。
 */

#include "stm32f10x.h"    // STM32F10x 设备头文件
#include "HCSR04.h"       // HC-SR04 模块驱动头文件
#include "delay.h"        // 微秒、毫秒级延时头文件

uint16_t Time;            // 定时器计数变量，用于记录 Echo 为高电平的时间周期数

/**
 * @brief  初始化 TIM4 定时器，用于计时 Echo 引脚高电平持续时间
 * @note   定时器时钟来源为内置时钟，计数周期：ARR=7199，PSC=0 可得每次更新中断间隔 0.0001s
 */
void TIM4_Init(void)
{
    // 使能 TIM4 时钟
    RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM4, ENABLE);

    // 配置为内部时钟模式
    TIM_InternalClockConfig(TIM4);

    // 定时器基础参数配置
    TIM_TimeBaseInitTypeDef TIM_TimeBaseInitStructure;
    TIM_TimeBaseInitStructure.TIM_ClockDivision = TIM_CKD_DIV1;          // 不分频
    TIM_TimeBaseInitStructure.TIM_CounterMode = TIM_CounterMode_Up;      // 向上计数模式
    TIM_TimeBaseInitStructure.TIM_Period = 7199;                         // 自动重装载寄存器 (ARR)，对应更新事件间隔 0.0001s
    TIM_TimeBaseInitStructure.TIM_Prescaler = 0;                         // 预分频器 (PSC)，不分频
    TIM_TimeBaseInitStructure.TIM_RepetitionCounter = 0;                 // 仅在高级定时器中有效，普通定时器置 0
    TIM_TimeBaseInit(TIM4, &TIM_TimeBaseInitStructure);

    // 清除更新中断标志
    TIM_ClearFlag(TIM4, TIM_FLAG_Update);
    // 使能更新中断
    TIM_ITConfig(TIM4, TIM_IT_Update, ENABLE);

    // 中断优先级配置
    NVIC_InitTypeDef NVIC_InitStructure;
    NVIC_InitStructure.NVIC_IRQChannel = TIM4_IRQn;                      // 定时器 4 中断通道
    NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;                      // 使能中断
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 2;            // 抢占优先级
    NVIC_InitStructure.NVIC_IRQChannelSubPriority = 1;                   // 响应优先级
    NVIC_Init(&NVIC_InitStructure);

    // 启动定时器
    TIM_Cmd(TIM4, ENABLE);
}

/**
 * @brief  TIM4 中断服务函数，每次更新中断调用一次
 * @note   在 Echo 引脚为高电平时累加 Time 计数
 */
void TIM4_IRQHandler(void)
{
    // 判断是否为更新中断
    if (TIM_GetITStatus(TIM4, TIM_IT_Update) == SET)
    {
        // 读取 PA5（Echo）引脚电平，高电平时计时变量加 1
        if (GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_5) == 1)
        {
            Time++;
        }
        // 清除中断标志
        TIM_ClearITPendingBit(TIM4, TIM_IT_Update);
    }
}

/**
 * @brief  初始化 HC-SR04 模块所用的 GPIO：Trig 输出，Echo 下拉输入
 */
void HCSR04_Init(void)
{
    // 使能 GPIOA 时钟
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA, ENABLE);
    GPIO_InitTypeDef GPIO_InitStruct;

    // Trig (PA4) 推挽输出，用于产生触发脉冲
    GPIO_InitStruct.GPIO_Mode = GPIO_Mode_Out_PP;
    GPIO_InitStruct.GPIO_Pin = GPIO_Pin_4;
    GPIO_InitStruct.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &GPIO_InitStruct);

    // Echo (PA5) 下拉输入，用于接收回波信号
    GPIO_InitStruct.GPIO_Mode = GPIO_Mode_IPD;  // 下拉输入
    GPIO_InitStruct.GPIO_Pin = GPIO_Pin_5;
    GPIO_InitStruct.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &GPIO_InitStruct);

    // 初始将 Trig 拉低
    GPIO_ResetBits(GPIOA, GPIO_Pin_4);
}

/**
 * @brief  发送 45μs 的高电平触发信号，并初始化计时
 */
void HCSR04_Start(void)
{
    // 发送 Trig 脉冲
    GPIO_SetBits(GPIOA, GPIO_Pin_4);  // 置高
    Delay_us(45);                     // 等待 45 微秒
    GPIO_ResetBits(GPIOA, GPIO_Pin_4);// 置低

    // 重置计时变量
    Time = 0;
    // 启动定时器计时 Echo 信号
    TIM4_Init();
}

/**
 * @brief  获取一次超声波测距结果（单位：cm）
 * @return 距离值，范围 ~2cm–400cm
 */
uint16_t HCSR04_GetValue(void)
{
    HCSR04_Start();       // 发射超声波，并开始计时
		Delay_ms(100);        // 等待一次测距周期完成;  HC-SR04官方建议：两次触发之间的最小间隔为60ms（原因：避免回波干扰、确保测距准确）
    TIM_Cmd(TIM4, DISABLE);// 测距完成后关闭定时器
		
		if(Time >235) Time = 0;  //测4米约需 23.5ms，要是大于4米就返回0米
	
    // 计算距离：
    // Time * 0.0001s 为 Echo 高电平总时间（单位：秒）
    // 声速约 340m/s → 34000cm/s
    // 往返时间，实际距离 = (time_sec * 34000) / 2
    return ((Time * 0.0001f) * 34000) / 2;
}

