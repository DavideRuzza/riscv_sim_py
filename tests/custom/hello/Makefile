CROSS_COMPILE=riscv64-unknown-linux-gnu-

hello: hello.o linker.ld
	${CROSS_COMPILE}ld -T linker.ld --no-dynamic-linker -m elf64lriscv -static -nostdlib -o hello.elf hello.o
	${CROSS_COMPILE}objcopy -O binary hello.elf hello.bin
	${CROSS_COMPILE}objdump -D hello.elf > hello.dump
	rm -f *.o

hello.o: hello.s
	${CROSS_COMPILE}as -march=rv64i -mabi=lp64 -o hello.o -c hello.s
	

clean:
	rm -f *.o
	rm -f *.elf
	rm -f *.bin
	rm -f *.dump