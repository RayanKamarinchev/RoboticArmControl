let servos = []
let serialPollInterval = null;

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

function pollSerialData() {
    fetch('/api/serial_read')
        .then(res => res.json())
        .then(data => {
            if (data.success && data.data.length > 0) {
                data.data.forEach(line => addSerialLine(line));
            }
        })
        .catch(err => console.error('Serial read error:', err));
}

function startSerialPolling() {
    if (serialPollInterval) {
        clearInterval(serialPollInterval);
    }
    serialPollInterval = setInterval(pollSerialData, 100);
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
    refreshPorts();
    updateStatus();
};