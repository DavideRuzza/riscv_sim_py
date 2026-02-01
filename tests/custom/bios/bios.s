.global _start
.section .text.bios


_start:

	la a1, 0x2000  # load a1 to the position of the device tree

    csrr a0, mhartid # load in a0 the hart id
    
    li t0, 0x80000000 # load boot address in main memory

    jr t0 # jump to main memory

    j . # should never each here

