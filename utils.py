import struct
from math import ceil, log2
from enum import Enum
from cpu_enums import *
from typing import Dict, List, Tuple
from elftools.elf.elffile import ELFFile

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import RV64Hart

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

def full_bin(num, l=32):
    bin_str = bin(num)[2:]
    return '0'*(l-len(bin_str))+bin_str

def get_symbol_info(elf_path, symbol_name):
    with open(elf_path, "rb") as f:
        elffile = ELFFile(f)

        for section in elffile.iter_sections():
            if section.header.sh_type not in ("SHT_SYMTAB", "SHT_DYNSYM"):
                continue

            for symbol in section.iter_symbols():
                if symbol.name == symbol_name:
                    return {
                        "name": symbol.name,
                        "address": symbol.entry.st_value,
                        "size": symbol.entry.st_size,
                        "section_index": symbol.entry.st_shndx
                    }
    return None

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
    
    def __getitem__(self, key):
        if isinstance(key, slice):
            start = key.start
            end = key.stop
            
            if start == None and end==None:
                return self.val
            if start == None:
                start = self.nbits-1
            if end == None:
                end = 0
            
            print(self.nbits, start, end)
            assert self.nbits>start>end>=0, "Slice error, check indexes"
            start += self.lsb
            stop += self.lsb
            return (self.val>>end) & ((1<<(start-end+1))-1)
        else:
            assert self.nbits>key>=0, "index out of bound"
            return (self.val>>key+self.lsb) & 0x01
        
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
    def __init__(
            self,
            n_regs,
            bus_size=32,
            reg_names:list[str]=None,
            lock_0=True, # lock writing first element
            ):
        
        self.n_regs = n_regs
        self.n_regs_log2 = int(log2(self.n_regs))
        self.bus_size = bus_size
        self.mask = (1<<self.bus_size)-1
        self.reg_file = [0]*self.n_regs
        self.reg_names = reg_names
        self.hex_fmt = "%016x" if bus_size==64 else "%016x"
        self.lock_0 = lock_0
        
        if not self.reg_names:
            self.reg_names = ["x%d"%i for i in range(self.n_regs)]
        else:
            assert self.n_regs == len(self.reg_names), "Number of names != reg number"
    
    def __getitem__(self, key):
        return self.reg_file[key]

    def __setitem__(self, key, value):
        # if key>0 or self.lock_0:
        if self.lock_0:
            if key>0:
                self.reg_file[key] = value & self.mask
        else:
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
    
class CsrReg():
    
    def __init__(self, 
            addr:int, 
            name:str, 
            xlen:int, 
            sections: Dict[str, List[int]],
            blk_warl : Dict[str, List[int]] = {}, 
            blk_wpri : Dict[str, List[int]] = {},
            reg : Reg = None,
        ):
        
        if reg==None:
            self.reg = Reg(xlen, 0)
        else:
            self.reg = reg
            
        self.nbits = self.reg.nbits
        self.mask = self.reg.mask
        # sections be like {"name": [12,0], "name1": [20:13], ... }
        # this will create n regslices referencing the csr bloks
        # self.xlen = xlen
        
        self.addr = addr
        self.name = name
    
        addr_reg = Reg(12, addr)
        self.rw = addr_reg[11:10]
        self.priv = Mode(addr_reg[9:8])
        
        # self.reg = Reg(xlen)
        self._blk_bit_map = sections.copy()
        self._blk_bit_map.update(blk_wpri)
        
        sections['all'] = [xlen-1, 0] # add the "all" section 
        
        self._blocks = {
                blk : RegSlice(self.reg, *bits) \
                    for blk, bits in sections.items()
            }
        
        self._blocks.update({blk: None for blk in blk_wpri})
        
        self.blk_warl = blk_warl # possible values for every WARL block
        self.blk_wpri = blk_wpri # unaccessible blocks defined with WPRI
        
        self.blk_mask = self.gen_blk_mask()
        self.blk_mask_n = self.gen_blk_mask(neg=True) #(~self.blk_mask) & self.mask
    
        self.wpri_mask = self.gen_wpri_mask(True) # negative
        
    def __getitem__(self, key):
        return self.reg[key]
    
    def __setitem__(self, key, value):
        self.reg[key] = value
    
    def __getattr__(self, attr):
        if attr in self._blocks:
            blk = self._blocks[attr]
            if attr=='all':
                if '_sdw' in self._blocks:
                    self._sdw = self._sdw_ref
            #     lsb=0
                # pass
            # else:
            #     lsb = self._blk_bit_map[attr][-1]
            if blk.nbits>15:
                log.debug(f"CSR block read {self.name}.{attr}"\
                    f" -> 0x{blk.val:0{int(self.nbits/4)}X}")
            else:
                log.debug(f"CSR block read {self.name}.{attr}"\
                    f" -> 0b{blk.val:0{blk.nbits}b}")
            return blk.val #& ((self.wpri_mask&self.gen_blk_mask(attr))>>lsb)
        raise AttributeError(f"{attr} not found")           
             
    def __setattr__(self, attr, value):
        # If _blocks not yet created → just set attributes normally
        if attr == "_blocks" or "_blocks" not in self.__dict__:
            super().__setattr__(attr, value)
        elif attr in self._blocks:
            blk = self._blocks[attr]
            written = False
            
            if attr=='all':
                # first write the csr parts that are not warl
                masked_value = (value&self.blk_mask_n) | (blk.val&self.blk_mask)
                blk.val = masked_value
                
                # then write all the blocks separately
                for name, bits in self._blk_bit_map.items():
                    # print(name, bits)
                    # sub_blk = self._blocks[attr]
                    if name in self.blk_wpri:
                        continue
                    blk_mask = self.gen_blk_mask(name)
                    blk_set_val = (value&blk_mask)>>bits[-1]
                    if name in self.blk_warl:
                        if blk_set_val in self.blk_warl[name]:
                            self._blocks[name].val = blk_set_val
                    else:
                        self._blocks[name].val = blk_set_val   

                log.debug(f"CSR write {self.name}"\
                    f" <- 0x{blk.val:0{int(self.nbits/4)}X}")
            else:
                
                if attr in self.blk_warl:
                    if value in self.blk_warl[attr]:
                        blk.val = value
                        written=True
                else:
                    blk.val = value
                    written=True
                
                if written:
                    if blk.nbits>15:
                        log.debug(f"CSR block write {self.name}.{attr}"\
                            f" <- 0x{blk.val:0{int(self.nbits/4)}X}")
                    else:
                        log.debug(f"CSR block write {self.name}.{attr}"\
                            f" <- 0b{blk.val:0{blk.nbits}b}")
        else:
            super().__setattr__(attr, value)  # allow normal attributes

    def add_warl_to_blk(self, blk_name:str, warl_value:int):
        
        if blk_name not in self.blk_warl:
            self.blk_warl[blk_name] = [warl_value]
        else:
            self.blk_warl[blk_name].append(warl_value)
    
    def update_warl_blk(self, blk_name:str, warl_list:List[int]):
        
        self.blk_warl[blk_name] = warl_list

    
    def gen_blk_mask(self, name=None, neg=False):
        # generate mask of 1 where there is a csr block
        mask = 0
        
        if name: assert name in self._blocks, f"{name} block don't exist"
        for n, bits in self._blk_bit_map.items():
            if name!=None and n!=name and name!='all':
                continue
            
            if len(bits)>1:
                bit_span = bits[0]-bits[1]+1
            else:
                bit_span = 1
            blk_mask = (1<<bit_span)-1
            mask |= (blk_mask<<bits[-1])
        
        if neg: mask = (~mask) & self.mask
    
        return mask & self.mask

    def gen_wpri_mask(self, neg=False):
        # generate mask of 1 where there is a csr WPRI block
        mask = 0
        
        for n, bits in self.blk_wpri.items():
            
            if len(bits)>1:
                bit_span = bits[0]-bits[1]+1
            else:
                bit_span = 1
            blk_mask = (1<<bit_span)-1
            mask |= (blk_mask<<bits[-1])
        
        if neg: mask = (~mask) & self.mask
    
        return mask & self.mask
    
#########################

class CsrFile():
    # TODO: implement attr get and set and log print on read. write is done

    def __init__(self, ext_list: List[Ext]=None):     
        
        self.ext_list = ext_list 
        self.csr_map : Dict[int, CsrReg] = {}
        self.name_to_addr : Dict[str, int] = {}
        self.addr_to_name : Dict[int, str] = {}
        
        self.add_csr_dict(CSR_M)
        
    def add_csr_dict(self, 
            csr_dict : Dict[int, Tuple[str, int, Dict[str, List[int]]]]):
        
        for name, value in csr_dict.items():
            addr, xlen, block_map, wpri, shadow = value
            
            if shadow:
                if '.' in shadow:
                    base, block = shadow.split(".")
                

                    shw_blk = self[base]._blocks[block]

                    block_map['_sdw'] = [shw_blk.nbits,0]
                    self.csr_map[addr] = CsrReg(
                        addr, name, 
                        xlen, block_map,
                        blk_wpri=wpri)
                    
                    self.csr_map[addr]._blocks['_sdw_ref'] = shw_blk
                    self.csr_map[addr]._blk_bit_map['_sdw_ref'] = [shw_blk.nbits,0]
                else:
                    self.csr_map[addr] = CsrReg(
                        addr, name, 
                        xlen, block_map,
                        blk_wpri=wpri, reg=self[shadow].reg)
            else:
                self.csr_map[addr] = CsrReg(
                    addr, name, 
                    xlen, block_map,
                    blk_wpri=wpri)
                
            self.name_to_addr[name] = addr
            self.addr_to_name[addr] = name
    
    
    def __getitem__(self, key):
        
        addr = key
        if type(key) == str:
            addr = self.name_to_addr[key]
        try:
            csr_reg = self.csr_map[addr]
        except:
            raise KeyError(f"no csr found in 0x{addr:03X}")

        return csr_reg

    def __setitem__(self, key, value):
        
        addr = key
        if type(key) == str:
            addr = self.name_to_addr[key]
        csr_reg = self.csr_map[addr]
        csr_reg[:] = value&((1<<csr_reg.nbits)-1)
        log.debug(f"CSR write {csr_reg.name}"\
                f" <- 0x{csr_reg[:]:0{int(csr_reg.nbits/4)}X}")
    
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
                f"{'rw' if csr.rw!=3 else f"r-"}-{csr.priv.name}- "\
                f"{rst}0x{csr.all:0{int(csr.nbits/4)}X}"
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