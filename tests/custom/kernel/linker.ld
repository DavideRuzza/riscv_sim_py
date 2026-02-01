MEMORY {
  dram_space (rwx) : ORIGIN = 0x80200000, LENGTH = 0x100
}

SECTIONS {
  .text : {
    kernel.o(.text.kernel)
  } > dram_space
}

