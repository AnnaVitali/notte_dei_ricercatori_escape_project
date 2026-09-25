"""Print USB joystick inputs in the terminal; no car, Bluetooth, or GUI."""
import argparse
import os
import time


def direction(hat):
    return {
        (0, 0): "RELEASED / STOP",
        (0, 1): "UP / FORWARD",
        (0, -1): "DOWN / BACKWARD",
        (-1, 0): "LEFT",
        (1, 0): "RIGHT",
    }.get(tuple(hat), "DIAGONAL / STOP")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="List connected controllers and exit")
    parser.add_argument("--device", type=int, default=0, help="Controller index (default: 0)")
    parser.add_argument("--axes", action="store_true", help="Also print analog-axis changes for diagnosis")
    args = parser.parse_args()

    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
    try:
        import pygame
    except ImportError:
        parser.exit(1, "Install Pygame first: python -m pip install pygame\n")

    try:
        # Initialize input/event support without creating a display window.
        pygame.display.init()
        pygame.joystick.init()
        count = pygame.joystick.get_count()
        if count == 0:
            parser.exit(1, "No joystick found. Connect the USB cable/receiver, turn on the controller, and run again.\n")
        controllers = []
        for index in range(count):
            joy = pygame.joystick.Joystick(index)
            joy.init()
            controllers.append(joy)
            print(f"[{index}] {joy.get_name()} | hats={joy.get_numhats()} "
                  f"buttons={joy.get_numbuttons()} axes={joy.get_numaxes()}", flush=True)
        if args.list:
            return
        if not 0 <= args.device < count:
            parser.exit(1, f"Choose --device between 0 and {count - 1}.\n")
        joy = controllers[args.device]
        instance_id = joy.get_instance_id()
        print(f"\nTesting [{args.device}] {joy.get_name()}")
        print("Press the D-pad arrows and buttons. Changes appear below. Ctrl+C exits.")
        if not args.axes:
            print("Analog axes are ignored. Add --axes to diagnose the controller's Mode setting.")
        if joy.get_numhats() == 0:
            print("No D-pad hat reported. Watch button events; try D/Mode if your controller has that setting.")
        print("Button and hat numbers are zero-based. Nothing is sent to the car.\n", flush=True)
        previous_hats = [None] * joy.get_numhats()
        started = time.monotonic()

        def report(text):
            print(f"[{time.monotonic() - started:7.2f}s] {text}", flush=True)

        pygame.event.pump()
        for button in range(joy.get_numbuttons()):
            if joy.get_button(button):
                report(f"Button {button}: already PRESSED")
        previous_axes = [joy.get_axis(axis) for axis in range(joy.get_numaxes())] if args.axes else []
        if args.axes:
            for axis, value in enumerate(previous_axes):
                report(f"Axis {axis}: {value:+.2f}")

        while True:
            for event in pygame.event.get():
                if event.type == pygame.JOYDEVICEREMOVED and event.instance_id == instance_id:
                    report("Controller disconnected. Reconnect and run this script again.")
                    return
                if getattr(event, "instance_id", None) != instance_id:
                    continue
                if event.type in (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP):
                    state = "PRESSED" if event.type == pygame.JOYBUTTONDOWN else "RELEASED"
                    report(f"Button {event.button}: {state}")
                elif event.type == pygame.JOYHATMOTION:
                    previous_hats[event.hat] = event.value
                    report(f"D-pad / hat {event.hat}: {event.value} -> {direction(event.value)}")
            # Also report the initial/current hat state without flooding output.
            for hat in range(joy.get_numhats()):
                value = joy.get_hat(hat)
                if value != previous_hats[hat]:
                    report(f"D-pad / hat {hat}: {value} -> {direction(value)}")
                    previous_hats[hat] = value
            if args.axes:
                for axis in range(joy.get_numaxes()):
                    value = joy.get_axis(axis)
                    if abs(value - previous_axes[axis]) >= 0.1:
                        report(f"Axis {axis}: {value:+.2f}")
                        previous_axes[axis] = value
            time.sleep(0.02)
    except KeyboardInterrupt:
        print("\nJoystick test stopped.")
    except pygame.error as error:
        parser.exit(1, f"Joystick error: {error}\n")
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
