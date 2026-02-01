MEMORY {
  dram_space (rwx) : ORIGIN = 0x0, LENGTH = 0x20
}

SECTIONS {
  .text : {
    bios.o(.text.bios)
  } > dram_space
}

