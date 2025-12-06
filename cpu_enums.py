from enum import Enum


class Ops(Enum):

    ILLEGAL     = 0b00_000_00
    LOAD        = 0b00_000_11
    STORE       = 0b01_000_11
    FMADD       = 0b10_000_11
    BRANCH      = 0b11_000_11
    LOAD_FP     = 0b00_001_11
    STORE_FP    = 0b01_001_11
    FMSUB       = 0b10_001_11
    JALR        = 0b11_001_11
    custom0     = 0b00_010_11
    custom1     = 0b01_010_11
    FMNSUB      = 0b10_010_11
    MISC_MEM    = 0b00_011_11
    AMO         = 0b01_011_11
    FNMADD      = 0b10_011_11
    JAL         = 0b11_011_11
    
    OP_IMM      = 0b00_100_11
    OP          = 0b01_100_11
    
    OP_FP       = 0b10_100_11
    SYSTEM      = 0b11_100_11
    AUIPC       = 0b00_101_11
    LUI         = 0b01_101_11
    OP_V        = 0b10_101_11
    OP_VE       = 0b11_101_11
    
    OP_IMM_32   = 0b00_110_11
    OP_32       = 0b01_110_11
    custom2     = 0b10_110_11
    custom3     = 0b11_110_11


class MISC_ALU_OP(Enum):
    SUB  = 0b0_00
    XOR  = 0b0_01
    OR   = 0b0_10
    AND  = 0b0_11
    SUBW = 0b1_00
    ADDW = 0b1_01
    RES1 = 0b1_10
    RES2 = 0b1_11
    
class Ops_C(Enum):
    ADDI4SPN = 0b000_00
    ADDI = 0b000_01
    SLLI = 0b000_10
    
    FLD = 0b001_00
    ADDIW = 0b001_01
    FLDSP = 0b001_10

    LW = 0b010_00
    LI = 0b010_01
    LWSP = 0b010_10
    
    LD = 0b011_00
    LUI_ADDI16SP = 0b011_01
    LDSP = 0b011_10
    
    reserved = 0b100_00
    MISC_ALU = 0b100_01
    JAL_JALR_MV_ADD = 0b100_10
    
    FSD = 0b101_00
    J = 0b101_01
    FSDSP = 0b101_10
    
    SW = 0b110_00
    BEQZ = 0b110_01
    SWSP = 0b110_10

    SD = 0b111_00
    BNEZ = 0b111_01
    SDSP = 0b111_10
    
class SYS_F12(Enum):
    ECALL = 0x000
    EBREAK = 0x000
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

class FP_ROUND_MODE(Enum):
    RNE = 0b000
    RTZ = 0b001
    RDN = 0b010
    RUP = 0b011
    RMM = 0b100
    RES1 = 0b101
    RES2 = 0b110
    DYN = 0b111
    
class FP_OP_F5(Enum):
    FADD = 0b00000
    FSUB = 0b00001
    FMUL = 0b00010
    FDIV = 0b00011
    FSQRT = 0b01011
    FSGNJ = 0b00100
    FMINMAX = 0b00101
    FCMP = 0b10100
    CVT_TO_FP = 0b11000
    CVT_TO_INT = 0b11010
    FMVT_X_W = 0b11100
    FCLASS = 0b11100
    FMVT_W_X = 0b11110

class FP_CMP_F3(Enum):
    EQ = 0b010
    LT = 0b001
    LE = 0b000
    
class FP_MINMAX_F3(Enum):
    FMIN = 0b000
    FMAX = 0b001

class FP_CLASS(Enum):
    negInf      = 1<<0
    negNorNum   = 1<<1 # normal
    negSubNum   = 1<<2 # subnormal
    negZero     = 1<<3
    posZero     = 1<<4
    posSubNum   = 1<<5 # subnormal
    posNorNum   = 1<<6 # normal
    posInf      = 1<<7
    sNan        = 1<<8
    qNan        = 1<<9
    
class FP_SGNJ_F3(Enum):
    J  = 0b000
    JN = 0b001
    JX = 0b010

class FP_CVT_RS2(Enum):
    W  = 0b00000
    WU = 0b00001
    L  = 0b00010
    LU = 0b00011
    
class OP_MUL_F3(Enum):
    MUL =  0b000
    MULH = 0b001
    MULHSU = 0b010
    MULHU = 0b011
    DIV = 0b100
    DIVU = 0b101
    REM = 0b110
    REMU = 0b111
    
class LD_F3(Enum):
    LB = 0b000
    LH = 0b001
    LW = 0b010
    LWU = 0b110
    LBU = 0b100
    LHU = 0b101
    LD = 0b011

class ST_F3(Enum):
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
    CSRRW  = 0b001
    CSRRWI = 0b101
    CSRRS  = 0b010
    CSRRSI = 0b110
    CSRRC  = 0b011
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
    VScall = 10
    Mcall = 11
    InstructionPageFault = 12
    LoadPageFault = 13
    StoreAmoPageFault = 15
    DoubleTrap = 16
    SoftwareSheck = 18
    HardwareError = 19
    IntructionGuestPageFault = 20
    LoadGuestPageFault = 21
    VirtualIntruction = 22
    StoreAmoGuestPageFault = 23

CSR_M = {    
    "mvendorid":(0xf11, 32, {"bank": [31, 7],"Offset": [6, 0]}, {}, None),
    "marchid":  (0xf12, 64, {"Architecture_ID": [63, 0]}, {}, None),
    "mimpid":   (0xf13, 64, {"Implementation": [63, 0]}, {}, None),
    "mhartid":  (0xf14, 64, {"Hart_ID": [63, 0]}, {}, None),
    "mconfigptr": (0xf15, 64, {}, {}, None),
    "mstatus":  (0x300, 64, {
            "SIE": [1], "MIE": [3], "UPIE": [4], "SPIE": [5], 
            "UBE" : [6], "MPIE": [7], "SPP": [8],"VS" : [10, 9], "MPP": [12, 11], 
            "FS": [14, 13],"XS": [16, 15], "MPRV": [17], "SUM": [18], "MXR": [19],
            "TVM": [20], "TW": [21], "TSR": [22], "SPLEP": [23], "SDT": [24], 
            "UXL": [33, 32],"SXL": [35, 34], "SBE": [63], "MBE": [37], 
            "GVA": [38], "MPV": [39], "MPLEP": [41], "MDT": [42], "SD": [63]
            }, {
                "WPRI_1": [0], "WPRI_2":[2], "WPRI_3": [31,25], 
                "WPRI_4": [40], "WPRI_5": [62, 43]
            }, None),
    
    "misa":     (0x301, 64, {"MXL": [63, 62], "MXLEN": [61, 26], "Extensions": [25, 0]}, {}, None),
    "medeleg":  (0x302, 64, {
            "IAM" : [0], "IAF" : [1], "II" : [2], "B" : [2], "LAM" : [4], 
            "LAF" : [5], "SAM" : [6], "EU" : [8], "ES" : [9], "EVS" : [10], 
            "EM" : [11], "IPF" : [12], "LPF" : [13], "SPF" : [15], "IGPF" : [20],
            "LGPF" : [21], "VI" : [22], "SGPF" : [23], 
            }, {
            "WPRI_0" : [14], "WPRI_1" : [19, 16], "WPRI_2" : [63, 24],
            }, None),
    
    "mideleg":  (0x303, 64, {}, {}, None),
    "mie":      (0x304, 64, {
                "SSIE": [1], "VSSIE": [2], "MSIE": [3], "STIE": [5], 
                "VSTIE": [6], "MTIE": [7], "SEIE": [9], "VSEIE": [10],
                "MEIE": [11], "SGEIE": [12], "LCOFIE": [13]
                }, {
                    "WRPI_0":[0], "WRPI_1":[4], "WRPI_2":[8], "WRPI_3":[63,14],
                }, None),
    
    "mtvec":    (0x305, 64, {"BASE": [63, 2], "MODE": [1, 0]}, {}, None),
    "mcountern":(0x306, 32, {}, {}, None),
    "mcountinhibit":(0x320, 32, {
        **{f"HPM{i}": [i] for i in range(3, 32)}, "IR":[2], "CY":[0]},
                     {"WPRI_0":[1]}, None),
    
    "mscratch": (0x340, 64, {}, {}, None),
    "mepc":     (0x341, 64, {}, {}, None),
    "mcause":   (0x342, 64, {"INT":[63], "CODE": [62, 0]}, {}, None),
    "mtval":    (0x343, 64, {}, {}, None),
    # "mip":      (0x344, 64, {"SSIP": [1], "MSIP": [3], "STIP": [5], "MTIP": [7],
    #                     "SEIP": [9], "MEIP": [11], "LCOFIP": [13]}, {}, None),
    "mip":      (0x344, 64, {
                "SSIP": [1], "VSSIP": [2], "MSIP": [3], "STIP": [5], 
                "VSTIP": [6], "MTIP": [7], "SEIP": [9], "VSEIP": [10],
                "MEIP": [11], "SGEIP": [12], "LCOFIP": [13]
                }, {
                    "WRPI_0":[0], "WRPI_1":[4], "WRPI_2":[8], "WRPI_3":[63,14],
                }, None),
    # mtinst
    # mtval2
    
    "pmpcfg0":  (0x3a0, 64, {}, {}, None),
    "pmpaddr0": (0x3B0, 64, {}, {}, None),
    
    "mnstatus": (0x744, 64, {}, {}, None),
    
    "mcycle":   (0xb00, 64, {}, {}, None), 
    "minstret": (0xb02, 64, {}, {}, None),
    
    
    # "mtime":    (0x000, 64, {}, {}, None),
    # "mtimecmp": (0x000, 64, {}, {}, None),
    ##### DEBUG #######
    "tcontrol": (0x7a5, 64, {"MPTE" : [7], "MPE":[3]}, {}, None),
    "tselect": (0x7a0, 64, {}, {}, None),
    "tdata1": (0x7a1, 64, {}, {}, None),
    "tdata2": (0x7a2, 64, {}, {}, None),
    "tdata3": (0x7a3, 64, {}, {}, None),
# }

# CSR_S = {
    "sstatus":  (0x100, 64, { "SIE": [1], "SPIE": [5], "UBE" : [6], "SPP": [8],
            "VS" : [10, 9], "FS": [14, 13], "XS": [16, 15], "SUM": [18], 
            "MXR": [19],"SPLEP": [23], "SDT": [24], "UXL": [33, 32], "SD": [63]
            }, {
                "WPRI_1": [0], "WPRI_2": [4, 2], "WPRI_3": [7], "WPRI_4": [12, 11],
                "WPRI_5": [17], "WPRI_6": [22, 20], "WPRI_7": [31, 25], 
                "WPRI_8": [62, 34]
            }, "mstatus"),
    
    
    "satp":     (0x180, 64, {}, {}, None), 
    "sie":      (0x104, 64, {
                "SSIE": [1], "STIE": [5], "SEIE": [9], "LCOFIE": [13]
                }, {
                    "WRPI_0":[0], "WRPI_1":[4, 2], "WRPI_2":[8,6],
                    "WRPI_3":[12, 10], "WRPI_4":[63,14],
                }, 'mie'),
    
    "stvec":    (0x105, 64, {"BASE": [63, 2], "MODE": [1, 0]}, {}, None), 
    "scountern":(0x106, 64, {}, {}, None), 
    "sscratch": (0x140, 64, {}, {}, None),
    "sepc":     (0x141, 64, {}, {}, None),
    "scause":   (0x142, 64, {"INT":[63], "CODE": [62, 0]}, {}, None),
    
    "sip":      (0x344, 64, {
                "SSIP": [1], "STIP": [5], "SEIP": [9], "LCOFIP": [13]
                }, {
                    "WRPI_0":[0], "WRPI_1":[4, 2], "WRPI_2":[8,6],
                    "WRPI_3":[12, 10], "WRPI_4":[63,14],
                }, 'mip'),

    "cycle":    (0xc00, 64, {}, {}, "mcycle"), 
    "instret":  (0xc02, 64, {}, {}, "minstret"), 
    
    
    "fcsr":     (0x003, 32, {
                    "FRM": [7,5], "NV":[4], "DZ":[3],
                    "OF":[2], "UF":[1], "NX":[0],
                    "FFL": [4,0],
                }, {
                    #"WPRI_0": [31, 8]
                }, None),

    "frm":     (0x002, 32, {
                    "FRM": [2,0]
                }, {
                    #"WPRI_0": [31, 3]
                }, 'fcsr.FRM'),
    
    "fflags":     (0x001, 32, {
                    "NV":[4], "DZ":[3],
                    "OF":[2], "UF":[1], "NX":[1]
                }, {
                    #"WPRI_0": [31, 5]
                }, 'fcsr'),
}
