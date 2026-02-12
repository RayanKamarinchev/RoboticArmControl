from flask import Flask, render_template, request, jsonify
import serial
import serial.tools.list_ports
import time

app = Flask(__name__)

ser = None
current_port = None

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
def get_limits():
    return jsonify({'success': True, 'servos': [s.to_dict() for s in servos]})

@app.route('/api/connect', methods=['POST'])
def connect():
    global ser, current_port
    
    try:
        data = request.json
        port = data.get('port')
        baudrate = 9600
        
        if ser and ser.is_open:
            ser.close()
        
        ser = serial.Serial(port, baudrate, timeout=1)
        current_port = port
        time.sleep(2)
        
        ser.write(b"activate\n")
        
        return jsonify({'success': True, 'message': f'Connected to {port}'})
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
    global ser
    
    try:
        if not ser or not ser.is_open:
            return jsonify({'success': False, 'error': 'Not connected to any port'})
        
        data = request.json
        servo_id = data.get('servo_id')
        angle = data.get('angle')
        
        # format: "S<id>:<angle>\n"
        # S0:090 = Servo 0, angle 90
        command = f"S{servo_id}:{angle:03d}\n"
        ser.write(command.encode())
        
        return jsonify({'success': True, 'message': f'Servo {servo_id} set to {angle}°'})
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
    global ser
    
    try:
        if not ser or not ser.is_open:
            return jsonify({'success': False, 'error': 'Not connected'})
        
        lines = []
        while ser.in_waiting > 0:
            try:
                line = ser.readline().decode('utf-8').strip()
                print(line)
                if line:
                    lines.append(line)
            except:
                pass
        
        return jsonify({'success': True, 'data': lines})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)