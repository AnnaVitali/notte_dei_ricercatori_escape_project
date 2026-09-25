"""USB D-pad -> Bluetooth UART car controller. Analog axes are never read."""
import argparse
import asyncio
import time

DEFAULT_ADDRESS = "C2:38:E3:86:54:78"
UART_WRITE = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"


def hat_command(hat):
    # Diagonals and neutral stop: only four unambiguous directions drive.
    return {(0, 1): "FORWARD", (0, -1): "BACKWARD",
            (-1, 0): "LEFT", (1, 0): "RIGHT"}.get(tuple(hat), "STOP")


def button_command(pressed):
    return ("FORWARD", "BACKWARD", "LEFT", "RIGHT")[pressed.index(True)] if sum(pressed) == 1 else "STOP"


class ReleaseGate:
    def __init__(self):
        self.ready = False

    def command(self, requested, focused, neutral):
        if not focused:
            self.ready = False
        elif neutral:
            self.ready = True
        return requested if focused and self.ready else "STOP"


class DpadWindow:
    def __init__(self, args):
        import pygame
        self.pg = pygame
        pygame.display.init()
        pygame.joystick.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((620, 240))
        pygame.display.set_caption("Car D-pad control")
        self.font = pygame.font.Font(None, 28)
        if not 0 <= args.device < pygame.joystick.get_count():
            raise RuntimeError("No controller at that index. Plug in the USB controller/receiver and try --list.")
        self.joy = pygame.joystick.Joystick(args.device)
        self.joy.init()
        self.buttons = args.buttons
        self.hat = args.hat
        if self.buttons:
            if len(set(self.buttons)) != 4 or any(i < 0 or i >= self.joy.get_numbuttons() for i in self.buttons):
                raise ValueError("--buttons needs four distinct valid indices: UP DOWN LEFT RIGHT")
        elif not 0 <= self.hat < self.joy.get_numhats():
            raise RuntimeError("No D-pad hat found. Try the controller's D/Input mode, or use --buttons UP DOWN LEFT RIGHT. Analog sticks are not used.")
        self.gate = ReleaseGate()
        self.closed = False

    def read(self):
        pg = self.pg
        for event in pg.event.get():
            if event.type == pg.QUIT or (event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE):
                self.closed = True
            if event.type == pg.JOYDEVICEREMOVED and event.instance_id == self.joy.get_instance_id():
                self.closed = True
        if self.closed:
            return "STOP"
        if self.buttons:
            pressed = [bool(self.joy.get_button(i)) for i in self.buttons]
            requested, neutral = button_command(pressed), not any(pressed)
        else:
            hat = self.joy.get_hat(self.hat)
            requested, neutral = hat_command(hat), hat == (0, 0)
        focused = bool(pg.key.get_focused()) and not pg.key.get_pressed()[pg.K_SPACE]
        return self.gate.command(requested, focused, neutral)

    def draw(self, command, dry_run):
        self.screen.fill((15, 23, 42))
        lines = [self.joy.get_name(), f"{'TEST ONLY' if dry_run else 'Bluetooth'}: {command}",
                 "D-pad: drive | release / diagonal: stop",
                 "Space: stop | Esc: quit | sticks ignored",
                 "Keep this window focused. Release D-pad to arm."]
        for index, line in enumerate(lines):
            self.screen.blit(self.font.render(line, True, (240, 245, 250)), (18, 20 + index * 40))
        self.pg.display.flip()


async def pump(window, write, dry_run):
    previous, sent_at = None, 0.0
    try:
        await write("STOP")
        while not window.closed:
            command = window.read()
            now = time.monotonic()
            if command != previous or now - sent_at >= 0.1:
                # No movement queue: send only the latest sampled state.
                await write(command)
                if command != previous:
                    print(command, flush=True)
                previous, sent_at = command, now
            window.draw(command, dry_run)
            await asyncio.sleep(0.02)
    finally:
        try:
            await asyncio.wait_for(write("STOP"), timeout=1)
        except Exception as error:
            print(f"Final Stop could not be sent: {error}. Firmware timeout will stop movement.")


async def run(args):
    window = DpadWindow(args)
    try:
        if args.dry_run:
            async def write(command):
                pass
            await pump(window, write, True)
        else:
            from bleak import BleakClient
            print(f"Connecting to {args.address}…", flush=True)
            async with BleakClient(args.address, timeout=20) as client:
                characteristic = client.services.get_characteristic(UART_WRITE)
                if characteristic is None:
                    raise RuntimeError("Car UART characteristic not found. Flash the updated smart_car.js first.")
                properties = characteristic.properties
                if "write-without-response" not in properties and "write" not in properties:
                    raise RuntimeError("Car UART characteristic is not writable.")
                async def write(command):
                    if not client.is_connected:
                        raise RuntimeError("Bluetooth disconnected. Restart after reconnecting the car.")
                    await asyncio.wait_for(client.write_gatt_char(
                        characteristic, (command + "#").encode("ascii"),
                        response="write-without-response" not in properties), timeout=1)
                await pump(window, write, False)
    finally:
        window.pg.quit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", default=DEFAULT_ADDRESS)
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--hat", type=int, default=0)
    parser.add_argument("--buttons", type=int, nargs=4, metavar=("UP", "DOWN", "LEFT", "RIGHT"))
    parser.add_argument("--dry-run", action="store_true", help="Show commands without connecting to the car")
    parser.add_argument("--list", action="store_true", help="List controllers, hats and button counts")
    args = parser.parse_args()
    try:
        if args.list:
            import pygame
            pygame.joystick.init()
            for index in range(pygame.joystick.get_count()):
                joy = pygame.joystick.Joystick(index)
                joy.init()
                print(f"{index}: {joy.get_name()} | hats={joy.get_numhats()} | buttons={joy.get_numbuttons()}")
            pygame.quit()
        else:
            asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
    except Exception as error:
        parser.exit(1, f"Controller error: {error}\n")


if __name__ == "__main__":
    main()
