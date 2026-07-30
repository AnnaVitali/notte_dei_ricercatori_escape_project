import cv2
import numpy as np
import sys
import os
from pathlib import Path


class ArUcoDetector:
    """Detect and track ArUco markers in video."""
    
    def __init__(self, dictionary_type=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)):
        """
        Initialize ArUco detector.
        
        Args:
            dictionary_type: ArUco dictionary type (default: 4x4_50 for your markers)
        """
        self.dictionary = dictionary_type
        self.parameters = cv2.aruco.DetectorParameters()
        self.detector = cv2.aruco.ArucoDetector(self.dictionary, self.parameters)
        
        # Load marker mapping from ArUco_marker directory
        self.marker_names = self._load_marker_names()
    
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
                        
                        # Draw single green marker outline
                        cv2.polylines(frame, [corners_reshaped], True, (0, 255, 0), 2)
                        
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
                    corners, ids, rejected = self.detect_markers(frame)
                    
                    # Draw markers
                    frame = self.draw_markers(frame, corners, ids)
                    
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
                    
                    # Progress indicator
                    if frame_count % 30 == 0:
                        print(f"Processed {frame_count} frames")
                
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
    # Get camera index from command line or use default
    camera_index = 0
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
    print("Controls: Press 'q' or close the window to quit")
    print("=" * 60)
    
    # Create detector and process webcam feed
    detector = ArUcoDetector()
    marker_log = detector.process_video(
        video_source=camera_index,
        output_path=None,  # Set to file path if you want to save output video
        display=True
    )
    
    # Save marker log to CSV (optional)
    if marker_log:
        import csv
        log_path = "marker_detection_log.csv"
        with open(log_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['frame', 'id', 'center_x', 'center_y'])
            writer.writeheader()
            writer.writerows(marker_log)
        print(f"Marker log saved to: {log_path}")


if __name__ == "__main__":
    main()
