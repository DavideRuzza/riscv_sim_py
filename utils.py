import struct
from math import ceil, log2
from enum import Enum
from cpu_enums import *
from typing import Dict, List, Tuple

import logging

log = logging.getLogger(__name__)

UNICODE = True

if UNICODE:
    TR="\u256e" # top right
    TL="\u256d" # top left
    BR="\u256f" # bottom right
    BL="\u2570" # bottom left
    VE="\u2502" # vertical
    HO="\u2500" # horizontal
    TC="\u252c" # top cross
    BC="\u2534" # bottom cross
else:
    TR="\\" # top right
    TL="/" # top left
    BR="/" # bottom right
    BL="\\" # bottom left
    VE="|" # vertical
    HO="-" # horizontal
    TC="+" # top cross
    BC="+" # bottom cross

COL = {
    "rst": "\033[0m",      # Reset all formatting
    "bold": "\033[1m",
    "underline": "\033[4m",

    # Regular colors
    "k" : "\033[30m",
    "r" : "\033[31m",
    "g" : "\033[32m",
    "y" : "\033[33m",
    "b" : "\033[34m",
    "m" : "\033[35m",
    "c" : "\033[36m",
    "w" : "\033[37m",
    "gr": "\033[90m",


    # Bright colors
    # "bright_black": "\033[90m",
    # "bright_red": "\033[91m",
    # "bright_green": "\033[92m",
    # "bright_yellow": "\033[93m",
    # "bright_blue": "\033[94m",
    # "bright_magenta": "\033[95m",
    # "bright_cyan": "\033[96m",
    # "bright_white": "\033[97m",
}

class Reg:
    def __init__(self, nbits, data=0):
        self.nbits = nbits
        self.mask = (1<<self.nbits)-1
        
        if data>0:
            assert log2(data) <= self.nbits, "%x can't be represented with %d bits, needs at least %d"%(data, self.nbits, log2(data)+1)
        self.reg = data & self.mask
    
    def write(self, data):
        self.reg = data & self.mask
    
    def data(self):
        return self.reg
    
    def __getitem__(self, key)->int:
        if isinstance(key, slice):
            start = key.start
            end = key.stop
            
            if start == None and end==None:
                return self.reg
            if start == None:
                start = self.nbits-1
            if end == None:
                end = 0

            assert self.nbits>start>end>=0, "Slice error, check indexes"
            return (self.reg>>end) & ((1<<(start-end+1))-1)
        else:
            assert self.nbits>key>=0, "index out of bound"
            return (self.reg>>key) & 0x01
    
    def __setitem__(self, key, value):
        
        if isinstance(key, slice):
            start = key.start
            end = key.stop
            if start == None:
                start = self.nbits-1
            if end == None:
                end = 0 
            bitsize = (start+1-end)
            assert self.nbits>start>end>=0, "Slice error, check indexes"
            assert len(bin(value)[2:]) <= bitsize
            
            slice_mask =  ~(((1<<bitsize)-1)<<end)&self.mask
            self.reg = (self.reg & slice_mask) | value << end
        elif isinstance(key, int):
            assert self.nbits>key>=0, "index out of bound"
            assert value < 2
            slice_mask =  ~(1<<key)&self.mask
            self.reg = (self.reg & slice_mask) | value << key
            
    def __or__(self, other):
        if isinstance(other, int):
            return self[:] | (other & self.mask)
        if isinstance(other, Reg):
            return self[:] | other[:]
    
    def __ior__(self, other):
        if isinstance(other, int):
            return self[:] | (other & self.mask)
        if isinstance(other, Reg):
            return self[:] | other[:]
    
    def __and__(self, other):
        if isinstance(other, int):
            return self[:] & (other & self.mask)
        if isinstance(other, Reg):
            return self[:] & other[:]
        
    def __iand__(self, other):
        if isinstance(other, int):
            return self[:] & (other & self.mask)
        if isinstance(other, Reg):
            return self[:] & other[:]
         
    def __str__(self):
        return "%x"%self.reg

class RegSlice():
    
    def __init__(self, reg: Reg, msb:int, lsb:int=None):
        
        self.reg : Reg = reg
        self.msb : int = msb
        self.lsb : int = lsb
        self.nbits : int 
        
        if lsb!=None:
            self.mask : int = (1<<(msb-lsb+1))-1
            self.nbits = msb-lsb
        else:
            self.mask = 0b1
            self.nbits = 1
        
    @property
    def val(self)->int:
        if self.lsb!=None:
            return self.reg[self.msb:self.lsb]
        else:
            return self.reg[self.msb]

    @val.setter
    def val(self, value : int):
        if self.lsb!=None:
            self.reg[self.msb:self.lsb] = value & self.mask
        else:
            self.reg[self.msb] = value & self.mask

class BlockReg(Reg):
    
    def __init__(self, xlen:int, data:int, sections:Dict[str, List[int]]
        ):
        super().__init__(xlen, data)
        
        # self.reg = Reg(xlen)
        sections['all'] = [xlen-1, 0]
        self._blocks = {
                blk : RegSlice(self, *bits) \
                    for blk, bits in sections.items()
            }
        self.end_attr = True

    def __getattr__(self, attr):
        if attr in self._blocks:
            blk = self._blocks[attr]
            # log.debug(f"CSR block read  {self.name}.{attr}"\
            #     f" -> 0b{blk.val:0{blk.nbits}b}")
            return blk.val
        raise AttributeError(f"{attr} not found")

    def __setattr__(self, attr, value):
        # If _blocks not yet created → just set attributes normally
        if attr == "_blocks" or "_blocks" not in self.__dict__:
            super().__setattr__(attr, value)
        elif attr in self._blocks:
            blk = self._blocks[attr]
            blk.val = value
            
            # if attr=='all':
            #     log.debug(f"CSR write {self.name}"\
            #         f" -> 0x{blk.val:0{int(self.nbits/4)}X}")
            # else:
            #     log.debug(f"CSR block write {self.name}.{attr}"\
            #         f" <- 0b{blk.val:0{blk.nbits}b}")
        else:
            super().__setattr__(attr, value)  # allow normal attributes
            
class RegFile:
    def __init__(self, n_regs, bus_size=32, reg_names:list[str]=None):
        self.n_regs = n_regs
        self.n_regs_log2 = int(log2(self.n_regs))
        self.bus_size = bus_size
        self.mask = (1<<self.bus_size)-1
        self.reg_file = [0]*self.n_regs
        self.reg_names = reg_names
        self.hex_fmt = "%016x" if bus_size==64 else "%016x"
        
        if not self.reg_names:
            self.reg_names = ["x%d"%i for i in range(self.n_regs)]
        else:
            assert self.n_regs == len(self.reg_names), "Number of names != reg number"
    
    def __getitem__(self, key):
        return self.reg_file[key]

    def __setitem__(self, key, value):
        if key>0:
            self.reg_file[key] = value & self.mask

    def show(self, stop=None):
        if not stop:
            stop = self.n_regs
            
        dump_str=""
        for i , name in zip(range(self.n_regs), self.reg_names):
            if (i)%4 == 0 and i>0:
                dump_str += '\n'
            if i>=stop:
                break
            if self.bus_size == 64:
                dump_str+="%3s: %016x " % (name, self.reg_file[i])
            else:
                dump_str+="%3s: %08x " % (name, self.reg_file[i])
        print(dump_str
        )
        
    def __str__(self):
        dump_str=""
        for i , name in zip(range(self.n_regs), self.reg_names):
            if (i)%4 == 0 and i>0:
                dump_str += '\n'
            if i>15:
                break
            if self.bus_size == 64:
                dump_str+="%3s: %016x " % (name, self.reg_file[i])
            else:
                dump_str+="%3s: %08x " % (name, self.reg_file[i])
        return dump_str

class CsrReg(Reg):
    
    def __init__(self, 
            addr:int, 
            name:str, 
            xlen:int, 
            sections:Dict[str, List[int]]
        ):
        super().__init__(xlen, 0)
        
        # sections be like {"name": [12,0], "name1": [20:13], ... }
        # this will create n regslices referencing the csr bloks
        # self.xlen = xlen
        self.addr = addr
        self.name = name
    
        addr_reg = Reg(12, addr)
        self.rw = addr_reg[11:10]
        self.priv = Mode(addr_reg[9:8])
        
        # self.reg = Reg(xlen)
        sections['all'] = [xlen-1, 0]
        self._blocks = {
                blk : RegSlice(self, *bits) \
                    for blk, bits in sections.items()
            }
        self.end_attr = True

    def __getattr__(self, attr):
        if attr in self._blocks:
            blk = self._blocks[attr]
            log.debug(f"CSR block read  {self.name}.{attr}"\
                f" -> 0b{blk.val:0{blk.nbits}b}")
            return blk.val
        raise AttributeError(f"{attr} not found")

    def __setattr__(self, attr, value):
        # If _blocks not yet created → just set attributes normally
        if attr == "_blocks" or "_blocks" not in self.__dict__:
            super().__setattr__(attr, value)
        elif attr in self._blocks:
            blk = self._blocks[attr]
            blk.val = value
            
            if attr=='all':
                log.debug(f"CSR write {self.name}"\
                    f" -> 0x{blk.val:0{int(self.nbits/4)}X}")
            else:
                log.debug(f"CSR block write {self.name}.{attr}"\
                    f" <- 0b{blk.val:0{blk.nbits}b}")
        else:
            super().__setattr__(attr, value)  # allow normal attributes

#########################

class CsrFile():
    # TODO: implement attr get and set and log print on read. write is done

    def __init__(self, ext_list: List[Ext]):     
        
        self.ext_list = ext_list 
        self.csr_map : Dict[int, CsrReg] = {}
        self.name_to_addr : Dict[str, int] = {}
            
        for ext in self.ext_list:
            if   ext==Ext.M: self.add_csr_dict(CSR_M)
            elif ext==Ext.S: self.add_csr_dict(CSR_S)
            elif ext==Ext.U: self.add_csr_dict(CSR_U)
            else:
                raise AssertionError(f"unknown extension {ext.name}")
        
    def add_csr_dict(self, 
            csr_dict : Dict[int, Tuple[str, int, Dict[str, List[int]]]]):
        
        for name, value in csr_dict.items():
            addr, xlen, block_map = value
            self.csr_map[addr] = CsrReg(addr, name, xlen, block_map)
            self.name_to_addr[name] = addr
    
    
    def __getitem__(self, key):
        
        addr = key
        if type(key) == str:
            addr = self.name_to_addr[key]
        csr_reg = self.csr_map[addr]

        return csr_reg

    def __setitem__(self, key, value):
        
        addr = key
        if type(key) == str:
            addr = self.name_to_addr[key]
        csr_reg = self.csr_map[addr]
        csr_reg[:] = value&((1<<csr_reg.nbits)-1)
        log.debug(f"CSR write {csr_reg.name}"\
                f" -> 0x{csr_reg[:]:0{int(csr_reg.nbits/4)}X}")
    
    def __getattr__(self, attr):
        if attr in self.name_to_addr:
            addr = self.name_to_addr[attr]
            csr_reg = self.csr_map[addr]
            return csr_reg
        raise AttributeError(f"{attr} not found")
    
    def __repr__(self):
        max_len = max([len(i) for i in self.name_to_addr.keys()])
        
        out = ["=== CSR File ==="]
        
        y = COL['y']
        g = COL['g']
        gr = COL['gr']
        rst = COL['rst']
        bold = COL['bold']
        ul = COL['underline']
        for addr, csr in self.csr_map.items():
            
            out.append(f"* {y}0x{addr:03X} {g}{ul}{csr.name}{rst} "\
                f"{gr}{bold}{'-'*(max_len-len(csr.name))}{gr}" \
                f"{'rw' if csr.rw==3 else f"r-"}-{csr.priv.name}- "\
                f"{rst}0x{csr[:]:0{int(csr.nbits/4)}X}"
                )
            
        return "\n".join(out)
    
    


def int_64(uint_64):
    uint_64 = Reg(64, uint_64)
    if uint_64[63]:
        return int(uint_64[:] - (1<<64))
    else:
        return uint_64[:] 
      
def int_32(uint_32):
    uint_32 = Reg(32, uint_32)
    if uint_32[31]:
        return int(uint_32[:] - (1<<32))
    else:
        return uint_32[:] 
    
def sign_extend(value, bits):
    sign_bit = 1 << (bits - 1)
    return (value & (sign_bit - 1)) - (value & sign_bit)

def zero_extend(num, n):
    return num & ((1<<n)-1)

def to_signed(num, nlen):
    # def sign_extend_32(value):
    if num & (1<<(nlen-1)):  # Check MSB for 32-bit
        num =  num - (1<<nlen)  # Subtract 2^32
    return num 
