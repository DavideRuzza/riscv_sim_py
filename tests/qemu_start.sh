#!/bin/bash

riscv64-unknown-elf-as -o boot.o boot.S
riscv64-unknown-elf-ld -T boot.ld -o boot.elf boot.o

qemu-system-riscv64 -machine virt -nographic \
    -bios boot.elf \
    -kernel rv64/elf/p/rv64mi-p-csr \
    -S -s