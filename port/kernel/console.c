/* 80-column text console for the bare-metal IIgs.
 *
 * Text layout (verified against GSSquared src/display/text_page_layout.hpp):
 * classic Apple II nonlinear row offsets; 80-col interleaves per char pair:
 * even column (2x) = AUX bank $01:0400, odd column (2x+1) = MAIN bank $00:0400.
 * All screen access goes through __far 24-bit pointers since the kernel runs
 * in bank $02 and the text pages live in banks 0/1.
 */
#include "console.h"

static unsigned char cur_row;
static unsigned char cur_col;

static unsigned short const row_off[24] = {
    0x00, 0x80, 0x100, 0x180, 0x200, 0x280, 0x300, 0x380,
    0x28, 0xA8, 0x128, 0x1A8, 0x228, 0x2A8, 0x328, 0x3A8,
    0x50, 0xD0, 0x150, 0x1D0, 0x250, 0x2D0, 0x350, 0x3D0
};

static volatile unsigned char __far *const main_text =
    (volatile unsigned char __far *)0x000400UL;
static volatile unsigned char __far *const aux_text =
    (volatile unsigned char __far *)0x010400UL;

void console_init(void)
{
    unsigned char r, c;

    for (r = 0; r < 24; r++) {
        for (c = 0; c < 40; c++) {
            main_text[(unsigned short)row_off[r] + c] = ' ';
            aux_text[(unsigned short)row_off[r] + c] = ' ';
        }
    }
    cur_row = 0;
    cur_col = 0;
}

void console_putchar(unsigned char c)
{
    unsigned short off;

    if (c == '\r') {
        cur_col = 0;
        return;
    }
    if (c == '\n') {
        cur_col = 0;
        if (cur_row < 23)
            cur_row++;
        return;
    }
    if (cur_col >= 80) {
        cur_col = 0;
        if (cur_row < 23)
            cur_row++;
    }
    off = (unsigned short)row_off[cur_row] + (cur_col >> 1);
    if (cur_col & 1)
        main_text[off] = c;      /* odd column in main */
    else
        aux_text[off] = c;       /* even column in aux */
    cur_col++;
}

void console_puts(const char *s)
{
    while (*s)
        console_putchar((unsigned char)*s++);
}
