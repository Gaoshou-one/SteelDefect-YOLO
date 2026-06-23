// static/js/main.js - 钢材缺陷检测系统前端脚本

// ==================== 全局变量 ====================
let currentImage = null;
let videoStream = null;
let isCameraMode = false;
let socket = null;
let animationId = null;
let videoElement = null;

const CLASS_NAME_MAP = {
    'crazing': '裂纹',
    'inclusion': '夹杂物',
    'patches': '斑块',
    'pitted_surface': '麻点',
    'rolled-in_scale': '氧化皮',
    'scratches': '划痕'
};

// ==================== 页面初始化 ====================
document.addEventListener('DOMContentLoaded', function() {
    console.log('页面加载完成，初始化...');

    // 初始化 WebSocket
    if (!socket) {
        socket = io();
        socket.on('connect', function() {
            console.log('WebSocket 连接成功');
        });

        socket.on('disconnect', function() {
            console.log('WebSocket 断开连接');
        });

        socket.on('detection_result', function(data) {
            console.log('收到检测结果, 缺陷数:', data.count);
            const canvas = document.getElementById('videoCanvas');
            if (canvas && data.image) {
                const ctx = canvas.getContext('2d');
                const img = new Image();
                img.onload = () => {
                    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                    // 显示canvas，隐藏视频
                    const liveVideo = document.getElementById('liveVideo');
                    if (liveVideo) liveVideo.style.display = 'none';
                    canvas.style.display = 'block';
                };
                img.src = data.image;
            }
            updateResults(data.detections, data.count);
        });
    }

    // 绑定置信度阈值滑块事件
    const confSlider = document.getElementById('confThreshold');
    if (confSlider) {
        confSlider.addEventListener('input', function() {
            const confValue = document.getElementById('confValue');
            if (confValue) confValue.innerText = this.value;
        });
    }

    // 绑定按钮事件
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    if (startBtn) startBtn.disabled = true;
    if (stopBtn) stopBtn.disabled = true;
});

// ==================== 摄像头控制函数 ====================

function startCamera() {
    console.log('开始启动摄像头...');

    // 关闭已有的流
    if (videoStream) {
        videoStream.getTracks().forEach(track => track.stop());
    }

    // 停止检测
    if (animationId) {
        clearTimeout(animationId);
        animationId = null;
    }

    showLoading('正在启动摄像头...');

    navigator.mediaDevices.getUserMedia({ video: true })
        .then(stream => {
            console.log('摄像头权限获取成功');
            videoStream = stream;

            // 创建视频元素
            videoElement = document.createElement('video');
            videoElement.id = 'liveVideo';
            videoElement.srcObject = stream;
            videoElement.autoplay = true;
            videoElement.playsInline = true;
            videoElement.style.width = '100%';
            videoElement.style.height = 'auto';
            videoElement.style.display = 'block';
            videoElement.style.borderRadius = '8px';

            // 获取容器并显示
            const displayContainer = document.querySelector('.display-container');
            if (!displayContainer) {
                console.error('找不到显示容器');
                hideLoading();
                showError('页面加载异常，请刷新重试');
                return;
            }

            // 隐藏其他元素
            const placeholder = document.getElementById('placeholder');
            const displayImage = document.getElementById('displayImage');
            const videoCanvas = document.getElementById('videoCanvas');

            if (placeholder) placeholder.style.display = 'none';
            if (displayImage) displayImage.style.display = 'none';
            if (videoCanvas) {
                videoCanvas.style.display = 'none';
                // 重置canvas内容
                const ctx = videoCanvas.getContext('2d');
                ctx.clearRect(0, 0, videoCanvas.width, videoCanvas.height);
            }

            // 移除旧的视频元素
            const oldVideo = document.getElementById('liveVideo');
            if (oldVideo) oldVideo.remove();

            // 添加新视频元素
            displayContainer.appendChild(videoElement);

            videoElement.onloadedmetadata = function() {
                console.log('视频尺寸:', videoElement.videoWidth, 'x', videoElement.videoHeight);

                // 设置canvas尺寸
                if (videoCanvas) {
                    videoCanvas.width = videoElement.videoWidth;
                    videoCanvas.height = videoElement.videoHeight;
                }

                isCameraMode = true;
                const startBtn = document.getElementById('startBtn');
                const stopBtn = document.getElementById('stopBtn');
                if (startBtn) {
                    startBtn.disabled = false;
                    startBtn.innerHTML = '<i class="bi bi-play-fill"></i> 开始检测';
                }
                if (stopBtn) stopBtn.disabled = true;

                hideLoading();
                showSuccess('摄像头已启动，点击"开始检测"进行缺陷识别');
            };

            videoElement.onerror = function(err) {
                console.error('视频错误:', err);
                hideLoading();
                showError('视频播放失败');
            };
        })
        .catch(err => {
            console.error('摄像头错误:', err.name, err.message);
            hideLoading();
            if (err.name === 'NotAllowedError') {
                showError('请允许摄像头访问权限后重试');
            } else if (err.name === 'NotFoundError') {
                showError('未检测到摄像头设备，请检查摄像头连接');
            } else if (err.name === 'NotReadableError') {
                showError('摄像头被其他应用占用，请关闭其他使用摄像头的程序');
            } else {
                showError('无法访问摄像头: ' + err.message);
            }
        });
}

function selectImage() {
    console.log('选择图片模式');

    // 停止检测
    if (animationId) {
        clearTimeout(animationId);
        animationId = null;
    }

    // 关闭摄像头
    if (videoStream) {
        videoStream.getTracks().forEach(track => track.stop());
        videoStream = null;
    }

    // 移除视频元素
    const liveVideo = document.getElementById('liveVideo');
    if (liveVideo) liveVideo.remove();

    isCameraMode = false;
    videoElement = null;

    // 重置按钮状态
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    if (startBtn) startBtn.disabled = true;
    if (stopBtn) stopBtn.disabled = true;

    // 显示文件选择器
    const imageInput = document.getElementById('imageInput');
    if (imageInput) imageInput.click();
}

function uploadImage() {
    const file = document.getElementById('imageInput').files[0];
    if (!file) return;

    // 检查文件类型
    if (!file.type.startsWith('image/')) {
        showError('请选择图片文件');
        return;
    }

    // 检查文件大小（限制10MB）
    if (file.size > 10 * 1024 * 1024) {
        showError('图片大小不能超过10MB');
        return;
    }

    showLoading('正在加载图片...');

    const reader = new FileReader();
    reader.onload = function(e) {
        currentImage = e.target.result;
        const img = document.getElementById('displayImage');
        const placeholder = document.getElementById('placeholder');
        const videoCanvas = document.getElementById('videoCanvas');
        const liveVideo = document.getElementById('liveVideo');

        if (img) {
            img.src = currentImage;
            img.style.display = 'block';
        }
        if (placeholder) placeholder.style.display = 'none';
        if (videoCanvas) videoCanvas.style.display = 'none';
        if (liveVideo) liveVideo.style.display = 'none';

        const startBtn = document.getElementById('startBtn');
        if (startBtn) {
            startBtn.disabled = false;
            startBtn.innerHTML = '<i class="bi bi-play-fill"></i> 开始检测';
        }

        hideLoading();
        showSuccess('图片加载成功，点击"开始检测"进行缺陷识别');
    };

    reader.onerror = function() {
        hideLoading();
        showError('图片加载失败，请重试');
    };

    reader.readAsDataURL(file);
}

// ==================== 检测控制函数 ====================

function startDetection() {
    if (isCameraMode) {
        startCameraDetection();
    } else if (currentImage) {
        uploadForDetection();
    } else {
        showError('请先上传图片或开启摄像头');
    }
}

function uploadForDetection() {
    const file = document.getElementById('imageInput').files[0];
    if (!file) {
        showError('请先选择图片');
        return;
    }

    showLoading('正在进行缺陷检测...');

    const formData = new FormData();
    formData.append('image', file);
    const confThreshold = document.getElementById('confThreshold');
    formData.append('conf_threshold', confThreshold ? confThreshold.value : 0.25);

    fetch('/detect/image', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            const displayImage = document.getElementById('displayImage');
            if (displayImage) displayImage.src = data.result_image;
            updateResults(data.detections, data.count);

            if (data.count > 0) {
                showSuccess(`检测到 ${data.count} 个缺陷`);
            } else {
                showInfo('未检测到缺陷，钢材表面状况良好');
            }
        } else {
            showError('检测失败: ' + (data.error || '未知错误'));
        }
    })
    .catch(err => {
        hideLoading();
        console.error('检测请求失败:', err);
        showError('请求失败: ' + err.message);
    });
}

function startCameraDetection() {
    if (!videoElement || !videoElement.videoWidth) {
        showError('摄像头未就绪，请重新开启摄像头');
        return;
    }

    // 停止之前的检测
    if (animationId) {
        clearTimeout(animationId);
        animationId = null;
    }

    // 显示原始视频，隐藏canvas
    const videoCanvas = document.getElementById('videoCanvas');
    const liveVideo = document.getElementById('liveVideo');

    if (liveVideo) liveVideo.style.display = 'block';
    if (videoCanvas) {
        videoCanvas.style.display = 'none';
        // 清空canvas
        const ctx = videoCanvas.getContext('2d');
        ctx.clearRect(0, 0, videoCanvas.width, videoCanvas.height);
    }

    console.log('开始摄像头检测');

    // 更新按钮状态
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    if (startBtn) {
        startBtn.disabled = true;
        startBtn.innerHTML = '<i class="bi bi-play-fill"></i> 检测中...';
    }
    if (stopBtn) stopBtn.disabled = false;

    showInfo('检测运行中，点击"停止检测"结束');

    function sendFrame() {
        if (!isCameraMode || !videoElement || videoElement.paused || !videoElement.videoWidth) {
            return;
        }

        try {
            const canvas = document.createElement('canvas');
            canvas.width = videoElement.videoWidth;
            canvas.height = videoElement.videoHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
            const frameData = canvas.toDataURL('image/jpeg', 0.7);

            if (socket && socket.connected) {
                const confThreshold = document.getElementById('confThreshold');
                socket.emit('video_frame', {
                    image: frameData,
                    conf_threshold: confThreshold ? confThreshold.value : 0.25
                });
            }
        } catch (err) {
            console.error('发送帧错误:', err);
        }

        animationId = setTimeout(sendFrame, 100); // 10 FPS
    }

    sendFrame();
}

function stopDetection() {
    if (animationId) {
        clearTimeout(animationId);
        animationId = null;
    }

    // 恢复显示原始视频
    const liveVideo = document.getElementById('liveVideo');
    const videoCanvas = document.getElementById('videoCanvas');

    if (liveVideo && videoCanvas) {
        liveVideo.style.display = 'block';
        videoCanvas.style.display = 'none';
    }

    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    if (startBtn) {
        startBtn.disabled = false;
        startBtn.innerHTML = '<i class="bi bi-play-fill"></i> 开始检测';
    }
    if (stopBtn) stopBtn.disabled = true;

    console.log('停止检测');
    showInfo('检测已停止');
}

// ==================== 结果更新函数 ====================

function updateResults(detections, count) {
    const resultCount = document.getElementById('resultCount');
    if (resultCount) {
        resultCount.innerHTML = count;
        resultCount.style.color = count > 0 ? '#ef4444' : '#10b981';
    }

    const resultDetails = document.getElementById('resultDetails');
    if (resultDetails) {
        if (detections && detections.length > 0) {
            let html = '';
            detections.forEach(d => {
                let defectName = d.chinese_name || CLASS_NAME_MAP[d.class_name] || d.class_name || '缺陷';
                let confidence = (d.confidence * 100).toFixed(1);
                let confidenceClass = confidence > 70 ? 'badge-high' : (confidence > 50 ? 'badge-medium' : 'badge-low');

                html += `
                    <div class="detection-item">
                        <div class="detection-name">
                            <i class="bi bi-bug"></i>
                            <span>${escapeHtml(defectName)}</span>
                        </div>
                        <span class="detection-badge ${confidenceClass}">${confidence}%</span>
                    </div>
                `;
            });
            resultDetails.innerHTML = html;
        } else {
            resultDetails.innerHTML = `
                <div class="text-center text-muted py-4">
                    <i class="bi bi-check-circle" style="font-size: 2rem;"></i>
                    <p class="mt-2 small">未检测到缺陷</p>
                </div>
            `;
        }
    }
}

// HTML转义函数，防止XSS攻击
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ==================== 提示函数 ====================

function showLoading(message) {
    Swal.fire({
        title: message,
        allowOutsideClick: false,
        didOpen: () => {
            Swal.showLoading();
        }
    });
}

function hideLoading() {
    Swal.close();
}

function showSuccess(message) {
    Swal.fire({
        icon: 'success',
        title: '成功',
        text: message,
        timer: 2000,
        showConfirmButton: false,
        background: '#fff',
        backdrop: true
    });
}

function showError(message) {
    Swal.fire({
        icon: 'error',
        title: '错误',
        text: message,
        confirmButtonColor: '#6366f1',
        confirmButtonText: '确定'
    });
}

function showInfo(message) {
    Swal.fire({
        icon: 'info',
        title: '提示',
        text: message,
        timer: 1500,
        showConfirmButton: false,
        background: '#fff'
    });
}

// ==================== 页面导航函数 ====================

function loadHistory() {
    showLoading('加载历史记录...');
    fetch('/history')
        .then(response => response.json())
        .then(data => {
            hideLoading();
            showHistoryPage(data.records);
        })
        .catch(err => {
            hideLoading();
            showError('加载失败: ' + err.message);
        });
}

function loadStats() {
    showLoading('加载统计数据...');
    fetch('/stats')
        .then(response => response.json())
        .then(data => {
            hideLoading();
            showStatsPage(data);
        })
        .catch(err => {
            hideLoading();
            showError('加载失败: ' + err.message);
        });
}

function loadUsers() {
    Swal.fire('提示', '用户管理功能开发中', 'info');
}

function showHistoryPage(records) {
    let html = `
        <div class="card fade-in-up">
            <div class="card-header">
                <i class="bi bi-clock-history"></i> 检测历史
            </div>
            <div class="card-body p-0">
                <div class="table-container">
                    <div class="table-responsive">
                        <table class="table table-hover mb-0">
                            <thead>
                                <tr>
                                    <th>时间</th>
                                    <th>来源</th>
                                    <th>缺陷数</th>
                                    <th>操作</th>
                                </tr>
                            </thead>
                            <tbody>
    `;

    if (!records || records.length === 0) {
        html += '<tr><td colspan="4" class="text-center text-muted py-4">暂无检测记录</td></tr>';
    } else {
        records.forEach(r => {
            html += `
                <tr>
                    <td><i class="bi bi-calendar3"></i> ${escapeHtml(r.created_at || '--')}</td>
                    <td><span class="badge bg-secondary">${escapeHtml(r.source_type || '--')}</span></td>
                    <td><span class="badge bg-danger">${r.total_detections || 0}</span></td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" onclick="viewDetail(${r.id})">
                            <i class="bi bi-eye"></i> 详情
                        </button>
                    </td>
                </tr>
            `;
        });
    }

    html += `
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    `;

    const mainContent = document.querySelector('.main-content');
    if (mainContent) mainContent.innerHTML = html;
}

function showStatsPage(stats) {
    let html = `
        <div class="row g-4 mb-4 fade-in-up">
            <div class="col-md-3">
                <div class="stat-card">
                    <div class="icon"><i class="bi bi-bar-chart"></i></div>
                    <div class="value">${stats.total_detections || 0}</div>
                    <div class="label">总检测次数</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card">
                    <div class="icon"><i class="bi bi-target"></i></div>
                    <div class="value">${stats.total_objects || 0}</div>
                    <div class="label">总检测目标</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card">
                    <div class="icon"><i class="bi bi-calendar-day"></i></div>
                    <div class="value">${stats.today_detections || 0}</div>
                    <div class="label">今日检测</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card">
                    <div class="icon"><i class="bi bi-people"></i></div>
                    <div class="value">${stats.total_users || 0}</div>
                    <div class="label">系统用户</div>
                </div>
            </div>
        </div>
        <div class="card fade-in-up">
            <div class="card-header">
                <i class="bi bi-graph-up"></i> 检测趋势
            </div>
            <div class="card-body">
                <canvas id="trendChart" height="300"></canvas>
            </div>
        </div>
    `;

    const mainContent = document.querySelector('.main-content');
    if (mainContent) mainContent.innerHTML = html;

    // 绘制图表
    const ctx = document.getElementById('trendChart');
    if (ctx && stats.trend_dates && stats.trend_counts) {
        new Chart(ctx.getContext('2d'), {
            type: 'line',
            data: {
                labels: stats.trend_dates,
                datasets: [{
                    label: '检测数量',
                    data: stats.trend_counts,
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99, 102, 241, 0.1)',
                    borderWidth: 2,
                    tension: 0.3,
                    fill: true,
                    pointBackgroundColor: '#6366f1',
                    pointBorderColor: '#fff',
                    pointRadius: 4,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        position: 'top',
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0,0,0,0.8)'
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });
    }
}

function viewDetail(id) {
    showLoading('加载详情...');
    fetch(`/history/detail/${id}`)
        .then(response => response.json())
        .then(data => {
            hideLoading();
            Swal.fire({
                title: '检测详情',
                html: `
                    <div class="text-start">
                        <p><strong><i class="bi bi-calendar3"></i> 时间:</strong> ${escapeHtml(data.record.created_at || '--')}</p>
                        <p><strong><i class="bi bi-tag"></i> 来源:</strong> ${escapeHtml(data.record.source_type || '--')}</p>
                        <p><strong><i class="bi bi-bug"></i> 缺陷数:</strong> ${data.record.total_detections || 0}</p>
                        <p><strong><i class="bi bi-sliders2"></i> 置信度阈值:</strong> ${data.record.confidence_threshold || 0.25}</p>
                        ${data.image ? `<img src="${data.image}" class="img-fluid mt-3 rounded" style="max-height: 300px;">` : ''}
                    </div>
                `,
                width: '600px',
                confirmButtonText: '关闭',
                confirmButtonColor: '#6366f1'
            });
        })
        .catch(err => {
            hideLoading();
            showError('加载失败: ' + err.message);
        });
}