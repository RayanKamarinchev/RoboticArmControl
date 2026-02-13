let servos = []
let serialPollInterval = null;
let selectedBoxId = null;
let worldCoordDebounce = null;
let armCoordDebounce = null;
let elementsEnabled = false;
let isWaitingPhoto = false;

function convertCoordsMetric(coords, from_server){
    if (from_server) {
        return coords.map(x=>Math.round(x*1000))
    }
    return coords.map(x=>x/1000)
}

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

function enableElements() {
    elementsEnabled = true;
    document.getElementById('armPositionSection').classList.remove('disabled');
    document.getElementById('servoGrid').classList.remove('disabled');
}

function enableWorldPosition(){
    document.getElementById('worldPositionSection').classList.remove('disabled');
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
    document.getElementById(`armPos${axis.toUpperCase()}`).textContent = value;
    
    clearTimeout(armCoordDebounce);
    armCoordDebounce = setTimeout(() => {
        sendArmPosition();
    }, 1000);
}

function updateWorldCoord(axis, value) {
    document.getElementById(`worldPos${axis.toUpperCase()}`).textContent = value;
    
    clearTimeout(worldCoordDebounce);
    worldCoordDebounce = setTimeout(() => {
        sendWorldPosition();
    }, 1000);
}

function setPosition(coords, is_world_frame){
    coords = convertCoordsMetric(coords, true);
    const axisOrder = ['X', 'Y', 'Z'];
    const frame = is_world_frame ? 'world' : 'arm';
    for (let i = 0; i < 3; i++) {
        document.getElementById(`${frame}Pos${axisOrder[i]}`).textContent = coords[i];
        document.getElementById(`${frame}PosValue${axisOrder[i]}`).value = coords[i];
    }
}


function sendArmPosition() {
    const x = parseInt(document.getElementById('armPosX').textContent);
    const y = parseInt(document.getElementById('armPosY').textContent);
    const z = parseInt(document.getElementById('armPosZ').textContent);

    const coords = convertCoordsMetric([x,y,z], false);

    fetch('/api/send_position', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({coordinates: coords, isWorldFrame: false})
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            console.log(data.otherFrameCoords)
            console.log(data.angles)
            setPosition(data.otherFrameCoords, true)
            setServoAngles(data.angles)
            addSerialLine(`Arm position set: (${x}, ${y}, ${z})`);
        }
    });
}

function sendWorldPosition() {
    const x = parseInt(document.getElementById('worldPosX').textContent);
    const y = parseInt(document.getElementById('worldPosY').textContent);
    const z = parseInt(document.getElementById('worldPosZ').textContent);

    const coords = convertCoordsMetric([x,y,z], false);

    fetch('/api/send_position', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({coordinates: coords, isWorldFrame: true})
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            setPosition(data.otherFrameCoords, false)
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
    if (isWaitingPhoto) {
        fetch('/api/boxes')
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    isWaitingPhoto = false;
                    window.lastBoxes = data.boxes;
                    updateBoxesList(data.boxes);
                }
            });

        fetch('/api/image')
            .then(res => res.json())
            .then(data => {
                if (data.success && data.image) {
                    isWaitingPhoto = false;
                    updateImage(data.image);
                }
            });
    }
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
        });
}

function setServoAngles(angles){
    for (let i = 0; i < angles.length; i++) {
        const valueSlider = document.getElementById(`servoId${i}`);
        if(valueSlider){
            valueSlider.value = angles[i];
            document.getElementById(`value${i}`).textContent = angles[i];
        }
    }
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
                <input id="servoId${servo.id}" type="range" min="${min}" max="${max}" value="${servo.initial_angle}" 
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

function takePhoto(){
    isWaitingPhoto = true;
    fetch('/api/cam');
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
            enableElements();
            setPosition(data.armPosition, false);
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
    
    sendServoCommand(id, angle);
    //  else {
    //     clearTimeout(window[`servoDebounce${id}`]);
    //     window[`servoDebounce${id}`] = setTimeout(() => {
    //         sendServoCommand(id, angle);
    //     }, 2000);
    // }
}

function sendServoCommand(id, angle) {
    fetch('/api/servo', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({servo_id: id, angle: parseInt(angle)})
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            setPosition(data.worldCoords, true);
            setPosition(data.armCoords, false);
        } else {
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
    document.getElementById('armPositionSection').classList.add('disabled');
    document.getElementById('servoGrid').classList.add('disabled');
};