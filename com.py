import socket
import threading
import time
import select
from collections import deque
from devices import BaseDevice


class UART16550(BaseDevice):
    """16550-compatible UART with socket interface for telnet connection"""
    
    # Register offsets
    RBR_THR = 0  # Receiver Buffer (R) / Transmit Holding (W)
    IER = 1      # Interrupt Enable Register
    IIR_FCR = 2  # Interrupt ID (R) / FIFO Control (W)
    LCR = 3      # Line Control Register
    MCR = 4      # Modem Control Register
    LSR = 5      # Line Status Register
    MSR = 6      # Modem Status Register
    SCR = 7      # Scratch Register
    
    # LSR bits
    LSR_DR = 0x01    # Data Ready
    LSR_OE = 0x02    # Overrun Error
    LSR_PE = 0x04    # Parity Error
    LSR_FE = 0x08    # Framing Error
    LSR_BI = 0x10    # Break Interrupt
    LSR_THRE = 0x20  # Transmitter Holding Register Empty
    LSR_TEMT = 0x40  # Transmitter Empty (bit 6 only)
    
    # IER bits
    IER_RDA = 0x01   # Received Data Available
    IER_THRE = 0x02  # Transmitter Holding Register Empty
    IER_RLS = 0x04   # Receiver Line Status
    IER_MS = 0x08    # Modem Status
    
    # IIR interrupt types
    IIR_NO_INT = 0x01
    IIR_RLS = 0x06     # Receiver Line Status (highest priority)
    IIR_RDA = 0x04     # Received Data Available
    IIR_CTI = 0x0C     # Character Timeout Indication
    IIR_THRE = 0x02    # THR Empty
    IIR_MS = 0x00      # Modem Status (lowest priority)
    
    def __init__(self, port=5555, irq_id=10):
        BaseDevice.__init__(self, 0x100, "UART0")
        
        self.irq_id = irq_id
        self.irq_callback = None  # Set by system to notify PLIC
        
        # Registers
        self.ier = 0
        self.iir = self.IIR_NO_INT
        self.lcr = 0x03  # 8N1 default
        self.mcr = 0
        self.lsr = self.LSR_THRE | self.LSR_TEMT  # Transmitter ready
        self.msr = 0
        self.scr = 0
        
        # FIFOs (16 bytes each)
        self.rx_fifo = deque(maxlen=16)
        self.tx_fifo = deque(maxlen=16)
        self.fifo_enabled = False
        
        # Divisor latch (for baud rate - we don't actually use it)
        self.dll = 0
        self.dlm = 0
        
        # Socket for telnet connection
        self.server_socket = None
        self.client_socket = None
        self.socket_lock = threading.Lock()
        self.running = True
        
        # Start socket server
        self._start_socket_server(port)
        
        print(f"[UART] Initialized on port {port}")
        print(f"[UART] Connect with: telnet localhost {port}")
    
    def is_connected(self):
        """Check if a client is currently connected"""
        with self.socket_lock:
            return self.client_socket is not None
    
    def _start_socket_server(self, port):
        """Start TCP server for telnet connections"""
        def accept_loop():
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('localhost', port))
            self.server_socket.listen(1)
            self.server_socket.settimeout(1.0)
            
            while self.running:
                try:
                    client, addr = self.server_socket.accept()
                    print(f"[UART] Client connected: {addr}")
                    
                    with self.socket_lock:
                        if self.client_socket:
                            try:
                                self.client_socket.close()
                            except:
                                pass
                        self.client_socket = client
                        self.client_socket.setblocking(False)
                    
                    # Start receive thread for this client
                    threading.Thread(target=self._receive_loop, daemon=True).start()
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"[UART] Accept error: {e}")
        
        threading.Thread(target=accept_loop, daemon=True).start()
    
    def _receive_loop(self):
        """Background thread to receive data from socket"""
        while self.running:
            with self.socket_lock:
                sock = self.client_socket
                if not sock:
                    break
            
            try:
                # Use select for better non-blocking behavior
                ready, _, _ = select.select([sock], [], [], 0.1)
                
                if ready:
                    data = sock.recv(1024)
                    if not data:
                        print("[UART] Client disconnected")
                        with self.socket_lock:
                            if self.client_socket:
                                try:
                                    self.client_socket.close()
                                except:
                                    pass
                                self.client_socket = None
                        break
                    
                    # Put received bytes into RX FIFO
                    for byte in data:
                        self._receive_byte(byte)
                
            except Exception as e:
                if self.running:
                    print(f"[UART] Receive error: {e}")
                with self.socket_lock:
                    if self.client_socket:
                        try:
                            self.client_socket.close()
                        except:
                            pass
                        self.client_socket = None
                break
    
    def _receive_byte(self, byte):
        """Put byte into RX FIFO and update status"""
        if len(self.rx_fifo) >= 16:
            # FIFO full - set overrun error
            self.lsr |= self.LSR_OE
        else:
            self.rx_fifo.append(byte)
            self.lsr |= self.LSR_DR  # Data ready
        self._update_interrupt()
    
    def _transmit_byte(self, byte):
        """Send byte to socket"""
        with self.socket_lock:
            if self.client_socket:
                try:
                    self.client_socket.send(bytes([byte]))
                except Exception as e:
                    print(f"[UART] Transmit error: {e}")
                    try:
                        self.client_socket.close()
                    except:
                        pass
                    self.client_socket = None
    
    def _update_interrupt(self):
        """Calculate interrupt state and notify PLIC"""
        old_iir = self.iir
        
        # Priority order: LSR > RDA > THRE > MS
        
        # Check for Line Status interrupt
        if (self.ier & self.IER_RLS) and (self.lsr & 0x1E):  # Any error bits
            self.iir = self.IIR_RLS
        # Check for Received Data Available
        elif (self.ier & self.IER_RDA) and (self.lsr & self.LSR_DR):
            self.iir = self.IIR_RDA
        # Check for THR Empty
        elif (self.ier & self.IER_THRE) and (self.lsr & self.LSR_THRE):
            self.iir = self.IIR_THRE
        # Check for Modem Status
        elif (self.ier & self.IER_MS) and (self.msr & 0x0F):
            self.iir = self.IIR_MS
        else:
            self.iir = self.IIR_NO_INT
        
        # Notify PLIC when interrupt state changes
        # if self.irq_callback and (old_iir != self.iir):
        #     if self.iir != self.IIR_NO_INT:
        # print('interrupt uart')
        self.irq_callback(self.irq_id)
    
    def read(self, addr, size=1):
        """CPU reads from UART register"""
        reg = (addr>>2) & 0x7
        
        # Check if accessing divisor latch
        if self.lcr & 0x80:  # DLAB set
            if reg == self.RBR_THR:
                return self.dll
            elif reg == self.IER:
                return self.dlm
        
        if reg == self.RBR_THR:
            # Read from RX FIFO
            if len(self.rx_fifo) > 0:
                byte = self.rx_fifo.popleft()
                if len(self.rx_fifo) == 0:
                    self.lsr &= ~self.LSR_DR  # No more data
                self._update_interrupt()
                return byte
            return 0
        
        elif reg == self.IER:
            return self.ier
        
        elif reg == self.IIR_FCR:
            # Reading IIR clears THRE interrupt
            iir = self.iir
            if self.fifo_enabled:
                iir |= 0xC0  # FIFOs enabled bits
            if iir == self.IIR_THRE:
                self.iir = self.IIR_NO_INT
                self._update_interrupt()
            return iir
        
        elif reg == self.LCR:
            return self.lcr
        
        elif reg == self.MCR:
            return self.mcr
        
        elif reg == self.LSR:
            lsr = self.lsr
            # Reading LSR clears error bits
            self.lsr &= ~0x1E
            self._update_interrupt()
            return lsr
        
        elif reg == self.MSR:
            msr = self.msr
            # Reading MSR clears delta bits
            self.msr &= ~0x0F
            self._update_interrupt()
            return msr
        
        elif reg == self.SCR:
            return self.scr
        
        return 0
    
    def write(self, addr, value, size=1):
        """CPU writes to UART register"""
        reg = (addr>>2) & 0x7
        value = value & 0xFF
        
        # Check if accessing divisor latch
        if self.lcr & 0x80:  # DLAB set
            if reg == self.RBR_THR:
                self.dll = value
                return
            elif reg == self.IER:
                self.dlm = value
                return
        
        if reg == self.RBR_THR:
            # Write to TX - immediately transmit
            self._transmit_byte(value)
            # In real hardware, THR would become empty after moving to shift register
            # We simulate instant transmission
            self.lsr |= self.LSR_THRE | self.LSR_TEMT
            self._update_interrupt()
        
        elif reg == self.IER:
            self.ier = value & 0x0F
            self._update_interrupt()
        
        elif reg == self.IIR_FCR:
            # Writing FCR
            if value & 0x01:
                self.fifo_enabled = True
            else:
                self.fifo_enabled = False
            
            if value & 0x02:  # Clear RX FIFO
                self.rx_fifo.clear()
                self.lsr &= ~self.LSR_DR
            
            if value & 0x04:  # Clear TX FIFO
                self.tx_fifo.clear()
                self.lsr |= self.LSR_THRE | self.LSR_TEMT
            
            self._update_interrupt()
        
        elif reg == self.LCR:
            self.lcr = value
        
        elif reg == self.MCR:
            self.mcr = value & 0x1F
        
        elif reg == self.SCR:
            self.scr = value
    
    def set_irq_callback(self, callback):
        """Set callback function to notify PLIC of interrupt state"""
        self.irq_callback = callback
    
    def shutdown(self):
        """Clean shutdown"""
        print("[UART] Shutting down...")
        self.running = False
        
        with self.socket_lock:
            if self.client_socket:
                try:
                    self.client_socket.close()
                except:
                    pass
            self.client_socket = None
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        print("[UART] Shutdown complete")