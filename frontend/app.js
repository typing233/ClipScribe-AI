const uploadArea = document.getElementById('upload-area');
const fileInput = document.getElementById('file-input');
const fileInfo = document.getElementById('file-info');
const fileName = document.getElementById('file-name');
const fileSize = document.getElementById('file-size');
const clearFile = document.getElementById('clear-file');
const generateBtn = document.getElementById('generate-btn');
const progressSection = document.getElementById('progress-section');
const progressFill = document.getElementById('progress-fill');
const progressText = document.getElementById('progress-text');
const resultSection = document.getElementById('result-section');
const resultVideo = document.getElementById('result-video');
const downloadBtn = document.getElementById('download-btn');
const scriptContent = document.getElementById('script-content');
const errorSection = document.getElementById('error-section');
const errorText = document.getElementById('error-text');
const retryBtn = document.getElementById('retry-btn');

let uploadedFilename = null;
let currentTaskId = null;
let pollInterval = null;

// Upload handling
uploadArea.addEventListener('click', () => fileInput.click());
uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
});
uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('dragover');
});
uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
        handleFile(e.dataTransfer.files[0]);
    }
});
fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
        handleFile(fileInput.files[0]);
    }
});

clearFile.addEventListener('click', () => {
    uploadedFilename = null;
    fileInfo.hidden = true;
    uploadArea.hidden = false;
    generateBtn.disabled = true;
    fileInput.value = '';
});

async function handleFile(file) {
    if (!file.type.startsWith('video/') && !file.name.match(/\.(mp4|mkv|avi|mov|flv|wmv|webm)$/i)) {
        alert('请选择视频文件');
        return;
    }

    uploadArea.hidden = true;
    fileInfo.hidden = false;
    fileName.textContent = file.name;
    fileSize.textContent = formatSize(file.size);
    generateBtn.disabled = true;
    generateBtn.textContent = '上传中...';

    try {
        const formData = new FormData();
        formData.append('file', file);

        const res = await fetch('/api/upload', { method: 'POST', body: formData });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '上传失败');
        }

        const data = await res.json();
        uploadedFilename = data.filename;
        generateBtn.disabled = false;
        generateBtn.textContent = '开始生成解说视频';
    } catch (e) {
        showError(e.message);
        clearFile.click();
    }
}

// Generate
generateBtn.addEventListener('click', startGeneration);

async function startGeneration() {
    if (!uploadedFilename) return;

    const style = document.querySelector('input[name="style"]:checked').value;

    generateBtn.disabled = true;
    errorSection.hidden = true;
    resultSection.hidden = true;
    progressSection.hidden = false;
    resetSteps();

    try {
        const res = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ video_filename: uploadedFilename, style }),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '启动失败');
        }

        const data = await res.json();
        currentTaskId = data.task_id;
        startPolling();
    } catch (e) {
        showError(e.message);
    }
}

function startPolling() {
    pollInterval = setInterval(async () => {
        try {
            const res = await fetch(`/api/status/${currentTaskId}`);
            const task = await res.json();

            progressFill.style.width = task.progress + '%';
            progressText.textContent = task.message;
            updateSteps(task.status);

            if (task.status === 'completed') {
                clearInterval(pollInterval);
                showResult(task);
            } else if (task.status === 'failed') {
                clearInterval(pollInterval);
                showError(task.error || '生成失败');
            }
        } catch (e) {
            // ignore poll errors
        }
    }, 1500);
}

function updateSteps(status) {
    const order = ['analyzing', 'generating_script', 'synthesizing_voice', 'composing_video'];
    const currentIdx = order.indexOf(status);

    order.forEach((step, idx) => {
        const el = document.getElementById(`step-${step}`);
        if (!el) return;
        el.classList.remove('active', 'done');
        if (idx < currentIdx) el.classList.add('done');
        else if (idx === currentIdx) el.classList.add('active');
    });
}

function resetSteps() {
    document.querySelectorAll('.step').forEach(el => {
        el.classList.remove('active', 'done');
    });
    progressFill.style.width = '0%';
}

function showResult(task) {
    progressSection.hidden = true;
    resultSection.hidden = false;

    resultVideo.src = `/api/download/${task.task_id}`;
    downloadBtn.onclick = () => {
        const a = document.createElement('a');
        a.href = `/api/download/${task.task_id}`;
        a.download = `clipscribe_${task.task_id}.mp4`;
        a.click();
    };

    if (task.script) {
        scriptContent.innerHTML = task.script.map(seg =>
            `<div class="script-segment">
                <span class="script-time">[${formatTime(seg.start_time)} - ${formatTime(seg.end_time)}]</span>
                ${seg.text}
            </div>`
        ).join('');
    }

    generateBtn.disabled = false;
    generateBtn.textContent = '重新生成';
}

function showError(msg) {
    progressSection.hidden = true;
    errorSection.hidden = false;
    errorText.textContent = msg;
    generateBtn.disabled = false;
    generateBtn.textContent = '开始生成解说视频';
}

retryBtn.addEventListener('click', () => {
    errorSection.hidden = true;
    startGeneration();
});

function formatSize(bytes) {
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
}
