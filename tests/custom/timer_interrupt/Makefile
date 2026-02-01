CROSS_COMPILE=riscv64-unknown-linux-gnu-

main: main.o linker.ld
	${CROSS_COMPILE}ld -T linker.ld --no-dynamic-linker -m elf64lriscv -static -nostdlib -o main.elf main.o
	${CROSS_COMPILE}objcopy -O binary main.elf main.bin
	${CROSS_COMPILE}objdump -D main.elf > main.dump
	rm -f *.o

main.o: main.s
	${CROSS_COMPILE}as -march=rv64imacf -mabi=lp64 -o main.o -c main.s
	

clean:
	rm -f *.o
	rm -f *.elf
	rm -f *.bin
	rm -f *.dump