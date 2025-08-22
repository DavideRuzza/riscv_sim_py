from enum import Enum


class Ops(Enum):

    INVALID = 0b0000000
    LUI = 0b0110111
    LOAD = 0b0000011
    STORE = 0b0100011
    
    AUIPC  = 0b0010111
    BRANCH = 0b1100011
    JAL = 0b1101111
    JALR = 0b1100111
    
    OP = 0b0110011
    OP_32 = 0b0111011
    OP_IMM = 0b0010011
    OP_IMM_32 = 0b0011011
    
    MISC_MEM = 0b0001111
    SYSTEM = 0b1110011

class SYS_F12(Enum):
    ECALL = 0x000
    MRET = 0x302
    SRET = 0x102
    
class OP_F3(Enum):
    ADD_SUB = 0b000
    SLL = 0b001
    SLT = 0b010 
    SLTU = 0b011
    XOR = 0b100
    SRX =  0b101
    OR = 0b110 
    AND = 0b111
    
class LOAD_F3(Enum):
    LB = 0b000
    LH = 0b001
    LW = 0b010
    LWU = 0b110
    LBU = 0b100
    LHU = 0b101
    LD = 0b011

class STORE_F3(Enum):
    SB = 0b000
    SH = 0b001
    SW = 0b010
    SD = 0b011
    
class BR_F3(Enum):
    BEQ = 0b000
    BNE = 0b001
    BLT = 0b100
    BGE = 0b101
    BLTU = 0b110
    BGEU = 0b111
    
class CSR_F3(Enum):
    ECALL = EBREAK = 0b000
    CSRRW = 0b001
    CSRRS = 0b010
    CSRRC = 0b011
    CSRRWI = 0b101
    CSRRSI = 0b110
    CSRRCI = 0b111
    

class Ext(Enum):
    A = 1<<0   # Atomic
    B = 1<<1   # B ext
    C = 1<<2   # Compressed
    D = 1<<3   # Double-precision float
    E = 1<<4   # RV32E/64E base ISA
    F = 1<<5   # Single-preceision float
    G = 1<<6   # Reserved
    H = 1<<7   # Hypervisor extension
    I = 1<<8   # RV32/64I base ISA
    J = 1<<9   # Reserved 
    K = 1<<10  # Reserved 
    L = 1<<11  # Reserved 
    M = 1<<12  # Int Mul/Div
    N = 1<<13  # -- User interrupt
    O = 1<<14  # Reserved 
    P = 1<<15  # packed SIMD ext
    Q = 1<<16  # Quad-precision float
    R = 1<<17  # Reserved 
    S = 1<<18  # Supervisor Mode
    T = 1<<19  # Reserved
    U = 1<<20  # User Mode
    V = 1<<21  # Vector Ext
    W = 1<<22  # Reserved
    X = 1<<23  # non-std extension
    Y = 1<<24  # Reserved
    Z = 1<<25  # Reserved

class Priviledge(Enum):
    U = 0b00
    S = 0b01
    H = 0b10
    M = 0b11


class Mode(Enum):
    U = 0
    S = 1
    H = 2
    M = 3

class ExceptionCode(Enum):
    InstructionAddressMisaligned = 0
    InstructionAccessFault = 1
    IllegalInstruction = 2
    Breakpoint = 3
    LoadAddressMisaligned = 4
    LoadAccessFault = 5
    StoreAmoAddressMisaligned = 6
    StoreAmoAccessFault = 7
    Ucall = 8
    Scall = 9
    Mcall = 11
    InstructionPageFault = 12
    LoadPageFault = 13
    StoreAmoPageFault = 15
    DoubleTrap = 16
    SoftwareSheck = 18
    HardwareError = 19

CSR_M = {    
    "mvendorid":(0xf11, 32, {"bank": [31, 7],"Offset": [6, 0]}),
    "marchid":  (0xf12, 64, {"Architecture_ID": [63, 0]}),
    "mimpid":   (0xf13, 64, {"Implementation": [63, 0]}),
    "mhartid":  (0xf14, 64, {"Hart_ID": [63, 0]}),
    "mconfigptr": (0xf15, 64, {}),
    "mstatus":  (0x300, 64, {
            "UIE": [0], "SIE": [1], "MIE": [3], "UPIE": [4], "SPIE": [5], 
            "UBE" : [6], "MPIE": [7], "SPP": [8],"VS" : [10, 9], "MPP": [12, 11], 
            "FS": [14, 13],"XS": [16, 15], "MPRV": [17], "SUM": [18], "MXR": [19],
            "TVM": [20], "TW": [21], "TSR": [22], "SPLEP": [23], "SDT": [24], 
            "UXL": [33, 32],"SXL": [35, 34], "SBE": [63], "MBE": [37], 
            "GVA": [38], "MPV": [39], "MPLEP": [41], "MDT": [42], "SD": [63]
            }),
    "misa":     (0x301, 64, {"MXLEN": [63, 62], "Extensions": [25, 0]}),
    "medeleg":  (0x302, 64, {}),
    "mideleg":  (0x303, 64, {}),
    "mie":      (0x304, 64, {"SSIE": [1], "MSIE": [3], "STIE": [5], "MTIE": [7],
                        "SEIE": [9], "MEIE": [11], "LCOFIE": [13]}),
    "mtvec":    (0x305, 64, {"BASE": [63, 2], "MODE": [1, 0]}),
    # mcountern
    "mscratch": (0x340, 64, {}),
    "mepc":     (0x341, 64, {}),
    "mcause":   (0x342, 64, {"INT":[63], "CODE": [62, 0]}),
    "mtval":    (0x343, 64, {}),
    "mip":      (0x344, 64, {"SSIP": [1], "MSIP": [3], "STIP": [5], "MTIP": [7],
                        "SEIP": [9], "MEIP": [11], "LCOFIP": [13]}),
    
    # mtinst
    # mtval2
    
    "pmpcfg0":  (0x3a0, 64, {}),
    "pmpaddr0": (0x3B0, 64, {}),
    
    "mnstatus": (0x744, 64, {}),
    
    "mcycle":   (0xb00, 64, {}), 
    "minstret": (0xb02, 64, {}),
    
    # "mtime":    (0x000, 64, {}),
    # "mtimecmp": (0x000, 64, {}),
    
}

CSR_S = {
    "satp":     (0x180, 64, {}), 
    "stvec":    (0x105, 64, {}), 
    "scountern":(0x106, 64, {}), 
}

CSR_U = {
    "cycle":    (0xc00, 64, {}), 
    
}
 
# CSR_U = {
#     0x000: "ustatus",
#     0x004: "uie",
#     0x005: "utvec",
#     0x040: "uscratch",
#     0x041: "uepc",
#     0x042: "ucause",
#     0x043: "utval",
#     0x044: "uip"
# }

# CSR_S = {
#     0x100: "sstatus",
#     0x102: "sedeleg",
#     0x103: "sideleg",
#     0x104: "sie",
#     0x105: "stvec",
#     0x106: "scounteren",
#     0x140: "sscratch",
#     0x141: "sepc",
#     0x142: "scause",
#     0x143: "stval",
#     0x144: "sip",
#     0x180: "satp",
#     0xDA0: "scountovf",
#     0x5A8: "scontext"
# }

# CSR_H = {
#     0x200: "vsstatus",
#     0x204: "vsie",
#     0x205: "vstvec",
#     0x240: "vsscratch",
#     0x241: "vsepc",
#     0x242: "vscause",
#     0x243: "vstval",
#     0x244: "vsip",
#     0x280: "vsatp",

#     0x600: "hstatus",
#     0x602: "hedeleg",
#     0x603: "hideleg",
#     0x604: "hie",
#     0x605: "htvec",
#     0x640: "hscratch",
#     0x641: "hepc",
#     0x642: "hcause",
#     0x643: "htval",
#     0x644: "hip",
#     0x645: "hvip",
#     0x646: "htinst",
#     0x64A: "henvcfg",
#     0x64B: "henvcfgh",  # RV32 only
#     0x680: "hgatp"
# }

# CSR_M = {
#     0xF11: "mvendorid",
#     0xF12: "marchid",
#     0xF13: "mimpid",
#     0xF14: "mhartid",
#     # 0xF14: "mconfigptr",
    
#     0x300: "mstatus",
#     0x301: "misa",
#     0x302: "medeleg",
#     0x303: "mideleg",
#     0x304: "mie",
#     0x305: "mtvec",
#     # 0x306: "mcounteren",
#     # 0x310: "mstatush",   # RV32 only
#     # 0x312: "mdelegh",   # RV32 only
    
#     0x340: "mscratch",
#     0x341: "mepc",
#     0x342: "mcause",
#     0x343: "mtval",
#     0x344: "mip",
#     # 0x345: "mtinst",
#     # 0x346: "mtval2",
    
#     # 0x3A0: "menvcfg",
#     # 0x3A1: "menvcfgh",     # RV32 only
#     # 0x747: "mseccfg",
#     # 0x757: "mseccfgh",     # RV32 only
# }


# CSR_DEBUG = {
#     0x7A0: "tselect",
#     0x7A1: "tdata1",
#     0x7A2: "tdata2",
#     0x7A3: "tdata3",
#     0x7B0: "dcsr",
#     0x7B1: "dpc",
#     0x7B2: "dscratch0",
#     0x7B3: "dscratch1"
# }


# # performance Counters / Timer 
# CSR_CTR_TMR = {
#     0xC00: "cycle",
#     0xC01: "time",
#     0xC02: "instret",
#     **{0xC03 + i: f"hpmcounter{i+3}" for i in range(29)},   # 0xC03 - 0xC1F

#     0xC80: "cycleh",       # RV32 only
#     0xC81: "timeh",        # RV32 only
#     0xC82: "instreth",     # RV32 only
#     **{0xC83 + i: f"hpmcounter{i+3}h" for i in range(29)}   # 0xC83 - 0xC9F (RV32 only)
# }


# CSR_F = {
#     0x001: "fflags",
#     0x002: "frm",
#     0x003: "fcsr"
# }