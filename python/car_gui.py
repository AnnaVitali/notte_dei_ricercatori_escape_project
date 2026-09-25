import cv2
import numpy as np
import sys
import os
from pathlib import Path
import tkinter as tk
from tkinter import Label, Button, messagebox
from tkinter import ttk
from car_challenge import Challenge, RESULTS_FILE, load_results, save_result
from PIL import Image, ImageTk
from car_bluetooth import BluetoothConnection
from gui_joystick import GuiJoystick

SMART_CAR_MARKER_ID = 16
NODE_GUARDS = {"0":0, "1": 8, "2": 3, "3": 5, "4":0, "5": 3, "6": 9, "7": 8, "8":0, "9": 4, "10":0, "11":0, "12": 10, "13": 8, "14": 14, "15": 8} # starting form 0

CAR_BT_ADDRESS = "C2:38:E3:86:54:78"

class ArUcoDetector:
    """Detect and track ArUco markers in video."""
    
    def __init__(self, dictionary_type=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), bt_connection=None):
        """
        Initialize ArUco detector.
        
        Args:
            dictionary_type: ArUco dictionary type (default: 4x4_50 for your markers)
            bt_connection: BluetoothConnection instance for sending commands
        """
        self.dictionary = dictionary_type
        self.parameters = cv2.aruco.DetectorParameters()
        self.detector = cv2.aruco.ArucoDetector(self.dictionary, self.parameters)
        
        # Load marker mapping from ArUco_marker directory
        self.marker_names = self._load_marker_names()
        
        # Initialize persistent guard sum tracking
        self.guard_sum = 0
        self.consecutive_guard_node = 0
        self.guards_collected = set()
        
        # Store Bluetooth connection for sending commands
        self.bt_connection = bt_connection
    
    def _load_marker_names(self):
        """
        Load marker names from ArUco_marker directory.
        Maps marker ID to file name.
        """
        marker_names = {}
        marker_dir = Path("../ArUco_marker")
        
        if marker_dir.exists():
            for svg_file in sorted(marker_dir.glob("*.svg")):
                # Extract ID from filename like "4x4_1000-0.svg"
                filename = svg_file.stem  # "4x4_1000-0"
                try:
                    # Extract the last number (marker ID)
                    marker_id = int(filename.split('-')[-1])
                    marker_names[marker_id] = filename
                except ValueError:
                    pass
        
        return marker_names
    
    def detect_markers(self, frame):
        """
        Detect ArUco markers in a frame.
        
        Args:
            frame: Input video frame
            
        Returns:
            corners: Detected marker corners
            ids: Detected marker IDs
            rejected: Rejected detections
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, rejected = self.detector.detectMarkers(gray)
        return corners, ids, rejected
    
    def get_marker_center(self, corners):
        """
        Calculate center point of marker.
        
        Args:
            corners: Marker corner coordinates
            
        Returns:
            center: (x, y) coordinates of marker center
        """
        corners = corners.reshape(4, 2)
        center_x = int(np.mean(corners[:, 0]))
        center_y = int(np.mean(corners[:, 1]))
        return center_x, center_y
    
    async def send_bt_command_async(self, cmd):
        """
        Send a Bluetooth command asynchronously.
        
        Args:
            cmd: Command to send
        """
        if self.bt_connection:
            self.bt_connection.queue_command(cmd)
    
    def send_bt_command(self, cmd):
        """
        Send a Bluetooth command (non-blocking via queue).
        
        Args:
            cmd: Command to send
        """
        if self.bt_connection:
            self.bt_connection.queue_command(cmd)
    
    def check_car_position(self, frame, centers, ids):
        """
        Check the position of the smart car marker (SMART_CAR_MARKER_ID) in relation to guards.
        When the car has the same x coordinate as a guard (within tolerance), add the guard's number to the cumulative sum (once).
        
        Args:
            frame: The video frame
            centers: Marker center coordinates
            ids: Detected marker IDs
        """
        if ids is None or SMART_CAR_MARKER_ID not in ids:
            return
        
        # Find car marker center
        car_idx = np.where(ids.flatten() == SMART_CAR_MARKER_ID)[0]
        if len(car_idx) == 0:
            return
        
        car_center = centers[car_idx[0]]
        car_x = car_center[0]
        
        # Check guards at same x coordinate (with tolerance) and add their numbers to persistent sum
        tolerance = 1  # pixels tolerance for x alignment
        
        # Track if car is aligned with any guard in this frame
        is_aligned_with_guard = False
        
        for marker_id_str, guard_number in NODE_GUARDS.items():
            marker_id = int(marker_id_str)
            guard_idx = np.where(ids.flatten() == marker_id)[0]
            if len(guard_idx) > 0:
                guard_center = centers[guard_idx[0]]
                guard_x = guard_center[0]
                
                # If car and guard have similar x coordinate (within tolerance) and guard not yet collected
                if abs(car_x - guard_x) <= tolerance:
                    if marker_id not in self.guards_collected:
                        self.guard_sum += guard_number
                        self.guards_collected.add(marker_id)
                        if guard_number > 0:
                            self.consecutive_guard_node += 1
                            if self.consecutive_guard_node == 1:
                                self.send_bt_command("ORANGE")
                            elif self.consecutive_guard_node == 2:
                                self.send_bt_command("PURPLE")
                            elif self.consecutive_guard_node > 2:
                                self.send_bt_command("RED")
                        else :
                            self.send_bt_command("CYAN" if marker_id in (0, 8) else "GREEN")
                            self.consecutive_guard_node = 0
        
        # If car is NOT aligned with any guard (neutral position)
        #if not is_aligned_with_guard:
            # If we had visited 2 or more consecutive guards, send GREEN on transition to neutral
        # if self.consecutive_guard_node == 0 or marker_id in NEUTRAL_NODES:
        #     self.send_bt_command("GREEN")
        #     # Reset counter when we leave the guards
        #     self.consecutive_guard_node = 0
                        
    
    def draw_markers(self, frame, corners, ids):
        """
        Draw detected markers on frame with enhanced highlighting.
        
        Args:
            frame: Input frame
            corners: Detected marker corners
            ids: Detected marker IDs
            
        Returns:
            frame: Frame with drawn markers
        """
        if ids is not None:
            try:
                for marker_corners, marker_id in zip(corners, ids):
                    try:
                        # Handle both scalar and array marker_id formats
                        if isinstance(marker_id, (list, np.ndarray)):
                            marker_id_value = int(marker_id[0])
                        else:
                            marker_id_value = int(marker_id)
                        
                        corners_reshaped = marker_corners.reshape(4, 2).astype(int)
                        
                        # Draw marker outline - purple for car marker (16), green for others
                        outline_color = (255, 0, 255) if marker_id_value == SMART_CAR_MARKER_ID else (0, 255, 0)
                        cv2.polylines(frame, [corners_reshaped], True, outline_color, 2)
                        
                        # Draw marker center (red, small)
                        center_x, center_y = self.get_marker_center(marker_corners)
                        cv2.circle(frame, (center_x, center_y), 5, (0, 0, 255), -1)
                        
                        # Display ID directly below the center marker in bright yellow
                        try:
                            cv2.putText(
                                frame,
                                f"{marker_id_value}",
                                (center_x - 12, center_y + 20),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.6,
                                (0, 255, 255),  # Bright yellow
                                2
                            )
                        except Exception as e:
                            pass
                        
                        # Display coordinates in white
                        try:
                            cv2.putText(
                                frame,
                                f"({center_x}, {center_y})",
                                (center_x - 45, center_y - 15),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.5,
                                (255, 255, 255),  # White
                                1
                            )
                        except Exception as e:
                            pass
                    
                    except Exception as e:
                        # Continue processing other markers if one fails
                        pass
            
            except Exception as e:
                # Continue even if marker drawing fails
                pass
        
        return frame

    def process_digital_twin_gui(self):
        """Display a camera-free digital twin and move the car by node number."""
        colors = {
            "background": "#e9eef5",
            "panel": "#ffffff",
            "road": "#26313d",
            "red": "#d21b16",
            "green": "#58b82a",
            "blue": "#2857c5",
            "car": "#00a6d6",
            "orange": "#f39c12",
            "text": "#17202a",
        }

        # Coordinates reproduce the supplied graph in a 760 x 540 canvas.
        node_positions = {
            1: (100, 92), 2: (218, 92), 3: (347, 92), 4: (500, 92),
            5: (683, 49), 6: (147, 307), 7: (254, 198), 8: (386, 209),
            9: (683, 444), 10: (135, 222), 11: (189, 444), 12: (300, 317),
            13: (429, 351), 14: (277, 444), 15: (530, 444), 16: (641, 232),
        }
        # Map palette (one-based node labels), matching the printed track.
        node_palette = {"cyan": "#69DAED", "green": "#A3E568", "yellow": "#FFE35A"}
        node_colors = {1: node_palette["cyan"], 5: node_palette["green"],
                       9: node_palette["cyan"], 11: node_palette["green"],
                       12: node_palette["green"]}

        # Each item is a road polyline; smoothing produces the curved map links.
        roads = [
            (1, 2), (2, 3), (3, 4), (2, 7), (3, 8), (7, 8),
            (6, 10), (11, 14), (14, 15), (15, 9), (12, 13),
            [(100, 92), (99, 160), (112, 205), (135, 222)],
            [(347, 92), (330, 50), (105, 50), (66, 68), (66, 390),
             (90, 430), (125, 444), (189, 444)],
            [(135, 222), (140, 270), (147, 307)],
            [(147, 307), (178, 356), (185, 405), (189, 444)],
            [(254, 198), (244, 263), (254, 294), (300, 317)],
            [(386, 209), (385, 261), (347, 286), (300, 317)],
            [(347, 92), (363, 139), (386, 183), (386, 209)],
            [(386, 209), (447, 214), (490, 165), (500, 92)],
            [(500, 92), (535, 94), (606, 112), (619, 143), (641, 232)],
            [(500, 92), (511, 44), (558, 25), (615, 27), (683, 49)],
            [(683, 49), (720, 91), (705, 180), (641, 232)],
            [(429, 351), (493, 278), (557, 248), (641, 232)],
            [(429, 351), (502, 361), (526, 393), (530, 444)],
            [(641, 232), (681, 293), (718, 350), (722, 398), (711, 430), (683, 444)],
            [(300, 317), (279, 357), (276, 401), (277, 444)],
        ]

        root = tk.Tk()
        root.title("Notte Europea dei ricercatori")
        root.geometry("1080x650")
        root.minsize(1000, 620)
        root.attributes("-fullscreen", True)
        root.bind("<Escape>", lambda event: root.attributes("-fullscreen", False))
        root.bind("<F11>", lambda event: root.attributes("-fullscreen", not root.attributes("-fullscreen")))
        root.configure(bg=colors["background"])

        header = tk.Frame(root, bg=colors["blue"], height=70)
        header.pack(fill="x")
        header.pack_propagate(False)
        title_group = tk.Frame(header, bg=colors["blue"])
        title_group.pack(side="left", padx=24, pady=8)
        tk.Label(title_group, text="Sei più veloce dell'Intelligenza Artificiale?", bg=colors["blue"],
                 fg="white", font=("Arial", 20, "bold")).pack(anchor="w")
        #tk.Label(title_group, text="Live digital twin control panel", bg=colors["blue"],
        #         fg="#cfe1ff", font=("Arial", 10)).pack(anchor="w")
        guard_sum_label = tk.Label(header, text=f"Somma guardie incontrate: {self.guard_sum}",
                                   bg=colors["blue"], fg="white",
                                   font=("Arial", 18, "bold"))
        guard_sum_label.pack(side="right", padx=24, pady=16)

        content = tk.Frame(root, bg=colors["background"])
        content.pack(fill="both", expand=True, padx=14, pady=14)
        canvas = tk.Canvas(content, width=760, height=540, bg="white",
                           highlightthickness=1, highlightbackground="#9aa0a6")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        canvas.grid(row=0, column=0, sticky="nsew")

        controls = tk.Frame(content, bg=colors["panel"], width=330, padx=20, pady=24,
                            highlightthickness=1, highlightbackground="#d9dde3")
        controls.grid(row=0, column=1, sticky="ns", padx=(14, 0))
        # Reserve the panel width before longer move and LED messages appear.
        controls.pack_propagate(False)
        reset_button = Button(controls, text="Reset", command=lambda: reset_game(),
                              bg=colors["red"], fg="white", activebackground="#ac1511",
                              font=("Arial", 11, "bold"), padx=16, pady=8, height=2)
        # Pack first at the bottom so game-over text cannot compress this button.
        reset_button.pack(side="bottom", fill="x", pady=(10, 0))
        tk.Label(controls, text="Car position", bg=colors["panel"], fg=colors["text"],
                 font=("Arial", 18, "bold")).pack(anchor="w")
        tk.Label(controls, text="Enter a node from 1 to 16", bg=colors["panel"],
                 fg="#505861", font=("Arial", 11)).pack(anchor="w", pady=(6, 14))

        node_value = tk.StringVar(value="")
        node_entry = tk.Entry(controls, textvariable=node_value, font=("Arial", 20),
                              justify="center", width=8, relief="solid", borderwidth=1)
        node_entry.pack(anchor="w", fill="x")
        current_label = tk.Label(controls, text="CAR AT NODE 1", bg=colors["panel"],
                                 fg=colors["car"], font=("Arial", 15, "bold"))
        current_label.pack(anchor="w", pady=(24, 6))
        status_label = tk.Label(controls, text="Ready", bg=colors["panel"],
                                fg="#505861", font=("Arial", 10), justify="left",
                                wraplength=230)
        status_label.pack(anchor="w", pady=(0, 20))
        next_nodes_label = tk.Label(controls, bg=colors["panel"], fg=colors["text"],
                                    font=("Arial", 10, "bold"), wraplength=230, justify="left")
        next_nodes_label.pack(anchor="w", pady=(0, 10))

        connection_frame = tk.Frame(controls, bg="#f6f8fb", padx=12, pady=10,
                                    highlightthickness=1, highlightbackground="#e0e5eb")
        connection_frame.pack(fill="x", pady=(0, 14))
        connection_dot = tk.Canvas(connection_frame, width=16, height=16,
                                   bg="#f6f8fb", highlightthickness=0)
        connection_dot.pack(side="left")
        connection_light = connection_dot.create_oval(3, 3, 13, 13, fill="#9aa0a6", outline="")
        connection_label = tk.Label(connection_frame, text="Checking Bluetooth…",
                                    bg="#f6f8fb", fg="#505861", font=("Arial", 10, "bold"))
        connection_label.pack(side="left", padx=(7, 0))

        led_card = tk.Frame(controls, bg="#17202a", padx=16, pady=14)
        led_card.pack(fill="x", pady=(0, 18))
        #tk.Label(led_card, text="MICRO:BIT LED STATUS", bg="#17202a", fg="#aeb8c2",
        #         font=("Arial", 9, "bold")).pack(anchor="w")
        led_row = tk.Frame(led_card, bg="#17202a")
        led_row.pack(fill="x", pady=(10, 0))
        led_preview = tk.Canvas(led_row, width=48, height=48, bg="#17202a", highlightthickness=0)
        led_preview.pack(side="left")
        led_glow = led_preview.create_oval(5, 5, 43, 43, fill=node_palette["cyan"],
                                           outline="#b7f1fa", width=3)
        led_label = tk.Label(led_row, text="CYAN\nStart / finish", bg="#17202a", fg="white",
                             font=("Arial", 12, "bold"), justify="left", wraplength=180)
        led_label.pack(side="left", padx=(12, 0))

        ranking_panel = tk.Frame(content, bg="white", padx=14, pady=20)
        ranking_panel.grid(row=0, column=2, sticky="ns", padx=(14, 0))
        tk.Label(ranking_panel, text="TIME CHALLENGE", bg="white",
                 font=("Arial", 16, "bold")).pack(anchor="w")
        tk.Label(ranking_panel, text="Player name", bg="white").pack(anchor="w", pady=(12, 2))
        player_value = tk.StringVar()
        player_entry = tk.Entry(ranking_panel, textvariable=player_value, width=24)
        player_entry.pack(fill="x")
        timer_label = tk.Label(ranking_panel, text="0.00 s", bg="white", font=("Arial", 25, "bold"))
        timer_label.pack(anchor="w", pady=12)
        tk.Label(ranking_panel, text="Start: first drive or node move\nFinish: node 9 • Follow connected roads",
                 bg="white", justify="left").pack(anchor="w")
        tk.Label(ranking_panel, text="RANKING · LOWEST COST FIRST", bg="white",
                 font=("Arial", 11, "bold")).pack(anchor="w", pady=(20, 8))
        ranking_table = tk.Frame(ranking_panel, bg="white")
        ranking_table.pack(fill="both", expand=True)
        ranking = ttk.Treeview(ranking_table, columns=("rank", "player", "time"),
                               show="headings", height=10)
        for column, label, width in (("rank", "#", 32), ("player", "Player", 130),
                                     ("time", "Seconds", 85)):
            ranking.heading(column, text=label)
            ranking.column(column, width=width, stretch=False)
        ranking.tag_configure("current_run", background="#ffe35a", foreground="#17202a")
        ranking.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(ranking_table, orient="vertical", command=ranking.yview)
        ranking.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        ranking_note = tk.Label(ranking_panel, text="Completed runs are saved in car_rankings.csv",
                                bg="white", wraplength=230, justify="left")
        ranking_note.pack(anchor="w", pady=8)
        position_label = tk.Label(ranking_panel, text="", bg="white", fg="#2857c5",
                                  font=("Arial", 13, "bold"), wraplength=230, justify="left")
        position_label.pack(anchor="w", pady=(0, 8))
        tk.Label(ranking_panel, text="Esc: leave full screen • F11: toggle", bg="white",
                 fg="#505861", font=("Arial", 9)).pack(anchor="w")

        def refresh_ranking():
            try:
                results = load_results()
                ranking.delete(*ranking.get_children())
                current_place = None
                for place, result in enumerate(results, 1):
                    is_current = (last_saved_result is not None and
                                  result["finished_at"] == last_saved_result["finished_at"])
                    ranking.insert("", "end", values=(place, result["player"],
                                   f'{float(result["elapsed_seconds"]):.2f}'),
                                   tags=("current_run",) if is_current else ())
                    if is_current:
                        current_place = place
                position_label.config(text=f"Your position: #{current_place}" if current_place else "")
            except (OSError, ValueError) as error:
                ranking_note.config(text=f"Cannot read rankings: {error}", fg=colors["red"])

        # Derive legal moves directly from the displayed roads.
        positions_to_nodes = {point: node for node, point in node_positions.items()}
        neighbours = {node: set() for node in node_positions}
        for road in roads:
            first, last = road if isinstance(road, tuple) else (positions_to_nodes[road[0]], positions_to_nodes[road[-1]])
            neighbours[first].add(last)
            neighbours[last].add(first)
        challenge = Challenge(neighbours=neighbours)

        def show_available_moves():
            available = ", ".join(map(str, challenge.available_moves))
            next_nodes_label.config(text=f"Available next nodes: {available or 'none'}")

        show_available_moves()
        map_scale = 1.0

        for road in roads:
            if isinstance(road, tuple):
                points = (*node_positions[road[0]], *node_positions[road[1]])
            else:
                points = tuple(coordinate for point in road for coordinate in point)
            canvas.create_line(*points, fill=colors["road"], width=11,
                               smooth=True, splinesteps=24, capstyle=tk.ROUND,
                               joinstyle=tk.ROUND)

        node_radius = 16
        node_items = {}
        for node, (x, y) in node_positions.items():
            fill = node_colors.get(node, node_palette["yellow"])
            node_items[node] = canvas.create_oval(
                x - node_radius, y - node_radius, x + node_radius, y + node_radius,
                fill=fill, outline="",
                tags=(f"node-{node}", "node")
            )
            canvas.create_text(x, y, text=str(node), fill="black",
                               font=("Arial", 12, "bold"), tags=(f"node-{node}", "node"))
            guard_value = NODE_GUARDS[str(node - 1)]
            if guard_value > 0:
                guard_x = x - 25 if x > 650 else x + 25
                guard_y = y + 22 if y < 70 else y - 22
                # Pointed shield badge; its number is the challenge's guard count.
                shield = [guard_x - 11, guard_y - 10, guard_x, guard_y - 13,
                          guard_x + 11, guard_y - 10, guard_x + 9, guard_y + 3,
                          guard_x, guard_y + 12, guard_x - 9, guard_y + 3]
                canvas.create_polygon(*shield, fill="#39aeda", outline="#176b87", width=2)
                canvas.create_line(guard_x - 7, guard_y - 7, guard_x + 7, guard_y - 7,
                                   fill="#a8e7f7", width=1)
                canvas.create_text(guard_x, guard_y - 1, text=str(guard_value), fill="white",
                                   font=("Arial", 8, "bold"))

        # Compact legend inside the map.
        canvas.create_rectangle(18, 482, 452, 524, fill="#ffffff", outline="#d9dde3")
        legend_items = [(node_palette["cyan"], "Start/finish"), (node_palette["green"], "Safe"),
                        (node_palette["yellow"], "Guard"), (colors["road"], "Car")]
        legend_x = 34
        for fill, label in legend_items:
            canvas.create_oval(legend_x, 498, legend_x + 14, 512, fill=fill, outline="")
            canvas.create_text(legend_x + 20, 505, text=label, anchor="w",
                               fill=colors["text"], font=("Arial", 9, "bold"))
            legend_x += 105

        car_radius = 12
        car_shadow = canvas.create_oval(0, 0, 0, 0, fill="#65717d", outline="")
        car_marker = canvas.create_oval(0, 0, 0, 0, fill="#000000",
                                        outline="white", width=3)
        car_text = canvas.create_text(0, 0, text="CAR", fill="white",
                                      font=("Arial", 7, "bold"))

        def draw_car(node):
            x, y = node_positions[node]
            # Place a separate black car marker beside the selected graph node.
            car_x = x - 23 if x > 650 else x + 23
            car_y = y + 23 if y < 65 else y - 23
            canvas.coords(car_shadow, car_x - car_radius + 2, car_y - car_radius + 3,
                          car_x + car_radius + 2, car_y + car_radius + 3)
            canvas.coords(car_marker, car_x - car_radius, car_y - car_radius,
                          car_x + car_radius, car_y + car_radius)
            canvas.coords(car_text, car_x, car_y)
            for item in (car_shadow, car_marker, car_text):
                canvas.scale(item, 0, 0, map_scale, map_scale)
            canvas.tag_raise(car_shadow)
            canvas.tag_raise(car_marker)
            canvas.tag_raise(car_text)

        current_led_command = "CYAN"

        def update_led(command):
            nonlocal current_led_command
            current_led_command = command
            styles = {
                "CYAN": (node_palette["cyan"], "#b7f1fa", "CYAN\nStart / finish"),
                "GREEN": (colors["green"], "#8ee269", "GREEN\nSafe node"),
                "ORANGE": (node_palette["yellow"], "#fff2a3", "YELLOW\n1 consecutive guard node"),
                "PURPLE": ("#A855F7", "#d8b4fe", "PURPLE\n2 consecutive guard nodes"),
                "RED": (colors["red"], "#ff817a", "RED\n3 consecutive guards: GAME OVER"),
            }
            fill, outline, text = styles[command]
            led_preview.itemconfig(led_glow, fill=fill, outline=outline)
            led_label.config(text=text)

        game_over = False
        last_saved_result = None
        joystick = None
        joystick_enabled = False
        closing_gui = False
        joystick_panel = tk.Frame(content, bg=colors["panel"], padx=12, pady=8)
        joystick_panel.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        tk.Label(joystick_panel, text="D-PAD CONTROL", bg=colors["panel"],
                 font=("Arial", 11, "bold")).grid(row=0, column=0, padx=(0, 10))
        controller_choice = ttk.Combobox(joystick_panel, state="readonly", width=30)
        controller_choice.grid(row=0, column=1, padx=4)
        joystick_status = tk.Label(joystick_panel, text="Joystick disabled", bg=colors["panel"],
                                   anchor="w", font=("Arial", 10))
        joystick_status.grid(row=1, column=0, columnspan=5, sticky="w", pady=(6, 0))
        tk.Label(joystick_panel, text="Hold arrows to drive; release to stop. Analog sticks ignored. Record reached nodes above.",
                 bg=colors["panel"], fg="#505861").grid(row=2, column=0, columnspan=5, sticky="w")

        def stop_joystick(reason="Stopped — enable joystick to drive again"):
            nonlocal joystick_enabled
            joystick_enabled = False
            if self.bt_connection:
                self.bt_connection.set_movement("STOP")
            if joystick:
                joystick.release()
            joystick_status.config(text=reason)

        def refresh_controllers():
            nonlocal joystick
            stop_joystick()
            try:
                if joystick is None:
                    joystick = GuiJoystick()
                devices = joystick.devices()
                controller_choice.config(values=devices)
                if devices:
                    controller_choice.current(0)
                else:
                    controller_choice.set("")
                joystick_status.config(text="Select controller and Enable joystick" if devices else "No controller found — connect USB and click Refresh")
            except Exception as error:
                joystick_status.config(text=f"Joystick unavailable: {error}")

        def enable_joystick():
            nonlocal joystick_enabled
            stop_joystick()
            if game_over:
                joystick_status.config(text="Run ended — press Reset before enabling")
                return
            if not self.bt_connection or not self.bt_connection.is_connected:
                joystick_status.config(text="Bluetooth offline — connect the car first")
                return
            try:
                if joystick is None or controller_choice.current() < 0:
                    raise ValueError("Connect a controller and click Refresh")
                joystick.select(controller_choice.current())
                joystick_enabled = True
                joystick_status.config(text="Release D-pad once, then hold an arrow to drive")
            except Exception as error:
                joystick_status.config(text=str(error))

        ttk.Button(joystick_panel, text="Refresh", command=refresh_controllers).grid(row=0, column=2, padx=4)
        ttk.Button(joystick_panel, text="Enable joystick", command=enable_joystick).grid(row=0, column=3, padx=4)
        Button(joystick_panel, text="STOP", bg=colors["red"], fg="white", command=stop_joystick,
               font=("Arial", 12, "bold")).grid(row=0, column=4, padx=8)
        controller_choice.bind("<<ComboboxSelected>>", lambda event: stop_joystick())

        def poll_joystick():
            if closing_gui:
                return
            if joystick_enabled:
                try:
                    if not self.bt_connection.is_connected:
                        stop_joystick("Bluetooth disconnected — stopped")
                    elif game_over:
                        stop_joystick("Run ended — stopped")
                    elif root.focus_displayof() is None:
                        stop_joystick("Window lost focus — stopped; enable to resume")
                    else:
                        command = joystick.read(True)
                        self.bt_connection.set_movement(command)
                        if command != "STOP":
                            challenge.start(player_value.get())
                            player_entry.config(state="disabled")
                        joystick_status.config(text=f"D-pad: {command}   |   {controller_choice.get()}")
                except Exception as error:
                    stop_joystick(f"Controller stopped: {error}")
            root.after(30, poll_joystick)

        def close_gui():
            nonlocal closing_gui
            closing_gui = True
            stop_joystick()
            if joystick:
                joystick.close()
            if self.bt_connection:
                self.bt_connection.close()
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", close_gui)

        def move_car(node=None):
            nonlocal game_over
            if game_over:
                return
            try:
                selected_node = int(node if node is not None else node_value.get())
            except (TypeError, ValueError):
                stop_joystick()
                messagebox.showerror("Invalid node", "Enter a whole number from 1 to 16.")
                return
            if selected_node not in node_positions:
                stop_joystick()
                messagebox.showerror("Invalid node", "Node must be between 1 and 16.")
                return

            if selected_node == challenge.path[-1]:
                return
            try:
                challenge.move(selected_node, player_value.get())
            except ValueError as error:
                status_label.config(text=str(error))
                return
            player_entry.config(state="disabled")

            node_value.set("")
            node_entry.focus_set()
            draw_car(selected_node)
            current_label.config(text=f"CAR AT NODE {selected_node}")

            # The displayed map is one-based; existing guard data is zero-based.
            marker_id = selected_node - 1
            guard_number = NODE_GUARDS[str(marker_id)]
            if marker_id not in self.guards_collected:
                self.guards_collected.add(marker_id)
                self.guard_sum += guard_number
                if guard_number > 0:
                    self.consecutive_guard_node += 1
                    if self.consecutive_guard_node == 1:
                        command = "ORANGE"  # Existing protocol name for yellow LEDs.
                    elif self.consecutive_guard_node == 2:
                        command = "PURPLE"
                    else:
                        command = "RED"
                else:
                    self.consecutive_guard_node = 0
                    command = "CYAN" if selected_node in (1, 9) else "GREEN"
                self.send_bt_command(command)
                update_led(command)
                if command == "RED":
                    game_over = True
                    status_label.config(
                        text=f"GAME OVER at node {selected_node}! Three consecutive guards reached.",
                        fg=colors["red"], font=("Arial", 11, "bold")
                    )
                    node_entry.config(state="disabled")
                else:
                    status_label.config(text=f"Node {selected_node}: {guard_number} guards collected",
                                        fg="#505861", font=("Arial", 10))
            else:
                status_label.config(text=f"Node {selected_node}: already visited")
            guard_sum_label.config(text=f"GUARD SUM: {self.guard_sum}")
            if game_over:
                challenge.stop()
            elif selected_node == 9:
                challenge.stop()
                game_over = True
                stop_joystick("Finish reached — car stopped")
                node_entry.config(state="disabled")
                status_label.config(text=f"Finished in {challenge.elapsed:.2f} seconds!")
                save_finished_run()
            elif not challenge.available_moves:
                challenge.stop()
                game_over = True
                node_entry.config(state="disabled")
                status_label.config(text="No unvisited neighbouring nodes remain. Press Reset to try again.")
            show_available_moves()
            if game_over:
                stop_joystick("Run ended — car stopped")

        def save_finished_run():
            nonlocal last_saved_result
            try:
                if last_saved_result is None:
                    last_saved_result = challenge.result()
                save_result(last_saved_result)
            except (OSError, ValueError) as error:
                ranking_note.config(text=f"Result not saved: {error}", fg=colors["red"])
                retry_button.pack(fill="x")
                return
            retry_button.pack_forget()
            ranking_note.config(text=f"Saved to {RESULTS_FILE.name}", fg=colors["text"])
            refresh_ranking()

        retry_button = Button(ranking_panel, text="Retry saving result", command=save_finished_run)

        def reset_game():
            nonlocal game_over, last_saved_result
            stop_joystick("Reset — enable joystick for the next player")
            game_over = False
            last_saved_result = None
            challenge.reset()
            show_available_moves()
            player_value.set("")
            player_entry.config(state="normal")
            retry_button.pack_forget()
            self.guard_sum = 0
            self.consecutive_guard_node = 0
            self.guards_collected.clear()
            guard_sum_label.config(text="GUARD SUM: 0")
            node_value.set("")
            draw_car(1)
            current_label.config(text="CAR AT NODE 1")
            status_label.config(text="Game reset — choose a node and press Enter",
                                fg="#505861", font=("Arial", 10))
            node_entry.config(state="normal")
            update_led("CYAN")
            self.send_bt_command("CYAN")

        node_entry.bind("<Return>", lambda _event: move_car())
        for node in node_positions:
            canvas.tag_bind(f"node-{node}", "<Button-1>",
                            lambda _event, selected=node: move_car(selected))
        draw_car(1)
        update_led("CYAN")

        def resize_map(event):
            nonlocal map_scale
            new_scale = min(event.width / 760, event.height / 540)
            if new_scale > 0:
                canvas.scale("all", 0, 0, new_scale / map_scale, new_scale / map_scale)
                map_scale = new_scale

        canvas.bind("<Configure>", resize_map)

        def refresh_timer():
            timer_label.config(text=f"{challenge.elapsed:.2f} s")
            root.after(50, refresh_timer)

        refresh_ranking()
        refresh_timer()

        was_connected = False

        def refresh_connection_status():
            nonlocal was_connected
            connected = bool(self.bt_connection and self.bt_connection.client and
                             self.bt_connection.client.is_connected)
            if connected and not was_connected:
                self.send_bt_command(current_led_command)
            was_connected = connected
            connection_dot.itemconfig(connection_light,
                                      fill=colors["green"] if connected else "#9aa0a6")
            connection_label.config(text="Bluetooth connected" if connected else "Bluetooth offline")
            root.after(1000, refresh_connection_status)

        refresh_connection_status()
        refresh_controllers()
        poll_joystick()
        node_entry.focus_set()
        try:
            root.mainloop()
        finally:
            if not closing_gui:
                stop_joystick()
                if joystick:
                    joystick.close()
                if self.bt_connection:
                    self.bt_connection.close()

    def process_video_gui(self, video_source=0, output_path=None):
        """
        Process video with a fancy GUI display using Bang Wong's accessible color palette.
        
        Args:
            video_source: Video source (0 for webcam, or path to video file)
            output_path: Path to save output video (optional)
        """
        # Bang Wong accessible color palette
        colors = {
            'black': '#000000',
            'orange': '#E69F00',
            'sky_blue': '#56B4E9',
            'green': '#009E73',
            'yellow': '#F0E442',
            'blue': '#0072B2',
            'red': '#D55E00',
            'purple': '#CC79A7',
            'white': '#FFFFFF'
        }
        
        # Create tkinter window
        root = tk.Tk()
        root.title("ArUco Marker Detection")
        root.geometry("1000x800")
        root.configure(bg=colors['white'])
        
        # Open video source
        cap = cv2.VideoCapture(video_source)
        if not cap.isOpened():
            print(f"Error: Cannot open video source {video_source}")
            return
        
        # Get video properties
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Setup video writer if output path specified
        writer = None
        if output_path:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        # Create top frame for Guard Sum
        top_frame = tk.Frame(root, bg=colors['blue'], height=60)
        top_frame.pack(fill="x", padx=5, pady=5)
        top_frame.pack_propagate(False)
        
        guard_sum_label = Label(
            top_frame,
            text=f"GUARD SUM: {self.guard_sum}",
            bg=colors['blue'],
            fg=colors['white'],
            font=("Arial", 24, "bold"),
            pady=10
        )
        guard_sum_label.pack(fill="both", expand=True)
        
        # Create info label (white background, black text)
        info_label = Label(
            root,
            text="Initializing...",
            bg=colors['white'],
            fg=colors['black'],
            font=("Arial", 11),
            justify="left",
            padx=10,
            pady=8,
            relief="solid",
            borderwidth=1
        )
        info_label.pack(fill="x", padx=5, pady=2)
        
        # Create video label
        video_label = Label(root, bg=colors['black'])
        video_label.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Create button frame
        button_frame = tk.Frame(root, bg=colors['white'])
        button_frame.pack(fill="x", padx=5, pady=5)
        
        # Reset button (centered)
        def reset_sum():
            self.guard_sum = 0
            self.consecutive_guard_node = 0
            self.guards_collected = set()
            guard_sum_label.config(text=f"GUARD SUM: {self.guard_sum}")
        
        reset_button = Button(
            button_frame,
            text="Reset Sum",
            command=reset_sum,
            bg=colors['red'],
            fg=colors['white'],
            font=("Arial", 12, "bold"),
            padx=20,
            pady=10
        )
        reset_button.pack(anchor="center", padx=5)
        
        frame_count = 0
        marker_log = []
        
        def update_frame():
            nonlocal frame_count
            
            ret, frame = cap.read()
            if not ret:
                cap.release()
                if writer:
                    writer.release()
                root.quit()
                return
            
            frame_count += 1
            
            # Detect markers
            corners, ids, _ = self.detect_markers(frame)
            
            # Draw markers
            frame = self.draw_markers(frame, corners, ids)
            
            # Check marker 16 position relative to guards
            if ids is not None and SMART_CAR_MARKER_ID in ids:
                centers = [self.get_marker_center(c) for c in corners]
                self.check_car_position(frame, centers, ids)
            
            # Log marker information
            if ids is not None:
                try:
                    for marker_corners, marker_id in zip(corners, ids):
                        if isinstance(marker_id, (list, np.ndarray)):
                            marker_id_value = int(marker_id[0])
                        else:
                            marker_id_value = int(marker_id)
                        
                        center_x, center_y = self.get_marker_center(marker_corners)
                        marker_log.append({
                            'frame': frame_count,
                            'id': marker_id_value,
                            'center_x': center_x,
                            'center_y': center_y
                        })
                except Exception as e:
                    print(f"Warning: Error logging marker data: {e}")
            
            # Write frame to output
            if writer:
                writer.write(frame)
            
            # Update Guard Sum display
            guard_sum_label.config(text=f"GUARD SUM: {self.guard_sum}")
            
            # Update info text
            marker_count = len(ids) if ids is not None else 0
            detected_ids = ""
            if ids is not None and marker_count > 0:
                detected_ids_list = []
                for m in ids:
                    if isinstance(m, (list, np.ndarray)):
                        detected_ids_list.append(str(int(m[0])))
                    else:
                        detected_ids_list.append(str(int(m)))
                detected_ids = ", ".join(detected_ids_list)
            
            info_text = f"Markers: {marker_count} | IDs: {detected_ids}"
            info_label.config(text=info_text)
            
            # Convert frame for display
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_pil = Image.fromarray(frame_rgb)
            frame_pil.thumbnail((970, 500), Image.Resampling.LANCZOS)
            frame_tk = ImageTk.PhotoImage(frame_pil)
            
            video_label.config(image=frame_tk)
            video_label.image = frame_tk
            
            # Schedule next frame update
            root.after(int(1000 / fps), update_frame)
        
        # Start updating frames
        root.after(0, update_frame)
        
        try:
            root.mainloop()
        finally:
            cap.release()
            if writer:
                writer.release()
            print(f"\nProcessing complete!")
            print(f"Total frames processed: {frame_count}")
            print(f"Total markers detected: {len(marker_log)}")
            print(f"Final Guard Sum: {self.guard_sum}")

    def process_video(self, video_source=0, output_path=None, display=True):
        """
        Process video and detect ArUco markers.
        
        Args:
            video_source: Video source (0 for webcam, or path to video file)
            output_path: Path to save output video (optional)
            display: Whether to display video in real-time (default: True)
        """
        # Open video source (0 = default webcam)
        cap = cv2.VideoCapture(video_source)
        
        if not cap.isOpened():
            print(f"Error: Cannot open video source {video_source}")
            return
        
        # Get video properties
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        print(f"Webcam: {width}x{height} @ {fps} FPS")
        
        # Setup video writer if output path specified
        writer = None
        if output_path:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
            print(f"Output will be saved to: {output_path}")
        
        frame_count = 0
        marker_log = []
        
        try:
            while True:
                try:
                    ret, frame = cap.read()
                    
                    if not ret:
                        break
                    
                    frame_count += 1
                    
                    # Detect markers
                    corners, ids, _ = self.detect_markers(frame)
                    
                    # Draw markers
                    frame = self.draw_markers(frame, corners, ids)
                    
                    # Check marker 16 position relative to guards
                    if ids is not None and SMART_CAR_MARKER_ID in ids:
                        centers = [self.get_marker_center(c) for c in corners]
                        self.check_car_position(frame, centers, ids)
                    
                    # Log marker information
                    if ids is not None:
                        try:
                            for marker_corners, marker_id in zip(corners, ids):
                                # Handle both scalar and array marker_id formats
                                if isinstance(marker_id, (list, np.ndarray)):
                                    marker_id_value = int(marker_id[0])
                                else:
                                    marker_id_value = int(marker_id)
                                
                                center_x, center_y = self.get_marker_center(marker_corners)
                                marker_log.append({
                                    'frame': frame_count,
                                    'id': marker_id_value,
                                    'center_x': center_x,
                                    'center_y': center_y
                                })
                        except Exception as e:
                            print(f"Warning: Error logging marker data: {e}")
                    
                    # Display marker count
                    marker_count = len(ids) if ids is not None else 0
                    cv2.putText(
                        frame,
                        f"Markers: {marker_count}",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 255),
                        1
                    )
                    
                    # Display detected marker IDs
                    if ids is not None and marker_count > 0:
                        try:
                            detected_ids_list = []
                            for m in ids:
                                if isinstance(m, (list, np.ndarray)):
                                    detected_ids_list.append(str(int(m[0])))
                                else:
                                    detected_ids_list.append(str(int(m)))
                            detected_ids = ", ".join(detected_ids_list)
                            cv2.putText(
                                frame,
                                f"IDs: {detected_ids}",
                                (10, 65),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.6,
                                (0, 255, 255),
                                1
                            )
                        except Exception as e:
                            pass
                    
                    # Always display the cumulative guard sum
                    cv2.putText(
                        frame,
                        f"Guard Sum: {self.guard_sum}",
                        (10, 100),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 255),
                        2
                    )
                    
                    # Write frame to output
                    if writer:
                        writer.write(frame)
                    
                    # Display frame
                    if display:
                        cv2.imshow('ArUco Marker Detection', frame)
                        
                        # Check for key press or window close
                        key = cv2.waitKey(1) & 0xFF
                        if key == ord('q'):
                            break
                        
                        # Check if window was closed by user
                        try:
                            if cv2.getWindowProperty('ArUco Marker Detection', cv2.WND_PROP_VISIBLE) < 1:
                                print("\nWindow closed by user.")
                                break
                        except:
                            break
                
                except Exception as e:
                    print(f"Error processing frame {frame_count}: {e}")
                    continue
        
        finally:
            # Cleanup
            cap.release()
            if writer:
                writer.release()
            if display:
                cv2.destroyAllWindows()
            
            print(f"\nProcessing complete!")
            print(f"Total frames processed: {frame_count}")
            print(f"Total markers detected: {len(marker_log)}")
            
            return marker_log


def main():
    """Run the camera-free smart-car digital twin."""
    bt = BluetoothConnection(CAR_BT_ADDRESS)
    bt.start_background_loop()  # Start persistent connection in background thread

    print("=" * 60)
    print("Smart Car Digital Twin")
    print("=" * 60)
    
    # Create detector with Bluetooth connection
    detector = ArUcoDetector(bt_connection=bt)
    detector.process_digital_twin_gui()
    
    # Stop background loop after GUI closes
    bt.close()
    if bt.thread:
        bt.thread.join(timeout=3)



if __name__ == "__main__":
    main()
