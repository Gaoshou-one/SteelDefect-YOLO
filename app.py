# app.py
import os
import sys
from pathlib import Path
from datetime import datetime
import json
import base64
import cv2
import numpy as np

# 🔴 设置环境变量避免 OpenMP 错误
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
from functools import wraps

sys.path.insert(0, str(Path(__file__).parent))

from core.detector import DefectDetector
from database.db_manager import DatabaseManager

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'
app.config['UPLOAD_FOLDER'] = Path(__file__).parent / 'static' / 'uploads'
app.config['UPLOAD_FOLDER'].mkdir(parents=True, exist_ok=True)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制上传文件大小为16MB

# 🔴 初始化 SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=60, ping_interval=25)

db = DatabaseManager()
detector = DefectDetector()

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'gif'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated


# ==================== WebSocket 事件 ====================

@socketio.on('connect')
def handle_connect():
    print('✅ 客户端已连接')
    emit('connected', {'message': 'WebSocket连接成功'})


@socketio.on('disconnect')
def handle_disconnect():
    print('❌ 客户端断开连接')


@socketio.on('video_frame')
def handle_video_frame(data):
    """处理视频帧检测"""
    try:
        # 解析 base64 图片
        image_data = data['image'].split(',')[1]
        image_bytes = base64.b64decode(image_data)
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            print("⚠️ 帧解码失败")
            return

        # 执行检测
        conf_threshold = float(data.get('conf_threshold', 0.25))
        result_frame, detections = detector.detect_video_frame(frame, conf_threshold)

        # 编码结果图片
        _, buffer = cv2.imencode('.jpg', result_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        result_base64 = base64.b64encode(buffer).decode('utf-8')

        # 发送结果
        emit('detection_result', {
            'image': f"data:image/jpeg;base64,{result_base64}",
            'detections': detections,
            'count': len(detections)
        })

    except Exception as e:
        print(f"❌ 视频帧处理错误: {e}")
        import traceback
        traceback.print_exc()


# ==================== 页面路由 ====================

@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            return render_template('login.html', error='请填写用户名和密码')

        user = db.authenticate_user(username, password)
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['real_name'] = user.get('real_name', '')

            # 更新最后登录时间
            db.update_last_login(user['id'])

            return redirect(url_for('dashboard'))
        return render_template('login.html', error='用户名或密码错误')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            return render_template('register.html', error='用户名和密码不能为空')

        if len(password) < 6:
            return render_template('register.html', error='密码长度至少6位')

        if db.create_user(
                username=username,
                password=password,
                role='operator',
                real_name=request.form.get('real_name', ''),
                department=request.form.get('department', ''),
                email=request.form.get('email', ''),
                phone=request.form.get('phone', '')
        ):
            return redirect(url_for('login'))
        return render_template('register.html', error='用户名已存在')
    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('index.html',
                           username=session.get('username'),
                           role=session.get('role'))


@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html',
                           username=session.get('username'),
                           role=session.get('role'),
                           real_name=session.get('real_name', ''))


# ==================== API 路由 ====================

@app.route('/detect/image', methods=['POST'])
@login_required
def detect_image():
    try:
        file = request.files['image']
        if not file or not allowed_file(file.filename):
            return jsonify({'error': '无效文件，请上传图片格式(jpg, png, bmp)'}), 400

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = secure_filename(file.filename)
        filepath = app.config['UPLOAD_FOLDER'] / f"{timestamp}_{filename}"
        file.save(str(filepath))

        conf_threshold = float(request.form.get('conf_threshold', 0.25))
        result = detector.detect_image(str(filepath), conf_threshold=conf_threshold)

        result_path = app.config['UPLOAD_FOLDER'] / f"result_{timestamp}.jpg"
        cv2.imwrite(str(result_path), result['image'])

        from database.models import DetectionRecord
        record = DetectionRecord(
            user_id=session['user_id'],
            username=session['username'],
            image_path=str(filepath),
            result_image_path=str(result_path),
            source_type='image',
            total_detections=result['count'],
            detections_json=json.dumps(result['detections'], ensure_ascii=False),
            inference_time=result['time'],
            confidence_threshold=conf_threshold
        )
        db.save_detection_record(record)

        with open(result_path, 'rb') as f:
            result_base64 = base64.b64encode(f.read()).decode('utf-8')

        return jsonify({
            'success': True,
            'detections': result['detections'],
            'count': result['count'],
            'result_image': f"data:image/jpeg;base64,{result_base64}"
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/history')
@login_required
def get_history():
    try:
        user_id = session['user_id'] if session['role'] != 'admin' else None
        records = db.get_detection_history(user_id=user_id, limit=100)
        return jsonify({'records': [{
            'id': r['id'],
            'created_at': str(r['created_at'])[:19] if r['created_at'] else '',
            'source_type': r['source_type'],
            'total_detections': r['total_detections']
        } for r in records]})
    except Exception as e:
        print(f"获取历史记录错误: {e}")
        return jsonify({'records': []})


@app.route('/stats')
@login_required
def get_stats():
    try:
        stats = db.get_statistics()
        records = db.get_detection_history(limit=100)
        daily = {}
        for r in records:
            if r['created_at']:
                date = str(r['created_at'])[:10]
                daily[date] = daily.get(date, 0) + r['total_detections']
        dates = sorted(daily.keys())[-7:] if daily else []
        return jsonify({
            'total_detections': stats.get('total_detections', 0),
            'total_objects': stats.get('total_objects', 0),
            'today_detections': stats.get('today_detections', 0),
            'total_users': stats.get('total_users', 0),
            'trend_dates': dates,
            'trend_counts': [daily[d] for d in dates]
        })
    except Exception as e:
        print(f"获取统计数据错误: {e}")
        return jsonify({
            'total_detections': 0,
            'total_objects': 0,
            'today_detections': 0,
            'total_users': 0,
            'trend_dates': [],
            'trend_counts': []
        })


@app.route('/history/detail/<int:record_id>')
@login_required
def history_detail(record_id):
    try:
        records = db.get_detection_history(limit=1000)
        record = next((r for r in records if r['id'] == record_id), None)
        if not record:
            return jsonify({'error': '记录不存在'}), 404

        # 读取结果图片
        image_base64 = None
        if record.get('result_image_path') and Path(record['result_image_path']).exists():
            with open(record['result_image_path'], 'rb') as f:
                image_base64 = base64.b64encode(f.read()).decode('utf-8')
                image_base64 = f"data:image/jpeg;base64,{image_base64}"

        return jsonify({
            'record': record,
            'image': image_base64
        })
    except Exception as e:
        print(f"获取详情错误: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== 个人主页 API ====================

@app.route('/api/user/info')
@login_required
def get_user_info():
    try:
        user_id = session['user_id']
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, role, real_name, department, email, phone, 
                   created_at, last_login
            FROM users WHERE id = ?
        ''', (user_id,))
        user = cursor.fetchone()
        conn.close()
        if user:
            return jsonify({
                'id': user[0],
                'username': user[1],
                'role': user[2],
                'real_name': user[3] or '',
                'department': user[4] or '',
                'email': user[5] or '',
                'phone': user[6] or '',
                'created_at': str(user[7]) if user[7] else '',
                'last_login': str(user[8]) if user[8] else ''
            })
        return jsonify({'error': '用户不存在'}), 404
    except Exception as e:
        print(f"获取用户信息错误: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/update', methods=['POST'])
@login_required
def update_user_info():
    try:
        data = request.get_json()
        user_id = session['user_id']
        update_fields = {}
        allowed_fields = ['real_name', 'department', 'email', 'phone']
        for field in allowed_fields:
            if field in data:
                update_fields[field] = data[field]
        if update_fields:
            db.update_user(user_id, **update_fields)
            if 'real_name' in update_fields:
                session['real_name'] = update_fields['real_name']
        return jsonify({'success': True, 'message': '信息更新成功'})
    except Exception as e:
        print(f"更新用户信息错误: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/change-password', methods=['POST'])
@login_required
def change_password():
    try:
        data = request.get_json()
        old_password = data.get('old_password')
        new_password = data.get('new_password')

        if not old_password or not new_password:
            return jsonify({'error': '请填写完整信息'}), 400
        if len(new_password) < 6:
            return jsonify({'error': '新密码长度至少6位'}), 400

        user = db.authenticate_user(session['username'], old_password)
        if not user:
            return jsonify({'error': '原密码错误'}), 400

        if db.change_password(session['user_id'], new_password):
            return jsonify({'success': True, 'message': '密码修改成功，请重新登录'})
        return jsonify({'error': '密码修改失败'}), 500
    except Exception as e:
        print(f"修改密码错误: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/stats')
@login_required
def get_user_stats():
    try:
        user_id = session['user_id']
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM detection_records WHERE user_id = ?', (user_id,))
        total_detections = cursor.fetchone()[0]
        cursor.execute('SELECT COALESCE(SUM(total_detections), 0) FROM detection_records WHERE user_id = ?', (user_id,))
        total_objects = cursor.fetchone()[0] or 0
        cursor.execute('SELECT COUNT(*) FROM detection_records WHERE user_id = ? AND DATE(created_at) = DATE("now")',
                       (user_id,))
        today_detections = cursor.fetchone()[0]
        cursor.execute(
            'SELECT COUNT(*) FROM detection_records WHERE user_id = ? AND DATE(created_at) >= DATE("now", "-7 days")',
            (user_id,))
        week_detections = cursor.fetchone()[0]
        cursor.execute('''
            SELECT created_at, source_type, total_detections 
            FROM detection_records 
            WHERE user_id = ? 
            ORDER BY created_at DESC LIMIT 5
        ''', (user_id,))
        recent_records = cursor.fetchall()
        conn.close()
        return jsonify({
            'total_detections': total_detections,
            'total_objects': total_objects,
            'today_detections': today_detections,
            'week_detections': week_detections,
            'recent_records': [{
                'created_at': str(r[0]) if r[0] else '',
                'source_type': r[1],
                'total_detections': r[2]
            } for r in recent_records]
        })
    except Exception as e:
        print(f"获取用户统计错误: {e}")
        return jsonify({
            'total_detections': 0,
            'total_objects': 0,
            'today_detections': 0,
            'week_detections': 0,
            'recent_records': []
        })


if __name__ == '__main__':
    print("=" * 50)
    print("🚀 钢材缺陷检测系统启动中...")
    print(f"📁 上传文件夹: {app.config['UPLOAD_FOLDER']}")
    print(f"🌐 访问地址: http://127.0.0.1:5000")
    print("=" * 50)
    socketio.run(app, host='127.0.0.1', port=5000, debug=True)