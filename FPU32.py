from cpu_enums import FP_OP_F5, FP_ROUND_MODE
from struct import unpack, pack
from utils import *
from typing import List, Union
from math import sqrt
from colorama import Fore
import math
import numpy as np




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

CANONICAL_QNAN = 0x7FC00000  # RISC-V canonical quiet NaN


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


INT32_MIN = -2**31
INT32_MAX =  2**31 - 1
UINT32_MAX = 2**32 - 1

INT64_MIN = -2**63
INT64_MAX =  2**63 - 1
UINT64_MAX = 2**64 - 1


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
    if rs2 in [FP_CVT_RS2.W, FP_CVT_RS2.W]:
        s_min, s_max = INT32_MIN, INT32_MAX
        u_max = UINT32_MAX
    else:  # 64-bit
        s_min, s_max = INT64_MIN, INT64_MAX
        u_max = UINT64_MAX

    # ---------- NaN ----------
    if math.isnan(f32):
        fflags["NV"] = 1
        return 0   # RISC-V says return 0


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
            fflags["NV"] = 1
            return 0

        if f32 > u_max:
            fflags["NV"] = 1
            return u_max

        return int(f32)

   
def FPU(
    a_f32: Union[float, int], 
    b_f32: Union[float, int], 
    f5:FP_OP_F5, 
    f3:int, 
    rs2:int,      
    **kwargs
    ):
    
    # Cast input to python float64
    if type(a_f32)==int:
        a_f32 = to_f32(a_f32)
    if type(b_f32)==int:
        b_f32 = to_f32(b_f32)
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
    if f5 == FP_OP_F5.CVT_TO_INT:
        
        rs2 = FP_CVT_RS2(rs2)
        signed = rs2 in [FP_CVT_RS2.W, FP_CVT_RS2.L]
        # print("float", a)
        is32 = rs2 in [FP_CVT_RS2.W, FP_CVT_RS2.WU]
        if math.isnan(a):
            MAXB = 32 if is32 else 64
            
            if signed:
                integer=(1<<(MAXB-1))-1
            else:
                integer=(1<<MAXB)-1
        else:
            integer = cvt_f32_to_int(a, signed, rs2, fflags)
        # print("integer", integer)
        if is32:
            return sign_extend(integer&0xffff_ffff, 32)&0xffff_ffff_ffff_ffff, fflags
        else:
            return integer&0xffff_ffff_ffff_ffff, fflags
    
    elif f5 in [FP_OP_F5.FADD, FP_OP_F5.FSUB, FP_OP_F5.FMUL, FP_OP_F5.FDIV, FP_OP_F5.FSQRT]:
        if math.isnan(a) or math.isnan(b):
            real = math.nan
        else:
            if f5 == FP_OP_F5.FADD:
                real = a + b
            elif f5 == FP_OP_F5.FSUB:
                real = a - b
            elif f5 == FP_OP_F5.FMUL:
                real = a * b
            elif f5 == FP_OP_F5.FDIV:
                if b == 0.0 and a != 0.0:
                    real=math.nan
                    fflags['DZ'] = True
                else:
                    real = a / b
            elif f5 == FP_OP_F5.FSQRT:
                if a>=0:
                    real = math.sqrt(a)
                else:
                    real = math.nan
            else:
                raise ValueError("unknown f5")

        # ----------------------
        # Convert result to float32 (FPU final result)
        # ----------------------
        f32 = round_f32(real, FP_ROUND_MODE(f3))

        # NV: invalid operations → real is NaN
        if math.isnan(real):
            fflags['NV'] = True
                
        # NX: inexact
        if f32 != real:
            fflags['NX'] = True

        # OF: overflow → final result is inf, but real was finite
        if math.isfinite(real) and math.isinf(f32):
            fflags['OF'] = True

        # UF: underflow → tiny + inexact
        F32_MIN_NORMAL = float.fromhex("0x1.0p-126")
        if abs(f32) < F32_MIN_NORMAL and fflags['NX']:
            fflags['UF'] = True

        return f32, fflags
    
        

# # Inf - (+Inf) -> NaN
# res = FPU(0x7f800000, 0x7f800000, f5=FP_OP_F5.FSUB, f3=0, rs2=0)
# # # Inf - (-Inf) -> +inf
# res = FPU(0x7f800000, 0xff800000, f5=FP_OP_F5.FSUB, f3=0, rs2=0)
# # # (-Inf) - (+Inf) -> -inf
# res = FPU(0xff800000, 0x7f800000, f5=FP_OP_F5.FSUB, f3=0, rs2=0)
# # # (-Inf) - (-Inf) -> NaN
# res = FPU(0xff800000, 0xff800000, f5=FP_OP_F5.FSUB, f3=0, rs2=0)

# # Inf + (+Inf) -> +Inf
# res = FPU(0x7f800000, 0x7f800000, f5=FP_OP_F5.FADD, f3=0, rs2=0)
# # # Inf + (-Inf) -> Nan
# res = FPU(0x7f800000, 0xff800000, f5=FP_OP_F5.FADD, f3=0, rs2=0)
# # # (-Inf) + (+Inf) -> Nan
# res = FPU(0xff800000, 0x7f800000, f5=FP_OP_F5.FADD, f3=0, rs2=0)
# # # (-Inf) + (-Inf) -> -Inf
# res = FPU(0xff800000, 0xff800000, f5=FP_OP_F5.FADD, f3=0, rs2=0)


# # Inf * (+Inf) -> +Inf
# res = FPU(0x7f800000, 0x7f800000, f5=FP_OP_F5.FMUL, f3=0, rs2=0)
# # # Inf * (-Inf) -> -Inf
# res = FPU(0x7f800000, 0xff800000, f5=FP_OP_F5.FMUL, f3=0, rs2=0)
# # # (-Inf) * (+Inf) -> -Inf
# res = FPU(0xff800000, 0x7f800000, f5=FP_OP_F5.FMUL, f3=0, rs2=0)
# # # (-Inf) * (-Inf) -> +Inf
# res = FPU(0xff800000, 0xff800000, f5=FP_OP_F5.FMUL, f3=0, rs2=0)


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

res = FPU(-np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
res = FPU(-np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)

res = FPU(-np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)
res = FPU(-np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)

res = FPU(np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)
res = FPU(np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.W)

res = FPU(np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)
res = FPU(np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.L)


res = FPU(-np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
res = FPU( np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
res = FPU(-np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)
res = FPU( np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.WU)

res = FPU(-np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
res = FPU( np.nan, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
res = FPU(-np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)
res = FPU( np.inf, 0.0, FP_OP_F5.CVT_TO_INT, 0, FP_CVT_RS2.LU)

print(res[0], res[1], f"{res[0]:016x}")