from cpu_enums import F_OP_F5, FP_ROUND_MODE
from struct import unpack, pack
from utils import BlockReg
from utils import *

def to_f64(num):
    mask = (1<<64)-1
    num = num&mask
    return unpack('>d', bytearray.fromhex(f"{num:016x}"))[0]

def to_f32(num):
    mask = (1<<32)-1
    num = num&mask
    return unpack('>f', bytearray.fromhex(f"{num:08x}"))[0]

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

def FPU(op1, op2, op3=0, f5: F_OP_F5=F_OP_F5.FADD, rnd= FP_ROUND_MODE.RNE, width=32):
    
       opf1 = BlockReg(32, op1, SF_block)
       opf2 = BlockReg(32, op2, SF_block)
       
       print(bin(opf1.S), bin(opf1.E-127), bin(opf1.M))
       print(bin(opf2.S), bin(opf2.E-127), bin(opf2.M))
       

# FPU(0x4020_0000, 0x3f80_0000)

csr = CsrFile([Ext.M])

# print(csr)
# print("fcsr", bin(csr.fcsr.all))
# print("frm ", bin(csr.frm.all))
# # print(csr.frm._blocks)
# # print(csr.frm._blk_bit_map)

# # csr.frm.all = 0b111
# # csr.frm.all = 0b1111111111
# # csr.frm.all
# print("fcsr", bin(csr.fcsr.all))
# print("frm ", bin(csr.frm.all))
# print(csr.fcsr._blocks)
# print(csr)
