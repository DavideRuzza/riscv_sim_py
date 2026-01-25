import logging
from struct import pack, unpack
from utils import CsrReg

from typing import List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from main import RV64Hart

log = logging.getLogger(__name__)


class BaseDevice:
    
    def __init__(self, size, name="dev"):
        self.size : int = size
        self.name : str = name
        # self.mem : bytearray = b'\x00'*self.size
    
    def read(self, addr: int, size: int = 4) -> int:
        assert NotImplementedError(
            "read() method not implemented for {}".format(self.__class__.__name__))
    
    def write(self, addr: int, value: int, size: int = 4):
        assert NotImplementedError(
            "read() method not implemented for {}".format(self.__class__.__name__))

    def check_mem_bounds(self, addr: int, size:int):
        assert addr>=0, "something is wrong addr < 0" 
        assert addr+size<=self.size-1, \
            f"addr: {hex(addr+size)} is more than device size"
        
    def __repr__(self):
        return f"{self.__class__.__name__}(name={self.name}, size={self.size:x})"



class MemoryDevice(BaseDevice):
    
    def __init__(self, size, name="dev"):
        self.size : int = size
        self.name : str = name
        self.mem : bytearray = b'\x00'*self.size
    
    @classmethod
    def from_binary_file(
            cls: 'BaseDevice', 
            filepath: str, 
            name='dev') -> 'MemoryDevice':
        
        with open(filepath, 'rb') as f:
            data = f.read()
        
        size = len(data)
        round_size = cls.round4Kb(len(data))
        newdev = cls(size=round_size, name=name)
        data = data+b'\x00'*(round_size-size)
        newdev.mem = data

        return newdev
    
    def read(self, addr: int, size: int = 4) -> int:
        assert addr>=0, "something is wrong addr < 0" 
        assert addr+size<=self.size-1, \
            f"addr: {hex(addr+size)} is more than dev size"
        
        enc_str = self.get_encoding(size)
        return unpack(enc_str, self.mem[addr:addr+size])[0]
    
    def write(self, addr: int, value: int, size: int = 4):
        
        assert addr>=0, "something is wrong addr < 0" 
        assert addr+size<=self.size-1, \
            f"addr: {hex(addr+size)} is more than dev size"
        
        mask = (1<<(size*8))-1
        enc_str = self.get_encoding(size)
        data = pack(enc_str, value&mask)
        self.mem = self.mem[:addr] + data + self.mem[addr+size:]
    
    @staticmethod
    def round4Kb(n: int) -> int:
        return ((n + 4095) // 4096) * 4096
    
    @staticmethod
    def get_encoding(size: int):
        if size == 8:
            return "<Q"
        elif size == 4:
            return "<L"
        elif size == 2:
            return "<H"
        else:
            return "<B"
    
    def hexdump(self, width: int = 16):
        def is_printable(b):
            return 32 <= b <= 126

        previous_chunk = None
        skipping = False
        data = self.mem
        for offset in range(0, len(data), width):
            chunk = data[offset:offset + width]

            if chunk == previous_chunk:
                if not skipping:
                    print("*")
                    skipping = True
                continue

            skipping = False
            previous_chunk = chunk

            hex_bytes = ' '.join(f'{b:02X}' for b in chunk)
            ascii_repr = ''.join(chr(b) if is_printable(b) else '.' for b in chunk)

            # Pad hex part to align properly
            padding = '   ' * (width - len(chunk))
            hex_part = f"{hex_bytes}{padding}"

            # Optional: add a space in the middle
            if len(chunk) > 8:
                hex_part = f"{hex_part[:3*8]} {hex_part[3*8:]}"

            print(f"{offset:08X}  {hex_part}  |{ascii_repr}|")

        print(f"{len(data):08X}")
    
    def size_str(self):
        
        s = self.size/8
        
        if s>1e9:
            return f"{s/1e9:.1f}Gb"
        elif s>1e6:
            return f"{s/1e6:.1f}Mb"
        elif s>1e3:
            return f"{s/1e3:.1f}Kb"
        else:
            return f"{s:.1f}b"
        
    def expand(self, end: int):
        new_size = self.round4Kb(end+self.size)
        data = self.mem+b'\x00'*(new_size-self.size)
        self.size = new_size
        self.mem = data
        
    def __repr__(self):
        return f"{self.__class__.__name__}(name={self.name}, size={self.size_str()})"
 
# https://stackoverflow.com/questions/78346549/clarifying-connectivity-and-memory-implementation-in-the-risc5-platform-architec
# https://chromitem-soc.readthedocs.io/en/0.9.9/clint.html
# https://pdos.csail.mit.edu/6.828/2025/readings/FU540-C000-v1.0.pdf
# https://www.kernel.org/doc/Documentation/devicetree/bindings/timer/sifive%2Cclint.yaml
class CLINT(BaseDevice):
    
    # standard timer interrupt bit in MIP csr
    MTIP = 7
    # STIP = 5
    
    # standard software interrupt bit in MIP csr
    MSIP = 3
    # SSIP = 1
    
    BASE_MSIP = 0x0
    BASE_MTIMECMP = 0x4000
    BASE_MTIME = 0xBFF8 
    
    def __init__(self):
        super().__init__(size=0x10000, name="CLINT")
            
        self.num_harts : int = 0
        self.hart_mip : List[CsrReg] = []
        
        self.timer_int_pending = []
        self.software_int_pending = []
        
        self.mtime : int = 0
        
        self.mtimecmp : List[int]= []
    
    def inc_time(self):
        
        self.mtime += 1
        self.update_logic()
        
    def update_logic(self):
        
        for i in range(self.num_harts):
            if self.mtimecmp[i] < self.mtime:
                print(f"hart {i} has timer interrupt")
                self.timer_int_pending[i] = 1
                self.hart_mip[i].MTIP = 1
            else:
                self.timer_int_pending[i] = 0
                self.hart_mip[i].MTIP = 0
                
        for i in range(self.num_harts):
            if self.software_int_pending[i] > 0:
                self.hart_mip[i].MSIP = 1
            else:
                self.hart_mip[i].MSIP = 0
        
        
    def register_hart(self, hart = 'RV64Hart'):
        self.num_harts+=1
        self.hart_mip.append(hart.csr.mip)
        self.timer_int_pending.append(0)
        self.software_int_pending.append(0)
        self.mtimecmp.append(0)

    
    def read(self, addr, size = 4):
        

        if self.BASE_MSIP<=addr<self.BASE_MTIMECMP:
            
            addr -= self.BASE_MSIP
            hart_id = addr>>2
            if hart_id<self.num_harts:
                return self.software_int_pending[hart_id]
            
        elif self.BASE_MTIMECMP<=addr<self.BASE_MTIME:
                
            addr -= self.BASE_MTIMECMP
            hart_id = addr>>2
            if hart_id<self.num_harts:
                return self.mtimecmp[hart_id]
            
        elif addr == self.BASE_MTIME:
            return self.mtime
                
        return 0
    
    def write(self, addr, value, size = 4):
        
        if self.BASE_MSIP<=addr<self.BASE_MTIMECMP:
            
            addr -= self.BASE_MSIP
            hart_id = addr>>2
            if hart_id<self.num_harts:
                self.software_int_pending[hart_id] = value & 0x1 
            
        elif self.BASE_MTIMECMP<=addr<self.BASE_MTIME:
                
            addr -= self.BASE_MTIMECMP
            hart_id = addr>>2
            if hart_id<self.num_harts:
                print("mtime_cmp h{}".format(hart_id), value)
                self.mtimecmp[hart_id] = value
            
        elif addr == self.BASE_MTIME:
            self.mtime = value
        
        self.update_logic()        


# https://www.kernel.org/doc/Documentation/devicetree/bindings/interrupt-controller/sifive%2Cplic-1.0.0.txt
# https://pdos.csail.mit.edu/6.828/2025/readings/FU540-C000-v1.0.pdf
class InterruptController(BaseDevice):
    
    PENDING_BASE = 0x1000
    ENABLE_BASE = 0x2000
    THRES_CLAIM_BASE = 0x20_0000
    
    CONTEXT_OFFSET = 0x1000
    
    def __init__(self, 
            context_num: int, 
            interrupt_source_num: int,
        ):
        super().__init__(size=0x400_0000, name="PLIC")
        
        self.num_sources = interrupt_source_num + 1 
        # every context is assigned to a MIP, MIE and xEIP bit position 
        self.ctx_list : List[Tuple[CsrReg, int]] = []
        self.priority = [0] * (self.num_sources)
        self.pending = [0] * (self.num_sources)
        self.enable = [[0] * (self.num_sources) for _ in range(context_num)]
        self.threshold = [0] * context_num
        self.claimed = [0] * context_num

    def set_interrupt(self, irq_source):
        self.pending[irq_source] = 1
        # print("Set Interrupt {}".format(irq_source))
        self.update_logic()
    
    def register_context(self, hart: 'RV64Hart', bit: int)->int:
        ''' 
        Register a context to a hart MIP register selecting 
        the bit to set as external interrupt (usually 9 for S mode, 11 for M mode)
        
        return the context id attached to this bit
        '''
        
        ctx_num = len(self.ctx_list)
        
        self.ctx_list.append(
            (hart.csr.mip, bit)
        ) 
        
        return ctx_num

    def update_logic(self):
        '''
        set per context the xPIE bit 
        in the csr if any interrupt is pending
        '''
        for ctx in range(len(self.ctx_list)):
            source_pending = 0
            for src in range(self.num_sources):
                # if the source is enabled for the context
                if self.pending[src] and self.enable[ctx][src]:
                    # if the treshold of the ctx allows interrupt from source 
                    if self.priority[src] > self.threshold[ctx]:
                        # if context has already claimed an interrupt
                        if self.claimed[ctx] != None:
                            source_pending = src
                            break
                        
            # set the bit in the mip of the context
            if source_pending>0:
                self.ctx_list[ctx][0][self.ctx_list[ctx][1]] = 1 # element 0 is the CsrReg MIP
            else:
                self.ctx_list[ctx][0][self.ctx_list[ctx][1]] = 0
        
    def read(self, addr, size = 4):
        return super().read(addr, size)
    
    def _claim(self, ctx: int)->int:
        # find best irq num
        
        if self.claimed[ctx]>0: # already claime
            return 0
        
        best_priority = -1
        irq_id = 0
        
        for src in range(self.num_sources):
            # if the source is enabled for the context
            if self.pending[src] and self.enable[ctx][src]:
                # if the treshold of the ctx allows interrupt from source 
                if self.priority[src] >= self.threshold[ctx]:
                    if self.priority[src] > best_priority:
                        irq_id = src
                        best_priority = self.priority[src]
        
        self.claimed[ctx] = irq_id 
        self.update_logic()
        log.debug(f"[PLIC] Context {ctx} claimed irq {irq_id}")
        return irq_id
        
    def _complete(self, src_num):
        
        for i in range(len(self.claimed)):
            if self.claimed[i] == src_num:
                # if src id match one serving interrupt, 
                # than clear it so more pending can happend
                self.claimed[i] = 0
                self.pending[src_num] = 0
                log.debug(f"[PLIC] irq {src_num} completed!")
        self.update_logic()
        
    
    def read(self, addr, size=4):
        
        if addr<self.PENDING_BASE: # proprity section
            src = addr>>2 # every source proprity is 4 byte aligned 
            
            if src<=self.num_sources: # don't allow more than max source
                # 0x7 -> 8 level of priprity allowed
                return self.priority[src]
        
        elif self.PENDING_BASE<=addr<self.ENABLE_BASE: # pending
            addr = addr-self.PENDING_BASE
            
            src_idx_line = addr>>2 # every address can hold 32 interrupt sources
            pending_total = 0
            # return a number capable or reading a 1, 2, 4, 8 byte long number
            for i in range(size*8):
                src = src_idx_line * 32 + i
                if src>=self.num_sources:
                    break
                pending_total += int(self.pending[src]>0) << i
            return pending_total

        elif self.ENABLE_BASE<=addr<self.THRES_CLAIM_BASE: # enables
            addr = addr-self.ENABLE_BASE
            
            ctx = addr // 0x80
            if ctx>=len(self.ctx_list):
                return 0
            
            src_idx_line = (addr % 0x80)>>2 # every address can hold 32 interrupt sources
            
            enable_total = 0
            # return a number capable or reading a 1, 2, 4, 8 byte long number
            for i in range(size*8):
                src = src_idx_line * 32 + i
                if src>=self.num_sources:
                    break
                # print('ctx', ctx)
                # print('src', src)
                enable_total += int(self.enable[ctx][src]>0) << i
            return enable_total
        
        elif self.THRES_CLAIM_BASE<=addr<self.size:
            addr = addr-self.THRES_CLAIM_BASE
            
            ctx = addr // self.CONTEXT_OFFSET
            if ctx>=len(self.ctx_list):
                return 0
            
            # check the memory address num
            reg_cond = ((addr-ctx*self.CONTEXT_OFFSET)>>2)
            if reg_cond == 0:
                # priority
                return self.threshold[ctx]
            elif reg_cond == 1:
                # claim/complete memory addr
                return self._claim(ctx)

            return 0
        self.update_logic()
        return 0
        
    
    def write(self, addr, value, size = 4):

        if addr<self.PENDING_BASE: # proprity section
            src = addr>>2 # every source proprity is 4 byte aligned 
            
            if src<=self.num_sources: # don't allow more than max source
                
                # 0x7 -> 8 level of priprity allowed
                self.priority[src] = value & 0x7
        
        elif self.ENABLE_BASE<=addr<self.THRES_CLAIM_BASE: # pending
            addr = addr-self.ENABLE_BASE
            
            ctx = addr // 0x80
            
            src_idx_line = (addr % 0x80)>>2 # every address can hold 32 interrupt sources
            
            for i in range(self.num_sources):
                src = src_idx_line * 32 + i
                self.enable[ctx][src] = (value>>i) & 0x1

        elif self.THRES_CLAIM_BASE<=addr<self.size:
            addr = addr-self.THRES_CLAIM_BASE
            
            ctx = addr // self.CONTEXT_OFFSET
            
            # check the memory address num
            reg_cond = ((addr-ctx*self.CONTEXT_OFFSET)>>2)
            
            if reg_cond == 0:
                # priority
                self.threshold[ctx] = value & 0x7
            elif reg_cond == 1:
                # claim/complete memory addr
                self._complete(value)
        
        self.update_logic()