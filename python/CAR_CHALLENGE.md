# Car challenge

Run `car_gui.py` using the Python environment with the project's GUI, OpenCV,
NumPy, Pillow and Bleak dependencies installed.
For all GUI dependencies including joystick support, run
`python -m pip install -r python/requirements-car-gui.txt` from the project root.

Use the D-PAD CONTROL bar in this same GUI: select the USB controller, click
Enable joystick, release the D-pad, then hold an arrow to drive. Release or
diagonal means Stop. Analog sticks are ignored. Refresh rescans controllers;
STOP disables joystick movement until you enable it again. The GUI works without
a controller or Pygame, with joystick availability explained in the status bar.
After an unplug, focus loss, Reset, finish or game over, enable again to resume.
Movement and guard LED commands share a single Bluetooth connection. Never run
the standalone `joystick_car.py` at the same time.

The GUI opens full screen. Escape leaves full screen; F11 toggles it. The map
scales to the space beside the controls and the ranking on the right.

Enter a player name (blank names become Anonymous). Every run starts at node 1.
The timer starts on the first D-pad drive command or first valid recorded move
away from 1 (whichever comes first) and stops when node 9 is recorded.
Only moves along a drawn road are accepted. Clicking the current node does
nothing; returning to any visited node is forbidden. Available next nodes are
shown beside the map. Reaching a dead end stops the run and requires Reset.
Invalid moves do not change the path, guard score or car position. Existing guard
and game-over rules still apply. Failed and reset runs do not enter the ranking.
Press Reset to prepare the next player.

Completed runs are saved to `car_rankings.csv` beside `car_gui.py`, regardless
of the working directory. Columns are `finished_at` (UTC), `player`,
`elapsed_seconds`, `path`, and `path_cost`. Path cost sums the guard values for
the visited nodes, matching the MiniZinc route objective. Existing ranking
files without `path_cost` remain readable and are upgraded when the next run is
saved. Times use a monotonic clock; the display shows seconds to two decimal
places. Rankings sort by path cost, lowest first, then by elapsed time, fastest
first; they reload on startup.
Every completed attempt is listed. The latest completed run is highlighted and
its rank number appears below the table.

If saving fails, the GUI shows the error and a Retry saving result button.
Retry before resetting or closing, which discards the unsaved attempt.
D-pad commands drive the physical car; they do not select graph nodes. Continue
recording reached nodes with the map or node entry. The neighbour/no-return checks
apply to recorded nodes, not to physical steering, which has no position feedback.
The GUI does not independently detect arrival at node 9.

Run the hardware-independent checks from the project root:

```powershell
python -m unittest discover -s python -p "test_car_*.py"
python -m unittest discover -s python -p "test*joystick*.py"
```
