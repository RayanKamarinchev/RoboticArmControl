import cv2
from flask import Flask, request, jsonify, send_file, render_template
import serial
import serial.tools.list_ports
import time
import os
from datetime import datetime
import io
import numpy as np
import json

from src.box_detection import get_box_coordinates, Box
from src.camera_utils import decode_image, get_camera_position, get_marker_positions, get_camera_matrix_and_dist_coeffs
from src.movement import get_move_angles, get_initial_angles, conv_camera_coords_to_gripper_coords, get_gripper_coords_and_cam_rotation_from_arm, transform_arm_to_space_coords, transform_space_to_arm_coords
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE" #TODO

app = Flask(__name__)

MARKER_SIZE=0.036
MARKER_SPACING=0.005
BASELINE=0.02

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
INSTRUCTIONS_DIR = os.path.join(UPLOAD_FOLDER, "instructions.json")
LATEST_IMAGE_PATH = os.path.join(UPLOAD_FOLDER, "latest.jpg")
IMAGE_1_PATH = os.path.join(UPLOAD_FOLDER, "image1.jpg")
IMAGE_2_PATH = os.path.join(UPLOAD_FOLDER, "image2.jpg")
IMAGE_PATHS = [IMAGE_1_PATH, IMAGE_2_PATH]
DEBUG_DATA_PATH = "src/data.csv"
instructions = []
flag = False
counter = 0
ser = None
current_port = None
translation = None

current_gripper_position_in_world = None
current_gripper_position_in_arm = get_gripper_coords_and_cam_rotation_from_arm(get_initial_angles())
detected_boxes = []
latest_image = None

class Servo:
    def __init__(self, servo_id, name, min_angle, max_angle, initial_angle):
        self.id = servo_id
        self.name = name
        self.min_angle = min_angle
        self.max_angle = max_angle
        self.initial_angle = initial_angle
        
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "min_angle": self.min_angle,
            "max_angle": self.max_angle,
            "initial_angle": self.initial_angle,
        }
        
        
servos = [Servo(0, "Servo Base", 0, 180, 30),
          Servo(1, "Servo Joint 1", 0, 180, 100),
          Servo(2, "Servo Joint 2", 0, 180, 100),
          Servo(4, "Servo Head Joint", 0, 180, 6), 
          Servo(5, "Servo Gripper", 90, 180, 160)]

@app.route('/get_position', methods=['POST'])
def receive_image():
    global flag
    global current_gripper_position_in_world
    global current_gripper_position_in_arm
    global detected_boxes
    global translation
    
    if 'imageFile' not in request.files:
        print("FILES:", request.files)
        return jsonify({"error": "No file part"}), 400

    file = request.files['imageFile']
    file_bytes = file.read()
    print("Received:", len(file_bytes), "bytes")

    img = decode_image(file_bytes)
    cv2.imwrite(LATEST_IMAGE_PATH, img)
    
    _, camera_position, coordinate_systems_angle, R, rvec, tvec = get_camera_position(img, get_marker_positions(MARKER_SIZE, MARKER_SPACING), MARKER_SIZE)
    
    current_gripper_position_in_world = conv_camera_coords_to_gripper_coords(camera_position, get_initial_angles(), coordinate_systems_angle)
    
    # angles = get_move_angles(camera_position, target_position, get_initial_angles(), coordinate_systems_angle)
    camera_matrix, dist_coeffs = get_camera_matrix_and_dist_coeffs()
    
    detected_boxes = get_box_coordinates(img, camera_position, R, camera_matrix, dist_coeffs, rvec, tvec)
    # angles = get_move_angles(camera_position, target_position, get_initial_angles(), coordinate_systems_angle)
    
    flag = True
    
    return jsonify({"message": "OK"}), 200

def get_available_ports():
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/ports', methods=['GET'])
def get_ports():
    try:
        ports = get_available_ports()
        return jsonify({'success': True, 'ports': ports})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/servos', methods=['GET'])
def get_servos():
    return jsonify({'success': True, 'servos': [s.to_dict() for s in servos]})

@app.route('/api/mode', methods=['GET'])
def get_mode():
    return jsonify({'mode': arm_mode})

@app.route('/api/position', methods=['GET'])
def get_position():
    return jsonify({'success': True, 'position': current_position})

@app.route('/api/boxes', methods=['GET'])
def get_boxes():
    return jsonify({'success': True, 'boxes': detected_boxes})

@app.route('/api/image', methods=['GET'])
def get_image():
    if latest_image:
        return jsonify({'success': True, 'image': latest_image})
    return jsonify({'success': False, 'image': None})

@app.route('/api/connect', methods=['POST'])
def connect():
    global ser, current_port, arm_mode
    
    try:
        data = request.json
        port = data.get('port')
        baudrate = 9600
        
        if ser and ser.is_open:
            ser.close()
        
        # Open connection with robust settings
        ser = serial.Serial(
            port=port, 
            baudrate=baudrate, 
            timeout=0.1,
            write_timeout=0.1,
            inter_byte_timeout=0.01
        )
        current_port = port
        
        # Flush buffers to clear any noise
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        time.sleep(2)
        
        ser.write(b"activate\n")
        
        # Switch to serial mode
        arm_mode = "serial"
        
        return jsonify({'success': True, 'message': f'Connected to {port}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/disconnect', methods=['POST'])
def disconnect():
    global ser, current_port, arm_mode
    
    try:
        if ser and ser.is_open:
            ser.close()
        current_port = None
        
        return jsonify({'success': True, 'message': 'Disconnected'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/servo', methods=['POST'])
def control_servo():
    global ser
    
    try:
        if not ser or not ser.is_open:
            return jsonify({'success': False, 'error': 'Not connected to any port'})
        
        data = request.json
        servo_id = data.get('servo_id')
        angle = data.get('angle')
        
        # format: "S<id>:<angle>\n"
        command = f"S{servo_id}:{angle:03d}\n"
        ser.write(command.encode())
        
        return jsonify({'success': True, 'message': f'Servo {servo_id} set to {angle}°'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/world_position', methods=['POST'])
def set_world_position():
    global current_gripper_position_in_world
    
    try:
        data = request.json
        x = data.get('x')
        y = data.get('y')
        z = data.get('z')
        
        # TODO: Implement inverse kinematics and send to arm
        # For now, just update the position
        current_gripper_position_in_world = [x,y,z]
        
        angles = get_move_angles()
        
        if ser and ser.is_open:
            # TODO: Send serial command to arm
            command = f"P:{x},{y},{z}\n"
            ser.write(command.encode())
        
        return jsonify({'success': True, 'message': f'Position set to ({x}, {y}, {z})'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/grab_box', methods=['POST'])
def grab_box():
    try:
        data = request.json
        box_id = data.get('box_id')
        
        # TODO: Implement grab logic
        # This would involve:
        # 1. Get box position from detected_boxes
        # 2. Calculate path to box
        # 3. Send commands to arm
        
        print(f"Grabbing box {box_id}")
        
        return jsonify({'success': True, 'message': f'Grabbing box {box_id}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/status', methods=['GET'])
def status():
    global ser, current_port
    
    connected = ser is not None and ser.is_open
    return jsonify({
        'connected': connected,
        'port': current_port if connected else None
    })

@app.route('/api/serial_read', methods=['GET'])
def serial_read():
    global ser, current_position, detected_boxes, latest_image
    
    try:
        if not ser or not ser.is_open:
            return jsonify({'success': False, 'error': 'Not connected'})
        
        lines = []
        try:
            # Flush input buffer first to clear any corrupted data
            ser.reset_input_buffer()
            
            # Wait a bit for new data
            time.sleep(0.05)
            
            # Read all available bytes
            if ser.in_waiting > 0:
                raw_data = ser.read(ser.in_waiting)
                # Decode and split by newlines
                text = raw_data.decode('utf-8', errors='ignore')
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                
                # Process special messages
                for line in lines:
                    print(line)
                    
                    # TODO: Parse position updates from arm
                    # Example: "POS:10.5,20.3,15.7"
                    if line.startswith("POS:"):
                        try:
                            coords = line[4:].split(',')
                            current_position = {
                                "x": float(coords[0]),
                                "y": float(coords[1]),
                                "z": float(coords[2])
                            }
                        except:
                            pass
                    
                    # TODO: Parse box detections
                    # Example: "BOX:id,x,y,z,width,height,depth"
                    if line.startswith("BOX:"):
                        try:
                            parts = line[4:].split(',')
                            box = {
                                "id": parts[0],
                                "x": float(parts[1]),
                                "y": float(parts[2]),
                                "z": float(parts[3]),
                                "width": float(parts[4]),
                                "height": float(parts[5]),
                                "depth": float(parts[6])
                            }
                            # Check if box already exists, update or add
                            existing = next((b for b in detected_boxes if b['id'] == box['id']), None)
                            if existing:
                                detected_boxes[detected_boxes.index(existing)] = box
                            else:
                                detected_boxes.append(box)
                        except:
                            pass
                    
                    # TODO: Parse image data
                    # This is a placeholder - implement based on your actual protocol
                    if line.startswith("IMG:"):
                        try:
                            # Example: base64 encoded image
                            img_data = line[4:]
                            latest_image = img_data
                        except:
                            pass
                        
        except Exception as e:
            # Character-by-character fallback
            try:
                chars = []
                start_time = time.time()
                while time.time() - start_time < 0.1:
                    if ser.in_waiting > 0:
                        char = ser.read(1).decode('utf-8', errors='ignore')
                        if char == '\n':
                            line = ''.join(chars).strip()
                            if line:
                                lines.append(line)
                                print(line)
                            chars = []
                        else:
                            chars.append(char)
                    else:
                        time.sleep(0.01)
            except:
                pass
        
        return jsonify({'success': True, 'data': lines})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# HTTP endpoint for arm to send data when in HTTP mode
@app.route('/api/arm_update', methods=['POST'])
def arm_update():
    global current_position, detected_boxes, latest_image
    
    try:
        data = request.json
        
        # Update position if provided
        if 'position' in data:
            current_position = data['position']
        
        # Update detected boxes if provided
        if 'boxes' in data:
            detected_boxes = data['boxes']
        
        # Update image if provided
        if 'image' in data:
            latest_image = data['image']
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)