from cpu_enums import FP_OP_F5, FP_ROUND_MODE
from struct import unpack, pack
from utils import *
from typing import List, Union

def to_f64(num):
    mask = (1<<64)-1
    num = num&mask
    return unpack('>d', bytearray.fromhex(f"{num:016x}"))[0]

def to_f32(num):
    mask = (1<<32)-1
    num = num&mask
    return unpack('>f', bytearray.fromhex(f"{num:08x}"))[0]

def to_f16(num):
    mask = (1<<16)-1
    num = num&mask
    return unpack('>e', bytearray.fromhex(f"{num:04x}"))[0]


def pack_f16(in_f:float):
    try:
        return unpack(">H", pack(">e", in_f))[0]    
    except OverflowError:
        return 0x7E00
    
def pack_f32(in_f:float):
    try:
        return unpack(">I", pack(">f", in_f))[0]
    except OverflowError:
        # Return IEEE 754 quiet NaN (32-bit)
        return 0x7FC00000
            
def pack_f64(in_f:float):
    try:
        return unpack(">Q", pack(">d", in_f))[0]
    except OverflowError:
        return 0x7FF8000000000000
 
def pack_fp(in_f:float, width=32):
    if width==16:
        return pack_f16(in_f)
    elif width==32:
        return pack_f32(in_f)
    elif width==64:
        return pack_f64(in_f)
    else:
        return 0
    
def find_msb(num):
    bin_num = bin(num)[2:]
    return len(bin_num) - 1 - bin_num.index('1')

n = 0x4060_0000 # 3.5


# print(find_msb(n))
# print(n>>find_msb(n))
# print(to_f32(0x4060_0000))

# 0 00000000 

HF_block = {"S": [15], "E":[14,10], "M":[9,0] } # half
SF_block = {"S": [31], "E":[30,23], "M":[22,0]} # single
DF_block = {"S": [63], "E":[62,52], "M":[51,0]} # double

FP_blocks = {
    16: {"S": [15], "E":[14,10], "M":[9 ,0] },
    32: {"S": [31], "E":[30,23], "M":[22,0]},
    64: {"S": [63], "E":[62,52], "M":[51,0]}
}

HF_block_op = {"S": [19], "E":[18,14], "UM":[14], "M":[13,3], "GRS":[2,0] , "FM": [14, 0]} # half
SF_block_op = {"S": [35], "E":[34,27], "UM":[26], "M":[25,3], "GRS":[2,0] , "FM": [26, 0]} # single
DF_block_op = {"S": [67], "E":[66,56], "UM":[55], "M":[54,3], "GRS":[2,0] , "FM": [55, 0]} # double

FP_blocks_op = {
    16: {"S": [20], "E":[19,16], "UM":[15,14], "M":[13,3], "GRS":[2,0] , "FM": [15, 0]}, # half
    32: {"S": [36], "E":[35,28], "UM":[27,26], "M":[25,3], "GRS":[2,0] , "FM": [27, 0]}, # single
    64: {"S": [68], "E":[67,57], "UM":[56,55], "M":[54,3], "GRS":[2,0] , "FM": [56, 0]} # double
}

def to_op_fp_reg(in_f: Union[BlockReg, float], width=32):
    assert width in [16, 32, 64], "non standard float width"
    
    if type(in_f)==float or type(in_f)==int:
        in_f = float(in_f)
        pack_fp = pack_f64(in_f) if width==64 else (pack_f16(in_f) if width==16 else pack_f32(in_f))
        return to_op_fp_reg(BlockReg(width, pack_fp, FP_blocks[width]), width)
    elif isinstance(in_f, BlockReg):
        s = in_f.nbits
        if s in [16, 32, 64]:
            block_sel = FP_blocks_op[s]
            new_f = BlockReg(s+5, 0, block_sel)
            new_f.S = in_f.S
            new_f.E = in_f.E
            new_f.M = in_f.M
            new_f.UM = 0 if in_f.E == 0 else 1     
            return new_f
        
        elif s-5 in [16, 32, 64]:
            return in_f
        else:
            print("block reg not good width")
            return None
    else:
        print("no fp")
        return None

def pack_to_fp_reg(fp_op_reg: BlockReg):
    size = fp_op_reg.nbits-5
    assert size in [16, 32, 64], "non standard float size"
    out_fp = BlockReg(size, 0, FP_blocks[size])
    
    out_fp.M = fp_op_reg.M
    out_fp.E = fp_op_reg.E
    out_fp.S = fp_op_reg.S
    
    return out_fp

def reg_to_float(fp_reg: BlockReg):
    
    size = fp_reg.nbits
    
    if size==64:
        return to_f64(fp_reg[:])
    elif size==32:
        return to_f32(fp_reg[:])
    elif size==16:
        return to_f16(fp_reg[:])
    else:
        return None

def normalize_fp(op_fp: BlockReg):
    
    len_fm = op_fp._blocks['FM'].nbits-1
    mantissa_diff = find_msb(op_fp.FM)-len_fm
    if mantissa_diff>0:
        op_fp.FM = op_fp.FM>>abs(mantissa_diff)
        op_fp.E+=abs(mantissa_diff)
    elif mantissa_diff<0:
        op_fp.FM = op_fp.FM<<abs(mantissa_diff)
        op_fp.E -= abs(mantissa_diff)
    
def full_bin(num, l=32):
    bin_str = bin(num)[2:]
    return '0'*(l-len(bin_str))+bin_str


def pretty_print_float(
            in_f: Union[Reg, BlockReg, float], 
            size=32, 
            show_op=True, 
            show_header=False,
            return_to_str=False,
    ):
    
    op_fp = to_op_fp_reg(in_f, size)
    
    blk = FP_blocks_op[op_fp.nbits-5]
    blk_sz = {k: blk[k][0]-blk[k][1]+1 if len(blk[k])>1 else 1 for k in blk.keys()}
    # print(blk_sz)
    if show_op:
        head_str = [
            "S", 
            f"{'Exp':<{blk_sz['E']+1}}"
            f"{'  Mantissa':<{blk_sz['M']+2}}",
            "GRS",
            ]

        fp_str = [
            str(op_fp.S).replace("1", "\033[33m1\033[0m"),
            full_bin(op_fp.E, blk_sz['E']).replace("1", "\033[34m1\033[0m"),
            (full_bin(op_fp.UM, blk_sz['UM'])+"."+full_bin(op_fp.M, blk_sz['M'])).replace("1", "\033[31m1\033[0m"),
            full_bin(op_fp.GRS, 3).replace("1", "\033[32m1\033[0m"),
            f"{reg_to_float(pack_to_fp_reg(op_fp))}"
        ]
    else:
        head_str = [
            "S", 
            f"{'Exp':<{blk_sz['E']+1}}"
            f"{'Mantissa':<{blk_sz['M']+1}}",
            ]

        fp_str = [
            str(op_fp.S).replace("1", "\033[33m1\033[0m"),
            full_bin(op_fp.E, blk_sz['E']).replace("1", "\033[34m1\033[0m"),
            full_bin(op_fp.M, blk_sz['M']).replace("1", "\033[31m1\033[0m"),
        ]
    
    
    header_str = " ".join(head_str)    
    fp_str = " ".join(fp_str)
    
    if return_to_str:
        return header_str+'\n'+fp_str
    # fp_str = fp_str.replace("1", "\033[31m1\033[0m")
    if show_header:
        print(" ".join(head_str))
    
    print(fp_str)



class fpReg(BlockReg):
    
    def __init__(self, num=0., width=32):
        assert width in [16, 32, 64]
        fp = to_op_fp_reg(num, width)
        super().__init__(width+5, fp[:], FP_blocks_op[width])
        self.fp_width=width

    def shift_mantissa(self, shmnt:int):
        if shmnt>0: 
            sticky = 1 if self[max(shmnt, shmnt-3):0]>0 else 0 # check if any 1 go after sticky bit 
            self.FM = self.FM>>abs(shmnt)
            self.GRS = self.GRS|sticky 
            self.E+=abs(shmnt)
        elif shmnt<0:
            self.FM = self.FM<<abs(shmnt)
            self.E -= abs(shmnt)
    
    def __str__(self):
        return pretty_print_float(self, return_to_str=True)
    

def FPU(op1, op2, f5:FP_OP_F5, op3=0, rnd=FP_ROUND_MODE.RNE, width=32):
    
    # opf1 = BlockReg(32, op1, SF_block)
    # opf2 = BlockReg(32, op2, SF_block)
    
    opf1 = to_op_fp_reg(op1, size = width)
    opf2 = to_op_fp_reg(op2, size = width)
    
    pretty_print_float(opf1, show_header=1)
    print(f5)
    exp_diff = opf1.E-opf2.E
    
    if exp_diff>0:
        opf2.FM = opf2.FM>>exp_diff
        opf2.E+=exp_diff
    elif exp_diff<0:
        opf1.FM = opf1.FM>>abs(exp_diff)
        opf1.E += abs(exp_diff)
    
    opf3 = to_op_fp_reg(0, size=width)
    
    if f5==FP_OP_F5.FADD:
        if opf1.S==opf2.S: # equal sign
            opf3.S = opf1.S
            opf3.E = opf1.E
            opf3.FM = opf1.FM+opf2.FM
        else:
            opf3.S = opf1.S^opf2.S
            opf3.E = opf1.E
            opf3.FM = opf1.FM-opf2.FM
    elif f5==FP_OP_F5.FSUB:
        if opf1.S==opf2.S: # equal sign
            opf3.S = opf1.S
            opf3.E = opf1.E
            opf3.FM = opf1.FM-opf2.FM
        else:
            opf3.S = opf1.S^opf2.S
            opf3.E = opf1.E
            opf3.FM = opf1.FM+opf2.FM
    else:
        print("No op")
        return 0
    pretty_print_float(opf3)
    
    # normalize result
    len_fm = opf3._blocks['FM'].nbits-1
    mantissa_diff = find_msb(opf3.FM)-len_fm
    if mantissa_diff>0:
        opf3.FM = opf3.FM>>abs(mantissa_diff)
        opf3.E+=abs(mantissa_diff)
    elif mantissa_diff<0:
        opf3.FM = opf3.FM<<abs(mantissa_diff)
        opf3.E -= abs(mantissa_diff)
    
    # ROUNDING
    if rnd==FP_ROUND_MODE.RNE:
        if opf3.GRS>0:
            opf3.M+=1
    else:
        print("No Rounding")
    
    pretty_print_float(opf3)
    
    opf1 = to_op_fp_reg(op1, size = width)
    opf2 = to_op_fp_reg(op2, size = width)
    
    return pack_to_fp_reg(opf1), pack_to_fp_reg(opf2), pack_to_fp_reg(opf3)


fp1 = fpReg(1234.0, 32)
# fp1.M = 0b101
print(fp1)
# fp1.shift_mantissa(6)
# print(fp1)
# fp1.shift_mantissa(-1)
# print(fp1)
# fp1.shift_mantissa(1)
# print(fp1)
# fp1.shift_mantissa(1)
# print(fp1)

# TEST_FP_OP2_S( 2,  fadd.s, 0,                3.5,        2.5,        1.0 );
# TEST_FP_OP2_S( 3,  fadd.s, 1,              -1234,    -1235.1,        1.1 );
# TEST_FP_OP2_S( 4,  fadd.s, 1,         3.14159265, 3.14159265, 0.00000001 );

# TEST_FP_OP2_S( 5,  fsub.s, 0,                1.5,        2.5,        1.0 );
# TEST_FP_OP2_S( 6,  fsub.s, 1,              -1234,    -1235.1,       -1.1 );
# TEST_FP_OP2_S( 7,  fsub.s, 1,         3.14159265, 3.14159265, 0.00000001 );

# TEST_FP_OP2_S( 8,  fmul.s, 0,                2.5,        2.5,        1.0 );
# TEST_FP_OP2_S( 9,  fmul.s, 1,            1358.61,    -1235.1,       -1.1 );
# TEST_FP_OP2_S(10,  fmul.s, 1,      3.14159265e-8, 3.14159265, 0.00000001 );
  
# FPU(30.25, 4.2646728, F_OP_F5.FSUB, width=32)

# res = FPU(2.5, 1, FP_OP_F5.FADD, width=32)
# res = FPU(-1235.1, 1.1, f5=FP_OP_F5.FADD, width=32)
# res = FPU(3.14159265, 0.00000001, f5=FP_OP_F5.FADD, width=32)

# res = FPU(2.5, 1, FP_OP_F5.FSUB, width=32)
# res = FPU(-1235.1, -1.1, f5=FP_OP_F5.FSUB, width=32)
# res = FPU(3.14159265, 0.00000001, f5=FP_OP_F5.FSUB, width=32)

# try:
#     print(hex(res[0].all), hex(res[1].all), "=", hex(res[2].all))
# except:
#     print("NULL")
# print(hex(pack_f32(1234.)))

# print(to_f32(0xc49a6333))