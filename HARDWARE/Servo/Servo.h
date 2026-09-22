#ifndef __Servo_H
#define __Servo_H	
#include "sys.h"


/*
*** TIM2  配置定时器2PWM与控制SG90舵机 ***

*** PWM频率：50Hz ***

*** 接口：PA0->舵机1   PA1->舵机2   PA2->舵机3   PA3->舵机4 ***

*** 原作者：chenjiayou  整理与补充：yingsangmao ***



*/

void myServo_Init(u16 arr,u16 psc);

void Servo_SetAngle(uint8_t angle);


#endif
