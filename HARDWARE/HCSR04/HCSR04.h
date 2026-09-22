#ifndef __HCSR04_H
#define __HCSR04_H
#include "stm32f10x.h"                  // Device header


void HCSR04_Init(void);
uint16_t HCSR04_GetValue(void);
void HCSR04_Start(void);


#endif 
