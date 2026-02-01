.section .text.bios
.globl _start

_start:
    # Setup stack pointer at 0x80002000
    li sp, 0x80002000

    # Setup trap vector
    la t0, trap_handler
    csrw mtvec, t0              # Set trap vector to trap_handler

    # Enable machine timer interrupt (MTI) in mie
    li t0, 0x80                 # MTI bit = bit 7
    csrw mie, t0                # Enable timer interrupts

    # Read current mtime
    li t0, 0x0200bff8           # mtime address
    ld t1, 0(t0)                # Read current time

    # Set mtimecmp to trigger interrupt soon (current time + 20)
    li t0, 0x02004000           # mtimecmp address (hart 0)
    li t2, 20                   # Delay value
    add t1, t1, t2              # mtime + 20
    sd t1, 0(t0)                # Write to mtimecmp

    # Enable global interrupts in mstatus
    li t0, 0x8                  # MIE bit = bit 3
    csrw mstatus, t0            # Enable machine interrupts globally

    # Wait for interrupt
wait_loop:
    wfi                         # Wait for interrupt
    j wait_loop                 # Loop (shouldn't reach here if interrupt works)

# Trap handler
.align 4
trap_handler:
    # Save context on stack
    addi sp, sp, -32
    sd ra, 0(sp)
    sd t0, 8(sp)
    sd t1, 16(sp)
    sd t2, 24(sp)

    # Check if it's a timer interrupt
    csrr t0, mcause
    li t1, 0x8000000000000007   # Machine timer interrupt code
    bne t0, t1, not_timer

timer_interrupt:
    # Clear the interrupt by setting mtimecmp to max value
    li t0, 0x02004000           # mtimecmp address
    li t1, -1                   # Max value (0xFFFFFFFFFFFFFFFF)
    sd t1, 0(t0)                # Disable future timer interrupts

    # Prepare exit code 1 for success
    li a7, 93
	li a0, 0
    li t0, 1                    # Exit code 1 = success
    la t1, tohost
    sd t0, 0(t1)                # Write to tohost

    # Restore context from stack
    ld ra, 0(sp)
    ld t0, 8(sp)
    ld t1, 16(sp)
    ld t2, 24(sp)
    addi sp, sp, 32

    # Return from trap
    mret

not_timer:
    # Unexpected trap - signal error
    li a7, 93
	li a0, 0
    li t0, 2                    # Exit code 2 = error
    la t1, tohost
    sd t0, 0(t1)

    # Restore context from stack
    ld ra, 0(sp)
    ld t0, 8(sp)
    ld t1, 16(sp)
    ld t2, 24(sp)
    addi sp, sp, 32

    # Return from trap
    mret

# Stack space (if needed)
.section .bss
.align 4
stack:
    .space 1024
stack_top:

# tohost section
.section .tohost, "aw", @progbits
.globl tohost
.globl fromhost
.align 6
tohost:   .dword 0
.align 6
fromhost: .dword 0