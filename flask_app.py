import cv2
from flask import Flask, request, jsonify, send_file, render_template
import serial
import serial.tools.list_ports
import time
import os
import numpy as np
import socket
import logging

from src.box_detection import get_box_coordinates, Box
from src.camera_utils import decode_image, get_camera_position, get_marker_positions, get_camera_matrix_and_dist_coeffs
from src.movement import (get_move_angles, get_initial_angles,
                          conv_camera_coords_to_gripper_coords, get_gripper_coords_and_cam_rotation_from_arm,
                          transform_arm_to_world_coords, transform_world_to_arm_coords,
                          get_translation, world_to_servo_angles, servo_to_world_angle)
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE" #TODO

class IgnoreEndpointsFilter(logging.Filter):
    def __init__(self, ignored_paths):
        super().__init__()
        self.ignored_paths = ignored_paths

    def filter(self, record):
        if record.levelno >= logging.ERROR:
            return True

        message = record.getMessage()

        return not any(path in message for path in self.ignored_paths)


ignored_endpoints = ["/api/serial_read"]

log = logging.getLogger("werkzeug")
log.addFilter(IgnoreEndpointsFilter(ignored_endpoints))

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
system_angle = None

world_angles = get_initial_angles()
current_gripper_position_in_world = np.zeros(3)
current_gripper_position_in_arm, _ = get_gripper_coords_and_cam_rotation_from_arm(world_angles)
detected_boxes = []
latest_img = None
server_ip = None

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

def move_to_position(target_coords, is_in_world_frame = True):
    global current_gripper_position_in_world, current_gripper_position_in_arm, translation, system_angle, world_angles
    
    if(is_in_world_frame):
        current_gripper_position_in_world = np.array(target_coords)
        if(translation is not None):
            current_gripper_position_in_arm = transform_world_to_arm_coords(current_gripper_position_in_world, system_angle, translation)
    else:
        current_gripper_position_in_arm = np.array(target_coords)
        if(translation is not None):
            current_gripper_position_in_world = transform_arm_to_world_coords(current_gripper_position_in_arm, system_angle, translation)
    
    print("World angles before: ", world_angles)
    world_angles = get_move_angles(np.array(target_coords), translation, system_angle, world_angles, is_in_world_frame)
    print("World angles after: ", world_angles)
    servo_angles = world_to_servo_angles(world_angles)
    if ser and ser.is_open:
        command = f"P{':'.join(map(str, servo_angles))}\n"
        print(command)
        ser.write(command.encode())
        
def get_local_ip():
    global server_ip
    if server_ip is None:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            server_ip = s.getsockname()[0]
        finally:
            s.close()
            
    print("Server ip: ", server_ip)
    return server_ip

@app.route('/get_position', methods=['POST'])
def receive_image():
    global flag, current_gripper_position_in_world, current_gripper_position_in_arm, detected_boxes, translation, system_angle, latest_img
    
    if 'imageFile' not in request.files:
        print("FILES:", request.files)
        return jsonify({"error": "No file part"}), 400

    file = request.files['imageFile']
    file_bytes = file.read()
    print("Received:", len(file_bytes), "bytes")

    img = decode_image(file_bytes)
    cv2.imwrite(LATEST_IMAGE_PATH, img)
    
    _, camera_position, coordinate_systems_angle, R, rvec, tvec = get_camera_position(img, get_marker_positions(MARKER_SIZE, MARKER_SPACING), MARKER_SIZE)

    print("Coordinate systems angle: ", np.degrees(coordinate_systems_angle))
    current_gripper_position_in_world = conv_camera_coords_to_gripper_coords(camera_position, world_angles, coordinate_systems_angle)
    arm_angle = np.arctan2(current_gripper_position_in_arm[1], current_gripper_position_in_arm[0])
    print("Arm angle: ", np.degrees(arm_angle))
    system_angle = coordinate_systems_angle-arm_angle
    
    translation = get_translation(current_gripper_position_in_world, current_gripper_position_in_arm, system_angle)
    
    camera_matrix, dist_coeffs = get_camera_matrix_and_dist_coeffs()
    
    detected_boxes = get_box_coordinates(img, camera_position, R, camera_matrix, dist_coeffs, rvec, tvec)
    print(detected_boxes)
    latest_img = img
    flag = True
    
    return jsonify({"message": "OK"}), 200

def get_available_ports():
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

@app.route('/')
def index():
    get_local_ip()
    return render_template('index.html')

@app.route('/api/cam', methods=['GET'])
def get_image():
    print("here")
    print(get_local_ip())
    if ser and ser.is_open:
        command = f"take_photo:{get_local_ip()}\n"
        print(command)
        ser.write(command.encode())
    return jsonify({'success': True})


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

#Pooling
@app.route('/api/boxes', methods=['GET'])
def get_boxes():
    global detected_boxes
    return jsonify({'success': True, 'boxes': detected_boxes})

@app.route('/api/image', methods=['GET'])
def get_latest_image():
    global latest_img
    if latest_img:
        return jsonify({'success': True, 'image': latest_img})
    return jsonify({'success': False, 'image': None})


@app.route('/api/send_position', methods=['POST'])
def set_world_position():
    global current_gripper_position_in_world, current_gripper_position_in_arm, world_angles
    
    try:
        data = request.json
        coords = data.get('coordinates')
        is_in_world_frame = data.get('isWorldFrame')
        move_to_position(coords, is_in_world_frame)
        other_frame_coords = current_gripper_position_in_arm if is_in_world_frame else current_gripper_position_in_world
        servo_angles = [int(x) for x in world_to_servo_angles(world_angles)]
        return jsonify({'success': True, 'otherFrameCoords': other_frame_coords.tolist(), 'angles': servo_angles})
    except Exception as e:
        print(str(e))
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/grab_box', methods=['POST'])
def grab_box():
    try:
        data = request.json
        box_id = data.get('box_id')
        box = next((box for box in detected_boxes if box.id==box_id), None)
        move_to_position(box.grab_point)
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
    
@app.route('/api/connect', methods=['POST'])
def connect():
    global ser, current_port, current_gripper_position_in_arm
    
    try:
        data = request.json
        port = data.get('port')
        baudrate = 9600
        
        if ser and ser.is_open:
            ser.close()
        
        ser = serial.Serial(port, baudrate, timeout=1)
        current_port = port
        time.sleep(2)
        
        # ser.reset_input_buffer()
        # ser.reset_output_buffer()
        
        time.sleep(2)
        
        ser.write(b"activate\n")
        
        return jsonify({'success': True, 'message': f'Connected to {port}', 'armPosition': current_gripper_position_in_arm.tolist()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/disconnect', methods=['POST'])
def disconnect():
    global ser, current_port
    
    try:
        if ser and ser.is_open:
            ser.close()
        current_port = None
        
        return jsonify({'success': True, 'message': 'Disconnected'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/servo', methods=['POST'])
def control_servo():
    global ser, world_angles, current_gripper_position_in_arm, current_gripper_position_in_world
    
    try:
        if not ser or not ser.is_open:
            return jsonify({'success': False, 'error': 'Not connected to any port'})
        
        data = request.json
        servo_id = data.get('servo_id')
        angle = data.get('angle')
        
        # format: "S<id>:<angle>\n"
        command = f"S{servo_id}:{angle:03d}\n"
        ser.write(command.encode())
        
        if(servo_id < 5):
            servo_angles_pattern = np.zeros(5)
            servo_angles_pattern[servo_id] = angle
            angle_name, new_world_angle = servo_to_world_angle(servo_angles_pattern, servo_id)
            world_angles[angle_name] = new_world_angle
        
            current_gripper_position_in_arm, _ = get_gripper_coords_and_cam_rotation_from_arm(world_angles)
            print("Pos: ",current_gripper_position_in_arm)
            if(translation is not None):
                current_gripper_position_in_world = transform_arm_to_world_coords(current_gripper_position_in_arm, system_angle, translation)
        
        return jsonify({'success': True, 'worldCoords': current_gripper_position_in_world.tolist(),
                        'armCoords': current_gripper_position_in_arm.tolist()})
    except Exception as e:
        print(str(e))
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/serial_read', methods=['GET'])
def serial_read():
    global ser
    
    try:
        if not ser or not ser.is_open:
            return jsonify({'success': False, 'error': 'Not connected'})
        
        lines = []
        lines = []
        while ser.in_waiting > 0:
            try:
                line = ser.readline().decode('utf-8').strip()
                if line:
                    lines.append(line)
            except:
                pass
                        
        # # except Exception as e:
        # #     try:
        #         chars = []
        #         start_time = time.time()
        #         while time.time() - start_time < 0.1:
        #             if ser.in_waiting > 0:
        #                 char = ser.read(1).decode('utf-8', errors='ignore')
        #                 if char == '\n':
        #                     line = ''.join(chars).strip()
        #                     if line:
        #                         lines.append(line)
        #                         print(line)
        #                     chars = []
        #                 else:
        #                     chars.append(char)
        #             else:
        #                 time.sleep(0.01)
        # #     except:
        # #         pass
        
        return jsonify({'success': True, 'data': lines})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)