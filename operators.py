from utils import *


def shift_unit(op, shamt, f3: OP_F3, f7:int, op32: bool=False):
    
    xlen = 32 if op32 else 64
    shamt = shamt&0b11111 if op32 else shamt&0b111111
    mask = (1<<xlen)-1
    
    if f3 == OP_F3.SLL:
        return (op&mask)<<shamt
    elif f3 == OP_F3.SRX:
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
 
def alu(op1:int, op2:int, f3: OP_F3, f7: int, op32: bool=False, op_imm:bool=False):  

    if not op_imm and f7&0b1==1: # is_M
        m_f3 = OP_MUL_F3(f3.value)
        log.error(m_f3)
        s_op1 = int_64(op1)
        s_op2 = int_64(op2)
        if m_f3==OP_MUL_F3.DIV:
            s = sign(s_op1)*sign(s_op2) # find sign
            if op2==0: return -1
            else: return s*(abs(s_op1)//abs(s_op2))
        if m_f3==OP_MUL_F3.DIVU:
            if op2==0: return -1
            else: return op1//op2
        if m_f3==OP_MUL_F3.REM:
            s = sign(int_64(op1)) # find sign
            if op2==0: return op1
            else: return s*(abs(s_op1)%abs(s_op2))
        if m_f3==OP_MUL_F3.REMU:                
            s = sign(int_64(op1)) # find sign
            if op2==0: return op1
            else: return op1%op2
        if m_f3==OP_MUL_F3.MUL:
            return s_op1*s_op2
        if m_f3==OP_MUL_F3.MULH:
            return (s_op1*s_op2)>>64
        if m_f3==OP_MUL_F3.MULHU:
            return (op1*op2)>>64
        if m_f3==OP_MUL_F3.MULHSU:
            return (s_op1*op2)>>64
        else:
            raise Exception(f"M extension f3 {m_f3} not implemented")
        
    elif f3==OP_F3.ADD_SUB:
        if f7:
            return op1-op2
        else:
            return op1+op2    
    elif f3==OP_F3.AND:
        return op1 & op2
    elif f3==OP_F3.OR:
        return op1 | op2
    elif f3==OP_F3.XOR:
        return op1 ^ op2
    elif f3==OP_F3.SLT:
        return int_64(op1) < int_64(op2)
    elif f3==OP_F3.SLTU:
        return op1 < op2
    elif f3==OP_F3.SLL or f3==OP_F3.SRX:
        return shift_unit(op1, op2, f3, f7, op32)
    else:
        raise Exception(f"{f3} not implemented in ALU")
