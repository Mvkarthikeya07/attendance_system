// ===============================
// LIVE FACE ATTENDANCE SYSTEM JS
// ===============================

const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const overlay = document.getElementById("overlay");
const statusDiv = document.getElementById("status");

const ctx = canvas.getContext("2d");
const overlayCtx = overlay.getContext("2d");

let isProcessing = false;
let streamStarted = false;


// ===============================
// INITIALIZE CAMERA
// ===============================
async function startCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: {
                facingMode: "user"
            },
            audio: false
        });

        video.srcObject = stream;
        streamStarted = true;

        statusDiv.innerText = "Camera Ready ✅";

    } catch (error) {
        console.error("Camera Error:", error);
        statusDiv.innerText = "Camera Access Denied ❌";
    }
}


// ===============================
// CAPTURE FRAME AND SEND TO API
// ===============================
async function captureAndSend() {
    if (!streamStarted) return;
    if (isProcessing) return;

    if (!video.videoWidth) return;

    isProcessing = true;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    overlay.width = video.videoWidth;
    overlay.height = video.videoHeight;

    ctx.drawImage(video, 0, 0);

    const imageData = canvas.toDataURL("image/jpeg", 0.7);

    try {
        const response = await fetch("/api/recognize", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image: imageData })
        });

        const data = await response.json();

        drawResults(data);

    } catch (error) {
        console.error("Server error:", error);
        statusDiv.innerText = "Server Error ❌";
    }

    isProcessing = false;
}


// ===============================
// DRAW BOUNDING BOXES + NAMES
// ===============================
function drawResults(data) {

    overlayCtx.clearRect(0, 0, overlay.width, overlay.height);

    if (!data || data.length === 0) {
        statusDiv.innerText = "No face detected";
        return;
    }

    let detectedNames = [];

    data.forEach(person => {

        const [x1, y1, x2, y2] = person.box;
        const name = person.name;

        detectedNames.push(name);

        // Box color
        overlayCtx.strokeStyle = name === "Unknown" ? "red" : "lime";
        overlayCtx.lineWidth = 3;
        overlayCtx.strokeRect(x1, y1, x2 - x1, y2 - y1);

        // Name label
        overlayCtx.fillStyle = "rgba(0,0,0,0.6)";
        overlayCtx.fillRect(x1, y1 - 30, 150, 30);

        overlayCtx.fillStyle = "white";
        overlayCtx.font = "16px Arial";
        overlayCtx.fillText(name, x1 + 5, y1 - 10);
    });

    statusDiv.innerText = "Detected: " + detectedNames.join(", ");
}


// ===============================
// END ATTENDANCE
// ===============================
async function endAttendance() {
    try {
        await fetch("/end_attendance");
        statusDiv.innerText = "Attendance Ended 🛑";
    } catch (error) {
        console.error(error);
    }
}


// ===============================
// AUTO START
// ===============================
startCamera();

// Capture every 1.5 seconds
setInterval(captureAndSend, 1500);
