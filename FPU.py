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
    try:
        return len(bin_num) - 1 - bin_num.index('1')
    except ValueError:
        return -1
    

# n = 0x4060_0000 # 3.5


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
    16: {"S": [20], "E":[19,16], "UM":[15,14], "M":[13,3], "GRS":[2,0] , "FM": [15, 0], "G":[2], "R":[1], "ST":[0]}, # half
    32: {"S": [36], "E":[35,28], "UM":[27,26], "M":[25,3], "GRS":[2,0] , "FM": [27, 0], "G":[2], "R":[1], "ST":[0]}, # single
    64: {"S": [68], "E":[67,57], "UM":[56,55], "M":[54,3], "GRS":[2,0] , "FM": [56, 0], "G":[2], "R":[1], "ST":[0]} # double
}

def to_op_fp_reg(in_f: Union[BlockReg, float], width=32):
    assert width in [16, 32, 64], "non standard float width"
    
    if type(in_f)==float:
        in_f = float(in_f)
        pack_fp = pack_f64(in_f) if width==64 else (pack_f16(in_f) if width==16 else pack_f32(in_f))
        return to_op_fp_reg(BlockReg(width, pack_fp, FP_blocks[width]), width)
    elif type(in_f)==int:
        return to_op_fp_reg(BlockReg(width, in_f, FP_blocks[width]), width)
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
            f"{'  Mantissa':<{blk_sz['M']+3}}",
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
            f"{'Mantissa':<{blk_sz['M']+3}}",
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
        
        self.mask_exp = (1<<(self._blocks['E'].nbits+1))-1
        self.quiet_bit = 1<<self._blocks['M'].nbits
        self.mask_payload = self.quiet_bit-1

    @classmethod
    def from_op_reg(cls, blk_reg: BlockReg):
        width = blk_reg.nbits-5
        obj = cls(0, width)
        obj.S = blk_reg.S
        obj.E = blk_reg.E
        obj.FM = blk_reg.FM
        return obj

    def to_Inf(self, neg = False):
        self.reg=0
        self.S = 1 if neg else 0
        self.E = self.mask_exp
        self.M = 0
        self.UM = 1
    
    def to_NaN(self):
        self.reg=0
        self.S = 0
        self.E = self.mask_exp
        self.M = 1<<self._blocks['M'].nbits
        self.UM = 1
    
    def is_qNaN(self) -> bool:
        return self.M&self.quiet_bit==1
    
    def is_inf(self) -> bool:
        if self.E==self.mask_exp and self.M==0:
            return True
        else:
            return False
    
    def is_inf(self) -> bool:
        if self.E==self.mask_exp and self.M==0:
            return True
        else:
            return False
    
    def is_nan(self) -> bool:
        mask_exp = (1<<(self._blocks['E'].nbits+1))-1
        if self.E==mask_exp and self.M!=0:
            return True
        else:
            return False
    
    def is_neg(self)->bool:
        return self.S==1
    
    def is_zero(self)->bool:
        return (self.E==0) and (self.M==0)
    
    
    def opposite(self):
        self.S = 0 if self.S==1 else 1
    
    def shift_mantissa(self, shmnt:int):
        """ positive shmnt means >>"""
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
    

def FPU(op1, op2, f5:FP_OP_F5, rnd=FP_ROUND_MODE.RNE, width=32):
    
    
    fflags = {
        "NV": 0, # Invalid operations
        "DZ": 0, # Division by zero
        "OF": 0, # Overflow
        "UF": 0, # Underflow
        "NX": 0, # Inexact
    }
    
    blk_dict = FP_blocks_op[width]
    
    opf1 = to_op_fp_reg(op1, width = width)
    opf2 = to_op_fp_reg(op2, width = width)
    
    opf1 = fpReg.from_op_reg(opf1)
    opf2 = fpReg.from_op_reg(opf2)
    
    
    pretty_print_float(opf1, show_header=1)
    pretty_print_float(opf2, show_header=0)
    
    exp_diff = opf1.E-opf2.E
    
    if f5==FP_OP_F5.FADD or f5==FP_OP_F5.FSUB: 
        if exp_diff>0:
            opf2.FM = opf2.FM>>exp_diff
            opf2.E+=exp_diff
        elif exp_diff<0:
            opf1.FM = opf1.FM>>abs(exp_diff)
            opf1.E += abs(exp_diff)
    
    opf3 = to_op_fp_reg(0, width=width)
    opf3 = fpReg.from_op_reg(opf3)
    print(f"--- op --- {f5.name[1:]}")
    # if f5==FP_OP_F5.FSUB:
    #     if opf2.E not in [0, 255]: # if not inf of nan
    
    
    if opf1.is_nan() or opf1.is_nan():
        opf3.to_NaN()
    else:
        if f5==FP_OP_F5.FADD:
            if opf1.S==opf2.S: # equal sign
                if opf2.is_inf() and opf1.is_inf():
                    opf3.to_Inf(neg=opf1.S)
                else:
                    opf3.S = opf1.S
                    opf3.E = opf1.E
                    opf3.FM = opf1.FM+opf2.FM
            else:
                if opf2.is_inf() and opf1.is_inf():
                    opf3.to_NaN()
                else:
                    opf3.S = opf1.S^opf2.S
                    opf3.E = opf1.E
                    opf3.FM = opf1.FM-opf2.FM
                    
        elif f5==FP_OP_F5.FSUB:
            
            if opf1.S==opf2.S: # equal sign
                if opf2.is_inf() and opf1.is_inf():
                    opf3.to_NaN()
                else:
                    opf3.S = opf1.S
                    opf3.E = opf1.E
                    opf3.FM = opf1.FM-opf2.FM
            else:
                if opf2.is_inf() and opf1.is_inf():
                    opf3.to_Inf(neg=(opf1.S&(~opf2.S)))
                else:
                    opf3.S = opf1.S^opf2.S
                    opf3.E = opf1.E
                    opf3.FM = opf1.FM+opf2.FM
                
                
        elif f5==FP_OP_F5.FMUL:
            # print("fmul")
            
            opf3.S = opf1.S^opf2.S
            
            if opf1.is_inf() and opf2.is_inf():
                opf3.to_Inf(opf3.S)
            elif (opf1.is_inf() and opf2.is_zero()) or \
                    (opf1.is_zero() and opf2.is_inf()):
                opf3.to_NaN()
            else:   
                m_size = opf3._blocks['M'].nbits+2
                mask = (1<<((m_size*2)))-1 # create a mask to double size of mantissa
                new_m = (opf1.FM>>3)*(opf2.FM>>3) # remove GRS from multiplication
        
                size_FM = blk_dict['FM'][0]-blk_dict['FM'][1]
                mult_norm_cond = (opf1.FM>>(size_FM-1)) and (opf2.FM>>(size_FM-1))

                new_m = new_m & mask
                
                opf3.FM = new_m>>(m_size-3)
                opf3.E = opf1.E+opf2.E-127+ (1 if mult_norm_cond else 0)

        else:
            print("No op")
            return 0


    # normalize result
    len_fm = opf3._blocks['FM'].nbits-1
    mantissa_diff = find_msb(opf3.FM)-len_fm
    if mantissa_diff>0:
        opf3.FM = opf3.FM>>abs(mantissa_diff)
        opf3.E+=abs(mantissa_diff)
    elif mantissa_diff<0:
        opf3.FM = opf3.FM<<abs(mantissa_diff)
        opf3.E -= abs(mantissa_diff)
    print("res->:", end ='') 
    pretty_print_float(opf3)
    
    # -------------------------- ROUNDING
    lsb = opf3.M & 0b1
    G = opf3.G
    R = opf3.R
    S = opf3.ST
    sign = opf3.S
    increment = False
    
    if rnd==FP_ROUND_MODE.RNE:
        if G and (R or S or lsb):
            increment = True
    elif rnd==FP_ROUND_MODE.RTZ:
        increment = False
    elif rnd==FP_ROUND_MODE.RDN:
        if sign == 1 and (G or R or S):
            increment = True
    elif rnd==FP_ROUND_MODE.RUP:
        if sign == 0 and (G or R or S):
            increment = True
    elif rnd==FP_ROUND_MODE.RMM:
        if G:
            increment = True
        
    if increment:
        retained_mantissa += 1
        if opf3.UM>1:
            opf3.shift_mantissa(1)
    
    ## --------------------set flags
    if opf3.GRS>0:
        fflags['NX'] = 1
    
    if opf3.is_nan():
        fflags['NV'] = 1
        
    print(fflags)
    print("--- ==== ---")
    opf1 = to_op_fp_reg(op1, width = width)
    opf2 = to_op_fp_reg(op2, width = width)
    
    return pack_to_fp_reg(opf1), pack_to_fp_reg(opf2), pack_to_fp_reg(opf3)


# TEST_FP_OP2_S( 2,  fadd.s, 0,                3.5,        2.5,        1.0 );
# TEST_FP_OP2_S( 3,  fadd.s, 1,              -1234,    -1235.1,        1.1 );
# TEST_FP_OP2_S( 4,  fadd.s, 1,         3.14159265, 3.14159265, 0.00000001 );

# TEST_FP_OP2_S( 5,  fsub.s, 0,                1.5,        2.5,        1.0 );
# TEST_FP_OP2_S( 6,  fsub.s, 1,              -1234,    -1235.1,       -1.1 );
# TEST_FP_OP2_S( 7,  fsub.s, 1,         3.14159265, 3.14159265, 0.00000001 );

# TEST_FP_OP2_S( 8,  fmul.s, 0,                2.5,        2.5,        1.0 );
# TEST_FP_OP2_S( 9,  fmul.s, 1,            1358.61,    -1235.1,       -1.1 );
# TEST_FP_OP2_S(10,  fmul.s, 1,      3.14159265e-8, 3.14159265, 0.00000001 );
  
# TEST_FP_OP2_S_HEX(11,  fsub.s, 0x10, qNaNf, Inff, Inff);
# FPU(30.25, 4.2646728, F_OP_F5.FSUB, width=32)


# res = FPU(2.5, 1.0, f5=FP_OP_F5.FMUL, width=32)
# res = FPU(-1235.1, -1.1, f5=FP_OP_F5.FMUL, width=32)
# res = FPU(3.14159265, 0.00000001, f5=FP_OP_F5.FMUL, width=32)

# res = FPU(2.5, 1, FP_OP_F5.FADD, width=32)
# res = FPU(-1235.1, 1.1, f5=FP_OP_F5.FADD, width=32)
# res = FPU(3.14159265, 0.00000001, f5=FP_OP_F5.FADD, width=32)


# res = FPU(2.5, 1.0, FP_OP_F5.FSUB, width=32)
# res = FPU(-1235.1, -1.1, f5=FP_OP_F5.FSUB, width=32)
# res = FPU(3.14159265, 0.00000001, f5=FP_OP_F5.FSUB, width=32)


# Inf - (+Inf) -> NaN
# res = FPU(0x7f800000, 0x7f800000, f5=FP_OP_F5.FSUB, width=32)
# # Inf - (-Inf) -> +inf
# res = FPU(0x7f800000, 0xff800000, f5=FP_OP_F5.FSUB, width=32)
# # (-Inf) - (+Inf) -> -inf
# res = FPU(0xff800000, 0x7f800000, f5=FP_OP_F5.FSUB, width=32)
# # (-Inf) - (-Inf) -> NaN
# res = FPU(0xff800000, 0xff800000, f5=FP_OP_F5.FSUB, width=32)

# Inf + (+Inf) -> +Inf
# res = FPU(0x7f800000, 0x7f800000, f5=FP_OP_F5.FADD, width=32)
# # Inf + (-Inf) -> Nan
# res = FPU(0x7f800000, 0xff800000, f5=FP_OP_F5.FADD, width=32)
# # (-Inf) + (+Inf) -> Nan
# res = FPU(0xff800000, 0x7f800000, f5=FP_OP_F5.FADD, width=32)
# # (-Inf) + (-Inf) -> -Inf
# res = FPU(0xff800000, 0xff800000, f5=FP_OP_F5.FADD, width=32)


# Inf * (+Inf) -> +Inf
res = FPU(0x7f800000, 0x7f800000, f5=FP_OP_F5.FMUL, width=32)
# Inf * (-Inf) -> -Inf
res = FPU(0x7f800000, 0xff800000, f5=FP_OP_F5.FMUL, width=32)
# (-Inf) * (+Inf) -> -Inf
res = FPU(0xff800000, 0x7f800000, f5=FP_OP_F5.FMUL, width=32)
# (-Inf) * (-Inf) -> +Inf
res = FPU(0xff800000, 0xff800000, f5=FP_OP_F5.FMUL, width=32)

# Inf * 0 -> NaN
res = FPU(0x7f800000, 0.0, f5=FP_OP_F5.FMUL, width=32)
# (-Inf) * 0 -> NaN
res = FPU(0xff800000, 0.0, f5=FP_OP_F5.FMUL, width=32)




try:
    print(hex(res[0].all), hex(res[1].all), "=", hex(res[2].all))
except:
    print("NULL")

# pretty_print_float(3.14159265e-8)
# print(hex(pack_f32(1234.)))

# print(to_f32(0xc49a6333))