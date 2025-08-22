import logging
from devices import *
from typing import List, Dict, Tuple

log = logging.getLogger(__name__)



class SystemInterface():
    
    def __init__(self):
        
        self.dev_map : Dict[int, BaseDevice] = {}
        self.dev_list : List[BaseDevice] = []
        self.mem_map : List[List[int, int]] = []
    
    def register_device(self, dev: BaseDevice, start_address):
        
        # TODO: optimize the whole function @DavideRuzza 
        
        assert dev not in self.dev_list, f"'{dev.name}' already registered"
        
        index = 0
        for i, addr in enumerate(self.mem_map):
            
            if start_address<addr[0]:
                index = i
            elif start_address>addr[1]:
                index = i+1
            
            if (addr[0]<=start_address<=addr[1]) or \
                (addr[0]<=start_address+dev.size<=addr[1]):
                raise Exception(f"address overlap with {self.dev_list[i].name}")
        
        self.dev_list.insert(index, dev)
        self.mem_map.insert(index, [start_address, start_address+dev.size-1])
        self.dev_map = {}
        
        for addr, dev in zip(self.mem_map, self.dev_list):
            self.dev_map[addr[0]] = dev
        
    def read(self, addr: int, size: int = 4):
        
        for mem in self.mem_map:
            st, end = mem
            
            if st<=addr<=end:
                rel_addr = addr-st
                dev = self.dev_map[st]
                result = dev.read(addr=rel_addr, size=size)
                log.debug(f"read {dev.name}: 0x{addr:X} -> 0x{result:0{size}x}")
                return result
            
        raise Exception(f"no device registered in 0x{addr:X}")
    
    def write(self, addr: int, value: int, size: int = 4):
        for mem in self.mem_map:
            st, end = mem
        
            if st<=addr<=end:
                rel_addr = addr-st
                dev = self.dev_map[st]
                dev.write(addr=rel_addr, value=value, size=size)
                log.debug(f"write {dev.name}: 0x{addr:X} <- 0x{value:0{size}x}")
                return True
        
        raise Exception(f"no device registered in 0x{addr:X}")
    
    def __repr__(self):
        
        head = " Memory Map "
        out = []
        for i, (start, end) in enumerate(self.mem_map):
            out.append(f"* 0x{start:08X} - 0x{end:08X} = {self.dev_map[start].name}")
        
        max_len = max([len(s) for s in out])
        half_head_len = int((max_len-len(head))/2)
        
        out.append("="*max_len)
        out.insert(0,"="*half_head_len+head+"="*(max_len-len(head)-half_head_len))

        return "\n".join(out)
