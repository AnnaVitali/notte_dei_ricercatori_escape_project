import cv2
import numpy as np
import sys
import os
from pathlib import Path
import tkinter as tk
from tkinter import Label, Button
from PIL import Image, ImageTk
import asyncio
from bleak import BleakClient
import threading
import queue

SMART_CAR_MARKER_ID = 16
NODE_GUARDS = {"0":0, "1": 8, "2": 3, "3": 5, "4":0, "5": 3, "6": 9, "7": 8, "8":0, "9": 4, "10":0, "11":0, "12": 10, "13": 8, "14": 14, "15": 8} # starting form 0

CAR_BT_ADDRESS = "C2:38:E3:86:54:78"

# Nordic UART Service UUIDs used by the micro:bit
UART_WRITE = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

class BluetoothConnection:
    def __init__(self, address):
        self.address = address
        self.client = None
        self.command_queue = queue.Queue()
        self.running = False
        self.loop = None
        
    async def connect(self):
        """Establish and keep the Bluetooth connection alive"""
        self.client = BleakClient(self.address)
        await self.client.connect()
        print("✅ Connected!")
        
    async def send_command(self, cmd):
        """Send a command through the open connection"""
        if not self.client or not self.client.is_connected:
            print("❌ Error: Not connected")
            return
            
        try:
            # Ensure command ends with # (micro:bit delimiter)
            if not cmd.endswith("#"):
                cmd = cmd + "#"
            
            # Use response=False for non-blocking, faster communication
            await self.client.write_gatt_char(UART_WRITE, cmd.encode(), response=False)
            print(f"✅ Sent: {cmd}")
        except Exception as e:
            print(f"❌ Error sending command: {e}")
            
    async def disconnect(self):
        """Close the connection"""
        if self.client and self.client.is_connected:
            try:
                await self.client.disconnect()
                print("✅ Disconnected!")
            except Exception as e:
                print(f"Disconnect error: {e}")
    
    async def _process_queue(self):
        """Process commands from the queue in an async loop"""
        while self.running:
            try:
                # Check if there's a command in the queue (non-blocking)
                cmd = self.command_queue.get_nowait()
                await self.send_command(cmd)
            except queue.Empty:
                await asyncio.sleep(0.01)  # Small delay to prevent busy-waiting
            except Exception as e:
                print(f"Error processing command: {e}")
    
    def _run_event_loop(self):
        """Run the event loop in a background thread"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.running = True
        
        try:
            self.loop.run_until_complete(self._connect_and_process())
        except Exception as e:
            print(f"Event loop error: {e}")
        finally:
            self.running = False
            if self.loop:
                self.loop.close()
    
    async def _connect_and_process(self):
        """Connect and process queue indefinitely"""
        try:
            await self.connect()
            await self._process_queue()
        except Exception as e:
            print(f"Connection error: {e}")
    
    def start_background_loop(self):
        """Start the background thread with event loop"""
        thread = threading.Thread(target=self._run_event_loop, daemon=True)
        thread.start()
        # Give the connection time to establish
        import time
        time.sleep(1)
    
    def queue_command(self, cmd):
        """Queue a command to be sent"""
        if self.running:
            self.command_queue.put(cmd)
        else:
            print("❌ Bluetooth not connected")
        
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
        tolerance = 20  # pixels tolerance for x alignment
        
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
                            if self.consecutive_guard_node <= 2:
                                self.send_bt_command("ORANGE")
                            elif self.consecutive_guard_node > 2:
                                self.send_bt_command("RED")
                        else :
                            self.send_bt_command("GREEN")
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
    """
    Main function to run ArUco marker detection on webcam feed.
    Can accept camera index as command-line argument.
    """
    bt = BluetoothConnection(CAR_BT_ADDRESS)
    bt.start_background_loop()  # Start persistent connection in background thread
    
    # Get camera index from command line or use default
    camera_index = 1
    if len(sys.argv) > 1:
        try:
            camera_index = int(sys.argv[1])
        except ValueError:
            print(f"Invalid camera index: {sys.argv[1]}")
            print("Using default camera (0)")
    
    print("=" * 60)
    print("ArUco Marker Detection")
    print("=" * 60)
    print(f"Camera: {camera_index}")
    print(f"Dictionary: 4x4_50")
    print("=" * 60)
    
    # Create detector with Bluetooth connection
    detector = ArUcoDetector(bt_connection=bt)
    detector.process_video_gui(
        video_source=camera_index,
        output_path=None  # Set to file path if you want to save output video
    )
    
    # Stop background loop after GUI closes
    bt.running = False
    import time
    time.sleep(0.5)



if __name__ == "__main__":
    main()
