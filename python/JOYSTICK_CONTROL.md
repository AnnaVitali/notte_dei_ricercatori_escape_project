# USB D-pad control over Bluetooth

The PC reads the Logitech controller's digital direction pad and sends commands
to the micro:bit car using its existing Bluetooth UART characteristic. Analog
axes are never read. This is physical driving, not automatic graph-node selection.

## Setup

1. Open the existing car project in MakeCode, replace its JavaScript with
   `javascript/smart_car.js`, compile and flash the micro:bit. Keep the MiniCar,
   IR and Bluetooth extensions used by the project. This file contains MakeCode
   TypeScript despite its `.js` extension; do not run it with Node.
2. Plug the controller or USB receiver into the PC. Power on the controller if
   needed. The precise model/input mapping cannot be confirmed from the photo.
3. Install the PC dependencies from the project root:

   ```powershell
   python -m pip install -r python/requirements-joystick.txt
   python python/joystick_car.py --list
   python python/joystick_car.py --dry-run
   ```

4. In the test window, release the D-pad once, then try each arrow. Confirm the
   indicated command. Moving either analog stick must leave the command at STOP.
   If the controller has a Mode button that swaps the stick and D-pad, choose the
   mode where only the physical D-pad changes the displayed command. If it has
   a D/X switch, D mode may expose the hat when the other mode does not.
5. Close the test window, power the car and connect:

   ```powershell
   python python/joystick_car.py
   ```

   The default car address is `C2:38:E3:86:54:78`, matching `car_gui.py`.
   Override with `--address AA:BB:CC:DD:EE:FF` if necessary. Keep the existing
   micro:bit pairing configuration; pair through Windows if that configuration
   requires it. The script checks the UART characteristic's write properties.

For the challenge, run `python python/car_gui.py` instead. Its D-PAD CONTROL bar
uses the GUI's existing Bluetooth connection for movement and LED commands.
Select a controller, click Enable joystick, release the D-pad once, then drive.
Refresh rescans USB controllers. STOP disables driving until enabled again.
Reset, finish, game over, focus loss, unplugging and closing stop driving.
Install its dependencies with `python -m pip install -r python/requirements-car-gui.txt`.
The standalone controller above remains a diagnostic tool; do not run it while
the GUI is using Bluetooth. The GUI currently reads the first D-pad hat.

## Controls

| D-pad | Car command |
| --- | --- |
| Up | Forward |
| Down | Backward |
| Left | Rotate left |
| Right | Rotate right |
| Released or diagonal | Stop |

Hold an arrow to keep driving. Space stops movement and requires releasing the
D-pad before resuming. Escape/window close exits and attempts Stop. Losing
window focus stops and also requires release before resuming. Controller removal
exits; restart after reconnecting. Test the first movements with wheels raised
to verify the car's motor wiring agrees with these directions.

`--device 1` selects another listed controller; `--hat 1` selects another hat.
For a driver that exposes the arrows as buttons instead of a hat, use
`--buttons UP DOWN LEFT RIGHT` with four confirmed zero-based button indices.
The script deliberately does not infer D-pad directions from analog axes.

## Command protocol

Commands are `FORWARD#`, `BACKWARD#`, `LEFT#`, `RIGHT#`, `STOP#` on
`6e400003-b5a3-f393-e0a9-e50e24dcca9e`. Input is sampled every ~20 ms; the latest
state is sent when it changes and every 100 ms. There is no movement backlog.
Bluetooth movement disables line tracking. After 500 ms without a movement
command the firmware stops and requires STOP (release) before resuming.
Disconnect also stops both motors. The IR Stop button still overrides movement;
continued D-pad heartbeats cannot undo it until the D-pad is released.
Actual timing depends on Bluetooth and the micro:bit scheduler.

## Checks

```powershell
python -m unittest discover -s python -p test_joystick_car.py
node javascript/smart_car.test.cjs
```

Software checks use hardware stubs. MakeCode compilation, the controller's actual
mapping, BLE delivery and motor response still require testing on your equipment.

API references: [Pygame joystick](https://www.pygame.org/docs/ref/joystick.html),
[Bleak Bluetooth writes](https://bleak.readthedocs.io/en/latest/api/client.html),
[MakeCode UART events](https://makecode.microbit.org/reference/bluetooth/on-uart-data-received).
