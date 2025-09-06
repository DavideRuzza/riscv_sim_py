# boot.S
    .section .text.init
    .globl _start
_start:
    lui   t0, 0x80000       # carica upper bits di 0x80000000
    jr    t0
