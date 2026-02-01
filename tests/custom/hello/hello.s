.global _start
.section .text.bios


_start:	addi a0, x0, 0x68
	li a1, 0x10000000
	sb a0, (a1) # 'h'

	addi a0, x0, 0x65
	sb a0, (a1) # 'e'

	addi a0, x0, 0x6C
	sb a0, (a1) # 'l'

	addi a0, x0, 0x6C
	sb a0, (a1) # 'l'\

	addi a0, x0, 0x6F
	sb a0, (a1) # 'o'

	li s0, 20  # set mtimecmp to interrupt at 8
	la s1, 0x2004000 # write to the clint
	sw s0, 0(s1)

	j .
	# j pass

pass:
	li a7, 93
	li a0, 0

	li t0, 1
	la t1, tohost     # Load address of tohost
	sd t0, 0(t1)      # Store to tohost

	j .

.section .tohost, "aw", @progbits
.globl tohost
.globl fromhost

.align 6
tohost:   .dword 0
.align 6
fromhost: .dword 0

