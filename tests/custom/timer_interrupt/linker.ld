MEMORY {
  dram_space (rwx) : ORIGIN = 0x80000000, LENGTH = 8K
}

SECTIONS {
  .text : {
    *(.text.bios)
    *(.text*)
  } > dram_space

  .bss : {
    *(.bss*)
  } > dram_space

  .tohost : {
    *(.tohost)
  } > dram_space
}