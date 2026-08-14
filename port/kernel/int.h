#ifndef MINIX_GS_INT_H
#define MINIX_GS_INT_H

extern volatile unsigned short jiffies;

void timer_init(void);
void int_enable(void);

#endif
