# import logging
# from logger_config import setup_logging
# from devices import MemoryDevice
# from system_interface import SystemInterface
# from utils import *
# from cpu_enums import *
# from pathlib import Path
# from collections import deque, Counter


# # Max allowed repeats within recent jumps
# MAX_JUMP_REPEAT = 20


# def shift_unit(op, shamt, f3:OP_F3, f7:int, op32:bool=False):
    
#     xlen = 32 if op32 else 64
#     shamt = shamt&0b11111 if op32 else shamt&0b111111
#     mask = (1<<xlen)-1
#     if f3 == OP_F3.SLL:
#         # print(hex(op), hex(shamt))
#         return (op&mask)<<shamt
#     elif f3 == OP_F3.SRX:
        
#         if f7: # SRA
#             # print(f3, op32, hex(op&mask), shamt)
#             return sign_extend((op&mask)>>shamt, xlen-shamt)&mask
#         else:
#             return (op&mask)>>shamt
#     else:
#         raise Exception(f"{f3} not implemented in shift unit")
    
# def alu(op1:int, op2:int, f3: OP_F3, f7: int, op32:bool=False):    
#     if f3==OP_F3.ADD_SUB:
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

# def branch_unit(op1:int, op2:int, f3: BR_F3):
#     if f3==BR_F3.BNE:
#         return op1!=op2
#     elif f3==BR_F3.BEQ:
#         return op1==op2
#     elif f3==BR_F3.BLT:
#         return int_64(op1) < int_64(op2)
#     elif f3==BR_F3.BGE:
#         return int_64(op1) >= int_64(op2)
#     elif f3==BR_F3.BGEU:
#         return op1>=op2
#     elif f3==BR_F3.BLTU:
#         return op1<op2
#     else:
#         raise Exception(f"{f3} not implemented in Branch unit")
    
# class RV64Hart():
    
#     XLEN = 64
#     MXL = 2
#     SXL = 2
#     UXL = 2
    
#     reg_names=['ze', 'ra', 'sp', 'gp', 'tp', 't0', 't1', 't2', 's0', 's1', 
#         'a0', 'a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'a7', 's2',
#         's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 
#         't3', 't4', 't5', 't6']
    
#     def __init__(self, 
#             id:int, 
#             bus: SystemInterface, 
#             extensions:List[Extension] = []
#         ):
        
#         self.id = id
#         self.bus = bus
        
#         if isinstance(extensions, Extension):
#             extensions = [extensions]
#         self.extensions = extensions
        
#         # Machine Mode implemented by default
#         if Extension.M not in self.extensions:
#             self.extensions.append(Extension.M) 
        
#         self.regfile = RegFile(32, self.XLEN, self.reg_names)
        
#         self.mask64 = 0xffff_ffff_ffff_ffff
#         self.mask32 = 0xffff_ffff
#         self.pc_rst = 0x8000_0000
        
#         self.pc = self.pc_rst
        
#         self.mode = Mode.M # start with mode M
#         # -------------------------------------------------------------------- #
#         # initialize csr regs
#         self.csr = CSRFile(self.extensions, self.XLEN)
        
#         self.csr['mhartid'] = self.id
        
#         self.csr['misa'][25:0] = sum([ext.value for ext in self.extensions])
#         self.csr['misa'][self.XLEN-1:self.XLEN-2] = self.MXL
        
#         # set MPP = U-mode for first return
#         self.csr['mstatus'][12:11] = Mode.U.value
#         self.csr['mstatus'][35:34] = self.SXL
#         self.csr['mstatus'][33:32] = self.UXL
        
 
#         # print(self.csr['mstatus'])
        
#         self.exc_or_int = False
        
#         self.terminate = False
        
#         self.recent_jumps = deque(maxlen=50)

#     def step(self):
#         pc_plus_4 = self.pc + 4
#         pc_plus_2 = self.pc + 2
        

#         ins = Reg(32, self.bus.read(self.pc, 4))
        
#         write_back = False
#         new_rd=0
#         self.exc_or_int = False # exception or interrupt ?
#         # --------------------------- COMPRESSED ----------------------------- #
#         if ins[1:0]!=3: # 
#             new_pc = pc_plus_2
            
#             sp = self.regfile[2]
            
#             f2 = ins[6:5]
#             f3 = ins[15:13]
#             f4 = ins[15:12]
#             f6 = ins[15:10]
            
#             # print(bin(ins[:]))
#             # imm0 = (ins[6:5]<<5)|(ins[12:10]<<3) #( FLD, LD, FSD, SD)
#             imm1 = (ins[10:7]<<6)|(ins[12:11]<<4)|(ins[5]<<3)|(ins[6]<<2 )# (ADDI4SPN)
#             imm2 = (ins[12:10]<<3)|(ins[6]<<2)|(ins[5]<<6)
#             imm3 = (ins[12]<<5)|(ins[6:2]) # (NOP, ADDI, ADDIW, LI, SRLI, SRAI, ANDI, SLLI)
#             imm4 = (ins[12]<<9)|(ins[6]<<4)|(ins[5]<<6)|(ins[4:3]<<7)|(ins[5]<<6)\
#                 |(ins[2]<<5) # (ADDI16SP)
            
#             if ins[1:0]==0b00: # C0 type Instruction
#                 # return False
#                 rd = ins[4:2]+8
#                 rs1 = ins[9:7]+8
#                 rs2 = ins[4:2]+8
#                 r1 = self.regfile[rs1]
#                 r2 = self.regfile[rs2]
                
#                 if f3 == 0b000: # C.ADDI4SPN
#                     log.debug("C.ADDI4SPN")
#                     new_rd = (sp+imm1)&self.mask64
#                     write_back=True
#                 elif f3 == 0b010: # C.LW
#                     log.debug("C.LW")
#                     addr = r1+imm2
#                     new_rd = sign_extend(self.bus.read(addr, 4), 32)
#                     write_back=True
#                 elif f3 == 0b011:
#                     return False
#                 elif f3 == 0b110: # C.SW
#                     addr = r1+imm2
#                     log.debug("C.SW")
#                     self.bus.write(addr, r2, 4)
#                 else:
#                     raise Exception(f"f3 {bin(f3)} not implemented for C0")
                
#             elif ins[1:0]==0b01: # C1 type Instruction
                
#                 rd = ins[11:7]
#                 rs1 = ins[11:7]
                
#                 if f3==0b011: # C.ADDI16SP
#                     new_rd = sp+sign_extend(imm4, 10)
#                     log.debug("C.ADDI16SP")
#                     write_back=True
#                 elif f3 == 0b000: # C.ADDI
#                     if rd==0:
#                         log.debug("C.NOP")
#                     else:
#                         log.debug("C.ADDI")
#                         new_rd=self.regfile[rd]+imm3
#                         write_back=True
                    
#                 else:
#                     raise Exception(f"f3 {bin(f3)} not implemented for C1")
                    
#                     # return False
            
#             else: # C2 type Instruction
#                 raise Exception(f"C2 not implemented")
                
#             # return False
        
#         # ------------------------------ FULL -------------------------------- #
        
#         else:
#             new_pc = pc_plus_4
#             opcode = Ops(ins[6:0])

#             rd = ins[11:7]
#             rs1 = ins[19:15]
#             rs2 = ins[24:20]
#             r1 = self.regfile[rs1]
#             r2 = self.regfile[rs2]
            
#             f3 = ins[14:12]
#             f7 = ins[31:25]
#             f12 = ins[31:20]
            
#             i_imm = sign_extend(ins[31:20], 12) & self.mask64
#             s_imm = sign_extend(ins[31:25]<<5 | ins[11:7], 12) & self.mask64
#             b_imm = sign_extend(ins[31]<<12 | ins[7]<<11 | \
#                 ins[30:25]<<5 | ins[11:8] << 1, 12) & self.mask64
#             u_imm = sign_extend(ins[31:12]<<12, 32) & self.mask64
#             j_imm = sign_extend(ins[31]<<20 | ins[19:12]<<12 | \
#                 ins[20]<<11 | ins[30:21] << 1, 20) & self.mask64
        
#         # -------------------------------------------------------------------- #

#             if opcode==Ops.JAL:
#                 new_pc = (self.pc + j_imm) & self.mask64
#                 new_rd = pc_plus_4
#                 write_back=True
                
#                 self.recent_jumps.append(new_pc)
#                 counts = Counter(self.recent_jumps)
#                 if counts[new_pc] > MAX_JUMP_REPEAT:
#                     log.critical(f"MAX jump iteration to addr {new_pc:08x}")
#                     return False
            
#             elif opcode==Ops.JALR:
#                 new_pc = (r1 + i_imm) & (self.mask64-1)
#                 new_rd = pc_plus_4
#                 write_back=True     
            
#             elif opcode==Ops.OP:
                
#                 new_rd = alu(r1, r2, OP_F3(f3), f7)
#                 write_back = True
                                
#             elif opcode==Ops.OP_32:
#                 f3 = OP_F3(f3)
#                 res32 = alu(r1, r2, f3, f7, True) 
#                 new_rd = sign_extend(res32 & self.mask32, 32)
#                 write_back = True
                
#             elif opcode==Ops.OP_IMM:
#                 f3 = OP_F3(f3)
#                 new_rd = alu(r1, i_imm, f3, f7 if f3!=OP_F3.ADD_SUB else 0)
#                 write_back = True
            
#             elif opcode==Ops.OP_IMM_32:
#                 f3 = OP_F3(f3)
#                 res32 = alu(r1, i_imm, f3, f7 if f3!=OP_F3.ADD_SUB else 0, True) 
#                 new_rd = sign_extend(res32 & self.mask32, 32)
#                 write_back = True
                
#             elif opcode==Ops.BRANCH:
#                 cond = branch_unit(r1, r2, BR_F3(f3))
#                 if cond:
#                     new_pc = self.pc + b_imm

#             elif opcode==Ops.LUI:
#                 new_rd = u_imm
#                 write_back = True
                
#             elif opcode==Ops.AUIPC:
#                 new_rd = self.pc + u_imm
#                 write_back = True
            
#             elif opcode==Ops.MISC_MEM:
#                 log.info("FENCE")
                
#             elif opcode==Ops.STORE:
#                 # log.info("Write")
#                 addr = ( r1 + s_imm) & self.mask64
                
#                 if addr == 0x80001000 or addr == 0x80001004:
#                     # print("to_host")
#                     return False
                
#                 # print("Addr", hex(addr))
#                 self.bus.write(addr, r2, 1<<f3)
            
#             elif opcode==Ops.LOAD:
#                 addr = ( r1 + i_imm) & self.mask64
                
#                 # LBU, LHU, LWU are just the same but with the bit 0b100
#                 size_byte = 1<<(f3&0b11) 
                
#                 new_rd = self.bus.read(addr, size_byte)
                
#                 f3_l = LD_F3(f3)
#                 if not (f3_l==LD_F3.LBU or f3_l==LD_F3.LHU or f3_l==LD_F3.LWU):
#                     new_rd = sign_extend(new_rd, size_byte*8)

#                 write_back = True
                
#             elif opcode==Ops.SYSTEM:
                
#                 if f3==0:
#                     try:
#                         sys_f12 = SYS_F12(f12)
#                     except:
#                         raise Exception(f'f12 0x{f12:03x} not defined')

#                     if sys_f12==SYS_F12.ECALL:
#                         log.debug("<----ECALL---->")
#                         if self.mode == Mode.M:
#                             self.raiseException(self.mode, ExceptionCode.ECALL_FROM_MMODE)
#                         elif self.mode == Mode.S:
#                             self.raiseException(self.mode, ExceptionCode.ECALL_FROM_SMODE)
#                         else:
#                             self.raiseException(self.mode, ExceptionCode.ECALL_FROM_UMODE)
#                         new_pc = self.csr["mepc"][:]
#                         new_pc = self.csr['mtvec']
                        
                        
#                     elif sys_f12==SYS_F12.MRET:
#                         log.info("<----MRET---->")
#                         # MIE = MPIE
#                         self.csr['mstatus'][3] = self.csr['mstatus'][7]
#                         # MPIE = 1
#                         self.csr['mstatus'][7] = 0b1
#                         # next mode = MPP
#                         self.mode = Mode(self.csr['mstatus'][12:11])
#                         # MPP = U-Mode
#                         self.csr['mstatus'][12:11] = Mode.U.value
                        
                        
#                     else:
#                         raise Exception(f'SYSTEM {sys_f12} not defined')
                    
#                 else: # CSR FUNCTION
#                     f3 = CSR_F3(f3)
#                     csr_key = f12
#                     csr_value = self.csr[csr_key][:]
                    
#                     new_rd = csr_value
#                     write_back = True
                    
#                     # immediate csr instruction differs from the 2 bit in f3
#                     # for I instruction instead of the content of r1 they use 
#                     # r1 position as immediate
#                     is_imm_csr = bool(f3.value>>2)
#                     value = rs1 if is_imm_csr else r1
                    
#                     if (f3 == CSR_F3.CSRRS) or (f3 == CSR_F3.CSRRSI):
#                         print("CSRRS")
#                         if (not is_imm_csr and (rs1 != 0)) or \
#                             (is_imm_csr and value != 0):
                                
#                             self.csr[csr_key][:] = csr_value | value
                        
#                     elif (f3 == CSR_F3.CSRRC) or (f3 == CSR_F3.CSRRCI):
#                         print("CSRRC")
#                         if (not is_imm_csr and (rs1 != 0)) or \
#                             (is_imm_csr and value != 0):
                                
#                             clear_bit_mask = (~value) & self.mask64
#                             self.csr[csr_key][:] = csr_value & clear_bit_mask
                            
#                     elif (f3 == CSR_F3.CSRRW) or (f3 == CSR_F3.CSRRWI):
#                         print("CSRRW")
#                         self.csr[csr_key] = value
                            
#                     else:
#                         raise Exception(f'CSR {f3} not defined')
                        
#             else:
#                 raise Exception(f"op {opcode.name} not implemented")
            
#         if write_back:
#             log.info(f"write reg - {self.reg_names[rd]} <- {hex(new_rd&self.mask64)}")
#             self.regfile[rd] = new_rd
        
#         if self.exc_or_int:
#             log.warning(f"Exception :'{ExceptionCode(self.csr['mcause'][self.XLEN-2:0]).name}'")
            
#         # breakpoint
#         if self.pc==0x8000_0174:

#             print(f"new_pc: 0x{new_pc & self.mask64:8x}")
#             print(hex(self.csr['mtvec'][1:0]))
#             # return False
        
#         self.pc = new_pc & self.mask64
        
#         if self.terminate:
#             return False
        
#         return True
    
#     def raiseException(self, handling_mode: Mode, ex: ExceptionCode):
#         if handling_mode==Mode.M:
#             self.csr['mepc'] = self.pc
#             self.csr['mcause'][self.XLEN-1] = 0b0 # exception not interrupt
#             self.csr['mcause'][self.XLEN-2:0] = ex.value
#             self.exc_or_int = True
#         if handling_mode==Mode.U:
#             self.csr['mepc'] = self.pc
#             self.csr['mcause'][self.XLEN-1] = 0b0 # exception not interrupt
#             self.csr['mcause'][self.XLEN-2:0] = ex.value
#             self.exc_or_int = True
#         # pass
    
#     def is_implemented(self, e: Extension):
#         extension_value = sum([ex.value for ex in self.extensions]) & self.mask64
#         return bool(extension_value&e.value)

# setup_logging(logging.DEBUG)
# # setup_logging(logging.CRITICAL)

# log = logging.getLogger(__name__)

# input_path = Path("tests/rv64/p_test/bin/")

# tests = sorted(list(input_path.glob("rv64ui*")))
# length = [len(str(t.stem)) for t in tests]
# # print(*tests, sep="\n")

# tests = [Path("tests/rv64/p_test/bin/rv64mi-p-csr.bin")]


# for test in tests:
#     # symtab = elf.get_section_by_name('.symtab')
#     print(f"{str(test.stem):<20s}", end='')
#     ram = MemoryDevice.from_binary(test, "RAM")
#     sys_bus = SystemInterface()
#     sys_bus.register_device(ram, 0x80000000)

#     h0 = RV64Hart(0, sys_bus, [Extension.S, Extension.U])
#     while(h0.step()):
#         pass
    
#     syscall_code = h0.regfile[17]
#     syscall_data = h0.regfile[10] 
#     if syscall_code==93: # exit code
#         if syscall_data == 0:
#             print(" ✅ Test PASSED")
#         else:
#             print(f" ❌ Test FAILED: {syscall_data>>1}") 
            
#     print(h0.regfile)
#     print(h0.csr._csr_str('mstatus'))
#     del h0

# # print(h0.csr)
# # print(hex(h0.pc))
# # hex(sys_bus.read(0x80000000, 4))
# # print(hex(ram.read(0x00002000, 8)))
# # csr = CSRFile([Extension.M])
# # print(csr)
# # csr['mhartid'] = 10

import logging
from devices import MemoryDevice
from system_interface import SystemInterface
from logger_config import setup_logging

setup_logging(logging.DEBUG)
log = logging.getLogger(__name__)
# dev = BaseDevice(0x100, 'main')

# dev.write(0, 0xdeadbeef)

# ram : MemoryDevice = MemoryDevice(0x50, 'RAM') 
ram =  MemoryDevice.from_binary_file("tests/rv32/bin/p/rv32mi-p-csr.bin", "RAM")
sys_bus = SystemInterface()
sys_bus.register_device(ram, 0x8000_0000)

print(sys_bus)
 
sys_bus.write(0x8000_0000, 0xaaaa_aaaa)
# print(hex(sys_bus.read(0x8000_2010, 1)))


ram.hexdump()