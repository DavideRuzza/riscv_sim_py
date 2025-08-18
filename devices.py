from struct import pack, unpack

class BaseDevice:
    
    def __init__(self, size, name="dev"):
        self.size = size
        self.name = name
        self.mem = b'\x00'*self.size
    
    @classmethod
    def from_binary_file(cls: 'BaseDevice', filepath: str, devname='dev'):
        
        with open(filepath, 'rb') as f:
            data = f.read()
        
        size = len(data)
        round_size = cls.round4Kb(len(data))
        newdev = cls(size=size, name=devname)
        data = data+b'\x00'*(round_size-size)
        newdev.mem = data

        return newdev

    def read(self, addr: int, size: int = 4):
        assert 0>=addr, "something is wrong addr < 0" 
        assert addr+size<=self.size, f"addr: {hex(addr)} is more than dev size"
        
        enc_str = self.get_encoding(size)
        return unpack(enc_str, self.mem[addr:addr+size])[0]
    
    def write(self, addr: int, value: int, size: int = 4):
        
        assert 0>=addr, "something is wrong addr < 0" 
        assert addr+size<=self.size, f"addr: {hex(addr)} is more than dev size"
        
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
        
            
        
    def __repr__(self):
        return f"BaseDevice(name={self.name}, size={self.size_str()})"