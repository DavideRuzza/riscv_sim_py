CROSS_COMPILE=riscv64-unknown-linux-gnu-

bios: bios.o bios.ld
	${CROSS_COMPILE}ld -T bios.ld --no-dynamic-linker -m elf64lriscv -static -nostdlib -o bios.elf bios.o
	${CROSS_COMPILE}objcopy -O binary bios.elf bios.bin
	${CROSS_COMPILE}objdump -D bios.elf > bios.dump
	rm -f *.o

bios.o: bios.s
	${CROSS_COMPILE}as -march=rv64imacf -mabi=lp64 -o bios.o -c bios.s
	

clean:
	rm -f *.o
	rm -f *.elf
	rm -f *.bin
	rm -f *.dump