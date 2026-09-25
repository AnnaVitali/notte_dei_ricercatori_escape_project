"""One Bluetooth connection for GUI LED commands and fresh D-pad movement."""
import asyncio
import queue
import threading
import time

UART_WRITE = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
MOVEMENT_COMMANDS = {"FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP"}


class MovementMailbox:
    """Replace pending movement; never replay a queue of old directions."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.value = None

    def put(self, command):
        if command not in MOVEMENT_COMMANDS:
            raise ValueError("Unknown movement command")
        with self.lock:
            self.value = (command, self.clock())

    def current(self):
        with self.lock:
            if self.value is None:
                return None
            command, refreshed = self.value
            # If Tk stops polling (modal dialog, stall, etc.), stop the car.
            return command if self.clock() - refreshed < 0.25 else "STOP"


class BluetoothConnection:
    def __init__(self, address):
        self.address = address
        self.client = None
        self.command_queue = queue.Queue()
        self.movement = MovementMailbox()
        self.running = False
        self.loop = None
        self.thread = None
        self.last_error = ""
        self.closing = threading.Event()

    @property
    def is_connected(self):
        return bool(self.running and self.client and self.client.is_connected)

    async def connect(self):
        from bleak import BleakClient
        self.client = BleakClient(self.address, timeout=15)
        await self.client.connect()
        await self.send_command("STOP")

    async def send_command(self, command):
        if not self.client or not self.client.is_connected:
            raise ConnectionError("Bluetooth disconnected")
        await asyncio.wait_for(self.client.write_gatt_char(
            UART_WRITE, (command.rstrip("#") + "#").encode(), response=False), timeout=1)

    async def disconnect(self):
        if self.client and self.client.is_connected:
            await asyncio.wait_for(self.client.disconnect(), timeout=2)

    async def _process_queue(self):
        previous, last_sent = None, 0.0
        while self.running and not self.closing.is_set():
            if not self.client.is_connected:
                raise ConnectionError("Bluetooth disconnected")
            command = self.movement.current()
            now = time.monotonic()
            if command is not None and (command != previous or now - last_sent >= 0.1):
                await self.send_command(command)
                previous, last_sent = command, now
            # At most one LED command before checking fresh movement again.
            try:
                command = self.command_queue.get_nowait()
            except queue.Empty:
                pass
            else:
                await self.send_command(command)
            await asyncio.sleep(0.01)

    async def _connect_and_process(self):
        try:
            await self.connect()
            await self._process_queue()
        except Exception as error:
            self.last_error = str(error)
            print(f"Bluetooth error: {error}")
        finally:
            self.running = False
            try:
                if self.client and self.client.is_connected:
                    await self.send_command("STOP")
            except Exception:
                pass  # Firmware timeout is the fallback for a failed link.
            try:
                await self.disconnect()
            except Exception:
                pass

    def _run_event_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._connect_and_process())
        finally:
            self.running = False
            self.loop.close()

    def start_background_loop(self):
        if self.thread and self.thread.is_alive():
            return
        self.closing.clear()
        self.last_error = ""
        self.running = True
        self.thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.thread.start()

    def queue_command(self, command):
        command = command.rstrip("#")
        if command in MOVEMENT_COMMANDS:
            self.set_movement(command)
        elif self.is_connected:
            self.command_queue.put(command)

    def set_movement(self, command):
        if command == "STOP" or self.is_connected:
            self.movement.put(command)

    def close(self):
        self.movement.put("STOP")
        self.closing.set()

