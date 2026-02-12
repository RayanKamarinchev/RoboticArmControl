let servos = []
let serialPollInterval = null;
let selectedBoxId = null;
let worldCoordDebounce = null;
let armCoordDebounce = null;
let worldPositionEnabled = false;

function addSerialLine(text) {
    const output = document.getElementById('serialOutput');
    const timestamp = new Date().toLocaleTimeString();
    const line = document.createElement('div');
    line.className = 'serial-line';
    line.innerHTML = `<span class="serial-timestamp">[${timestamp}]</span><span>${text}</span>`;
    output.appendChild(line);
    output.scrollTop = output.scrollHeight;
}

function clearSerialOutput() {
    const output = document.getElementById('serialOutput');
    output.innerHTML = '<div class="serial-line"><span class="serial-timestamp">[System]</span><span>Serial monitor cleared</span></div>';
}

function updateModeIndicator(mode) {
    const indicator = document.getElementById('modeIndicator');
    currentMode = mode;
    if (mode === 'http') {
        indicator.textContent = 'HTTP MODE';
        indicator.className = 'mode-indicator mode-http';
    } else {
        indicator.textContent = 'SERIAL MODE';
        indicator.className = 'mode-indicator mode-serial';
    }
}

function enableWorldPosition() {
    worldPositionEnabled = true;
    document.getElementById('worldPositionSection').classList.remove('disabled');
}

function updateArmPosition(position) {
    document.getElementById('armPosX').textContent = position.x.toFixed(1);
    document.getElementById('armPosY').textContent = position.y.toFixed(1);
    document.getElementById('armPosZ').textContent = position.z.toFixed(1);
}

function updateWorldPosition(position) {
    document.getElementById('worldPosX').textContent = position.x.toFixed(1);
    document.getElementById('worldPosY').textContent = position.y.toFixed(1);
    document.getElementById('worldPosZ').textContent = position.z.toFixed(1);
}

function updateImage(imageData) {
    const display = document.getElementById('imageDisplay');
    if (imageData) {
        display.innerHTML = `<img src="data:image/jpeg;base64,${imageData}" alt="Camera feed">`;
        enableWorldPosition();
    } else {
        display.innerHTML = '<div class="no-image">No image available</div>';
    }
}

function updateBoxesList(boxes) {
    const list = document.getElementById('boxesList');
    if (!boxes || boxes.length === 0) {
        list.innerHTML = '<div class="no-boxes">No objects detected</div>';
        return;
    }

    list.innerHTML = boxes.map(box => `
        <div class="box-item ${selectedBoxId === box.id ? 'selected' : ''}" onclick="selectBox('${box.id}')">
            <div class="box-header">
                <span class="box-id">Box ${box.id}</span>
                <button class="btn-grab" onclick="grabBox('${box.id}'); event.stopPropagation();">Grab</button>
            </div>
            <div class="box-details">
                <div>Position: (${box.x.toFixed(1)}, ${box.y.toFixed(1)}, ${box.z.toFixed(1)}) mm</div>
                <div>Size: ${box.width.toFixed(1)} × ${box.height.toFixed(1)} × ${box.depth.toFixed(1)} mm</div>
            </div>
        </div>
    `).join('');
}

function selectBox(boxId) {
    selectedBoxId = boxId;
    updateBoxesList(window.lastBoxes || []);
}

function grabBox(boxId) {
    fetch('/api/grab_box', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({box_id: boxId})
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showMessage(`Grabbing box ${boxId}...`, 'success');
            addSerialLine(`Command sent: Grab box ${boxId}`);
        } else {
            showMessage('Error: ' + data.error, 'error');
        }
    });
}

function updateArmCoord(axis, value) {
    document.getElementById(`armTarget${axis.toUpperCase()}`).textContent = value + ' mm';
    
    // Debounce for HTTP mode
    if (currentMode === 'http') {
        clearTimeout(armCoordDebounce);
        armCoordDebounce = setTimeout(() => {
            sendArmPosition();
        }, 2000);
    } else {
        sendArmPosition();
    }
}

function updateWorldCoord(axis, value) {
    document.getElementById(`worldTarget${axis.toUpperCase()}`).textContent = value + ' mm';
    
    if (currentMode === 'http') {
        clearTimeout(worldCoordDebounce);
        worldCoordDebounce = setTimeout(() => {
            sendWorldPosition();
        }, 2000);
    } else {
        sendWorldPosition();
    }
}

function sendArmPosition() {
    const x = parseInt(document.getElementById('armTargetX').textContent);
    const y = parseInt(document.getElementById('armTargetY').textContent);
    const z = parseInt(document.getElementById('armTargetZ').textContent);

    fetch('/api/world_position', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({x, y, z, frame: 'arm'})
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            addSerialLine(`Arm position set: (${x}, ${y}, ${z})`);
        }
    });
}

function sendWorldPosition() {
    const x = parseInt(document.getElementById('worldTargetX').textContent);
    const y = parseInt(document.getElementById('worldTargetY').textContent);
    const z = parseInt(document.getElementById('worldTargetZ').textContent);

    fetch('/api/world_position', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({x, y, z, frame: 'world'})
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            addSerialLine(`World position set: (${x}, ${y}, ${z})`);
        }
    });
}

function pollSerialData() {
    fetch('/api/serial_read')
        .then(res => res.json())
        .then(data => {
            if (data.success && data.data.length > 0) {
                data.data.forEach(line => addSerialLine(line));
            }
        });
}

function pollArmData() {
    fetch('/api/position')
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                updateArmPosition(data.position);
            }
        });

    fetch('/api/boxes')
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                window.lastBoxes = data.boxes;
                updateBoxesList(data.boxes);
            }
        });

    fetch('/api/image')
        .then(res => res.json())
        .then(data => {
            if (data.success && data.image) {
                updateImage(data.image);
            }
        });

    fetch('/api/mode')
        .then(res => res.json())
        .then(data => {
            updateModeIndicator(data.mode);
        });
}

function startSerialPolling() {
    if (serialPollInterval) {
        clearInterval(serialPollInterval);
    }
    serialPollInterval = setInterval(() => {
        pollSerialData();
        pollArmData();
    }, 100);
}

function stopSerialPolling() {
    if (serialPollInterval) {
        clearInterval(serialPollInterval);
        serialPollInterval = null;
    }
}

function showMessage(text, type) {
    const msg = document.getElementById('message');
    msg.textContent = text;
    msg.className = `message ${type} show`;
    setTimeout(() => msg.classList.remove('show'), 3000);
}

function updateStatus() {
    fetch('/api/status')
        .then(res => res.json())
        .then(data => {
            const status = document.getElementById('status');
            if (data.connected) {
                status.textContent = `Connected: ${data.port}`;
                status.className = 'status connected';
            } else {
                status.textContent = 'Disconnected';
                status.className = 'status disconnected';
            }
            updateModeIndicator(data.mode);
        });
}

function loadServos() {
    fetch('/api/servos')
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                servos = data.servos;
                createServoCards();
            }
        });
}

function createServoCards() {
    const grid = document.getElementById('servoGrid');
    grid.innerHTML = '';

    servos.forEach(servo => {
        const min = servo.min_angle
        const max = servo.max_angle

        const card = document.createElement('div');
        card.className = 'servo-card';
        card.innerHTML = `
            <div class="servo-header">
                <span class="servo-title">${servo.name}</span>
                <span class="servo-value" id="value${servo.id}">${servo.initial_angle}°</span>
            </div>
            <div class="slider-container">
                <input type="range" min="${min}" max="${max}" value="${servo.initial_angle}" 
                        oninput="updateServo(${servo.id}, this.value)">
                <div class="angle-labels">
                    <span>${min}°</span>
                    <span>${Math.floor((min + max) / 2)}°</span>
                    <span>${max}°</span>
                </div>
            </div>
        `;
        grid.appendChild(card);
    });
}

function refreshPorts() {
    fetch('/api/ports')
        .then(res => res.json())
        .then(data => {
            const select = document.getElementById('portSelect');
            select.innerHTML = '<option value="">Select Port...</option>';
            
            if (data.success) {
                data.ports.forEach(port => {
                    const option = document.createElement('option');
                    option.value = port;
                    option.textContent = port;
                    select.appendChild(option);
                });
                showMessage('Ports refreshed', 'success');
            } else {
                showMessage('Error: ' + data.error, 'error');
            }
        });
}

function connect() {
    const port = document.getElementById('portSelect').value;

    if (!port) {
        showMessage('Please select a port', 'error');
        return;
    }

    fetch('/api/connect', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({port})
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showMessage(data.message, 'success');
            addSerialLine('Connected to ' + port);
            addSerialLine('Sent: activate');
            updateStatus();
            startSerialPolling();
            loadServos();
        } else {
            showMessage('Error: ' + data.error, 'error');
            addSerialLine('Connection failed: ' + data.error);
        }
    });
}

function disconnect() {
    fetch('/api/disconnect', {method: 'POST'})
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                showMessage(data.message, 'success');
                addSerialLine('Disconnected');
                updateStatus();
                stopSerialPolling();
            } else {
                showMessage('Error: ' + data.error, 'error');
            }
        });
}

function updateServo(id, angle) {
    document.getElementById(`value${id}`).textContent = `${angle}°`;
    
    if (currentMode === 'serial') {
        sendServoCommand(id, angle);
    } else {
        clearTimeout(window[`servoDebounce${id}`]);
        window[`servoDebounce${id}`] = setTimeout(() => {
            sendServoCommand(id, angle);
        }, 2000);
    }
}

function sendServoCommand(id, angle) {
    fetch('/api/servo', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({servo_id: id, angle: parseInt(angle)})
    })
    .then(res => res.json())
    .then(data => {
        if (!data.success) {
            showMessage('Error: ' + data.error, 'error');
        }
    });
}

window.onload = function() {
    loadServos();
    refreshPorts();
    updateStatus();
    startSerialPolling();
    
    // Disable world position initially
    document.getElementById('worldPositionSection').classList.add('disabled');
};