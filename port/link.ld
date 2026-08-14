MEMORY {
    BANK (rwx) : ORIGIN = 0x020000, LENGTH = 0x10000
}

SECTIONS {
    .zpage 0x020000 : { *(zpage*) } > BANK
    .text  0x020100 : { *(*) } > BANK
}
