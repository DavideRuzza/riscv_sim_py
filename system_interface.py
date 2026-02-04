from typing import Dict, List, Optional, Tuple
import threading
# import logging
from devices import *
# from typing import List, Dict, Optional, TYPE_CHECKING
# import threading


PAGE_SHIFT = 12          # 4KB pages (cambialo se vuoi)
PAGE_SIZE  = 1 << PAGE_SHIFT


class SystemInterface:
    """
    High-performance system bus for simulators/emulators.

    Design goals:
    - O(1) device lookup
    - no loops in read/write hot path
    - page based dispatch (like real MMU/bus)
    """

    # =========================================================
    # INIT
    # =========================================================

    def __init__(self):

        # devices
        self.dev_list: List[BaseDevice] = []

        # solo per debug / __repr__
        self.mem_map: List[Tuple[int, int, BaseDevice]] = []

        # 🔥 FAST PATH: page -> (start_addr, device)
        self.page_table: Dict[int, Tuple[int, BaseDevice]] = {}

        # locks
        self._lock = threading.Lock()
        self._bus_owner: Optional[int] = None

        # LR/SC reservations
        # hart -> [addr, size, valid]
        self.reservations: Dict[int, List[int]] = {}

    # =========================================================
    # DEVICE REGISTRATION
    # =========================================================

    def register_device(self, dev: BaseDevice, start_address: int):
        """
        Register device and build page table mapping.
        Called rarely → ok to be slower here.
        """

        assert dev not in self.dev_list, f"{dev.name} already registered"

        end = start_address + dev.size - 1

        # overlap check (slow path, ok)
        for st, ed, _ in self.mem_map:
            if not (end < st or start_address > ed):
                raise Exception(f"address overlap with existing device")

        self.dev_list.append(dev)
        self.mem_map.append((start_address, end, dev))

        # precompute burst capability (avoid hasattr in hot path)
        dev._has_read_burst = hasattr(dev, "read_burst")
        dev._has_raw_burst  = hasattr(dev, "read_raw_burst")

        # 🔥 page mapping (FAST)
        for addr in range(start_address, end + 1, PAGE_SIZE):
            page = addr >> PAGE_SHIFT
            self.page_table[page] = (start_address, dev)

    # =========================================================
    # INTERNAL FAST RESOLVE
    # =========================================================

    def _resolve(self, addr: int):
        """
        O(1) page lookup.
        Critical hot path.
        """
        page = addr >> PAGE_SHIFT
        try:
            base, dev = self.page_table[page]
            return dev, addr - base
        except KeyError:
            raise Exception(f"no device registered in 0x{addr:X}")

    # =========================================================
    # READ / WRITE (HOT PATH)
    # =========================================================

    def read(self, addr: int, size: int = 4):
        dev, rel = self._resolve(addr)
        return dev.read(rel, size)

    def write(self, addr: int, value: int, size: int = 4):
        dev, rel = self._resolve(addr)
        dev.write(rel, value, size)
        self.check_invalidate_reservations(addr, size)
        return True

    # =========================================================
    # BURST ACCESS
    # =========================================================

    def read_burst(self, addr: int, num: int, size: int = 4):
        dev, rel = self._resolve(addr)

        if dev._has_read_burst:
            return list(dev.read_burst(rel, num, size))
        
        return [dev.read(rel + i * size, size) for i in range(num)]
        
    def read_raw_burst(self, addr: int, num: int, size: int = 4):
        dev, rel = self._resolve(addr)

        if dev._has_raw_burst:
            return dev.read_raw_burst(rel, num, size)

        out = bytearray()
        for i in range(num * size):
            out.append(dev.read(rel + i, 1))
        return out

    # =========================================================
    # LR/SC SUPPORT
    # =========================================================

    def register_hart(self, hartid: int):
        self.reservations[hartid] = [0, 0, False]

    def load_reserve(self, addr: int, size: int, hartid: int):
        self.reservations[hartid] = [addr, size, True]
        return self.read(addr, size)

    def store_conditional(self, addr: int, value: int, size: int, hartid: int):
        res_addr, res_size, valid = self.reservations[hartid]

        if valid and res_addr == addr and res_size == size:
            self.write(addr, value, size)
            return True

        return False

    def check_invalidate_reservations(self, addr: int, size: int):
        end = addr + size

        for r in self.reservations.values():
            res_addr, res_size, _ = r
            if addr < res_addr + res_size and end > res_addr:
                r[2] = False

    # =========================================================
    # BUS LOCK
    # =========================================================

    def lock(self, hart_id: int, blocking: bool = True, timeout: float = None):
        acquired = self._lock.acquire(
            blocking=blocking,
            timeout=timeout if timeout else -1
        )

        if acquired:
            self._bus_owner = hart_id
            return True

        return False

    def unlock(self, hart_id: int):
        if self._bus_owner != hart_id:
            raise RuntimeError(
                f"Hart {hart_id} doesn't own the bus lock "
                f"(owner: {self._bus_owner})"
            )

        self._bus_owner = None
        self._lock.release()

    def try_lock(self, hart_id: int):
        return self.lock(hart_id, blocking=False)

    def is_locked(self) -> bool:
        return self._bus_owner is not None

    def get_lock_owner(self) -> Optional[int]:
        return self._bus_owner

    # =========================================================
    # DEBUG
    # =========================================================

    def __repr__(self):
        if not self.mem_map:
            return "==== Memory Map ====\nempty"

        rows = [
            f"* 0x{st:08X} - 0x{ed:08X} = {dev.name}"
            for st, ed, dev in self.mem_map
        ]

        head = " Memory Map "
        max_len = max(len(head), *(len(r) for r in rows))
        pad = (max_len - len(head)) // 2

        rows.insert(0, "=" * pad + head + "=" * (max_len - len(head) - pad))
        rows.append("=" * max_len)

        return "\n".join(rows)
