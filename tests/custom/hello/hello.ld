MEMORY {
  dram_space (rwx) : ORIGIN = 0x80000000, LENGTH = 0x100000
  clint (rw)       : ORIGIN = 0x80200000, LENGTH = 0x10000
}

SECTIONS {
  .text : {
    hello.o(.text.bios)
  } > dram_space

  .tohost : {
    *(.tohost)
  } > dram_space
}

