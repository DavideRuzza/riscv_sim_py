#!/bin/bash

cd opensbi/opensbi-main
make clean
make \
    PLATFORM=generic \
    FW_JUMP=y \
    DEBUG=y \
    FW_TEXT_START=0x80000000 \
    FW_JUMP_OFFSET=0x200000 \
    ARCH=riscv \
    CROSS_COMPILE=riscv64-unknown-linux-gnu- \
    PLATFORM_RISCV_ISA=rv64ima_zicsr_zifencei \
    FW_JUMP_FDT_OFFSET=0x100000 # position where devicetree will be relocated for the kernel
    # DEBUG=1
    # FW_FDT_PATH=/home/davide/projects/riscv/riscv_sim_py/device_tree/platform.dtb \

cd ../..

rm opensbi/bin/*
rm opensbi/elf/*
rm opensbi/*.dump

cp ./opensbi/opensbi-main/build/platform/generic/firmware/*.bin ./opensbi/bin/
cp ./opensbi/opensbi-main/build/platform/generic/firmware/*.elf ./opensbi/elf/

riscv64-unknown-linux-gnu-objdump -d ./opensbi/elf/fw_jump.elf > ./opensbi/fw_jump.dump
