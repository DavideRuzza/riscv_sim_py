import logging
from cpu_enums import *
from devices import MemoryDevice
from utils import *
from system_interface import SystemInterface
from logger_config import setup_logging
from pathlib import Path
from typing import List, Dict, Tuple
# from math import abs
# # Max allowed repeats within recent jumps
# MAX_JUMP_REPEAT = 20


def shift_unit(op, shamt, f3:OP_F3, f7:int, op32: bool=False):
    
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
        mf3 = OP_MUL_F3(f3.value)
        # print(hex(op1), hex(op2))
        # print(abs(int_64(op1)), abs(int_64(op2)))
        log.error(mf3)
        s_op1 = int_64(op1)
        s_op2 = int_64(op2)
        if mf3==OP_MUL_F3.DIV:
            s = sign(s_op1)*sign(s_op2) # find sign
            if op2==0: return -1
            else: return s*(abs(s_op1)//abs(s_op2))
        if mf3==OP_MUL_F3.DIVU:
            if op2==0: return -1
            else: return op1//op2
        if mf3==OP_MUL_F3.REM:
            s = sign(int_64(op1)) # find sign
            if op2==0: return op1
            else: return s*(abs(s_op1)%abs(s_op2))
        if mf3==OP_MUL_F3.REMU:                
            s = sign(int_64(op1)) # find sign
            if op2==0: return op1
            else: return op1%op2
        if mf3==OP_MUL_F3.MUL:
            return s_op1*s_op2
        if mf3==OP_MUL_F3.MULH:
            return (s_op1*s_op2)>>64
        if mf3==OP_MUL_F3.MULHU:
            return (op1*op2)>>64
        if mf3==OP_MUL_F3.MULHSU:
            return (s_op1*op2)>>64
        else:
            raise Exception(f"M extension f3 {mf3} not implemented")
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

def branch_unit(op1:int, op2:int, f3: BR_F3):
    if f3==BR_F3.BNE:
        return op1!=op2
    elif f3==BR_F3.BEQ:
        return op1==op2
    elif f3==BR_F3.BLT:
        return int_64(op1) < int_64(op2)
    elif f3==BR_F3.BGE:
        return int_64(op1) >= int_64(op2)
    elif f3==BR_F3.BGEU:
        return op1>=op2
    elif f3==BR_F3.BLTU:
        return op1<op2
    else:
        raise Exception(f"{f3} not implemented in Branch unit")
    
INSTR_BLK_MAP = {
    "opcode" : [6, 0],
    "I_f12" : [31,20],
    "I_f7" : [31,25],
    "I_f3" : [14,12],
    "I_rd" : [11,7],
    "I_rs1" : [19,15],
    "I_rs2" : [24,20],
    "I_csr" : [31,20]    
}

CINSTR_BLK_MAP = {
    "C_op":[1,0],
    "C_f2":[6,5],
    "C_f2_prime":[11,10],
    "C_f3":[15,13],
    "C_f4":[15,12],
    "C_f6":[15,10],
    "C_rd":[11,7],
    "C_rs1":[11,7],
    "C_rs2":[6,2],
    "C0_rd_prime":[4,2],
    "C1_rd_prime":[9,7],
    "C_rs1_prime":[9,7],
    "C_rs2_prime":[4,2],
    "C_jump_target":[12,2],
}



class RV64Hart():
    
    xlen=64
    
    reg_names=['ze', 'ra', 'sp', 'gp', 'tp', 't0', 't1', 't2', 's0', 's1', 
    'a0', 'a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'a7', 's2',
    's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 
    't3', 't4', 't5', 't6']

    def __init__(self, 
            hartid, 
            bus: SystemInterface = None, 
            extension_list: List[Ext] = [],
            entry_point = 0x8000_0000,
            to_host_addr = 0x8000_1000):
        
        
        self.mask64 = 0xffff_ffff_ffff_ffff
        self.mask32 = 0xffff_ffff
        self.mask16 = 0xffff

        self.hartid : int = hartid
        self.sys_bus = bus
        self.ext_list : List[Ext] = [Ext.M]+extension_list
        
        self.regfile = RegFile(32, self.xlen, self.reg_names)
        self.csr = CsrFile(self.ext_list)
        self.pc_rst = entry_point
        
        self.mode = Mode.M
        self.pc = entry_point
        
        self.exception_list : List[ExceptionCode] = []
        self.to_host_addr = to_host_addr
        
        # ------------- control variable value
        self.new_pc = 0
        self.write_back = False
        self.write_csr = False
        self.inst_ret = True
        self.cnt_cycle = True
        self.breakpoint_addr = 0 #0x8000_0218
        
        # ------------- SETUP CSR
        self.csr.misa.Extensions = sum([e.value for e in self.ext_list])
        
        self.csr.misa.MXL = 0b10 # for 64bit
        self.csr.mhartid = self.hartid
        self.csr.mstatus.MPP = self.mode.value # set M mode state
        
        self.csr.mstatus.add_warl_to_blk('MPP', Mode.M.value)
        
        if self.is_ext_impl(Ext.S) : 
            self.csr.mstatus.SXL = 2 # for 64bit s-mode
            self.csr.mstatus.add_warl_to_blk("SXL", 2)
            self.csr.mstatus.add_warl_to_blk('MPP', Mode.S.value)
            
        if self.is_ext_impl(Ext.U) : 
            self.csr.mstatus.UXL = 2 # for 64bit u-mode
            self.csr.mstatus.add_warl_to_blk("UXL", 2)
            self.csr.mstatus.add_warl_to_blk('MPP', Mode.U.value)
            
        self.csr.mtvec.update_warl_blk("MODE", [0, 1]) # normal mode or vectored
        

        # self.terminate = False # used to stop the process whethever bad happends

    def set_breakpoint(self, brkpt):
        self.breakpoint_addr=brkpt
        
    def is_ext_impl(self, e: Ext):
        return (e in self.ext_list)

    def raiseException(self, e: ExceptionCode):
        self.exception_list.append(e)
        self.inst_ret = False
        
    def handleException(self):
        if len(self.exception_list)>0:
            e = self.exception_list.pop()
            
            medeleg = self.csr.medeleg.all
            
            # check if the exception is delegated to S mode
            deleg_cond = (medeleg>>e.value)&0b1

            log.error(f"--- Exception : {e.name}, Handle: {"S" if deleg_cond else "M"} ---")

            if deleg_cond:
                self.csr.sepc.all = self.pc
                self.new_pc = self.csr.stvec.BASE<<2
                
                # check for vectored exception
                if self.csr.stvec.MODE==1:
                    log.error("--- Vectored ---")
                    self.new_pc += 4*e.value
                
                self.csr.scause.INT = 0b0 # is an exception, not an interrupt
                self.csr.scause.CODE = e.value
                self.csr.sstatus.SPP = self.mode.value
                
                self.mode = Mode.S
            else:
                self.csr.mepc.all = self.pc
                self.new_pc = self.csr.mtvec.BASE<<2
                
                # check for vectored exceptions
                if self.csr.mtvec.MODE==1:
                    log.error("--- Vectored ---")
                    self.new_pc += 4*e.value
                
                self.csr.mcause.INT = 0b0 # is an exception, not an interrupt
                self.csr.mcause.CODE = e.value
                self.csr.mstatus.MPP = self.mode.value
                
                self.mode = Mode.M

        return True

    def set_mode(self, mode: Mode):
        self.mode = mode
        
    def mret(self):
        self.csr.mstatus.MIE = self.csr.mstatus.MPIE
        self.csr.mstatus.MPIE = 1
        
        mpp = self.csr.mstatus.MPP
        
        if (mpp == 0b00):
            self.set_mode(Mode.U)
        elif (mpp == 0b01):
            self.set_mode(Mode.S)
        elif (mpp == 0b11):
            self.set_mode(Mode.M)
        
        # print("IMPL", self.is_ext_impl(Ext.U))
        self.csr.mstatus.MPP = 0b00 if self.is_ext_impl(Ext.U) else 0b11
        return self.csr.mepc.all
    
    def sret(self):
        self.csr.sstatus.SIE = self.csr.sstatus.SPIE
        self.csr.sstatus.SPIE = 1
        
        spp = self.csr.sstatus.SPP
        
        if spp==1:
            self.set_mode(Mode.S)
        else:
            self.set_mode(Mode.U)

        self.csr.mstatus.SPP = 0b0
        return self.csr.sepc.all
     
    def step(self):
        
        # ---------------------------- FETCH --------------------------------- #
        ins = BlockReg(32, self.sys_bus.read(self.pc), INSTR_BLK_MAP)
        
        pc_plus_4 = self.pc+4
        pc_plus_2 = self.pc+2
        
        self.new_pc = pc_plus_4
        
        new_rd = 0
        
        csr_key = 0
        new_csr = 0
        
        self.write_back = False
        self.write_csr = False
        
        self.inst_ret = True
        self.cnt_cycle = True
        
        is_compressed = False
        
        # ------------------------------ DECODE ------------------------------ #


        # ---------------- 16 bit to 32 bit stage translation ---------------- #
        
        if ins[1:0] != 0b11:
            
            new_ins = BlockReg(32, 0, INSTR_BLK_MAP)
            if new_ins[:] != 0:
                
                new_ins.opcode=Ops.OP_IMM.value
                base_reg = 0x8
                # decode and create the 32 version of this compressed instruction
                is_compressed = True
                
                ins_c = BlockReg(16, ins.all&self.mask16, CINSTR_BLK_MAP)
                
                c_opcode = Ops_C((ins_c.C_f3<<2) | (ins_c.C_op))
                log.warning(c_opcode)
                
                # is_op_imm=False
                if   c_opcode==Ops_C.ADDI4SPN:
                    i_imm = (ins_c[12:11]<<4) | (ins_c[10:7]<<6) | (ins_c[6]<<2) | (ins_c[5]<<3)
                    new_ins.I_rd = ins_c.C0_rd_prime+base_reg # from stack pointer
                    new_ins.I_rs1 = 2 # from stack pointer
                    new_ins.opcode = Ops.OP_IMM.value             
                elif c_opcode==Ops_C.LUI_ADDI16SP:
                    if ins_c.C_rd!=2: # is a LUI
                        log.warning("-> LUI")
                        u_imm = sign_extend((ins_c[12]<<17) | (ins_c[6:2]<<12), 18)
                        new_ins.I_rd = ins_c.C_rd
                        new_ins.opcode = Ops.LUI.value
                    else: #is add 16
                        log.warning("-> ADDI16SP")
                        i_imm = sign_extend((ins_c[12]<<9)|(ins_c[6]<<4)|\
                            (ins_c[5]<<6)|(ins_c[4:3]<<7)|(ins_c[2]<<5), 10)
                        new_ins.I_rs1 = 2 # from stack pointer
                        new_ins.I_rd = 2 # from stack pointer
                        new_ins.opcode = Ops.OP_IMM.value
                elif c_opcode==Ops_C.LI:
                    i_imm = sign_extend((ins_c[12]<<5) | (ins_c[6:2]), 6)
                    if ins_c.C_rd!=0:
                        new_ins.I_rd = ins_c.C_rd
                        new_ins.I_rs1 = 0
                        new_ins.opcode = Ops.OP_IMM.value
                elif c_opcode==Ops_C.ADDI:
                    i_imm = sign_extend((ins_c[12]<<5) | (ins_c[6:2]), 6)
                    if ins_c.C_rd!=0 and i_imm!=0:
                        new_ins.I_rd = ins_c.C_rd
                        new_ins.I_rs1 = new_ins.I_rd
                        new_ins.opcode = Ops.OP_IMM.value
                elif c_opcode==Ops_C.ADDIW:
                    i_imm = sign_extend((ins_c[12]<<5) | (ins_c[6:2]), 6)
                    if ins_c.C_rd!=0:
                        new_ins.I_rd = ins_c.C_rd
                        new_ins.I_rs1 = new_ins.I_rd
                        new_ins.opcode = Ops.OP_IMM_32.value
                elif c_opcode in [Ops_C.LW, Ops_C.LD]: # LOAD
                    if c_opcode==Ops_C.LW:
                        new_ins.I_f3 = 0b010
                        i_imm = (ins_c[12:10]<<3)|(ins_c[6]<<2)|(ins_c[5]<<6)
                    elif c_opcode==Ops_C.LD:
                        new_ins.I_f3 = 0b011
                        i_imm = (ins_c[12:10]<<3)|(ins_c[6:5]<<6)
                    new_ins.I_rd = ins_c.C0_rd_prime+base_reg
                    new_ins.I_rs1 = ins_c.C_rs1_prime+base_reg
                    new_ins.opcode = Ops.LOAD.value
                elif c_opcode in [Ops_C.LWSP, Ops_C.LDSP]: # LOAD
                    if c_opcode==Ops_C.LWSP:
                        new_ins.I_f3 = 0b010
                        i_imm = (ins_c[12]<<5)|(ins_c[6:4]<<2)|(ins_c[3:2]<<6)
                    elif c_opcode==Ops_C.LDSP:
                        new_ins.I_f3 = 0b011
                        i_imm = (ins_c[12]<<5)|(ins_c[6:5]<<3)|(ins_c[4:2]<<6)
                    new_ins.I_rd = ins_c.C_rd
                    new_ins.I_rs1 = 2
                    new_ins.opcode = Ops.LOAD.value
                elif c_opcode in [Ops_C.SW, Ops_C.SD]: # STORE
                    if c_opcode==Ops_C.SW:
                        new_ins.I_f3 = 0b010
                        s_imm = (ins_c[12:10]<<3)|(ins_c[6]<<2)|(ins_c[5]<<6)
                    elif c_opcode==Ops_C.SD:
                        new_ins.I_f3 = 0b011
                        s_imm = (ins_c[12:10]<<3)|(ins_c[6:5]<<6) 
                    new_ins.I_rs2 = ins_c.C_rs2_prime+base_reg
                    new_ins.I_rs1 = ins_c.C_rs1_prime+base_reg
                    new_ins.opcode = Ops.STORE.value
                elif c_opcode in [Ops_C.SWSP, Ops_C.SDSP]: # STORE
                    if c_opcode==Ops_C.SWSP:
                        new_ins.I_f3 = 0b010
                        s_imm = (ins_c[12:9]<<2)|(ins_c[8:7]<<6)
                    elif c_opcode==Ops_C.SDSP:
                        new_ins.I_f3 = 0b011
                        s_imm = (ins_c[12:10]<<3)|(ins_c[9:7]<<6) 
                    new_ins.I_rs2 = ins_c.C_rs2
                    new_ins.I_rs1 = 2
                    new_ins.opcode = Ops.STORE.value
                elif c_opcode==Ops_C.MISC_ALU:
                    if ins_c.C_f2_prime in [0b00, 0b01, 0b10]: # SRLI, SRAI, ANDI
                        i_imm = (ins_c[12]<<5)|(ins_c[6:2])
                        new_ins.I_rd = ins_c.C1_rd_prime+base_reg
                        new_ins.I_rs1 = new_ins.I_rd
                        if ins_c.C_f2_prime==0b10: # ANDI
                            new_ins.I_f3 = OP_F3.AND.value
                            i_imm = sign_extend(i_imm, 6)
                            log.warning( "-> ANDI")
                        else:
                            new_ins.I_f3 = OP_F3.SRX.value
                            new_ins.I_f7 = 0x20 if ins_c.C_f2_prime==0b01 else 0b0 # f7=0 when srli
                            log.warning( "-> SRAI" if ins_c.C_f2_prime==0b01 else "-> SRLI")
                        new_ins.opcode = Ops.OP_IMM.value
                    else:
                        misc_alu_op = MISC_ALU_OP((ins_c[12]<<2)|(ins_c[6:5]))
                        new_ins.I_rd = ins_c.C1_rd_prime+base_reg
                        new_ins.I_rs1 = new_ins.I_rd
                        new_ins.I_rs2 = ins_c.C_rs2_prime+base_reg
                        
                        op32 = False
                        if misc_alu_op==MISC_ALU_OP.SUB:
                            new_ins.I_f3 = OP_F3.ADD_SUB.value
                            new_ins.I_f7 = 0x20
                            log.warning( "-> SUB")
                        elif misc_alu_op==MISC_ALU_OP.XOR:
                            new_ins.I_f3 = OP_F3.XOR.value
                            log.warning( "-> XOR")
                        elif misc_alu_op==MISC_ALU_OP.OR:
                            new_ins.I_f3 = OP_F3.OR.value
                            log.warning( "-> OR")
                        elif misc_alu_op==MISC_ALU_OP.AND:
                            new_ins.I_f3 = OP_F3.AND.value
                            log.warning( "-> AND")
                        elif misc_alu_op==MISC_ALU_OP.ADDW:
                            new_ins.I_f3 = OP_F3.ADD_SUB.value
                            log.warning( "-> ADDW")
                            op32=True
                        elif misc_alu_op==MISC_ALU_OP.SUBW:
                            new_ins.I_f3 = OP_F3.ADD_SUB.value
                            new_ins.I_f7 = 0x20
                            log.warning( "-> SUBW")
                            op32=True
                        else:
                            log.error(f"Misc mem {misc_alu_op} not defined")
                            return False
                        if op32:
                            new_ins.opcode = Ops.OP_32.value
                        else:
                            new_ins.opcode = Ops.OP.value
                elif c_opcode==Ops_C.SLLI:
                    i_imm = (ins_c[12]<<5)|(ins_c[6:2])
                    if ins_c.C_rd!=0:
                        new_ins.I_rd = ins_c.C_rd
                        new_ins.I_rs1 = new_ins.I_rd
                        new_ins.I_f3 = OP_F3.SLL.value
                        log.warning( "-> SLLI")
                        new_ins.opcode = Ops.OP_IMM.value
                elif c_opcode==Ops_C.J:
                    j_imm=(ins_c[12]<<11)|(ins_c[11]<<4)|(ins_c[10:9]<<8)|\
                        (ins_c[8]<<10)|(ins_c[7]<<6)|(ins_c[6]<<7)|(ins_c[5:3]<<1)|\
                        (ins_c[2]<<5)
                    j_imm=sign_extend(j_imm, 12)
                    new_ins.opcode=Ops.JAL.value
                    new_ins.I_rd = 0
                elif c_opcode in [Ops_C.BEQZ, Ops_C.BNEZ]:
                    b_imm=(ins_c[12]<<8)|(ins_c[11:10]<<3)|(ins_c[6:5]<<6)|\
                        (ins_c[4:3]<<1)|(ins_c[2]<<5)
                    b_imm=sign_extend(b_imm, 12)
                    new_ins.opcode = Ops.BRANCH.value
                    new_ins.I_f3 = BR_F3.BEQ.value if c_opcode==Ops_C.BEQZ else BR_F3.BNE.value
                    new_ins.I_rd = 0
                    new_ins.I_rs1 = ins_c.C_rs1_prime+base_reg
                    new_ins.I_rs2 = 0
                    log.warning("-> BEQZ" if c_opcode==Ops_C.BEQZ else "BNEZ")
                elif c_opcode==Ops_C.JAL_JALR_MV_ADD:
                    if ins_c.C_rs2==0:
                        if ins_c[12]==0:
                            log.warning("-> JR")
                            new_ins.opcode=Ops.JALR.value
                            new_ins.I_rs1 = ins_c.C_rs1
                            new_ins.I_rd = 0
                            i_imm=0
                        else:
                            if ins_c.C_rs1!=0:
                                log.warning("-> JALR")
                                new_ins.opcode=Ops.JALR.value
                                new_ins.I_rs1 = ins_c.C_rs1
                                new_ins.I_rd = 1
                                i_imm=0
                            else:
                                log.warning("-> BREAK")
                                new_ins.I_f12 = 0b1
                                new_ins.opcode=Ops.SYSTEM.value
                    else:
                        new_ins.opcode=Ops.OP.value
                        new_ins.I_f3 = OP_F3.ADD_SUB.value
                        new_ins.I_f7 = 0
                        new_ins.I_rs2 = ins_c.C_rs2
                        new_ins.I_rd = ins_c.C_rd
                        if ins_c[12]==0: # MV
                            log.warning("-> MV")
                            new_ins.I_rs1 = 0
                        else: # ADD
                            log.warning("-> ADD")
                            new_ins.I_rs1 = new_ins.I_rd
                else:
                    log.error(f"compressed Opcode {c_opcode} not defined")
                    return False
                
                self.new_pc = pc_plus_2
                
                ins = new_ins
        
        # -------------------- 32 bit instruction decoder -------------------- #
        
        op = Ops(ins.opcode)
        if op==Ops.ILLEGAL: self.raiseException(ExceptionCode.IllegalInstruction)
        self.handleException()
        log.info(f"{self.pc:08x} {op.name}")
                
        r1 = self.regfile[ins.I_rs1]
        r2 = self.regfile[ins.I_rs2]
        
        if not is_compressed:
            i_imm = sign_extend(ins[31:20], 12) & self.mask64
            s_imm = sign_extend(ins[31:25]<<5 | ins[11:7], 12) & self.mask64
            b_imm = sign_extend(ins[31]<<12 | ins[7]<<11 | \
                ins[30:25]<<5 | ins[11:8] << 1, 12) & self.mask64
            u_imm = sign_extend(ins[31:12]<<12, 32) & self.mask64
            j_imm = sign_extend(ins[31]<<20 | ins[19:12]<<12 | \
                ins[20]<<11 | ins[30:21] << 1, 20) & self.mask64
        
        # ---------------------------- EXECUTE ------------------------------- #
        
        if op in [Ops.JAL, Ops.OP, Ops.OP_32, Ops.OP_IMM, Ops.JALR,
                    Ops.OP_IMM_32, Ops.AUIPC, Ops.LUI, Ops.LOAD ]:
            self.write_back=True
        
        if op==Ops.ILLEGAL:
            self.raiseException(ExceptionCode.IllegalInstruction) 
        elif op==Ops.JAL:
            new_rd = self.new_pc
            self.new_pc = self.pc+j_imm
        elif op==Ops.JALR:
            new_rd = self.new_pc
            self.new_pc = (r1 + i_imm) & (self.mask64-1)
        elif op==Ops.OP:
            # print(ins.I_rs1, ins.I_rs2)
            new_rd = alu(r1, r2, OP_F3(ins.I_f3), ins.I_f7, False, False)
        elif op==Ops.OP_32:
            f3 = OP_F3(ins.I_f3)
            res32 = alu(r1, r2, f3, ins.I_f7, True, False) 
            new_rd = sign_extend(res32 & self.mask32, 32)
        elif op==Ops.OP_IMM:
            
            f3 = OP_F3(ins.I_f3)
            cond = (f3!=OP_F3.ADD_SUB) or (f3==OP_F3.SRX)
            f7 = ins.I_f7 if cond else 0
            # if f3==OP_F3.SRX:# for SRAI and SRLI f7 is actually only the top 6 bits
            #     f7 >>= 1
            new_rd = alu(r1, i_imm, f3, f7, False, True)          
        elif op==Ops.OP_IMM_32:
            f3 = OP_F3(ins.I_f3)
            cond = (f3!=OP_F3.ADD_SUB) or (f3==OP_F3.SRX)
            f7 = ins.I_f7 if cond else 0
            # if f3==OP_F3.SRX: 
            #     f7 >>= 1
            res32 = alu(r1, i_imm, f3, f7, True, True) 
            new_rd = sign_extend(res32 & self.mask32, 32)            
        elif op==Ops.BRANCH:
            if branch_unit(r1, r2, BR_F3(ins.I_f3)):
                log.info("taken")
                self.new_pc = self.pc + b_imm
            else:
                log.info("not taken")
        elif op==Ops.AUIPC:
            new_rd = self.pc + u_imm
        elif op==Ops.LUI:
            new_rd = u_imm
        elif op==Ops.MISC_MEM:
            pass
        elif op==Ops.STORE:
            addr = ( r1 + s_imm) & self.mask64  
            if (addr == self.to_host_addr):
                log.error("__to_host__")
                return False
            self.sys_bus.write(addr, r2, 1<<ins.I_f3)
        elif op==Ops.LOAD:
            addr = ( r1 + i_imm) & self.mask64
            # LBU, LHU, LWU are just the same but with the bit 0b100
            size_byte = 1<<(ins.I_f3&0b11) 
            
            if addr%size_byte!=0:
                log.debug(f"load addr: {addr:08x}")
                self.raiseException(ExceptionCode.LoadAddressMisaligned)
                self.write_back = False
            else:
                new_rd = self.sys_bus.read(addr, size_byte)
                f3_l = LD_F3(ins.I_f3)
                # print(size_byte)
                if not (f3_l==LD_F3.LBU or f3_l==LD_F3.LHU or f3_l==LD_F3.LWU):
                    new_rd = sign_extend(new_rd, size_byte*8)         
        elif op==Ops.SYSTEM:
            if ins.I_f3 == 0:
                f12 = SYS_F12(ins.I_f12)
                if f12==SYS_F12.MRET:
                    log.error("--MRET--")
                    self.new_pc = self.mret()
                elif f12==SYS_F12.SRET:
                    log.error("--SRET--")
                    self.new_pc = self.sret()
                elif f12==SYS_F12.ECALL:
                    log.error("--ECALL--")
                    if (self.mode==Mode.M): self.raiseException(ExceptionCode.Mcall)
                    elif (self.mode==Mode.S): self.raiseException(ExceptionCode.Scall)
                    elif (self.mode==Mode.U): self.raiseException(ExceptionCode.Ucall)
                else:                    
                    log.error(f" {f12} Not Implemented")
                    return False
            else:
                f3 = CSR_F3(ins.I_f3)
                csr_key = ins.I_f12
                new_csr = None
                # read csr if the mode allows
                
                csr = self.csr[csr_key]
                if csr.priv.value <= self.mode.value:
                    csr_value = csr.all
                    new_rd = csr_value
                    self.write_back = True
                
                    # immediate csr instruction differs from the 2 bit in f3
                    # for I instruction instead of the content of r1 they use 
                    # r1 position as immediate
                    is_imm_csr = bool(f3.value>>2)
                    value = ins.I_rs1 if is_imm_csr else r1
                    
                    csrsrc_cond = (not is_imm_csr and (ins.I_rs1 != 0)) or \
                                    (is_imm_csr and value != 0)
                                    
                    if (f3 == CSR_F3.CSRRS) or (f3 == CSR_F3.CSRRSI):
                        log.info("CSRRS")
                        if csrsrc_cond:
                            new_csr = csr_value | value
                            self.write_csr = True
                    elif (f3 == CSR_F3.CSRRC) or (f3 == CSR_F3.CSRRCI):
                        log.info("CSRRC")
                        if csrsrc_cond:
                            clear_bit_mask = (~value) & self.mask64
                            new_csr = csr_value & clear_bit_mask
                            self.write_csr = True  
                    elif (f3 == CSR_F3.CSRRW) or (f3 == CSR_F3.CSRRWI):
                        log.info("CSRRW")
                        new_csr = value
                        self.write_csr = True    
                    else:
                        raise Exception(f'CSR OP {f3} not defined')
                else:
                    log.error("not enough priviledge")
                    self.raiseException(ExceptionCode.IllegalInstruction)
        else:
            # raise Exception(f"{op} not implemented")
            log.error("Not Implemented")
            return False
        
        self.handleException()
        
        if self.write_csr:
            if self.csr[csr_key].rw != 0b11: # is read-only
                self.csr[csr_key].all = new_csr
                
                if self.csr.addr_to_name[csr_key] == "minstret":
                    self.inst_ret = False
            else:
                self.write_back = False
                self.raiseException(ExceptionCode.IllegalInstruction)
        
        self.handleException()

        if self.write_back:
            log.info(f"write reg - {self.reg_names[ins.I_rd]} <- {hex(new_rd&self.mask64)}")
            self.regfile[ins.I_rd] = new_rd
            
            # print(hex(self.csr['mtvec'][1:0]))
            # print(self.regfile)
        
        if self.inst_ret:
            if self.csr['mcountinhibit']._blocks['IR'].val == 0:
                self.csr.minstret[:] = self.csr.minstret[:] + 1  # = self.csr.minstret.all+1
            
        if self.cnt_cycle:
            if self.csr['mcountinhibit']._blocks['CY'].val == 0:
                self.csr.cycle[:] = self.csr.cycle[:] + 1  # = self.csr.minstret.all+1
            
        if self.pc==self.breakpoint_addr:
            log.error("-- Breakpoint --")
            print(f"self.new_pc: 0x{(self.new_pc & self.mask64):8x}")
            return False
        
        self.pc = self.new_pc & self.mask64
        
        return True
        
# setup_logging(logging.DEBUG)
setup_logging(logging.CRITICAL)

log = logging.getLogger(__name__)
input_path = Path("tests/rv64/bin/p")

tests = sorted(list(input_path.glob("rv64um-p-*.bin")))
length = [len(str(t.stem)) for t in tests]


# tests = [Path("tests/rv64/bin/p/rv64um-p-div.bin")]
# tests = [Path("xv6-riscv/kernel.bin")]
# tests = [tests[10]]
RISCV_TEST = True
DEBUG = 0

for test in tests:
    print(f"{COL['r']}{str(test.stem):<20s}{COL['rst']}", end='', flush=True)
    ram = MemoryDevice.from_binary_file(test, "RAM")
    sys_bus = SystemInterface()
    sys_bus.register_device(ram, 0x8000_0000)
    if RISCV_TEST:
        to_host_addr = get_symbol_info("tests/rv64/elf/p/"+test.stem, 'tohost')['address']
    else:
        to_host_addr=0
    
    h0 = RV64Hart(0, sys_bus, [Ext.S, Ext.U, Ext.C], to_host_addr=to_host_addr)

    break_debug=True
    while(h0.step() and break_debug):
        if DEBUG:
            while True: # Debugger
                cmd = input("> ")
                cmd : List[str] = [c.lower() for c in cmd.strip().split(" ")]
                
                if cmd[0]=="q" or cmd[0]=="quit":
                    print("Exiting CPU loop.")
                    break_debug=False
                    break 
                elif cmd[0]=="priv":
                    print(h0.mode)
                elif cmd[0]=="reg":
                    if len(cmd)>1:
                        if cmd[1].isnumeric():
                            if int(cmd[1])<32:
                                reg_name = h0.reg_names[int(cmd[1])]
                                print(f"{reg_name}: {h0.regfile[int(cmd[1])]:016x}\n")
                            else:
                                print(f"No reg x{cmd[1]}\n")
                        else:
                            if cmd[1] in h0.reg_names:
                                print(f"{cmd[1]}: 0x{h0.regfile[h0.reg_names.index(cmd[1])]:016x}\n")
                            else:
                                print(f"No reg named {cmd[1]}\n")
                    else:
                        print(h0.regfile)
                elif cmd[0]=="":
                    break
                elif cmd[0]=="br":
                    if len(cmd)>1:
                        h0.set_breakpoint(int(cmd[1], 16))
                        while(h0.step()):pass
                        h0.set_breakpoint(0)
                    break
        else: pass
        
    syscall_code = h0.regfile[17]
    syscall_data = h0.regfile[10] 
    if syscall_code==93: # exit code
        if syscall_data == 0:
            print(" ✅ Test PASSED")
        else:
            print(f" ❌ Test FAILED: {syscall_data>>1}")
    else:
        print(f"{COL['g']} sys_code = {syscall_code}, sys_data = {syscall_data}, ")
    
    del h0

# csr = CsrFile([Ext.M])
# csr.mstatus.update_warl_blk("MPP", [1, 2, 3])
# csr.mepc.all=0x800001a8
# print(hex(csr.mepc.all))
# csr.mstatus.MPP = 1
# # print(csr.mstatus.blk_wpri)
# # print(bin(csr.mstatus.gen_wpri_mask()))
# # print(bin(csr.mstatus.gen_wpri_mask(True)))
# # print(bin(csr.mstatus.gen_blk_mask('MPP')))
# print(csr.mstatus.all)
# csr.sstatus.all = 0xffff_ffff_ffff_ffff
# print(bin(csr.mstatus.all))
# print(bin(csr.sstatus.all))
# print(bin(csr.mstatus.all))

# print(h0.csr)
# print(hex(h0.pc))
# hex(sys_bus.read(0x80000000, 4))
# print(hex(ram.read(0x00002000, 8)))
# csr = CSRFile([Ext.M])
# print(csr)
# csr['mhartid'] = 10

# import logging
# from devices import MemoryDevice
# from system_interface import SystemInterface
# from logger_config import setup_logging

# setup_logging(logging.DEBUG)
# log = logging.getLogger(__name__)
# ram =  MemoryDevice.from_binary_file("tests/rv32/bin/p/rv32mi-p-csr.bin", "RAM")
# sys_bus = SystemInterface()
# sys_bus.register_device(ram, 0x8000_0000)
 
# print(sys_bus)

# sys_bus.write(0x8000_0000, 0xaaaa_aaaa)
# # print(hex(sys_bus.read(0x8000_2010, 1)))

# ram.hexdump()
