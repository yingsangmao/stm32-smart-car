/**
 * @file    mycontrol.h
 * @brief   避障、循迹与手势遥控模式的接口声明
 *
 * @note    属于 stm32-smart-car 项目（STM32F103C8T6 蓝牙循迹避障智能小车）。
 *          原作者：chenjiayou      整理与补充：yingsangmao
 *          各部分代码的具体来源与授权见仓库根目录 README.md / LICENSE。
 */

#ifndef __mycontrol_H
#define __mycontrol_H
#include "sys.h"

void Avoidance(void);
void Trace_task(void);

/* ================= 手势遥控模式（电脑摄像头 → 蓝牙 → 串口1） ================
 * 复用原有 0x00/0x03/0x04 三条指令，不新增运动指令：
 *   0x00 停车   0x03 左转   0x04 右转
 * 模式切换用两个原来未占用的字节，不影响手机 App 的 0x00~0x06。
 * ========================================================================= */
#define CMD_GESTURE_ENTER   0x10   /* 进入手势遥控模式 */
#define CMD_GESTURE_EXIT    0x11   /* 退出手势遥控模式 */

/* 心跳超时时间(ms)：电脑约每 100ms 发一帧，超过这个时间没收到就停车 */
#define GESTURE_TIMEOUT_MS  500

void Gesture_Init(void);        /* 上电初始化一次：开 TIM1 的 1ms 时间基准 */
void Gesture_OnRxByte(u8 byte); /* 在 USART1 接收中断里调用，刷新心跳 */
u8   Gesture_IsActive(void);    /* 1 = 当前处于手势遥控模式 */
u8   Gesture_IsTimedOut(void);  /* 1 = 本模式下已超时停车（供 OLED 显示） */
void Gesture_Enter(void);       /* 进入模式（立即停车） */
void Gesture_Exit(void);        /* 退出模式（立即停车） */
void Gesture_Task(void);        /* 主循环调用：超时判断 + 电机输出 */

#endif

