CROSS_COMPILE=riscv64-unknown-linux-gnu-

kernel: kernel.o linker.ld
	${CROSS_COMPILE}ld -T linker.ld --no-dynamic-linker -m elf64lriscv -static -nostdlib -o kernel.elf kernel.o
	${CROSS_COMPILE}objcopy -O binary kernel.elf kernel.bin
	${CROSS_COMPILE}objdump -D kernel.elf > kernel.dump
	rm -f *.o

kernel.o: kernel.s
	${CROSS_COMPILE}as -march=rv64imacf -mabi=lp64 -o kernel.o -c kernel.s
	

clean:
	rm -f *.o
	rm -f *.elf
	rm -f *.bin
	rm -f *.dump