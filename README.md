![Alt](https://repobeats.axiom.co/api/embed/d42572a175b41c8faeb88ea3732ce61a16d7cf58.svg "Repobeats analytics image")

# RISCV 64bit python cpu simulation.


This project is my first approach to computer architecture. I have been working on this for more than a year an now the OpenSBI can be loaded even though the performances are terribly slow. Still it works!! 

I will use my knowledge to implement the same in hardware using an FPGA. 

## Features 

* Base ISA:
    - [x] I
    - [x] A
    - [x] M
    - [x] C
    - [x] F
    - [ ] D

* M, S and U priviledges
* CLINT
* PLIC
* UART 16550 compatible


## debug

number of execution for every instruction during the loading of OpenSBI

------ INSTRUCTION PROFILE -------
- LOAD     : 4726377
- OP_IMM   : 4708848
- OP_IMM_32: 3016173
- JAL      : 2501307
- STORE    : 2242817
- OP       : 751578
- BRANCH   : 720401
- JALR     : 417138
- OP_32    : 184519
- LUI      : 35628
- AUIPC    : 9091
- MISC_MEM : 5560
- SYSTEM   : 537
- AMO      : 152
- ILLEGAL  : 0
- FMADD    : 0
- LOAD_FP  : 0
- STORE_FP : 0
- FMSUB    : 0
- custom0  : 0
- custom1  : 0
- FMNSUB   : 0
- FNMADD   : 0
- OP_FP    : 0
- OP_V     : 0
- OP_VE    : 0
- custom2  : 0
- custom3  : 0
----------------------------------