# import logging
# from devices import *
# from typing import List, Dict, Optional, TYPE_CHECKING
# import threading

# log = logging.getLogger(__name__)

# if TYPE_CHECKING:
#     from main import RV64Hart


# class SystemInterface():
    
#     def __init__(self):
        
#         self.dev_map : Dict[int, BaseDevice] = {}
#         self.dev_list : List[BaseDevice] = []
#         self.mem_map : List[List[int, int]] = []

#         self._lock = threading.Lock()
#         self._bus_owner: Optional[int] = None  # Which hart owns the bus

#         # (addr, size, valid)
#         self.reservations : Dict[int, List[int, int, bool]] = {}
    
#     def register_hart(self, hartid: int):
#         self.reservations[hartid] =  [0, 0, False]
        
#     def load_reserve(self, addr: int, size: int, hartid: int)->int:
#         """return reservation index to check"""
        
#         self.reservations[hartid] = [addr, size, True]
#         log.debug(f"made reservation {self.reservations[hartid]}")
#         return self.read(addr, size)
    
#     def store_conditional(self, addr: int, value:int, size: int, hartid: int):
        
#         res_addr, res_size, res_valid = self.reservations[hartid]
        
#         if res_valid and res_addr==addr and res_size==size:
            
#             log.debug("BUS: Succeful Store Conditional")
#             self.write(addr, value, size)
#             return True
#         log.debug("BUS: Failed Store Conditional")
#         return False
    
#     def check_invalidate_reservations(self, addr: int, size: int):
        
#         for hid in self.reservations:
#             res_addr, res_size, _ = self.reservations[hid]
            
#             if addr < res_addr + res_size and addr + size > res_addr:
#                 # invalidate the reservation
#                 log.debug(f"BUS: invalidate reservation from {hid}")
#                 self.reservations[hid][2] = False 
            
#     def register_device(self, dev: BaseDevice, start_address):
        
#         # TODO: optimize the whole function @DavideRuzza 
        
#         assert dev not in self.dev_list, f"'{dev.name}' already registered"
#         # print("adding", dev)
#         index = 0
#         for i, addr in enumerate(self.mem_map):
#             # print(f"dev | {self.dev_list[i].name:<15}: {hex(addr[0])} - {hex(addr[1])}")
#             if start_address<addr[0]:
#                 index = i
#             elif start_address>addr[1]:
#                 index = i+1
            
#             if (addr[0]<=start_address<=addr[1]) or \
#                 (addr[0]<=start_address+dev.size-1<=addr[1]):
#                 raise Exception(f"address overlap with {self.dev_list[i].name}")
#         # print("----")
#         self.dev_list.insert(index, dev)
#         self.mem_map.insert(index, [start_address, start_address+dev.size-1])
#         self.dev_map = {}
        
#         for addr, dev in zip(self.mem_map, self.dev_list):
#             self.dev_map[addr[0]] = dev
        
#     def read(self, addr: int, size: int = 4):
        
#         for mem in self.mem_map:
#             st, end = mem
            
#             if st<=addr<=end:
#                 rel_addr = addr-st
#                 dev = self.dev_map[st]
#                 result = dev.read(addr=rel_addr, size=size)
#                 log.debug(f"read {dev.name}: 0x{addr:X} -> 0x{result:0{size}x}")
#                 return result
            
#         raise Exception(f"no device registered in 0x{addr:X}")
    
#     def write(self, addr: int, value: int, size: int = 4):
#         for mem in self.mem_map:
#             st, end = mem
        
#             if st<=addr<=end:
#                 rel_addr = addr-st
#                 dev = self.dev_map[st]
#                 dev.write(addr=rel_addr, value=value, size=size)
#                 # print(size)
#                 mask = (1<<(size*8))-1
#                 log.debug(f"write {dev.name}: 0x{addr:X} <- 0x{value&mask:0{size}x}")
#                 self.check_invalidate_reservations(addr, size)
#                 return True
        
#         raise Exception(f"no device registered in 0x{addr:X}")
    
#     def lock(self, hart_id: int, blocking: bool = True, timeout: float = None) -> bool:
#         """
#         Acquire exclusive bus lock
        
#         Args:
#             hart_id: Hart ID requesting the lock
#             blocking: If True, wait for lock. If False, return immediately
#             timeout: Maximum time to wait (only if blocking=True)
            
#         Returns:
#             True if lock acquired, False otherwise
            
#         Example:
#             if bus.lock(hart_id=0):
#                 # Do atomic operations
#                 bus.unlock(hart_id=0)
#         """
        
#         acquired = self._lock.acquire(blocking=blocking, timeout=timeout if timeout else -1)
        
#         if acquired:
#             self._bus_owner = hart_id
#             return True
#         return False
    
#     def unlock(self, hart_id: int):
#         """
#         Release bus lock
        
#         Args:
#             hart_id: Hart ID releasing the lock
            
#         Raises:
#             RuntimeError: If hart doesn't own the lock
            
#         Example:
#             bus.unlock(hart_id=0)
#         """
        
#         if self._bus_owner != hart_id:
#             raise RuntimeError(f"Hart {hart_id} doesn't own the bus lock (owner: {self._bus_owner})")
        
#         self._bus_owner = None
#         self._lock.release()
    
#     def is_locked(self) -> bool:
#         """
#         Check if bus is currently locked
        
#         Returns:
#             True if locked, False if available
            
#         Example:
#             if not bus.is_locked():
#                 print("Bus is available")
#         """
        
#         return self._bus_owner is not None
    
#     def get_lock_owner(self) -> Optional[int]:
#         """
#         Get the hart ID that owns the lock
        
#         Returns:
#             Hart ID if locked, None if unlocked
            
#         Example:
#             owner = bus.get_lock_owner()
#             if owner is not None:
#                 print(f"Bus locked by hart {owner}")
#         """
        
#         return self._bus_owner
    
#     def try_lock(self, hart_id: int) -> bool:
#         """
#         Try to acquire lock without blocking (non-blocking version)
        
#         Args:
#             hart_id: Hart ID requesting the lock
            
#         Returns:
#             True if lock acquired, False if already locked
            
#         Example:
#             if bus.try_lock(hart_id=0):
#                 # Got the lock!
#                 bus.unlock(hart_id=0)
#             else:
#                 # Someone else has it
#                 pass
#         """
        
#         return self.lock(hart_id, blocking=False)
    
#     def __repr__(self):
        
#         head = " Memory Map "
#         out = []
#         for i, (start, end) in enumerate(self.mem_map):
#             out.append(f"* 0x{start:08X} - 0x{end:08X} = {self.dev_map[start].name}")
        
#         if len(out)==0:
#             out = ['empty'] 
        
#         max_len = max([len(s) for s in out]+[len(head)])
#         half_head_len = int((max_len-len(head))/2)
        
#         out.append("="*max_len)
#         out.insert(0,"="*half_head_len+head+"="*(max_len-len(head)-half_head_len))

#         return "\n".join(out)


import logging
from devices import *
from typing import List, Dict, Optional, TYPE_CHECKING
import threading

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from main import RV64Hart


class SystemInterface():
    
    def __init__(self):
        
        self.dev_map : Dict[int, BaseDevice] = {}
        self.dev_list : List[BaseDevice] = []
        self.mem_map : List[List[int, int]] = []

        self._lock = threading.Lock()
        self._bus_owner: Optional[int] = None  # Which hart owns the bus

        # (addr, size, valid)
        self.reservations : Dict[int, List[int, int, bool]] = {}
    
    def register_hart(self, hartid: int):
        self.reservations[hartid] =  [0, 0, False]
    
    def read_burst(self, addr: int, num:int, size: int=4)->List[int]:
        for mem in self.mem_map:
            st, end = mem
            
            if st<=addr<=end:
                rel_addr = addr-st
                dev = self.dev_map[st]
                
                if hasattr(dev, 'read_burst'): # mimic the reading of multiple word without calling the read on the bus each time
                    result = list(dev.read_burst(addr=rel_addr, num=num, size=size))
                else:
                    result = [dev.read(addr=rel_addr+size*i, size=size) for i in range(num)]
                # -log.debug(f"read {dev.name}: 0x{addr:X} -> 0x{result:0{size}x}")
                return result
            
        raise Exception(f"no device registered in 0x{addr:X}")

    def read_raw_burst(self, addr: int, num:int, size: int=4)->bytearray:
        for mem in self.mem_map:
            st, end = mem
            
            if st<=addr<=end:
                rel_addr = addr-st
                dev = self.dev_map[st]
                
                if hasattr(dev, 'read_raw_burst'): # mimic the reading of multiple word without calling the read on the bus each time
                    result = dev.read_burst(addr=rel_addr, num=num, size=size)
                else:
                    result = sum([dev.read(addr=rel_addr+size*i, size=1) for i in range(num*size)])
                # -log.debug(f"read {dev.name}: 0x{addr:X} -> 0x{result:0{size}x}")
                return result
            
        raise Exception(f"no device registered in 0x{addr:X}")
    
    def load_reserve(self, addr: int, size: int, hartid: int)->int:
        """return reservation index to check"""
        
        self.reservations[hartid] = [addr, size, True]
        # -log.debug(f"made reservation {self.reservations[hartid]}")
        return self.read(addr, size)
    
    def store_conditional(self, addr: int, value:int, size: int, hartid: int):
        
        res_addr, res_size, res_valid = self.reservations[hartid]
        
        if res_valid and res_addr==addr and res_size==size:
            
            # -log.debug("BUS: Succeful Store Conditional")
            self.write(addr, value, size)
            return True
        # -log.debug("BUS: Failed Store Conditional")
        return False
    
    def check_invalidate_reservations(self, addr: int, size: int):
        
        for hid in self.reservations:
            res_addr, res_size, _ = self.reservations[hid]
            
            if addr < res_addr + res_size and addr + size > res_addr:
                # invalidate the reservation
                # -log.debug(f"BUS: invalidate reservation from {hid}")
                self.reservations[hid][2] = False 
            
    def register_device(self, dev: BaseDevice, start_address):
        
        # TODO: optimize the whole function @DavideRuzza 
        
        assert dev not in self.dev_list, f"'{dev.name}' already registered"
        # print("adding", dev)
        index = 0
        for i, addr in enumerate(self.mem_map):
            # print(f"dev | {self.dev_list[i].name:<15}: {hex(addr[0])} - {hex(addr[1])}")
            if start_address<addr[0]:
                index = i
            elif start_address>addr[1]:
                index = i+1
            
            if (addr[0]<=start_address<=addr[1]) or \
                (addr[0]<=start_address+dev.size-1<=addr[1]):
                raise Exception(f"address overlap with {self.dev_list[i].name}")
        # print("----")
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
                # -log.debug(f"read {dev.name}: 0x{addr:X} -> 0x{result:0{size}x}")
                return result
            
        raise Exception(f"no device registered in 0x{addr:X}")
    
    def write(self, addr: int, value: int, size: int = 4):
        for mem in self.mem_map:
            st, end = mem
        
            if st<=addr<=end:
                rel_addr = addr-st
                dev = self.dev_map[st]
                dev.write(addr=rel_addr, value=value, size=size)
                # print(size)
                mask = (1<<(size*8))-1
                # -log.debug(f"write {dev.name}: 0x{addr:X} <- 0x{value&mask:0{size}x}")
                self.check_invalidate_reservations(addr, size)
                return True
        
        raise Exception(f"no device registered in 0x{addr:X}")
    
    def lock(self, hart_id: int, blocking: bool = True, timeout: float = None) -> bool:
        """
        Acquire exclusive bus lock
        
        Args:
            hart_id: Hart ID requesting the lock
            blocking: If True, wait for lock. If False, return immediately
            timeout: Maximum time to wait (only if blocking=True)
            
        Returns:
            True if lock acquired, False otherwise
            
        Example:
            if bus.lock(hart_id=0):
                # Do atomic operations
                bus.unlock(hart_id=0)
        """
        
        acquired = self._lock.acquire(blocking=blocking, timeout=timeout if timeout else -1)
        
        if acquired:
            self._bus_owner = hart_id
            return True
        return False
    
    def unlock(self, hart_id: int):
        """
        Release bus lock
        
        Args:
            hart_id: Hart ID releasing the lock
            
        Raises:
            RuntimeError: If hart doesn't own the lock
            
        Example:
            bus.unlock(hart_id=0)
        """
        
        if self._bus_owner != hart_id:
            raise RuntimeError(f"Hart {hart_id} doesn't own the bus lock (owner: {self._bus_owner})")
        
        self._bus_owner = None
        self._lock.release()
    
    def is_locked(self) -> bool:
        """
        Check if bus is currently locked
        
        Returns:
            True if locked, False if available
            
        Example:
            if not bus.is_locked():
                print("Bus is available")
        """
        
        return self._bus_owner is not None
    
    def get_lock_owner(self) -> Optional[int]:
        """
        Get the hart ID that owns the lock
        
        Returns:
            Hart ID if locked, None if unlocked
            
        Example:
            owner = bus.get_lock_owner()
            if owner is not None:
                print(f"Bus locked by hart {owner}")
        """
        
        return self._bus_owner
    
    def try_lock(self, hart_id: int) -> bool:
        """
        Try to acquire lock without blocking (non-blocking version)
        
        Args:
            hart_id: Hart ID requesting the lock
            
        Returns:
            True if lock acquired, False if already locked
            
        Example:
            if bus.try_lock(hart_id=0):
                # Got the lock!
                bus.unlock(hart_id=0)
            else:
                # Someone else has it
                pass
        """
        
        return self.lock(hart_id, blocking=False)
    
    def __repr__(self):
        
        head = " Memory Map "
        out = []
        for i, (start, end) in enumerate(self.mem_map):
            out.append(f"* 0x{start:08X} - 0x{end:08X} = {self.dev_map[start].name}")
        
        if len(out)==0:
            out = ['empty'] 
        
        max_len = max([len(s) for s in out]+[len(head)])
        half_head_len = int((max_len-len(head))/2)
        
        out.append("="*max_len)
        out.insert(0,"="*half_head_len+head+"="*(max_len-len(head)-half_head_len))

        return "\n".join(out)
