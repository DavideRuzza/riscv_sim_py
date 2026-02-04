import logging
from cpu_enums import *
from devices import MemoryDevice, CLINT, InterruptController
from utils import *
from system_interface import SystemInterface
from logger_config import setup_logging
from pathlib import Path
from typing import List, Dict, Tuple
from FPU32 import FPU, pack_f32, pack_fflags, qNaNf
from operators import alu
from com import UART16550
import traceback
import datetime
from pyinstrument import Profiler


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
    "I_f5" : [31,27],
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

class Instruction(Reg):
    INSTR_BLK_MAP = {
        "opcode": [6, 0],
        "I_f12": [31, 20],
        "I_f7": [31, 25],
        "I_f5": [31, 27],
        "I_f3": [14, 12],
        "I_rd": [11, 7],
        "I_rs1": [19, 15],
        "I_rs2": [24, 20],
        "I_csr": [31, 20]
    }
    
    def __init__(self, value):
        super().__init__(32, value)
    
    def __getattr__(self, name):
        if name in self.INSTR_BLK_MAP:
            high, low = self.INSTR_BLK_MAP[name]
            # Extract bits from high to low (inclusive)
            mask = (1 << (high - low + 1)) - 1
            return (self.reg >> low) & mask
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


class RV64Hart():
    
    xlen=64
    
    reg_names=['ze', 'ra', 'sp', 'gp', 'tp', 't0', 't1', 't2', 's0', 's1', 
    'a0', 'a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'a7', 's2',
    's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 
    't3', 't4', 't5', 't6']
    
    fp_reg_names=[
        'ft0', 'ft1', 'ft2', 'ft3', 'ft4', 'ft5', 'ft6', 'ft7',
        'fs0', 'fs1', 
        'fa0', 'fa1', 'fa2', 'fa3', 'fa4', 'fa5', 'fa6', 'fa7',
        'fs2', 'fs3', 'fs4', 'fs5', 'fs6', 'fs7', 'fs8', 'fs9', 'fs10', 'fs11',
        'ft8', 'ft9', 'ft10', 'ft11'
    ]
    
    OPS = {
        0b00_000_00: "ILLEGAL",
        0b00_000_11: "LOAD",
        0b01_000_11: "STORE",
        0b10_000_11: "FMADD",
        0b11_000_11: "BRANCH",
        0b00_001_11: "LOAD_FP",
        0b01_001_11: "STORE_FP",
        0b10_001_11: "FMSUB",
        0b11_001_11: "JALR",
        0b00_010_11: "custom0",
        0b01_010_11: "custom1",
        0b10_010_11: "FMNSUB",
        0b00_011_11: "MISC_MEM",
        0b01_011_11: "AMO",
        0b10_011_11: "FNMADD",
        0b11_011_11: "JAL",
        0b00_100_11: "OP_IMM",
        0b01_100_11: "OP",
        0b10_100_11: "OP_FP",
        0b11_100_11: "SYSTEM",
        0b00_101_11: "AUIPC",
        0b01_101_11: "LUI",
        0b10_101_11: "OP_V",
        0b11_101_11: "OP_VE",
        0b00_110_11: "OP_IMM_32",
        0b01_110_11: "OP_32",
        0b10_110_11: "custom2",
        0b11_110_11: "custom3",
    }
    
    
    # write_back_inst = [Ops.JAL, Ops.OP, Ops.OP_32, Ops.OP_IMM, Ops.JALR,
    #                 Ops.OP_IMM_32, Ops.AUIPC, Ops.LUI, Ops.LOAD, Ops.AMO]
    
    write_back_inst = ["JAL", "OP", "OP_32", "OP_IMM", "JALR",
                    "OP_IMM_32", "AUIPC", "LUI", "LOAD", "AMO"]
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
        self.fp_regfile = RegFile(32, self.xlen, self.fp_reg_names, lock_0=False)
        
        self.csr = CsrFile(self.ext_list)
        self.pc_rst = entry_point
        
        self.mode = Mode.M
        self.pc = entry_point
        
        self.exception_list : List[ExceptionCode] = []
        self.to_host_addr = to_host_addr
        
        self.wait_mode = False
        
        self.ins = Instruction(0) #BlockReg(32, 0, INSTR_BLK_MAP) # initialize Block reg
        # ------------- control variable value
        self.new_pc = 0
        self.write_back = False
        self.write_csr = False
        self.to_float_reg = False
        self.inst_ret = True
        self.cnt_cycle = True
        self.breakpoint_addr = -1 # 0x8000_01fc
        self.store_breakpoint_addr = -1
        self.load_breakpoint_addr = -1
        
        self.instruction_profile = {n: 0 for n in self.OPS.values()}
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
        
        # -------------------- cache definition 
        # needs to be easy just array or dictionary
        # fully associative, word aligned
        N_WORD = 16 # -> 4 bit word id
        N_LINES = 512 # -> 9 bit line id
        # -> 32 - 4 - 9 - 2 (for word aligment) = 17 bit tag
        #
        # 31              15         6    2  0
        #  v               v         v    v  v
        #  ttttttttttttttttt lllllllll wwww aa
        # cache line : [valid bit, tag, [word1, word2, ...]]
        # when valid bit is set to 0 the cache line is not valid
        # self.cache = [[0, []] for ]

    def set_breakpoint(self, brkpt):
        self.breakpoint_addr=brkpt
    
    def set_store_breakpoint(self, brkpt):
        self.store_breakpoint_addr=brkpt
        
    def set_load_breakpoint(self, brkpt):
        self.load_breakpoint_addr=brkpt
        
    def is_ext_impl(self, e: Ext):
        return (e in self.ext_list)

    def raiseException(self, e: ExceptionCode):
        self.exception_list.append(e)
        self.inst_ret = False
    
    def handleException(self):
        if len(self.exception_list)>0:
            e = self.exception_list.pop()
            # print(f"code {e}, pc 0x{hex(self.pc)}")
            medeleg = self.csr.csr_map[0x302].reg.reg
            
            # check if the exception is delegated to S mode
            deleg_cond = (medeleg>>e.value)&0b1

            # -log.error(f"--- Exception : {e.name}, Handle: {"S" if deleg_cond else "M"} ---")

            if deleg_cond and self.mode!=Mode.M:
                self.csr.sepc.all = self.pc
                self.new_pc = self.csr.stvec.BASE<<2
                
                # check for vectored exception
                if self.csr.stvec.MODE==1:
                    # -log.error("--- Vectored ---")
                    self.new_pc += 4*e.value
                
                self.csr.scause.INT = 0b0 # is an exception, not an interrupt
                self.csr.scause.CODE = e.value
                self.csr.sstatus.SPP = self.mode.value
                
                self.set_mode(Mode.S)
            else:
                self.csr.mepc.all = self.pc
                self.new_pc = self.csr.mtvec.BASE<<2
                
                # check for vectored exceptions
                if self.csr.mtvec.MODE==1:
                    # -log.error("--- Vectored ---")
                    self.new_pc += 4*e.value
                
                self.csr.mcause.INT = 0b0 # is an exception, not an interrupt
                self.csr.mcause.CODE = e.value
                self.csr.mstatus.MPP = self.mode.value
                
                self.set_mode(Mode.M)

        return True

    def _find_highest_priority_interrupt(self, pending_mask, current_mode):
        """
        Find the highest priority pending interrupt.
        RISC-V interrupt priority (high to low):
        - MEI (11), MSI (3), MTI (7)  [Machine level]
        - SEI (9), SSI (1), STI (5)  [Supervisor level]
        
        priority order:  MEI, MSI, MTI, SEI, SSI, STI, LCOFI
        """
        # Check in priority order
        if current_mode == Mode.M:
            priority_order = [11, 3, 7, 9, 1, 5]  # M interrupts first
        else:
            priority_order = [9, 1, 5]  # S-delegated interrupts only
        
        for interrupt_code in priority_order:
            if (pending_mask >> interrupt_code) & 0b1:
                return interrupt_code
        
        return None
    
    def handleInterrupts(self):
        """
        Handle pending interrupts based on current privilege mode and CSR settings.
        Returns True if an interrupt was handled, False otherwise.
        
        Key behavior:
        - M-mode interrupts can interrupt S-mode code regardless of SIE
        - S-mode interrupts only interrupt S-mode code if delegated and SIE=1
        - In M-mode, only handle if MIE=1
        """
        
        
        if self.mode == Mode.M:
            # In M mode: check if M-mode interrupts are globally enabled
            # mie_enabled = self.csr.mstatus._blocks['MIE'].val  # MIE bit in mstatus
            # self.csr.csr_map[0x300].reg.reg
            # mie_enabled = self.csr.mstatus.reg.reg>>3 & 0x1 # faster
            mie_enabled = self.csr.csr_map[0x300].reg.reg>>3 & 0x1 # faster
            
            if not mie_enabled:
                return False
            
            # Get pending interrupts from mip
            # mip = self.csr.mip.reg.reg
            mip = self.csr.csr_map[0x344].reg.reg
            
            # Get interrupt delegation - which interrupts are delegated to S mode
            # mideleg = self.csr.mideleg.reg.reg
            mideleg = self.csr.csr_map[0x303].reg.reg
            
            # Get interrupt enable flags
            # mie = self.csr.mie.reg.reg
            mie = self.csr.csr_map[0x304].reg.reg
        
            # Handle M-mode interrupts (not delegated) that are pending and enabled
            pending = mip & mie & ~mideleg
        
        else:  # S mode
            # In S mode, we have two cases:
            # Get pending interrupts from mip
            # mip = self.csr.mip.reg.reg
            mip = self.csr.csr_map[0x344].reg.reg
            
            # Get interrupt delegation - which interrupts are delegated to S mode
            # mideleg = self.csr.mideleg.reg.reg
            mideleg = self.csr.csr_map[0x303].reg.reg
            
            # Get interrupt enable flags
            # mie = self.csr.mie.reg.reg
            mie = self.csr.csr_map[0x304].reg.reg
            
            # sie = self.csr.sie.reg.reg
            sie = self.csr.csr_map[0x104].reg.reg
            
            # Case 1: M-mode interrupts (not delegated)
            # These ALWAYS interrupt S mode, regardless of SIE
            m_mode_pending = mip & mie & ~mideleg
            
            if m_mode_pending != 0:
                # M-mode interrupt has priority, handle in M mode
                interrupt_code = self._find_highest_priority_interrupt(m_mode_pending, Mode.M)
                if interrupt_code is not None:
                    self._take_interrupt(interrupt_code, Mode.M)
                    return True
            
            # Case 2: S-mode delegated interrupts
            # These only interrupt if SIE=1 in sstatus
            # sie_enabled = self.csr.sstatus.reg.reg>>1 & 0x1 # SIE bit in sstatus
            sie_enabled = self.csr.csr_map[0x100].reg.reg>>1 & 0x1 # SIE bit in sstatus
            
            if not sie_enabled:
                return False
            
            # Handle S-mode delegated interrupts that are pending and enabled
            pending = mip & sie & mideleg
        
        if pending == 0:
            return False
        
        # Find highest priority interrupt
        interrupt_code = self._find_highest_priority_interrupt(pending, self.mode)
        
        if interrupt_code is None:
            return False
        
        self._take_interrupt(interrupt_code, self.mode)
        
        return True

    def _take_interrupt(self, interrupt_code, target_mode):
        """
        Take an interrupt and switch to the target privilege mode.
        """
        mideleg = self.csr.mideleg.value
        deleg_cond = (mideleg >> interrupt_code) & 0b1
        
        # -log.error(f"--- Interrupt: {InterruptCode(interrupt_code).name}, Handle: {"S" if deleg_cond else "M"} ---")
        
        if target_mode == Mode.S:
            # Handle in S mode
            self.csr.sepc.reg.reg = self.pc
            self.new_pc = self.csr.stvec.BASE << 2
            print(hex(self.new_pc))
            # Check for vectored interrupts
            if self.csr.stvec.MODE == 1:
                # -log.error("--- Vectored ---")
                self.new_pc += 4 * interrupt_code
            
            self.csr.scause.INT = 0b1  # This is an interrupt
            self.csr.scause.CODE = interrupt_code
            self.csr.sstatus.SPP = self.mode.value
            
            # Save the current SIE state to SPIE
            self.csr.sstatus.SPIE = self.csr.sstatus.SIE
            # Disable interrupts in S mode
            self.csr.sstatus.SIE = 0b0
            
            self.mode = Mode.S
        
        else:  # M mode
            # Handle in M mode
            self.csr.mepc.reg.reg = self.pc
            self.new_pc = self.csr.mtvec.BASE << 2
            print(hex(self.new_pc))
            # Check for vectored interrupts
            if self.csr.mtvec.MODE == 1:
                # -log.error("--- Vectored ---")
                self.new_pc += 4 * interrupt_code
            
            self.csr.mcause.INT = 0b1  # This is an interrupt
            self.csr.mcause.CODE = interrupt_code
            self.csr.mstatus.MPP = self.mode.value
            
            # Save the current MIE state to MPIE
            self.csr.mstatus.MPIE = self.csr.mstatus.MIE
            # Disable interrupts in M mode
            self.csr.mstatus.MIE = 0b0
            
            self.mode = Mode.M
        self.wait_mode = False
    
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
        
        if sys_bus.is_locked():
            return True
        
        # ---------------------------- FETCH --------------------------------- #
        # -log.debug(" - - - - - - - - - - ")
        # ins = BlockReg(32, self.sys_bus.read(self.pc), INSTR_BLK_MAP)
        
        raw_ins = self.sys_bus.read(self.pc)
        self.ins.reg = raw_ins
        ins = self.ins
        
        pc_plus_4 = self.pc+4
        # pc_plus_2 = self.pc+2
        
        self.new_pc = pc_plus_4
        
        new_rd = 0
        self.to_float_reg = False
        
        csr_key = 0
        new_csr = 0
        
        self.write_back = False
        self.write_csr = False
        
        
        self.inst_ret = True
        self.cnt_cycle = True
        
        # is_compressed = False
        
        
        if self.handleInterrupts():
            print("int after pc", hex(self.new_pc))
            self.pc = self.new_pc & self.mask64
            return True
        
        if self.wait_mode:
            # -log.error(f"-- WFI at {self.pc:08x}", )
            return True
        
        # ------------------------------ DECODE ------------------------------ #

        # ---------------- 16 bit to 32 bit stage translation ---------------- #
        
        # if ins[1:0] != 0b11:
        #     new_ins = BlockReg(32, 0, INSTR_BLK_MAP)
            
        #     if ins[15:0] != 0:
        #         # print("is Compressed")
                
        #         new_ins.opcode=Ops.OP_IMM.value
        #         base_reg = 0x8
        #         # decode and create the 32 version of this compressed instruction
        #         is_compressed = True
        #         ins_c = BlockReg(16, ins.all&self.mask16, CINSTR_BLK_MAP)
                
        #         # print((ins_c.C_f3<<2) | (ins_c.C_op))
        #         ins_c = BlockReg(16, ins.all&self.mask16, CINSTR_BLK_MAP)
        #         c_opcode = Ops_C((ins_c.C_f3<<2) | (ins_c.C_op))
        #         # -log.warning(c_opcode)
                
        #         # is_op_imm=False
        #         if c_opcode==Ops_C.ADDI4SPN:
        #             i_imm = (ins_c[12:11]<<4) | (ins_c[10:7]<<6) | (ins_c[6]<<2) | (ins_c[5]<<3)
        #             new_ins.I_rd = ins_c.C0_rd_prime+base_reg # from stack pointer
        #             new_ins.I_rs1 = 2 # from stack pointer
        #             new_ins.opcode = Ops.OP_IMM.value             
        #         elif c_opcode==Ops_C.LUI_ADDI16SP:
        #             if ins_c.C_rd!=2: # is a LUI
        #                 # -log.warning("-> LUI")
        #                 u_imm = sign_extend((ins_c[12]<<17) | (ins_c[6:2]<<12), 18)
        #                 new_ins.I_rd = ins_c.C_rd
        #                 new_ins.opcode = Ops.LUI.value
        #             else: #is add 16
        #                 # -log.warning("-> ADDI16SP")
        #                 i_imm = sign_extend((ins_c[12]<<9)|(ins_c[6]<<4)|\
        #                     (ins_c[5]<<6)|(ins_c[4:3]<<7)|(ins_c[2]<<5), 10)
        #                 new_ins.I_rs1 = 2 # from stack pointer
        #                 new_ins.I_rd = 2 # from stack pointer
        #                 new_ins.opcode = Ops.OP_IMM.value
        #         elif c_opcode==Ops_C.LI:
        #             i_imm = sign_extend((ins_c[12]<<5) | (ins_c[6:2]), 6)
        #             if ins_c.C_rd!=0:
        #                 new_ins.I_rd = ins_c.C_rd
        #                 new_ins.I_rs1 = 0
        #                 new_ins.opcode = Ops.OP_IMM.value
        #         elif c_opcode==Ops_C.ADDI:
        #             i_imm = sign_extend((ins_c[12]<<5) | (ins_c[6:2]), 6)
        #             if ins_c.C_rd!=0 and i_imm!=0:
        #                 new_ins.I_rd = ins_c.C_rd
        #                 new_ins.I_rs1 = new_ins.I_rd
        #                 new_ins.opcode = Ops.OP_IMM.value
        #         elif c_opcode==Ops_C.ADDIW:
        #             i_imm = sign_extend((ins_c[12]<<5) | (ins_c[6:2]), 6)
        #             if ins_c.C_rd!=0:
        #                 new_ins.I_rd = ins_c.C_rd
        #                 new_ins.I_rs1 = new_ins.I_rd
        #                 new_ins.opcode = Ops.OP_IMM_32.value
        #         elif c_opcode in [Ops_C.LW, Ops_C.LD]: # LOAD
        #             if c_opcode==Ops_C.LW:
        #                 new_ins.I_f3 = 0b010
        #                 i_imm = (ins_c[12:10]<<3)|(ins_c[6]<<2)|(ins_c[5]<<6)
        #             elif c_opcode==Ops_C.LD:
        #                 new_ins.I_f3 = 0b011
        #                 i_imm = (ins_c[12:10]<<3)|(ins_c[6:5]<<6)
        #             new_ins.I_rd = ins_c.C0_rd_prime+base_reg
        #             new_ins.I_rs1 = ins_c.C_rs1_prime+base_reg
        #             new_ins.opcode = Ops.LOAD.value
        #         elif c_opcode in [Ops_C.LWSP, Ops_C.LDSP]: # LOAD
        #             if c_opcode==Ops_C.LWSP:
        #                 new_ins.I_f3 = 0b010
        #                 i_imm = (ins_c[12]<<5)|(ins_c[6:4]<<2)|(ins_c[3:2]<<6)
        #             elif c_opcode==Ops_C.LDSP:
        #                 new_ins.I_f3 = 0b011
        #                 i_imm = (ins_c[12]<<5)|(ins_c[6:5]<<3)|(ins_c[4:2]<<6)
        #             new_ins.I_rd = ins_c.C_rd
        #             new_ins.I_rs1 = 2
        #             new_ins.opcode = Ops.LOAD.value
        #         elif c_opcode in [Ops_C.SW, Ops_C.SD]: # STORE
        #             if c_opcode==Ops_C.SW:
        #                 new_ins.I_f3 = 0b010
        #                 s_imm = (ins_c[12:10]<<3)|(ins_c[6]<<2)|(ins_c[5]<<6)
        #             elif c_opcode==Ops_C.SD:
        #                 new_ins.I_f3 = 0b011
        #                 s_imm = (ins_c[12:10]<<3)|(ins_c[6:5]<<6) 
        #             new_ins.I_rs2 = ins_c.C_rs2_prime+base_reg
        #             new_ins.I_rs1 = ins_c.C_rs1_prime+base_reg
        #             new_ins.opcode = Ops.STORE.value
        #         elif c_opcode in [Ops_C.SWSP, Ops_C.SDSP]: # STORE
        #             if c_opcode==Ops_C.SWSP:
        #                 new_ins.I_f3 = 0b010
        #                 s_imm = (ins_c[12:9]<<2)|(ins_c[8:7]<<6)
        #             elif c_opcode==Ops_C.SDSP:
        #                 new_ins.I_f3 = 0b011
        #                 s_imm = (ins_c[12:10]<<3)|(ins_c[9:7]<<6) 
        #             new_ins.I_rs2 = ins_c.C_rs2
        #             new_ins.I_rs1 = 2
        #             new_ins.opcode = Ops.STORE.value
        #         elif c_opcode==Ops_C.MISC_ALU:
        #             if ins_c.C_f2_prime in [0b00, 0b01, 0b10]: # SRLI, SRAI, ANDI
        #                 i_imm = (ins_c[12]<<5)|(ins_c[6:2])
        #                 new_ins.I_rd = ins_c.C1_rd_prime+base_reg
        #                 new_ins.I_rs1 = new_ins.I_rd
        #                 if ins_c.C_f2_prime==0b10: # ANDI
        #                     new_ins.I_f3 = OP_F3.AND.value
        #                     i_imm = sign_extend(i_imm, 6)
        #                     # -log.warning( "-> ANDI")
        #                 else:
        #                     new_ins.I_f3 = OP_F3.SRX.value
        #                     new_ins.I_f7 = 0x20 if ins_c.C_f2_prime==0b01 else 0b0 # f7=0 when srli
        #                     # -log.warning( "-> SRAI" if ins_c.C_f2_prime==0b01 else "-> SRLI")
        #                 new_ins.opcode = Ops.OP_IMM.value
        #             else:
        #                 misc_alu_op = MISC_ALU_OP((ins_c[12]<<2)|(ins_c[6:5]))
        #                 new_ins.I_rd = ins_c.C1_rd_prime+base_reg
        #                 new_ins.I_rs1 = new_ins.I_rd
        #                 new_ins.I_rs2 = ins_c.C_rs2_prime+base_reg
                        
        #                 op32 = False
        #                 if misc_alu_op==MISC_ALU_OP.SUB:
        #                     new_ins.I_f3 = OP_F3.ADD_SUB.value
        #                     new_ins.I_f7 = 0x20
        #                     # -log.warning( "-> SUB")
        #                 elif misc_alu_op==MISC_ALU_OP.XOR:
        #                     new_ins.I_f3 = OP_F3.XOR.value
        #                     # -log.warning( "-> XOR")
        #                 elif misc_alu_op==MISC_ALU_OP.OR:
        #                     new_ins.I_f3 = OP_F3.OR.value
        #                     # -log.warning( "-> OR")
        #                 elif misc_alu_op==MISC_ALU_OP.AND:
        #                     new_ins.I_f3 = OP_F3.AND.value
        #                     # -log.warning( "-> AND")
        #                 elif misc_alu_op==MISC_ALU_OP.ADDW:
        #                     new_ins.I_f3 = OP_F3.ADD_SUB.value
        #                     # -log.warning( "-> ADDW")
        #                     op32=True
        #                 elif misc_alu_op==MISC_ALU_OP.SUBW:
        #                     new_ins.I_f3 = OP_F3.ADD_SUB.value
        #                     new_ins.I_f7 = 0x20
        #                     # -log.warning( "-> SUBW")
        #                     op32=True
        #                 else:
        #                     # -log.error(f"Misc mem {misc_alu_op} not defined")
        #                     return False
        #                 if op32:
        #                     new_ins.opcode = Ops.OP_32.value
        #                 else:
        #                     new_ins.opcode = Ops.OP.value
        #         elif c_opcode==Ops_C.SLLI:
        #             i_imm = (ins_c[12]<<5)|(ins_c[6:2])
        #             if ins_c.C_rd!=0:
        #                 new_ins.I_rd = ins_c.C_rd
        #                 new_ins.I_rs1 = new_ins.I_rd
        #                 new_ins.I_f3 = OP_F3.SLL.value
        #                 # -log.warning( "-> SLLI")
        #                 new_ins.opcode = Ops.OP_IMM.value
        #         elif c_opcode==Ops_C.J:
        #             j_imm=(ins_c[12]<<11)|(ins_c[11]<<4)|(ins_c[10:9]<<8)|\
        #                 (ins_c[8]<<10)|(ins_c[7]<<6)|(ins_c[6]<<7)|(ins_c[5:3]<<1)|\
        #                 (ins_c[2]<<5)
        #             j_imm=sign_extend(j_imm, 12)
        #             new_ins.opcode=Ops.JAL.value
        #             new_ins.I_rd = 0
        #         elif c_opcode in [Ops_C.BEQZ, Ops_C.BNEZ]:                    
        #             b_imm=(ins_c[12]<<8)|(ins_c[11:10]<<3)|(ins_c[6:5]<<6)|(ins_c[4:3]<<1)|(ins_c[2]<<5)
        #             b_imm=sign_extend(b_imm, 8)
        #             # print("debuuugg: ", hex(b_imm), bin(b_imm), bin(ins_c[12:10]), bin(ins_c[6:2]),  int_64(b_imm))
        #             new_ins.opcode = Ops.BRANCH.value
        #             new_ins.I_f3 = BR_F3.BEQ.value if c_opcode==Ops_C.BEQZ else BR_F3.BNE.value
        #             new_ins.I_rd = 0
        #             new_ins.I_rs1 = ins_c.C_rs1_prime+base_reg
        #             new_ins.I_rs2 = 0
        #             # -log.warning("-> BEQZ" if c_opcode==Ops_C.BEQZ else "BNEZ")
        #         elif c_opcode==Ops_C.JAL_JALR_MV_ADD:
        #             if ins_c.C_rs2==0:
        #                 if ins_c[12]==0:
        #                     # -log.warning("-> JR")
        #                     new_ins.opcode=Ops.JALR.value
        #                     new_ins.I_rs1 = ins_c.C_rs1
        #                     new_ins.I_rd = 0
        #                     i_imm=0
        #                 else:
        #                     if ins_c.C_rs1!=0:
        #                         # -log.warning("-> JALR")
        #                         new_ins.opcode=Ops.JALR.value
        #                         new_ins.I_rs1 = ins_c.C_rs1
        #                         new_ins.I_rd = 1
        #                         i_imm=0
        #                     else:
        #                         # -log.warning("-> BREAK")
        #                         new_ins.I_f12 = 0b1
        #                         new_ins.opcode=Ops.SYSTEM.value
        #             else:
        #                 new_ins.opcode=Ops.OP.value
        #                 new_ins.I_f3 = OP_F3.ADD_SUB.value
        #                 new_ins.I_f7 = 0
        #                 new_ins.I_rs2 = ins_c.C_rs2
        #                 new_ins.I_rd = ins_c.C_rd
        #                 if ins_c[12]==0: # MV
        #                     # -log.warning("-> MV")
        #                     new_ins.I_rs1 = 0
        #                 else: # ADD
        #                     # -log.warning("-> ADD")
        #                     new_ins.I_rs1 = new_ins.I_rd
        #         else:
        #             # -log.error(f"compressed Opcode {c_opcode} not defined")
        #             return False
                
        #         self.new_pc = pc_plus_2
                
        #         ins = new_ins
        
        # -------------------- 32 bit instruction decoder -------------------- #
        
        # op = Ops(ins.opcode)
        # op_name = op.name
        op_name = self.OPS[ins.opcode]
        self.instruction_profile[op_name] += 1
        
        if op_name=="ILLEGAL": 
            self.raiseException(ExceptionCode.IllegalInstruction)
            self.handleException()
        # -log.info(f"{self.pc:08x} {op.name}")
        
        
        I_rs1 = (raw_ins>>15) & 0b11111
        I_rs2 = (raw_ins>>20) & 0b11111
        I_f5 = (raw_ins>>27) & 0b11111
        I_f3 = (raw_ins>>12) & 0b111
        I_f7 = (raw_ins>>25) & 0b1111111
        I_f12 = (raw_ins>>20) & 0b111111111111
        I_rd = (raw_ins>>7) & 0b11111
        
        r1 = self.regfile[I_rs1]
        r2 = self.regfile[I_rs2]
        
        # if not is_compressed:
        #     i_imm = sign_extend(ins[31:20], 12) & self.mask64
        #     s_imm = sign_extend(ins[31:25]<<5 | ins[11:7], 12) & self.mask64
        #     b_imm = sign_extend(ins[31]<<12 | ins[7]<<11 | \
        #         ins[30:25]<<5 | ins[11:8] << 1, 12) & self.mask64
        #     u_imm = sign_extend(ins[31:12]<<12, 32) & self.mask64
        #     j_imm = sign_extend(ins[31]<<20 | ins[19:12]<<12 | \
        #         ins[20]<<11 | ins[30:21] << 1, 20) & self.mask64
        
        # ---------------------------- EXECUTE ------------------------------- #
        
        # print(op.name)
        if op_name in self.write_back_inst:
            self.write_back=True   
        if   op_name=="OP_IMM":
            cond = (I_f3!=0) or (I_f3==0b101)
            f7 = I_f7 if cond else 0
            if I_f3==0b101:# for SRAI and SRLI f7 is actually only the top 6 bits
                f7 >>= 1
            i_imm = sign_extend(I_f12, 12) & self.mask64
            new_rd = alu(r1, i_imm, I_f3, f7, False, True)            
        elif op_name=="LOAD":
            i_imm = sign_extend(I_f12, 12) & self.mask64
            addr = ( r1 + i_imm) & self.mask64
            # LBU, LHU, LWU are just the same but with the bit 0b100
            size_byte = 1<<(I_f3&0b11) 
            if addr%size_byte!=0:
                # -log.debug(f"load addr: {addr:08x}")
                self.raiseException(ExceptionCode.LoadAddressMisaligned)
                self.handleException()
                self.write_back = False
            else:
                if (addr == self.load_breakpoint_addr):
                    self.breakpoint_addr=self.pc
                new_rd = self.sys_bus.read(addr, size_byte)
                f3_l = LD_F3(I_f3)

                if not (f3_l==LD_F3.LBU or f3_l==LD_F3.LHU or f3_l==LD_F3.LWU):
                    new_rd = sign_extend(new_rd, size_byte*8) 
        elif op_name=="OP_IMM_32":
            cond = (I_f3!=0) or (I_f3==0b101)
            f7 = I_f7 if cond else 0
            i_imm = sign_extend(I_f12, 12) & self.mask64
            res32 = alu(r1, i_imm, I_f3, f7, True, True) 
            new_rd = sign_extend(res32 & self.mask32, 32) 
        elif op_name=="STORE":
            s_imm = sign_extend(ins[31:25]<<5 | ins[11:7], 12) & self.mask64
            addr = ( r1 + s_imm) & self.mask64  
            if (addr == self.to_host_addr):
                # -log.error("__to_host__")
                return False
            if (addr == self.store_breakpoint_addr):
                self.breakpoint_addr=self.pc
            self.sys_bus.write(addr, r2, 1<<I_f3)                
        elif op_name=="OP":
            # print(ins.I_rs1, ins.I_rs2)
            new_rd = alu(r1, r2, I_f3, I_f7, False, False)
        elif op_name=="BRANCH":
            if branch_unit(r1, r2, BR_F3(I_f3)):
                # -log.info("taken")
                b_imm = sign_extend(ins[31]<<12 | ins[7]<<11 | \
                    ins[30:25]<<5 | ins[11:8] << 1, 12) & self.mask64
                self.new_pc = self.pc + b_imm
            else:
                pass
                # -log.info("not taken")    
        elif op_name=="JAL":
            new_rd = self.new_pc
            j_imm = sign_extend(ins[31]<<20 | ins[19:12]<<12 | \
                ins[20]<<11 | ins[30:21] << 1, 20) & self.mask64
            self.new_pc = self.pc+j_imm           
        elif op_name=="JALR":
            new_rd = self.new_pc
            i_imm = sign_extend(I_f12, 12) & self.mask64
            self.new_pc = (r1 + i_imm) & (self.mask64-1)
        elif op_name=="OP_32":
            # f3 = self.OP_F3[I_f3]
            res32 = alu(r1, r2, I_f3, I_f7, True, False) 
            new_rd = sign_extend(res32 & self.mask32, 32)                        
        elif op_name=="LUI":
            u_imm = sign_extend(ins[31:12]<<12, 32) & self.mask64
            new_rd = u_imm
        elif op_name=="AUIPC":
            u_imm = sign_extend(ins[31:12]<<12, 32) & self.mask64
            new_rd = self.pc + u_imm        
        elif op_name=="MISC_MEM":
            pass
        elif op_name=="AMO":
            
            assert sys_bus.try_lock(self.hartid), 'AMO: hart {} could not lock the bus'.format(self.hartid)
            size_byte = 1<<I_f3
            
            amo_f5 = AMO_OP_F5(I_f5)
            
            if amo_f5==AMO_OP_F5.LR:
                val1 = sys_bus.load_reserve(r1&self.mask32, size_byte, self.hartid)
            else:
                val1 = sys_bus.read(r1&self.mask32, size_byte)
            
            val2 = r2
            new_rd = sign_extend(val1&self.mask32, 32) if size_byte==4 else val1
            
            val1 = val1 & (1<<(size_byte*8))-1
            val2 = val2 & (1<<(size_byte*8))-1
                
            if amo_f5==AMO_OP_F5.AMOSWAP:
                amo_result = val2
            elif amo_f5==AMO_OP_F5.AMOADD:
                amo_result = val1 + val2
            elif amo_f5==AMO_OP_F5.AMOAND:
                amo_result = val1 & val2
            elif amo_f5==AMO_OP_F5.AMOOR:
                amo_result = val1 | val2
            elif amo_f5==AMO_OP_F5.AMOXOR:
                amo_result = val1 ^ val2
            elif amo_f5==AMO_OP_F5.AMOMAX:
                gt = to_signed(val1, size_byte*8)>to_signed(val2, size_byte*8)
                amo_result = val1 if gt else val2
            elif amo_f5==AMO_OP_F5.AMOMAXU:
                gt = val1>val2
                amo_result = val1 if gt else val2
            elif amo_f5==AMO_OP_F5.AMOMIN:
                gt = to_signed(val1, size_byte*8)<to_signed(val2, size_byte*8)
                amo_result = val1 if gt else val2
            elif amo_f5==AMO_OP_F5.AMOMINU:
                gt = val1<val2
                amo_result = val1 if gt else val2
            elif amo_f5==AMO_OP_F5.LR:
                pass
            elif amo_f5==AMO_OP_F5.SC:
                amo_result = val2
            else:
                raise Exception(f"{amo_f5} not defined")
            
            # sign extend if AMO.W operation
            
            
            if amo_f5==AMO_OP_F5.SC:
                valid_store = sys_bus.store_conditional(r1, amo_result, size_byte, self.hartid)
                if valid_store:
                    new_rd=0
                else:
                    new_rd=1
                    self.inst_ret=False
            elif amo_f5==AMO_OP_F5.LR:
                pass
            else:
                amo_result = sign_extend(amo_result&self.mask32, 32) if size_byte==4 else amo_result
                sys_bus.write(r1, amo_result, size_byte)
                
            sys_bus.unlock(self.hartid)         
        elif op_name=="LOAD_FP":
            # fpr1 = self.fp_regfile[I_rs1]
            # fpr2 = self.fp_regfile[I_rs2]
            # fpr3 = self.fp_regfile[I_f5]
            i_imm = sign_extend(I_f12, 12) & self.mask64
            addr = ( r1 + i_imm) & self.mask64   
            # 010 (2) for W; 011 (3) for D; 100 (4) for Q; 
            size_byte = 1<<I_f3
            new_rd = self.sys_bus.read(addr, size_byte)
            self.to_float_reg = True
            self.write_back = True
        elif op_name=="STORE_FP":
            # fpr1 = self.fp_regfile[I_rs1]
            fpr2 = self.fp_regfile[I_rs2]
            # fpr3 = self.fp_regfile[I_f5]
            s_imm = sign_extend(ins[31:25]<<5 | ins[11:7], 12) & self.mask64
            addr = ( r1 + s_imm) & self.mask64  
            if (addr == self.to_host_addr):
                # -log.error("__to_host__")
                return False
            if (addr == self.store_breakpoint_addr):
                self.breakpoint_addr=self.pc
            self.sys_bus.write(addr, fpr2, 1<<I_f3)           
        elif op_name in ["FMADD", "FNMADD"]:
            fpr1 = self.fp_regfile[I_rs1]
            fpr2 = self.fp_regfile[I_rs2]
            fpr3 = self.fp_regfile[I_f5]
            f_f3 = I_f3
            res1, fflags1 = FPU(fpr1, fpr2, FP_OP_F5.FMUL, f_f3, I_rs2)
        
            res2, fflags2 = FPU(res1, fpr3, FP_OP_F5.FADD, f_f3, I_rs2)
            
            fflags1 = pack_fflags(fflags1)
            fflags2 = pack_fflags(fflags2)
            
            res2 = res2 if op_name=="FMADD" else -res2
            
            new_rd = sign_extend(pack_f32(res2), 32)&self.mask64
                
            self.to_float_reg = True
            self.write_back = True
            
            self.csr.fcsr.FFL = fflags1|fflags2  
        elif op_name in ["FMSUB", "FMNSUB"]:
            fpr1 = self.fp_regfile[I_rs1]
            fpr2 = self.fp_regfile[I_rs2]
            fpr3 = self.fp_regfile[I_f5]
            f_f3 = I_f3
            res1, fflags1 = FPU(fpr1, fpr2, FP_OP_F5.FMUL, f_f3, I_rs2)
        
            res2, fflags2 = FPU(res1, fpr3, FP_OP_F5.FSUB, f_f3, I_rs2)
            
            fflags1 = pack_fflags(fflags1)
            fflags2 = pack_fflags(fflags2)
            
            res2 = res2 if op_name=="FMSUB" else -res2
            
            new_rd = sign_extend(pack_f32(res2), 32)&self.mask64
                
            self.to_float_reg = True
            self.write_back = True
            
            self.csr.fcsr.FFL = fflags1|fflags2           
        elif op_name=="OP_FP":
            fpr1 = self.fp_regfile[I_rs1]
            fpr2 = self.fp_regfile[I_rs2]
            # fpr3 = self.fp_regfile[I_f5]
            f_f5 = FP_OP_F5(I_f5)
            f_f3 = I_f3
            
            # dont_sign_extend = False
            # print(f_f5, f_f3)
            if f_f5 == FP_OP_F5.FMVT_X_W and f_f3==0:
                new_rd = fpr1
                fflags = self.csr.fcsr.FFL
            elif f_f5 == FP_OP_F5.FMVT_W_X:
                new_rd = r1
                self.to_float_reg=True
                fflags = self.csr.fcsr.FFL
            elif f_f5 in [FP_OP_F5.FSGNJ, FP_OP_F5.FMINMAX, FP_OP_F5.FADD, FP_OP_F5.FSUB, FP_OP_F5.FMUL, FP_OP_F5.FDIV, FP_OP_F5.FSQRT]:
                res, fflags = FPU(fpr1, fpr2, f_f5, f_f3, I_rs2)
                self.to_float_reg = True
                
                if f_f5!=FP_OP_F5.FSGNJ:
                    new_rd = pack_f32(res)
                else:
                    new_rd = res
                    
                if fflags['NV']==1 and f_f5!=FP_OP_F5.FMINMAX:
                    new_rd = 0x7fc00000
            elif f_f5 in [FP_OP_F5.CVT_TO_FP]:
                res, fflags = FPU(r1, 0.0, f_f5, 0, ins.I_rs2)
                self.to_float_reg = True
                new_rd = pack_f32(res)
            
            elif f_f5 in [FP_OP_F5.FCLASS, FP_OP_F5.FCMP, FP_OP_F5.CVT_TO_INT]:
                res, fflags = FPU(fpr1, fpr2, f_f5, f_f3, ins.I_rs2)
                new_rd = res&self.mask64
            else:
                raise Exception(f"Unknown operation {f_f5}")  
            
            if type(fflags)==dict:
                fflags = pack_fflags(fflags)
            
            if f_f5!=FP_OP_F5.CVT_TO_INT:
                new_rd = sign_extend(new_rd, 32)&self.mask64
                
            self.write_back = True
            
            self.csr.fcsr.FFL = fflags         
        elif op_name=="ILLEGAL":
            self.raiseException(ExceptionCode.IllegalInstruction)
            self.handleException()
        elif op_name=="SYSTEM":
            if I_f3 == 0:
                f12 = SYS_F12(I_f12)
                if f12==SYS_F12.MRET:
                    # -log.error("--MRET--")
                    self.new_pc = self.mret()
                elif f12==SYS_F12.SRET:
                    # -log.error("--SRET--")
                    self.new_pc = self.sret()
                elif f12==SYS_F12.ECALL:
                    # -log.error("--ECALL--")
                    if (self.mode==Mode.M): 
                        self.raiseException(ExceptionCode.Mcall)
                    elif (self.mode==Mode.S): 
                        self.raiseException(ExceptionCode.Scall)
                    elif (self.mode==Mode.U): 
                        self.raiseException(ExceptionCode.Ucall)
                    self.handleException()
                elif f12==SYS_F12.EBREAK:
                    # -log.error("--EBREAK--")
                    # TODO: implement debugger for FPGA @DavideRuzza
                    self.raiseException(ExceptionCode.Breakpoint)
                    self.handleException()
                elif f12==SYS_F12.WFI:
                    # -log.error("--WFI--")
                    self.wait_mode = True
                else:                    
                    # -log.error(f" {f12} Not Implemented")
                    return False
            else: # CSR
                f3 = CSR_F3(I_f3)
                csr_key = I_f12
                new_csr = None
                # read csr if the mode allows
                
                
                csr_implemented = True 
                try:
                    csr = self.csr[csr_key]
                except KeyError:
                    csr_implemented = False
                
                if csr_implemented:
                    if csr.priv.value <= self.mode.value:
                        csr_value = csr.all
                        new_rd = csr_value
                        self.write_back = True
                    
                        # immediate csr instruction differs from the 2 bit in f3
                        # for I instruction instead of the content of r1 they use 
                        # r1 position as immediate
                        is_imm_csr = bool(f3.value>>2)
                        value = I_rs1 if is_imm_csr else r1
                        
                        csrsrc_cond = (not is_imm_csr and (I_rs1 != 0)) or \
                                        (is_imm_csr and value != 0)
                                        
                        if (f3 == CSR_F3.CSRRS) or (f3 == CSR_F3.CSRRSI):
                            # -log.info("CSRRS")
                            if csrsrc_cond:
                                new_csr = csr_value | value
                                self.write_csr = True
                        elif (f3 == CSR_F3.CSRRC) or (f3 == CSR_F3.CSRRCI):
                            # -log.info("CSRRC")
                            if csrsrc_cond:
                                clear_bit_mask = (~value) & self.mask64
                                new_csr = csr_value & clear_bit_mask
                                self.write_csr = True  
                        elif (f3 == CSR_F3.CSRRW) or (f3 == CSR_F3.CSRRWI):
                            # -log.info("CSRRW")
                            new_csr = value
                            self.write_csr = True    
                        else:
                            raise Exception(f'CSR OP {f3} not defined')
                    else:
                        # -log.error("not enough priviledge")
                        self.raiseException(ExceptionCode.IllegalInstruction)
                        self.handleException()
                else:
                    # -log.error(f"csr 0x{hex(csr_key)} not implemented")
                    self.raiseException(ExceptionCode.IllegalInstruction)
                    self.handleException()               
        else:
            # raise Exception(f"{op} not implemented")
            # -log.error("Not Implemented")
            return False
        
        # ------------------------------------------------------------------------
        # self.handleException()
        
        if self.write_csr:
            if self.csr[csr_key].rw != 0b11: # is read-only
                self.csr[csr_key].all = new_csr
                
                if self.csr.addr_to_name[csr_key] == "minstret":
                    self.inst_ret = False
            else:
                self.write_back = False
                self.raiseException(ExceptionCode.IllegalInstruction)
                self.handleException()
        
        # self.handleException()

        if self.write_back:
            if self.to_float_reg:
                # -log.info(f"write reg - {self.fp_reg_names[ins.I_rd]} <- {hex(new_rd&self.mask64)}")
                self.fp_regfile[I_rd] = new_rd
            else:
                # -log.info(f"write reg - {self.reg_names[ins.I_rd]} <- {hex(new_rd&self.mask64)}")
                self.regfile[I_rd] = new_rd
        
        mcountinhibit = self.csr['mcountinhibit'].value
        if self.inst_ret:
            # IR -> bit 2 position
            if (mcountinhibit>>2) & 0x1 == 0:
                self.csr.csr_map[0xb02].reg.reg +=  1  # = self.csr.minstret.all+1
            
        if self.cnt_cycle:
            # CY -> bit 0 position
            if mcountinhibit & 0x1 == 0:
                self.csr.csr_map[0xc00].reg.reg += 1  # = self.csr.minstret.all+1
            
        if self.pc==self.breakpoint_addr:
            # -log.error("-- Breakpoint --")
            print(f"self.new_pc: 0x{(self.new_pc & self.mask64):8x}")
            self.pc = self.new_pc & self.mask64
            return False
        
        self.pc = self.new_pc & self.mask64
        
        return True


# ---- settings
RISCV_TEST = 1
CUSTOM_TEST = 0

VERBOSE = 0
DEBUG = 0

CONSOLE = 1
PROFILE = 0

VERBOSE_LEVEL = None
csr = CsrFile()

# ----------------------------------- VERBOSE setup
def set_log_level(new_level):
    """Change logging level at any point"""
    logger = logging.getLogger()
    logger.setLevel(new_level)
    for handler in logger.handlers:
        handler.setLevel(new_level)
        
log = logging.getLogger(__name__)

if VERBOSE:
    setup_logging(logging.DEBUG)
    VERBOSE_LEVEL = logging.DEBUG
else:
    setup_logging(logging.CRITICAL)
    VERBOSE_LEVEL = logging.CRITICAL
# ------------------------------------

input_path = Path("tests/rv64/bin/p")
  
        
tests = sorted(list(input_path.glob("rv64ui-p-*.bin")))
length = [len(str(t.stem)) for t in tests]

# ------------------------------ memory map
# ref : https://stackoverflow.com/questions/78346549/clarifying-connectivity-and-memory-implementation-in-the-risc5-platform-architec


# tests = [Path("opensbi/bin/fw_jump.bin")]
# tests = [Path("./tests/custom/hello/hello.bin")]
# tests = [Path("./tests/custom/timer_interrupt/main.bin")]
# tests = [tests[0]]


CLINT_BASE = 0x0200_0000
PLIC_BASE = 0x0c00_0000
UART_BASE = 0x1000_0000
RAM_BASE = 0x8000_0000

MEIP_BIT = 11
SEIP_BIT = 9


for test in tests:
    print(f"{COL['r']}{str(test.stem):<20s}{COL['rst']}", 
          end='\n' if VERBOSE else '', flush=True)
    
    if CONSOLE:
        uart = UART16550()
        
    bios = MemoryDevice.from_binary_file("tests/custom/bios/bios.bin", 'BIOS')
    kernel = MemoryDevice.from_binary_file("tests/custom/kernel/kernel.bin", 'KERNEL')
    dts = MemoryDevice.from_binary_file("device_tree/platform.dtb", 'DEVICE_TREE')
    
    ram = MemoryDevice.from_binary_file(test, "RAM")
    ram.expand(0x1f_ffff)
    
    # clint = CLINT()
    clint = CLINT()
    plic = InterruptController(context_num=2, interrupt_source_num=31)
    

    sys_bus = SystemInterface()
    
    sys_bus.register_device(bios, 0x0)
    sys_bus.register_device(dts, 0x2000)
    sys_bus.register_device(kernel, 0x80200000)
    
    sys_bus.register_device(clint, CLINT_BASE)
    sys_bus.register_device(plic, PLIC_BASE)
    if CONSOLE:
        sys_bus.register_device(uart, UART_BASE)
        
    sys_bus.register_device(ram, RAM_BASE)
    
    # print(sys_bus)
    if CONSOLE:
        uart.set_irq_callback(plic.set_interrupt)
    
    print(sys_bus)
    
    if RISCV_TEST:
        if CUSTOM_TEST:
            to_host_addr = get_symbol_info(test.parent/(test.stem+".elf"), 'tohost')['address']
        else:
            to_host_addr = get_symbol_info("tests/rv64/elf/p/"+test.stem, 'tohost')['address']
    else:
        to_host_addr=0
    
    h0 = RV64Hart(0, sys_bus, [Ext.S, Ext.U, Ext.C, Ext.M, Ext.F, Ext.A], to_host_addr=to_host_addr,
                  entry_point=0x0)
    h0.set_breakpoint(-1)
    break_debug=True
    
    h0_m_ctx_plic = plic.register_context(hart=h0, bit=MEIP_BIT)
    h0_s_ctx_plic = plic.register_context(hart=h0, bit=SEIP_BIT)
    
    clint.register_hart(h0)
    
    sys_bus.register_hart(hartid=0)
    
    
    # wait for uart connection
    if CONSOLE:
        print("Waiting connection...")
        while not uart.is_connected():
            pass
            
    if PROFILE:
        profiler = Profiler()
        profiler.start()
        
    # break
    try:
        counter = 0
        time = datetime.datetime.now()
        while(h0.step() and break_debug):
            
            if DEBUG:
                while True: # Debugger
                    cmd = input("> ")
                    cmd : List[str] = [c.lower() for c in cmd.strip().split(" ")]
                    
                    if cmd[0]=="q" or cmd[0]=="quit":
                        print("Exiting CPU loop.")
                        break_debug=False
                        break 
                    elif cmd[0] in ['help', 'h']:
                        print("\n RISC-V debugger by @DavideRuzza. \n Basic commands list:\n"+\
                            " - 'ret key'         just by pressing return key the program counter will be increased by one\n"+\
                            " - priv              return current priviledge mode of the core\n"+\
                            " - reg xxx           xxx=[0, 1, a0, ra, ...] if passed a valid integer register number or name\n"+\
                            "                         it will return the content of that register. if no argument is passed\n"+\
                            "                         the entire integer register file will be printed\n"+\
                            " - freg xxx          xxx=[0, 1, fs0, ft0, ...] if passed a valid float register number or name\n"+\
                            "                         it will return the content of that register. if no argument is passed\n"+\
                            "                         the entire float register file will be printed\n"+\
                            " - br 0x12345678     set a breakpoint until specified address and run free until target point\n"+\
                            " - csr yyy           yyy=[mstatus, 0x300, ...] return the value of a csr register by name or \n"+\
                            "                     hex address\n"+\
                            " - q / quit          quit debugger\n\n"                          
                        )                            
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
                    elif cmd[0]=="freg":
                        if len(cmd)>1:
                            if cmd[1].isnumeric():
                                if int(cmd[1])<32:
                                    reg_name = h0.fp_reg_names[int(cmd[1])]
                                    print(f"{reg_name}: {h0.fp_regfile[int(cmd[1])]:016x}\n")
                                else:
                                    print(f"No reg x{cmd[1]}\n")
                            else:
                                if cmd[1] in h0.fp_reg_names:
                                    print(f"{cmd[1]}: 0x{h0.fp_regfile[h0.fp_reg_names.index(cmd[1])]:016x}\n")
                                else:
                                    print(f"No reg named {cmd[1]}\n")
                        else:
                            print(h0.fp_regfile)
                    elif cmd[0]=="":
                        clint.inc_time()
                        # -log.error(clint.mtime)
                        break
                    elif cmd[0]=="br":
                        if len(cmd)>1:
                            h0.set_breakpoint(int(cmd[1], 16))
                            set_log_level(logging.CRITICAL)
                            while(h0.step()):
                                clint.inc_time()
                                # -log.error(clint.mtime)
                            h0.set_breakpoint(-1)
                            set_log_level(VERBOSE_LEVEL)
                    elif cmd[0]=="brst":
                        if len(cmd)>1:
                            h0.set_store_breakpoint(int(cmd[1], 16))
                            while(h0.step()):
                                clint.inc_time()
                                # -log.error(clint.mtime)
                            h0.set_store_breakpoint(-1)
                            h0.set_breakpoint(-1)
                    elif cmd[0]=="brld":
                        if len(cmd)>1:
                            h0.set_load_breakpoint(int(cmd[1], 16))
                            while(h0.step()):
                                clint.inc_time()
                                # -log.error(clint.mtime)
                            h0.set_load_breakpoint(-1)
                            h0.set_breakpoint(-1)
                    elif cmd[0]=="untilcsr":
                        if len(cmd)>2:
                            try:
                                csr_addr = -1
                                if cmd[1].startswith('0x'):
                                    csr_addr = int(cmd[1], 16)
                                    h0.csr[int(cmd[1], 16)]
                                else:
                                    # if cmd[1] in h0.csr.name_to_addr:
                                    csr_addr = h0.csr.name_to_addr[cmd[1]]
                                    h0.csr[h0.csr.name_to_addr[cmd[1]]]
                                
                                # print(hex(csr_addr), h0.csr[csr_addr].all)
                                while(h0.step()):
                                    clint.inc_time()
                                    # -log.error(clint.mtime)
                                    if h0.csr[csr_addr].all==int(cmd[2]):
                                        break
                                
                            except KeyError:
                                print(f"{cmd[1]} not a valid csr" )   
                        else:
                            print("Expected csr and value")
                                
                    elif cmd[0]=='csr':
                        try:
                            if cmd[1].startswith('0x'):
                                print(h0.csr[int(cmd[1], 16)])
                            else:
                                # if cmd[1] in h0.csr.name_to_addr:
                                print(h0.csr[h0.csr.name_to_addr[cmd[1]]])
                        except KeyError:
                            print(f"{cmd[1]} not a valid csr" )   
            else: 
                if (counter%500000 == 0):
                    now = datetime.datetime.now()
                    print(f"{now.strftime("%H:%M:%S")} : dt={(now-time).total_seconds():.2f} - {counter/1e6: .1f}mln ops")
                    time = datetime.datetime.now()
                if counter%4==0:
                    clint.inc_time()
                counter+=1
                # -log.error(clint.mtime)
    
    except Exception as e:       
        # print("Keyboard Interrupt")
        print("Exception", f"pc {hex(h0.pc)}")
        traceback.print_exc()
        print(e)
    finally:
        if CONSOLE:
            uart.shutdown()
            del uart
                
        if PROFILE:
            profiler.stop()
            with open('profile.html', 'w') as f:
                f.write(profiler.output_html())
                
        print("------ INSTRUCTION PROFILE -------")
        sorted_dict = dict(sorted(h0.instruction_profile.items(), key=lambda x: x[1], reverse=True))
        max_name_len = max(map(lambda x: len(x.name), list(Ops)))
        
        for k, v in sorted_dict.items():
            print(f"- {k:<{max_name_len}}: {v}")
        print("----------------------------------")
        
        
    syscall_code = h0.regfile[17]
    syscall_data = h0.regfile[10] 
    if syscall_code==93: # exit code
        if syscall_data == 0:
            if CUSTOM_TEST:
                print(" ✅ End.")
            else:
                print(" ✅ Test PASSED")
        else:
            print(f" ❌ Test FAILED: {syscall_data>>1}")
    else:
        print(f"{COL['g']} sys_code = {syscall_code}, sys_data = {syscall_data}, ")
    
    del h0, ram, sys_bus
    
