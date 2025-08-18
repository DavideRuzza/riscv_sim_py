import struct
from math import ceil, log2
# from enum import Enum
from cpu_enums import Extension
from cpu_enums import *

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

# MASK64 = (1<<64)-1
# MASK32 = (1<<32)-1



class MainMemory:
    def __init__(self, size_Kb, offset=0, bus_size=32):
        # size in KB
        self.offset = offset
        self.mask = (1<<bus_size)-1
        self.size_kb = size_Kb
        self.size_byte = self.size_kb*0x400
        self.mem = b'\x00' * self.size_byte
    
    def clear(self):
        self.mem = b'\x00' * self.size_byte
    
    def write(self, addr, data: bytearray):
        addr -= self.offset
        assert 0 <= addr
        assert addr <= int(self.size_byte), "address "+hex(addr)+" with size "+hex(self.size_byte)
        self.mem = self.mem[:addr] + struct.pack("<I", data&self.mask) + self.mem[addr+4:]
    
    def write_double(self, addr, data: bytearray):
        addr -= self.offset
        assert 0 <= addr
        assert addr <= int(self.size_byte), "address "+hex(addr)+" with size "+hex(self.size_byte)
        self.mem = self.mem[:addr] + struct.pack("<Q", data&self.mask) + self.mem[addr+8:]
    
    
    def write_block(self, addr, data: bytearray):
        addr -= self.offset
        assert 0 <= addr
        assert addr <= int(self.size_byte), "address "+hex(addr)+" with size "+hex(self.size_byte)
        self.mem = self.mem[:addr] + data + self.mem[addr+len(data):]

    def hexdump(self, bytes_per_line=16):
                   
        previous_line = None
        repeated = False
        offset = 0

        for i in range(0, len(self.mem), bytes_per_line):
            chunk = self.mem[i:i + bytes_per_line]
            hex_part = " ".join(f"{b:02x}" for b in chunk)
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            if chunk == previous_line:
                if not repeated:
                    print("*")
                    repeated = True
            else:
                print(f"{offset:08x}  {hex_part:<{bytes_per_line * 3}}  |{ascii_part}|")
                repeated = False
            previous_line = chunk
            offset += bytes_per_line
        
        if repeated:
            print(f"{offset-bytes_per_line:08x}  {hex_part:<{bytes_per_line * 3}}  |{ascii_part}|")
        
    def __getitem__(self, addr):
        if isinstance(addr, int):
            addr -= self.offset
            assert 0 <= addr < int(self.size_byte), f"Addr {addr:016x}"
            return struct.unpack("<I", self.mem[addr:addr+4])[0]
        
        elif isinstance(addr, slice):
            start = addr.start - self.offset
            end = addr.stop - self.offset
            return self.mem[int(start):int(end)]
    
    def __setitem__(self, addr, value):
        addr -= self.offset
        # word = struct.pack("<I", value&self.mask)
        # print(f"set item in memory {addr:08x} {value:08x} {word}")
        assert 0 <= addr, "address negative"
        assert addr < int(self.size_byte), "not enough space to allocate data"
        self.mem = self.mem[:addr] + struct.pack("<I", value&self.mask) + self.mem[addr+4:]
        
    def __str__(self):
        return f"Memory size: {len(self.mem)} ({self.size_kb} KB)"
       
class Reg:
    def __init__(self, nbits, data=0):
        self.nbits = nbits
        self.mask = (1<<self.nbits)-1
        
        if data>0:
            assert log2(data) <= self.nbits, "%x can't be represented with %d bits, needs at least %d"%(data, self.nbits, log2(data)+1)
        self.reg = data & self.mask
    
    def write(self, data):
        # print("type ",type(data), log2(3) )
        # assert log2(data) < self.nbits, "Reg assigment invalid, not enough bit %d %d"%(data, self.nbits)
        self.reg = data & self.mask
    
    def data(self):
        return self.reg
    
    def __getitem__(self, key):
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
            
    def __str__(self):
        return "%x"%self.reg
    
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
    
    def __init__(self, addr, value, name, xlen=32):
        super().__init__(xlen, value)
        
        self.addr = addr
        self.name = name
        
        addr_reg = Reg(12, addr)
        self.rw_perm = addr_reg[11:10]
        self.priviledge = addr_reg[9:8]
    
    def value(self):
        return self.reg[:]
        
    def bits_set(self, sets):
        self |= sets
    
    def bits_clear(self, clear):
        self &= ~clear
    
    def __repr__(self):
        return f"<0x{self.addr:03X} {self.reg:08X} {self.name} rw={self.rw_perm}>"
    
    def __str__(self):
        
        value = f"value={self.reg:016X} " if self.nbits==64 else f"value={self.reg:08X} "
        return f"<addr=0x{self.addr:03X} "+  \
            value+ \
            f"rw={(self.rw_perm>1)&0b1}{(self.rw_perm)&0b1} " + \
            f"priv={Priviledge(self.priviledge).name} "  + \
            f"name=\"{self.name}\">"


##########################

class CsrFile():

    csr_F = {
        0x001: "fflags",
        0x002: "frm",
        0x003: "fcsr"
    }

    csr_M = {

        0x740: "mnscratch",
        0x741: "mnepc",
        0x742: "mncause",
        0x744: "mnstatus",
        0xF11: "mverndorid",
        0xF12: "marchid",
        0xF13: "mimpid",
        0xF14: "mhartid",
        0xF15: "mconfigptrid",
        
        0x300: "mstatus",
        0x301: "misa",
        0x302: "medeleg",
        0x303: "mideleg",
        0x304: "mie",
        0x305: "mtvec",
        0x306: "mcounteren",
        0x310: "mstatush",   # RV32 only
        0x312: "mdelegh",   # RV32 only
        
        0x340: "mscratch",
        0x341: "mepc",
        0x342: "mcause",
        0x343: "mtval",
        0x344: "mip",
        0x34A: "mtinst",
        0x34B: "mtval2",
        
        0x3B0: "pmpaddr0",
        0x3A0: "pmpcfg0"
        
    }
    
    csr_S = {
        0x100: "sstatus",
        0x104: "sie",
        0x105: "stvec",
        0x106: "scounteren",
        
        0x10A: "senvcfg",
        0x120: "scountinhibit",
        
        0x140: "sscratch",
        0x141: "sepc",
        0x142: "scause",
        0x143: "stval",
        0x144: "sip",
        0xDA0: "scountovf",
        
        0x180: "satp",
        0x5A8: "scontext",
        
        0x10C: "sstateen0",
        0x10D: "sstateen1",
        0x10E: "sstateen2",
        0x10F: "sstateen3"
    }

    def __init__(self, extensions, xlen=32):

        # self.csr_dict
        self.regs = {}
        self.xlen = xlen
        
        self.extensions = extensions

        self._inverted_keys = {}
            
        self.initialize()
        
    
    def initialize(self):
        # print("Csr File")
        if self.has_extension(Extension.M):
            print(" - Machine CSR")
            self.create_from_dict(self.csr_M)
        
        if self.has_extension(Extension.S):
            print(" - Supervisor CSR")
            self.create_from_dict(self.csr_S)
         
    def create_from_dict(self, csr_dict: dict):
        
        for addr, name in csr_dict.items():
            self.regs[addr] = CsrReg(addr, 0, name, self.xlen)

        self._inverted_keys.update({v: k for k, v in csr_dict.items()})
            
    
    def has_extension(self, ext: Extension):
        return bool(self.extensions & ext.value)

    def show(self):
        for addr, reg in self.regs.items():
            print(reg)
        
    def __setitem__(self, key, value):
        if isinstance(key, int): # by address
            self.regs[key][:] = value
        if isinstance(key, str):
            assert key in self._inverted_keys, f"{key} not in CsrFile"
            self.regs[self._inverted_keys[key]][:] = value

    def __getitem__(self, key):
        if isinstance(key, int): # by address
            return self.regs[key]
        if isinstance(key, str):
            assert key in self._inverted_keys, f"{key} not in CsrFile"
            return self.regs[self._inverted_keys[key]]
    

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
