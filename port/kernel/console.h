#ifndef MINIX_GS_CONSOLE_H
#define MINIX_GS_CONSOLE_H

void console_init(void);
void console_putchar(unsigned char c);
void console_puts(const char *s);
void console_beep(void);

#endif
