from utils import *
from functools import lru_cache


# def shift_unit(op, shamt, f3: OP_F3, f7:int, op32: bool=False):
    
#     xlen = 32 if op32 else 64
#     shamt = shamt&0b11111 if op32 else shamt&0b111111
#     mask = (1<<xlen)-1
    
#     if f3 == OP_F3.SLL:
#         return (op&mask)<<shamt
#     elif f3 == OP_F3.SRX:
#         if f7: # SRA
#             return sign_extend((op&mask)>>shamt, xlen-shamt)&mask
#         else:
#             return (op&mask)>>shamt
#     else:
#         raise Exception(f"{f3} not implemented in shift unit")
    
def shift_unit(op, shamt, f3: str, f7:int, op32: bool=False):
    
    xlen = 32 if op32 else 64
    shamt = shamt&0b11111 if op32 else shamt&0b111111
    mask = (1<<xlen)-1
    
    if f3 == "SLL":
        return (op&mask)<<shamt
    elif f3 == "SRX":
        if f7: # SRA
            return sign_extend((op&mask)>>shamt, xlen-shamt)&mask
        else:
            return (op&mask)>>shamt
    else:
        raise Exception(f"{f3} not implemented in shift unit")

def sign(num):
    return -1 if num<0 else 1

def sign64(num):
    return -1 if (num>>64)==1 else 1

def sign32(num):
    return -1 if (num>>32)==1 else 1



# Define operation handlers outside the function for better performance
def _mul_handler(op1: int, op2: int, f3: OP_F3, f7: int):
    """Handle M-extension (multiply/divide) operations"""
    m_f3 = OP_MUL_F3(f3)
    s_op1 = int_64(op1)
    s_op2 = int_64(op2)
    
    # Use a dispatch dictionary for M-extension operations
    if m_f3 == OP_MUL_F3.MUL:
        return s_op1 * s_op2
    elif m_f3 == OP_MUL_F3.MULH:
        return (s_op1 * s_op2) >> 64
    elif m_f3 == OP_MUL_F3.MULHU:
        return (op1 * op2) >> 64
    elif m_f3 == OP_MUL_F3.MULHSU:
        return (s_op1 * op2) >> 64
    elif m_f3 == OP_MUL_F3.DIV:
        if op2 == 0:
            return -1
        s = sign(s_op1) * sign(s_op2)
        return s * (abs(s_op1) // abs(s_op2))
    elif m_f3 == OP_MUL_F3.DIVU:
        return -1 if op2 == 0 else op1 // op2
    elif m_f3 == OP_MUL_F3.REM:
        if op2 == 0:
            return op1
        s = sign(s_op1)
        return s * (abs(s_op1) % abs(s_op2))
    elif m_f3 == OP_MUL_F3.REMU:
        return op1 if op2 == 0 else op1 % op2
    else:
        raise Exception(f"M extension f3 {m_f3} not implemented")


# ALU operation dispatch table
ALU_OPS = {
    "AND": lambda op1, op2, f3, f7, op32, op_imm: op1 & op2,
    "OR": lambda op1, op2, f3, f7, op32, op_imm: op1 | op2,
    "XOR": lambda op1, op2, f3, f7, op32, op_imm: op1 ^ op2,
    "SLT": lambda op1, op2, f3, f7, op32, op_imm: int_64(op1) < int_64(op2),
    "SLTU": lambda op1, op2, f3, f7, op32, op_imm: op1 < op2,
    "SLL": lambda op1, op2, f3, f7, op32, op_imm: shift_unit(op1, op2, f3, f7, op32),
    "SRX": lambda op1, op2, f3, f7, op32, op_imm: shift_unit(op1, op2, f3, f7, op32),
}


OP_F3_dict = {
    0b000 : "ADD_SUB", 
    0b001 : "SLL", 
    0b010 : "SLT",  
    0b011 : "SLTU", 
    0b100 : "XOR", 
    0b101 : "SRX",  
    0b110 : "OR",  
    0b111 : "AND", 
}

def alu(op1: int, op2: int, f3: str, f7: int, op32: bool = False, op_imm: bool = False) -> int:
    """Optimized ALU with dispatch table and reduced branching"""
    
    # Handle M-extension (multiply/divide) operations
    if not op_imm and (f7 & 0b1) == 1:  # is_M
        return _mul_handler(op1, op2, f3, f7)
    f3 = OP_F3_dict[f3]
    # Handle ADD/SUB separately (common operations)
    if f3 == "ADD_SUB":
        return op1 - op2 if f7 else op1 + op2
    
    # Use dispatch table for remaining operations
    if f3 in ALU_OPS:
        return ALU_OPS[f3](op1, op2, f3, f7, op32, op_imm)
    
    raise Exception(f"{f3} not implemented in ALU")

# def alu(op1:int, op2:int, f3: OP_F3, f7: int, op32: bool=False, op_imm:bool=False):  

#     if not op_imm and f7&0b1==1: # is_M
#         m_f3 = OP_MUL_F3(f3.value)
#         # -log.error(m_f3)
#         s_op1 = int_64(op1)
#         s_op2 = int_64(op2)
#         if m_f3==OP_MUL_F3.DIV:
#             s = sign(s_op1)*sign(s_op2) # find sign
#             if op2==0: return -1
#             else: return s*(abs(s_op1)//abs(s_op2))
#         if m_f3==OP_MUL_F3.DIVU:
#             if op2==0: return -1
#             else: return op1//op2
#         if m_f3==OP_MUL_F3.REM:
#             s = sign(int_64(op1)) # find sign
#             if op2==0: return op1
#             else: return s*(abs(s_op1)%abs(s_op2))
#         if m_f3==OP_MUL_F3.REMU:                
#             s = sign(int_64(op1)) # find sign
#             if op2==0: return op1
#             else: return op1%op2
#         if m_f3==OP_MUL_F3.MUL:
#             return s_op1*s_op2
#         if m_f3==OP_MUL_F3.MULH:
#             return (s_op1*s_op2)>>64
#         if m_f3==OP_MUL_F3.MULHU:
#             return (op1*op2)>>64
#         if m_f3==OP_MUL_F3.MULHSU:
#             return (s_op1*op2)>>64
#         else:
#             raise Exception(f"M extension f3 {m_f3} not implemented")
        
#     elif f3==OP_F3.ADD_SUB:
#         if f7:
#             return op1-op2
#         else:
#             return op1+op2    
#     elif f3==OP_F3.AND:
#         return op1 & op2
#     elif f3==OP_F3.OR:
#         return op1 | op2
#     elif f3==OP_F3.XOR:
#         return op1 ^ op2
#     elif f3==OP_F3.SLT:
#         return int_64(op1) < int_64(op2)
#     elif f3==OP_F3.SLTU:
#         return op1 < op2
#     elif f3==OP_F3.SLL or f3==OP_F3.SRX:
#         return shift_unit(op1, op2, f3, f7, op32)
#     else:
#         raise Exception(f"{f3} not implemented in ALU")
