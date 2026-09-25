"""D-pad input for Tk: no second window and no Bluetooth connection."""
import os
from joystick_car import hat_command, ReleaseGate


class GuiJoystick:
    def __init__(self):
        # SDL has no focused window here; Tk checks focus before sending input.
        os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
        import pygame
        self.pg = pygame
        pygame.display.init()
        pygame.joystick.init()
        self.device = None
        self.gate = ReleaseGate()

    def devices(self):
        self.pg.event.pump()
        devices = []
        for index in range(self.pg.joystick.get_count()):
            device = self.pg.joystick.Joystick(index)
            device.init()
            devices.append(f"{index}: {device.get_name()}")
        return devices

    def select(self, index):
        self.release()
        self.device = self.pg.joystick.Joystick(index)
        self.device.init()
        if self.device.get_numhats() == 0:
            self.release()
            raise ValueError("No D-pad hat: try the controller's D/Mode setting, then reconnect.")

    def read(self, allowed):
        if self.device is None:
            return "STOP"
        for event in self.pg.event.get():
            if event.type == self.pg.JOYDEVICEREMOVED and event.instance_id == self.device.get_instance_id():
                self.release()
                raise ConnectionError("Controller unplugged. Reconnect and enable it again.")
        hat = self.device.get_hat(0)
        return self.gate.command(hat_command(hat), allowed, hat == (0, 0))

    def release(self):
        self.gate = ReleaseGate()
        if self.device is not None:
            device = self.device
            self.device = None
            try:
                device.quit()
            except self.pg.error:
                pass  # An unplugged device may already be closed by SDL.

    def close(self):
        self.release()
        self.pg.quit()
