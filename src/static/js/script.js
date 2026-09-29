// NOTE: legacy live-stream demo script. Not referenced by any template.
// Kept hardened (null-guards) so it can't throw if ever included.
window.addEventListener('load', () => {
  const video = document.getElementById('camera');
  const output = document.getElementById('output');
  if (!video || !output) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    output.innerText = 'Camera not supported in this browser';
    return;
  }

  const fields = ['id', 'name', 'program', 'branch', 'gmail', 'total', 'last', 'welcome', 'attendance-time'];
  const elements = {};
  fields.forEach(f => { elements[f] = document.getElementById(f); });

  const faceSnapshot = document.getElementById('face-snapshot');
  let inFlight = false;
  let timer = null;

  navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } })
    .then(stream => {
      video.srcObject = stream;
      timer = setInterval(() => captureAndSendFrame(video), 3000);
      window.addEventListener('beforeunload', () => {
        if (timer) clearInterval(timer);
        try { stream.getTracks().forEach(t => t.stop()); } catch (_) {}
      });
    })
    .catch(err => {
      console.error('Camera error:', err);
      output.innerText = 'Failed to access camera';
    });

  function setText(el, v) { if (el) el.innerText = v ?? ''; }

  function captureAndSendFrame(videoEl) {
    if (inFlight) return;
    if (!videoEl.videoWidth || !videoEl.videoHeight || videoEl.readyState < 2) return;
    inFlight = true;
    const canvas = document.createElement('canvas');
    canvas.width = videoEl.videoWidth;
    canvas.height = videoEl.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(videoEl, 0, 0);

    const dataURL = canvas.toDataURL('image/jpeg');

    fetch('/process_frame', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: dataURL })
    })
      .then(res => {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(data => {
        if (data.name) {
          output.innerText = data.message || 'Matched';

          setText(elements['id'], data.id);
          setText(elements['name'], data.name);
          setText(elements['program'], data.program);
          setText(elements['branch'], data.branch);
          setText(elements['gmail'], data.gmail);
          setText(elements['total'], data.total);
          setText(elements['last'], data.last);
          setText(elements['welcome'], `Welcome, ${data.name}`);
          setText(elements['attendance-time'], `Attendance marked at ${data.last}`);

          if (faceSnapshot && data.face_image) {
            faceSnapshot.src = `data:image/jpeg;base64,${data.face_image}`;
          }
        } else {
          output.innerText = data.message || 'Unknown face';
        }
      })
      .catch(err => {
        console.error('Error:', err);
        output.innerText = 'Error sending image';
      })
      .finally(() => { inFlight = false; });
  }
});
