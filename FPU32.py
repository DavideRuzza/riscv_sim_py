from cpu_enums import FP_OP_F5, FP_ROUND_MODE
from struct import unpack, pack
from utils import *
from typing import List, Union
from math import sqrt
from colorama import Fore
import math
import numpy as np




def to_f64(num)->float:
    mask = (1<<64)-1
    num = num&mask
    return unpack('>d', bytearray.fromhex(f"{num:016x}"))[0]

def to_f32(num)->float:
    mask = (1<<32)-1
    num = num&mask
    return unpack('>f', bytearray.fromhex(f"{num:08x}"))[0]

def to_f16(num)->float:
    mask = (1<<16)-1
    num = num&mask
    return unpack('>e', bytearray.fromhex(f"{num:04x}"))[0]


def pack_f16(in_f:float)->int:
    try:
        return unpack(">H", pack(">e", in_f))[0]    
    except OverflowError:
        return 0x7E00
    
def pack_f32(in_f:float)->int:
    try:
        return unpack(">I", pack(">f", in_f))[0]
    except OverflowError:
        # Return IEEE 754 quiet NaN (32-bit)
        return 0x7FC00000
            
def pack_f64(in_f:float)->int:
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

CANONICAL_QNAN = 0x7FC00000  # RISC-V canonical quiet NaN
INT32_MIN = -2**31
INT32_MAX =  2**31 - 1
UINT32_MAX = 2**32 - 1

INT64_MIN = -2**63
INT64_MAX =  2**63 - 1
UINT64_MAX = 2**64 - 1
sNAN = 0x7f80_0001
qNAN = 0x7fff_ffff
nZero = 0x8000_0000
pZero = 0x0000_0000


def round_f32(real, frm: FP_ROUND_MODE):
    """Round python float64 'real' to float32 using RISC-V rounding mode frm."""
    
    # Convert to nearest-even float32 first
    nearest = np.float32(real)

    # If no rounding occurred, return directly
    if float(nearest) == real:
        return nearest

    # Compute neighbors
    down = np.nextafter(nearest, -np.inf, dtype=np.float32)
    up   = np.nextafter(nearest, +np.inf, dtype=np.float32)

    # Determine direction relative to nearest
    if float(nearest) < real:
        lower = nearest
        upper = up
    else:
        lower = down
        upper = nearest

    # Compute distances
    dist_lower = abs(real - float(lower))
    dist_upper = abs(real - float(upper))

    # ------------------------------
    #      Apply rounding mode
    # ------------------------------
    # 0 – RNE: round to nearest even
    if frm == FP_ROUND_MODE.RNE:
        # If exactly half way → choose even
        if dist_lower == dist_upper:
            # choose the even mantissa → the one with LSB=0
            if (np.float32(lower).view('uint32') & 1) == 0:
                return lower
            else:
                return upper
        return lower if dist_lower < dist_upper else upper

    # 1 – RTZ: toward zero
    if frm == FP_ROUND_MODE.RTZ:
        if real > 0:
            return lower
        else:
            return upper

    # 2 – RDN: toward -∞
    if frm == FP_ROUND_MODE.RDN:
        return lower if real >= 0 else upper

    # 3 – RUP: toward +∞
    if frm == FP_ROUND_MODE.RUP:
        return upper if real >= 0 else lower

    # 4 – RMM: round to nearest, ties to max magnitude
    if frm == FP_ROUND_MODE.RMM:
        if dist_lower == dist_upper:
            # choose the value with larger magnitude
            return lower if abs(lower) > abs(upper) else upper
        return lower if dist_lower < dist_upper else upper

    # 7 – DYN → in emulator just treat like RNE or error
    if frm == FP_ROUND_MODE.DYN:
        return nearest  # or raise

    # otherwise: illegal rounding mode
    return nearest

def is_sNan(flt):
    exponent = (flt >> 23) & 0xFF
    fraction = flt & 0x7FFFFF  # 23 bits

    if exponent != 0xFF or fraction == 0:
        return 0

    quiet_bit = (fraction >> 22) & 1
    payload = fraction & 0x3FFFFF  # lower 22 bits

    return quiet_bit==0

def fp_pos(fp):
    return (pack_f32(fp)>>31)==0

def fp_neg(fp):
    return (pack_f32(fp)>>31)==1


def is_subnormal(fp):
    return ((pack_f32(fp) >> 23) & 0xFF) == 0

def cvt_f32_to_int(
        f32, 
        is_signed, 
        rs2 : FP_CVT_RS2, 
        fflags):
    """
    Convert float32 to integer (32 or 64 bit).
    Implements FCVT.W.S / FCVT.WU.S / FCVT.L.S / FCVT.LU.S
    """

    f32 = float(np.float32(f32))   # exact float32 → float64

    # clear flags
    fflags["NV"] = 0
    fflags["DZ"] = 0
    fflags["OF"] = 0
    fflags["UF"] = 0
    fflags["NX"] = 0

    # ---------- Limits ----------
    if rs2 in [FP_CVT_RS2.W, FP_CVT_RS2.WU]:
        s_min, s_max = INT32_MIN, INT32_MAX
        u_max = UINT32_MAX
    else:  # 64-bit
        s_min, s_max = INT64_MIN, INT64_MAX
        u_max = UINT64_MAX

    # ---------- Signed conversion ----------
    if is_signed:
        if f32 < s_min:
            fflags["NV"] = 1
            return s_min
        if f32 > s_max:
            fflags["NV"] = 1
            return s_max
        return int(f32)
    # ---------- Unsigned conversion ----------
    else:
        if f32 < 0:
            if int(f32)==0: # special case
                fflags["NX"] = 1
            else:
                fflags["NV"] = 1
            return 0
        if f32 > u_max:
            fflags["NV"] = 1
            return u_max
        return int(f32)
    
def cvt_int_to_f32(i_raw, is_signed, rs2, frm, fflags):
    """
    INT → FLOAT32 using only Python floats and your rounding function.
    No bit manipulation.
    """

    # reset flags
    fflags["NV"] = 0
    fflags["DZ"] = 0
    fflags["OF"] = 0
    fflags["UF"] = 0
    fflags["NX"] = 0

    # -------------------------
    # Interpret the integer
    # -------------------------

    # select width
    if rs2 in (FP_CVT_RS2.W, FP_CVT_RS2.WU):
        width = 32
    else:
        width = 64

    mask = (1 << width) - 1
    raw = i_raw & mask

    if is_signed:
        signbit = 1 << (width - 1)
        if raw & signbit:
            value = raw - (1 << width)   # sign-extend
        else:
            value = raw
    else:
        value = raw   # unsigned exact magnitude

    # -------------------------
    # Step 1: exact real value (float64)
    # -------------------------
    real = float(value)  # convert to double precision (perfect)

    # -------------------------
    # Step 2: apply rounding mode
    # -------------------------
    rounded = round_f32(real, frm)  # float32 with correct frm rounding

    # -------------------------
    # Step 3: detect inexact
    # -------------------------
    if float(rounded) != real:
        fflags["NX"] = 1

    # -------------------------
    # Step 4: detect overflow
    # -------------------------
    if math.isfinite(real) and math.isinf(rounded):
        fflags["OF"] = 1
        fflags["NX"] = 1   # OF implies NX

    # -------------------------
    # Step 5: detect underflow
    # -------------------------
    F32_MIN_NORMAL = float.fromhex("0x1.0p-126")
    if abs(float(rounded)) < F32_MIN_NORMAL and fflags["NX"]:
        fflags["UF"] = 1

    return np.float32(rounded)
  

def pack_fflags(fflags:dict):
    ff = fflags['NX']
    ff |= fflags['UF']<<1
    ff |= fflags['OF']<<2
    ff |= fflags['DZ']<<3
    ff |= fflags['NV']<<4
    return ff
    
def_fflags = {
        "NV": 0, # Invalid operations
        "DZ": 0, # Division by zero
        "OF": 0, # Overflow
        "UF": 0, # Underflow
        "NX": 0, # Inexact
    }  

def FPU(
    a_f32: Union[float, int], 
    b_f32: Union[float, int], 
    f5:FP_OP_F5, 
    f3:int, 
    rs2:int,    
    **kwargs
    ):
    
    a_i32 = a_f32
    b_i32 = b_f32
    
    
    a_sNan = 0 
    b_sNan = 0 
    
    if type(a_f32)==int:
        a_sNan = is_sNan(a_f32) 
        a_f32 = to_f32(a_f32)
    else:
        # If it's a Python float, convert to float32 first!
        a_f32 = np.float32(a_f32)

    if type(b_f32)==int:
        b_sNan = is_sNan(b_f32)
        b_f32 = to_f32(b_f32)
    else:
        # If it's a Python float, convert to float32 first!
        b_f32 = np.float32(b_f32)

    # Now convert to float64 for computation
    a = float(a_f32)
    b = float(b_f32)

    # ----------------------
    # fflags
    # ----------------------
    fflags = {
        "NV": 0, # Invalid operations
        "DZ": 0, # Division by zero
        "OF": 0, # Overflow
        "UF": 0, # Underflow
        "NX": 0, # Inexact
    }
    
    # ----------------------
    # Perform real operation
    # ----------------------
    if f5 == FP_OP_F5.FSGNJ: # -> return fp
        
        f3 = FP_SGNJ_F3(f3)
        zero_sign_mask = (1<<31)-1
        sign_mask = (1<<31)
        
        a = pack_f32(a)
        b = pack_f32(b)
        
        a_sign = a&sign_mask
        b_sign = b&sign_mask
        b_nsign = 0 if b_sign>>31 else 1
        b_nsign = (b_nsign<<31)&sign_mask
        
        a = a&zero_sign_mask
        
        print(hex(a_sign), hex(b_sign), hex(b_nsign))
        if f3==FP_SGNJ_F3.J:
            a = a | b_sign
        elif f3==FP_SGNJ_F3.JN:
            a = a | b_nsign
        elif f3==FP_SGNJ_F3.JX:
            a = a | ((a_sign^b_sign)&sign_mask)
        else:
            print("FSGNJ-boh")
        
        return a, fflags
    
    elif f5==FP_OP_F5.FMINMAX:  # -> return fp
        f3 = FP_MINMAX_F3(f3)
        
        
        if math.isnan(a) and math.isnan(b):
            real = math.nan
            fflags['NV'] = 1
        elif math.isnan(a) and not math.isnan(b):
            real = b
            fflags['NV'] = 1
        elif not math.isnan(a) and math.isnan(b):
            real = a
            fflags['NV'] = 1
        else:
            if f3==FP_MINMAX_F3.FMIN:
                if a==0 and b==0:
                    if fp_pos(a) and fp_neg(b):
                        real = b
                    elif fp_neg(a) and fp_pos(b):
                        real = a
                    else:
                        real = a # either is equal
                else:
                    if a>b:
                        real = b
                    else:
                        real = a
            elif f3==FP_MINMAX_F3.FMAX:
                if a==0 and b==0:
                    if fp_pos(a) and fp_neg(b):
                        real = a
                    elif fp_neg(a) and fp_pos(b):
                        real = b
                    else:
                        real = a # either is equal
                else:
                    if a>b:
                        real = a
                    else:
                        real = b
        return real, fflags
                                       
    elif f5 == FP_OP_F5.FCLASS and f3==1:
        class_res = 0
        if math.isinf(a):
            if fp_pos(a):
                class_res = FP_CLASS.posInf
            else:
                class_res = FP_CLASS.negInf
        elif a==0:
            if fp_pos(a):
                class_res = FP_CLASS.posZero
            else:
                class_res = FP_CLASS.negZero
        elif math.isnan(a):
            if is_sNan(a_i32):
                class_res = FP_CLASS.sNan
            else:
                class_res = FP_CLASS.qNan
        elif is_subnormal(a):
            if fp_pos(a):
                class_res = FP_CLASS.posSubNum
            else:
                class_res = FP_CLASS.negSubNum
        else:
            if fp_pos(a):
                class_res = FP_CLASS.posNorNum
            else:
                class_res = FP_CLASS.negNorNum
        return class_res, fflags
    
    elif f5 == FP_OP_F5.FCMP:
        
        
        f3 = FP_CMP_F3(f3)
        
        cond = 0
        if f3 == FP_CMP_F3.EQ:
            if (math.isnan(a_f32) and a_sNan) or \
                (math.isnan(b_f32) and b_sNan):
                fflags['NV'] = 1
                
            cond = 1 if a_f32==b_f32 else 0
        elif f3 == FP_CMP_F3.LT:
            cond = 1 if a_f32<b_f32 else 0
        elif f3 == FP_CMP_F3.LE:
            cond = 1 if a_f32<=b_f32 else 0
            
        if (math.isnan(a_f32) and not a_sNan) or \
            (math.isnan(b_f32) and not b_sNan) or \
            (math.isnan(a_f32) or math.isnan(b_f32)):
            if f3 in [FP_CMP_F3.LT, FP_CMP_F3.LE]:
                fflags['NV'] = 1
                return 0, fflags
        
        
        return cond, fflags

    elif f5 == FP_OP_F5.CVT_TO_FP:  # -> return fp
        rs2 = FP_CVT_RS2(rs2)
        signed = rs2 in [FP_CVT_RS2.W, FP_CVT_RS2.L]
        is32 = rs2 in [FP_CVT_RS2.W, FP_CVT_RS2.WU]
        
        real = cvt_int_to_f32(a_i32, signed, rs2, FP_ROUND_MODE(f3), fflags)
        
        return real, fflags
    
    elif f5 == FP_OP_F5.CVT_TO_INT:
        
        rs2 = FP_CVT_RS2(rs2)
        signed = rs2 in [FP_CVT_RS2.W, FP_CVT_RS2.L]
        is32 = rs2 in [FP_CVT_RS2.W, FP_CVT_RS2.WU]
        if math.isnan(a):
            MAXB = 32 if is32 else 64
            if signed:
                integer=(1<<(MAXB-1))-1
            else:
                integer=(1<<MAXB)-1
            fflags['NV'] = 1
        else:
            integer = cvt_f32_to_int(a, signed, rs2, fflags)
            
        # print("integer", integer)
        if is32:
            print(integer, a)
            if float(integer)!=float(a) and fflags['NV']!=1:
                fflags['NX'] = 1
            return sign_extend(integer&0xffff_ffff, 32)&0xffff_ffff_ffff_ffff, fflags
        else:
            if float(integer)!=float(a) and fflags['NV']!=1:
                fflags['NX'] = 1
            return integer&0xffff_ffff_ffff_ffff, fflags
    
    elif f5 in [FP_OP_F5.FADD, FP_OP_F5.FSUB, FP_OP_F5.FMUL, FP_OP_F5.FDIV, FP_OP_F5.FSQRT]:
        # Track if this is an invalid operation from the start
        invalid_op = False
        
        if math.isnan(a) or math.isnan(b):
            real = math.nan
            invalid_op = True
        else:
            if f5 == FP_OP_F5.FADD:
                real = a + b
            elif f5 == FP_OP_F5.FSUB:
                real = a - b
            elif f5 == FP_OP_F5.FMUL:
                real = a * b
            elif f5 == FP_OP_F5.FDIV:
                if b == 0.0 and a != 0.0:
                    real = math.nan
                    fflags['DZ'] = 1
                else:
                    real = a / b
            elif f5 == FP_OP_F5.FSQRT:
                if a >= 0:
                    real = math.sqrt(a)
                else:
                    real = math.nan
                    invalid_op = True
            else:
                raise ValueError("unknown f5")

        # Check for invalid operations that produce NaN
        # Inf - Inf, Inf + (-Inf), 0 * Inf, Inf / Inf, 0 / 0, sqrt(negative)
        if math.isnan(real) and not invalid_op:
            invalid_op = True

        # ----------------------
        # Convert result to float32 (FPU final result)
        # ----------------------
        f32 = round_f32(real, FP_ROUND_MODE(f3))

        # NV: invalid operations → result is NaN from invalid operation
        if invalid_op:
            fflags['NV'] = 1
                
        # NX: inexact - only check if NOT an invalid operation
        # Invalid operations don't set inexact flag
        if not invalid_op and not math.isnan(real):
            if float(f32) != real:
                fflags['NX'] = 1

        # OF: overflow → final result is inf, but real was finite
        if math.isfinite(real) and math.isinf(f32):
            fflags['OF'] = 1
            fflags['NX'] = 1  # Overflow implies inexact

        # UF: underflow → tiny + inexact
        F32_MIN_NORMAL = float.fromhex("0x1.0p-126")
        if abs(f32) < F32_MIN_NORMAL and fflags['NX']:
            fflags['UF'] = 1

        return f32, fflags
    
"""
# ------------------------------------------------------------------------- fadd.S

# res = FPU(2.5, 1.0, FP_OP_F5.FADD, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))
# res = FPU(-1235.1, 1.1, f5=FP_OP_F5.FADD, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))
# res = FPU(3.14159265, 0.00000001, f5=FP_OP_F5.FADD, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))

# res = FPU(2.5, 1.0, FP_OP_F5.FSUB, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))
# res = FPU(-1235.1, -1.1, f5=FP_OP_F5.FSUB, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))
# res = FPU(3.14159265, 0.00000001, f5=FP_OP_F5.FSUB, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))


# res = FPU(2.5, 1.0, f5=FP_OP_F5.FMUL, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))
# res = FPU(-1235.1, -1.1, f5=FP_OP_F5.FMUL, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))
# res = FPU(3.14159265, 0.00000001, f5=FP_OP_F5.FMUL, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))


# # Inf - (+Inf) -> NaN
# res = FPU(0x7f800000, 0x7f800000, f5=FP_OP_F5.FSUB, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))
# # # Inf - (-Inf) -> +inf
# res = FPU(0x7f800000, 0xff800000, f5=FP_OP_F5.FSUB, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))
# # # (-Inf) - (+Inf) -> -inf
# res = FPU(0xff800000, 0x7f800000, f5=FP_OP_F5.FSUB, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))
# # # (-Inf) - (-Inf) -> NaN
# res = FPU(0xff800000, 0xff800000, f5=FP_OP_F5.FSUB, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))

# # Inf + (+Inf) -> +Inf
# res = FPU(0x7f800000, 0x7f800000, f5=FP_OP_F5.FADD, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))
# # # Inf + (-Inf) -> Nan
# res = FPU(0x7f800000, 0xff800000, f5=FP_OP_F5.FADD, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))
# # # (-Inf) + (+Inf) -> Nan
# res = FPU(0xff800000, 0x7f800000, f5=FP_OP_F5.FADD, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))
# # # (-Inf) + (-Inf) -> -Inf
# res = FPU(0xff800000, 0xff800000, f5=FP_OP_F5.FADD, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))

# # Inf * (+Inf) -> +Inf
# res = FPU(0x7f800000, 0x7f800000, f5=FP_OP_F5.FMUL, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))
# # # Inf * (-Inf) -> -Inf
# res = FPU(0x7f800000, 0xff800000, f5=FP_OP_F5.FMUL, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))
# # # (-Inf) * (+Inf) -> -Inf
# res = FPU(0xff800000, 0x7f800000, f5=FP_OP_F5.FMUL, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))
# # # (-Inf) * (-Inf) -> +Inf
# res = FPU(0xff800000, 0xff800000, f5=FP_OP_F5.FMUL, f3=0, rs2=0)
# print(res[0], f'{pack_f32(res[0]):08x}', hex(pack_fflags(res[1])))

## ------------------------------------------------------------------------fcmp.S
# res = FPU(-1.36, -1.36, FP_OP_F5.FCMP, FP_CMP_F3.EQ, 0)
# print(res[0], hex(pack_fflags(res[1])))
# res = FPU(-1.36, -1.36, FP_OP_F5.FCMP, FP_CMP_F3.LE, 0)
# print(res[0], hex(pack_fflags(res[1])))
# res = FPU(-1.36, -1.36, FP_OP_F5.FCMP, FP_CMP_F3.LT, 0)
# print(res[0], hex(pack_fflags(res[1])))

# res = FPU(-1.37, -1.36, FP_OP_F5.FCMP, FP_CMP_F3.EQ, 0)
# print(res[0], hex(pack_fflags(res[1])))
# res = FPU(-1.37, -1.36, FP_OP_F5.FCMP, FP_CMP_F3.LE, 0)
# print(res[0], hex(pack_fflags(res[1])))
# res = FPU(-1.37, -1.36, FP_OP_F5.FCMP, FP_CMP_F3.LT, 0)
# print(res[0], hex(pack_fflags(res[1])))

# print(res[0], res[1])


# res = FPU(0x7fff_ffff, 0, FP_OP_F5.FCMP, FP_CMP_F3.EQ, 0)
# print(res[0], hex(pack_fflags(res[1])))
# res = FPU(0x7fff_ffff, 0x7fff_ffff, FP_OP_F5.FCMP, FP_CMP_F3.EQ, 0)
# print(res[0], hex(pack_fflags(res[1])))
# res = FPU(0x7f80_0001, 0.0, FP_OP_F5.FCMP, FP_CMP_F3.EQ, 0)
# print(res[0], hex(pack_fflags(res[1])))
# print(res[0], res[1])

# res = FPU(qNAN, 0, FP_OP_F5.FCMP, FP_CMP_F3.LT, 0)
# print(res[0], hex(pack_fflags(res[1])))
# res = FPU(qNAN, qNAN, FP_OP_F5.FCMP, FP_CMP_F3.LT, 0)
# print(res[0], hex(pack_fflags(res[1])))
# res = FPU(0x7f80_0001, 0.0, FP_OP_F5.FCMP, FP_CMP_F3.LT, 0)
# print(res[0], hex(pack_fflags(res[1])))
# # print(res[0], res[1])

# res = FPU(qNAN, 0, FP_OP_F5.FCMP, FP_CMP_F3.LE, 0)
# print(res[0], hex(pack_fflags(res[1])))
# # print(res[0], res[1]) # qNan
# res = FPU(qNAN, qNAN, FP_OP_F5.FCMP, FP_CMP_F3.LE, 0)
# print(res[0], hex(pack_fflags(res[1])))
# # print(res[0], res[1]) # sNan
# res = FPU(0x7f80_0001, 0.0, FP_OP_F5.FCMP, FP_CMP_F3.LE, 0)
# print(res[0], hex(pack_fflags(res[1])))
# # print(res[0], res[1])
"""
# --------------------------------------------------------------------------fcvt_w.S
# res = FPU(-1.1, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(-1.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(-0.9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(0.9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(1.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(1.1, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(-3e9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(3e9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))

# res = FPU(-3.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(-1.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(-0.9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(0.9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(1.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(1.1, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(-3e9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(3000000000., 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))

# res = FPU(-1.1, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(-1.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(-0.9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(0.9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(1.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(1.1, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))


# res = FPU(-3.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(-1.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(-0.9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(0.9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(1.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(1.1, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))
# res = FPU(-3e9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# print(f"{res[0]:016x}", hex(pack_fflags(res[1])))

# res = FPU(-np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# res = FPU(-np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)

# res = FPU(-np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)
# res = FPU(-np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)

# res = FPU(np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# res = FPU(np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)

# res = FPU(np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)
# res = FPU(np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)


# res = FPU(-np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# res = FPU( np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# res = FPU(-np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# res = FPU( np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)

# res = FPU(-np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# res = FPU( np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# res = FPU(-np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# res = FPU( np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)

# print(res[0], res[1], f"{res[0]:016x}")

# res = FPU( 0, 0, FP_OP_F5.FSGNJ, FP_SGNJ_F3.J, 0)
# print(res[0], res[1], f"{res[0]:08x}")

# res = FPU(2, 0.0, FP_OP_F5.CVT_TO_FP, 0, FP_CVT_RS2.W)
# res = FPU(-2, 0.0, FP_OP_F5.CVT_TO_FP, 0, FP_CVT_RS2.W)
# res = FPU(2, 0.0, FP_OP_F5.CVT_TO_FP, 0, FP_CVT_RS2.WU)
# res = FPU(-2, 0.0, FP_OP_F5.CVT_TO_FP, 0, FP_CVT_RS2.WU)

# res = FPU(2, 0.0, FP_OP_F5.CVT_TO_FP, 0, FP_CVT_RS2.L)
# res = FPU(-2, 0.0, FP_OP_F5.CVT_TO_FP, 0, FP_CVT_RS2.L)
# res = FPU(2, 0.0, FP_OP_F5.CVT_TO_FP, 0, FP_CVT_RS2.LU)
# res = FPU(-2, 0.0, FP_OP_F5.CVT_TO_FP, 0, FP_CVT_RS2.LU)
"""
# res = FPU(2.5, 1.0, f5=FP_OP_F5.FMUL, f3=0, rs2=0)
# res = FPU(-1235.1, -1.1, f5=FP_OP_F5.FMUL, f3=0, rs2=0)
# res = FPU(3.14159265, 0.00000001, f5=FP_OP_F5.FMUL, f3=0, rs2=0)

# res = FPU(2.5, 1.0, FP_OP_F5.FADD, f3=0, rs2=0)
# res = FPU(-1235.1, 1.1, f5=FP_OP_F5.FADD, f3=0, rs2=0)
# res = FPU(3.14159265, 0.00000001, f5=FP_OP_F5.FADD, f3=0, rs2=0)

# res = FPU(2.5, 1.0, FP_OP_F5.FSUB, f3=0, rs2=0)
# res = FPU(-1235.1, -1.1, f5=FP_OP_F5.FSUB, f3=0, rs2=0)
# res = FPU(3.14159265, 0.00000001, f5=FP_OP_F5.FSUB, f3=0, rs2=0)


# res = FPU(3.14159265, 2.71828182, f5=FP_OP_F5.FDIV, f3=0, rs2=0)
# res = FPU(-1234.0, 1235.1, f5=FP_OP_F5.FDIV, f3=0, rs2=0)
# res = FPU(3.14159265, 1.0, f5=FP_OP_F5.FDIV, f3=0, rs2=0)

# res = FPU(3.14159265, 0.0, f5=FP_OP_F5.FSQRT, f3=0, rs2=0)
# res = FPU(10000.0, 0.0, f5=FP_OP_F5.FSQRT, f3=0, rs2=0)
# res = FPU(-1.0, 0.0, f5=FP_OP_F5.FSQRT, f3=0, rs2=0)
# res = FPU(171.0, 0.0, f5=FP_OP_F5.FSQRT, f3=0, rs2=0)


# print(f"{pack_f32(res[0]):08x}", res[0], res[1])
    
# res = FPU(-1.1, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# res = FPU(-1.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# res = FPU(-0.9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# res = FPU(0.9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# res = FPU(1.1, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# res = FPU(1.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# res = FPU(-3e9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# res = FPU(3e9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)

# res = FPU(-3.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# res = FPU(-1.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# res = FPU(-0.9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# res = FPU(0.9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# res = FPU(1.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# res = FPU(1.1, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# res = FPU(-3e9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# res = FPU(3000000000., 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)

# res = FPU(-1.1, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)
# res = FPU(-1.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)
# res = FPU(-0.9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)
# res = FPU(0.9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)
# res = FPU(1.1, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)
# res = FPU(1.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)


# res = FPU(-3.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# res = FPU(-1.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# res = FPU(-0.9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# res = FPU(0.9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# res = FPU(1.0, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# res = FPU(1.1, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# res = FPU(-3e9, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)

# res = FPU(-np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# res = FPU(-np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)

# res = FPU(-np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)
# res = FPU(-np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)

# res = FPU(np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
# res = FPU(np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)

# res = FPU(np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)
# res = FPU(np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)


# res = FPU(-np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# res = FPU( np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# res = FPU(-np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
# res = FPU( np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)

# res = FPU(-np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# res = FPU( np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# res = FPU(-np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
# res = FPU( np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)

# print(res[0], res[1], f"{res[0]:016x}")

# res = FPU( 0, 0, FP_OP_F5.FSGNJ, FP_SGNJ_F3.J, 0)
# print(res[0], res[1], f"{res[0]:08x}")

# res = FPU(2, 0.0, FP_OP_F5.CVT_TO_FP, 0, FP_CVT_RS2.W)
# res = FPU(-2, 0.0, FP_OP_F5.CVT_TO_FP, 0, FP_CVT_RS2.W)
# res = FPU(2, 0.0, FP_OP_F5.CVT_TO_FP, 0, FP_CVT_RS2.WU)
# res = FPU(-2, 0.0, FP_OP_F5.CVT_TO_FP, 0, FP_CVT_RS2.WU)

# res = FPU(2, 0.0, FP_OP_F5.CVT_TO_FP, 0, FP_CVT_RS2.L)
# res = FPU(-2, 0.0, FP_OP_F5.CVT_TO_FP, 0, FP_CVT_RS2.L)
# res = FPU(2, 0.0, FP_OP_F5.CVT_TO_FP, 0, FP_CVT_RS2.LU)
# res = FPU(-2, 0.0, FP_OP_F5.CVT_TO_FP, 0, FP_CVT_RS2.LU)

# print(res[0], res[1])


# res = FPU(-1.36, -1.36, FP_OP_F5.FCMP, FP_CMP_F3.EQ, 0)
# res = FPU(-1.36, -1.36, FP_OP_F5.FCMP, FP_CMP_F3.LE, 0)
# res = FPU(-1.36, -1.36, FP_OP_F5.FCMP, FP_CMP_F3.LT, 0)

# res = FPU(-1.37, -1.36, FP_OP_F5.FCMP, FP_CMP_F3.EQ, 0)
# res = FPU(-1.37, -1.36, FP_OP_F5.FCMP, FP_CMP_F3.LE, 0)
# res = FPU(-1.37, -1.36, FP_OP_F5.FCMP, FP_CMP_F3.LT, 0)

# print(res[0], res[1])


# res = FPU(0x7fff_ffff, 0, FP_OP_F5.FCMP, FP_CMP_F3.EQ, 0)
# res = FPU(0x7fff_ffff, 0x7fff_ffff, FP_OP_F5.FCMP, FP_CMP_F3.EQ, 0)
# res = FPU(0x7f80_0001, 0.0, FP_OP_F5.FCMP, FP_CMP_F3.EQ, 0)
# print(res[0], res[1])

# res = FPU(0x7fff_ffff, 0, FP_OP_F5.FCMP, FP_CMP_F3.LT, 0)
# res = FPU(0x7fff_ffff, 0x7fff_ffff, FP_OP_F5.FCMP, FP_CMP_F3.LT, 0)
# res = FPU(0x7f80_0001, 0.0, FP_OP_F5.FCMP, FP_CMP_F3.LT, 0)
# print(res[0], res[1])

# res = FPU(0x7fff_ffff, 0, FP_OP_F5.FCMP, FP_CMP_F3.LE, 0)
# print(res[0], res[1]) # qNan
# res = FPU(0x7fff_ffff, 0x7fff_ffff, FP_OP_F5.FCMP, FP_CMP_F3.LE, 0)
# print(res[0], res[1]) # sNan
# res = FPU(0x7f80_0001, 0.0, FP_OP_F5.FCMP, FP_CMP_F3.LE, 0)
# print(res[0], res[1])

res = FPU(-np.inf, 0, FP_OP_F5.FCLASS, 1, 0)
res = FPU(0xbf800000, 0, FP_OP_F5.FCLASS, 1, 0)
res = FPU(0x807fffff, 0, FP_OP_F5.FCLASS, 1, 0)
res = FPU(0x80000000, 0, FP_OP_F5.FCLASS, 1, 0)
res = FPU(0x00000000, 0, FP_OP_F5.FCLASS, 1, 0)
res = FPU(0x007fffff, 0, FP_OP_F5.FCLASS, 1, 0)
res = FPU(0x3f800000, 0, FP_OP_F5.FCLASS, 1, 0)
res = FPU(0x7f800001, 0, FP_OP_F5.FCLASS, 1, 0)
res = FPU(0x7fffffff, 0, FP_OP_F5.FCLASS, 1, 0)

print(res[0], res[1])

res = FPU(1.0, 2.5, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMIN, 0)
res = FPU(1.1, -1235.1, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMIN, 0)
res = FPU(-1235.1, 1.1, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMIN, 0)
res = FPU(-1235.1, np.nan, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMIN, 0)
res = FPU(0.00000001, 3.14159265, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMIN, 0)
res = FPU(-2.0, -1.0, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMIN, 0)

res = FPU(1.0, 2.5, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMAX, 0)
res = FPU(1.1, -1235.1, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMAX, 0)
res = FPU(-1235.1, 1.1, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMAX, 0)
res = FPU(-1235.1, np.nan, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMAX, 0)
res = FPU(0.00000001, 3.14159265, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMAX, 0)
res = FPU(-2.0, -1.0, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMAX, 0)

res = FPU(0x3f800000, sNAN, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMAX, 0)
res = FPU(sNAN, sNAN, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMAX, 0)


res = FPU(nZero, pZero, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMIN, 0)
res = FPU(pZero, nZero, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMIN, 0)

res = FPU(nZero, pZero, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMAX, 0)
res = FPU(pZero, nZero, FP_OP_F5.FMINMAX, FP_MINMAX_F3.FMAX, 0)
print(res[0], f"{pack_f32(res[0]):08x}", res[1])

"""