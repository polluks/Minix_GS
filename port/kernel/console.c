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
    volatile unsigned char __far *sw;

    /* SET80COL soft switch ($C00D): select the 80-column text mode so the
     * VGC/scanner interleaves the aux+main text buffers we write below.
     * The ROM leaves the display in 40-col mode for a raw boot.
     * SETALTCHAR ($C00F): GSSquared's CharRom maps screen codes $40-$7F
     * through the Apple-II flash table, which garbles lowercase (a-z lands on
     * punctuation glyphs). The ALT charset it selects uses the linear code->glyph
     * table, which contains the true lowercase glyphs.
     * Written via the bank $E0 MegaII window: the kernel inhibits IOLC
     * shadowing (see int.c), so bank-0 $C0xx reads as RAM. */
    sw = (volatile unsigned char __far *)0x00E0C00DUL;
    *sw = 0;
    sw = (volatile unsigned char __far *)0x00E0C00FUL;
    *sw = 0;

    for (r = 0; r < 24; r++) {
        for (c = 0; c < 40; c++) {
            main_text[(unsigned short)row_off[r] + c] = ' ';
            aux_text[(unsigned short)row_off[r] + c] = ' ';
        }
    }
    cur_row = 0;
    cur_col = 0;
}

/* Ensoniq DOC host interface, reached via the bank $E0 MegaII window (the
 * kernel inhibits IOLC shadowing, so bank-0 $C0xx reads as RAM): Sound
 * Control $C03C, Sound Data $C03D, Sound Address $C03E/$C03F.  Control bit 6
 * = RAM mode, bit 5 = auto-increment, low nibble = system volume.  This is
 * the same path the ROM boot beep uses; GSSquared emulates the DOC with SDL
 * audio output.
 *
 * Voice 0 runs a 256-sample square wave from DOC RAM $0000, looping (free
 * run).  The table holds only $FF/$01 so it never hits the DOC's halt-on-zero
 * sample.  Pitch = doc_rate * freq / 2^17 (res 0, 256-sample table),
 * doc_rate = 7159090/8/3, so freq=440 gives ~1 kHz.
 */
static void doc_wr(volatile unsigned char __far *adrl,
                   volatile unsigned char __far *dat,
                   unsigned char reg, unsigned char val)
{
    *adrl = reg;                /* register number (lo address byte) */
    *dat = val;                 /* data */
}

void console_beep(void)
{
    volatile unsigned char __far *ctl =
        (volatile unsigned char __far *)0x00E0C03CUL;
    volatile unsigned char __far *dat =
        (volatile unsigned char __far *)0x00E0C03DUL;
    volatile unsigned char __far *adrl =
        (volatile unsigned char __far *)0x00E0C03EUL;
    volatile unsigned char __far *adrh =
        (volatile unsigned char __far *)0x00E0C03FUL;
    unsigned short i;
    volatile unsigned int d;

    *ctl = 0x0F;                /* register mode, system volume 15 */
    doc_wr(adrl, dat, 0xA0, 0x01);   /* halt voice 0 while we program it */
    doc_wr(adrl, dat, 0xE1, 0x01);   /* exactly 1 oscillator enabled */

    /* Load the square wave into DOC RAM $0000 (auto-increment RAM mode). */
    *ctl = 0x6F;
    *adrh = 0x00;
    *adrl = 0x00;
    for (i = 0; i < 256; i++)
        *dat = (i & 0x80) ? 0x01 : 0xFF;

    /* Voice 0 registers: freq lo/hi, volume, wave pointer, table config. */
    *ctl = 0x0F;
    doc_wr(adrl, dat, 0x00, 440 & 0xFF);    /* freq lo (~1 kHz) */
    doc_wr(adrl, dat, 0x01, 440 >> 8);      /* freq hi */
    doc_wr(adrl, dat, 0x40, 0x7F);          /* volume */
    doc_wr(adrl, dat, 0x80, 0x00);          /* wave table pointer = $0000 */
    doc_wr(adrl, dat, 0xC0, 0x00);          /* bank 0, 256-sample, res 0 */
    doc_wr(adrl, dat, 0xA0, 0x00);          /* key on voice 0 */
    doc_wr(adrl, dat, 0xE1, 0x01);          /* (re)confirm 1 oscillator */

    for (d = 0; d < 30000; d++) ;           /* ring ~0.2 s */

    doc_wr(adrl, dat, 0xA0, 0x01);          /* halt voice 0 */
}

void console_putchar(unsigned char c)
{
    unsigned short off;

    if (c == '\a') {
        console_beep();
        return;
    }
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
    /* Under the ALT charset the linear table renders codes $00-$1F as
     * @A-Z[\]^_ (same glyphs the flash table uses for $40-$5F), so fold
     * the $40-$5F range down to $00-$1F. Everything else maps linearly. */
    if (c >= 0x40 && c < 0x60)
        c -= 0x40;
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
