# core/detector.py - 完整替换（支持中文显示）
from ultralytics import YOLO
import cv2
import numpy as np
from pathlib import Path
import torch
import time
import yaml
from PIL import Image, ImageDraw, ImageFont
from PyQt5.QtCore import QThread, pyqtSignal
import os


class DefectDetector:
    """缺陷检测器（支持中文显示）"""

    def __init__(self, model_path='models/best.pt', config_path='config/classes.yaml'):
        project_root = Path(__file__).parent.parent

        if model_path is None:
            model_path = project_root / 'models' / 'best.pt'
        else:
            model_path = Path(model_path)

        if config_path is None:
            config_path = project_root / 'config' / 'classes.yaml'
        else:
            config_path = Path(config_path)

        self.model_path = model_path
        self.config_path = config_path

        # 🔴 强制设置类别名称（硬编码，确保一定有值）
        self.class_names = ['crazing', 'inclusion', 'patches', 'pitted_surface', 'rolled-in_scale', 'scratches']
        self.chinese_names = ['裂纹', '夹杂物', '斑块', '麻点', '氧化皮', '划痕']
        self.class_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255)]

        print(f"🔴 类别名称已设置: {self.chinese_names}")

        # 字体缓存
        self._font_cache = {}

        self.load_model()
        self.reset_stats()

    def _get_chinese_font(self, size=20):
        """获取中文字体（带缓存）"""
        if size in self._font_cache:
            return self._font_cache[size]

        # 按优先级尝试不同系统字体路径
        font_paths = [
            'C:/Windows/Fonts/simhei.ttf',  # Windows 黑体
            'C:/Windows/Fonts/msyh.ttc',  # Windows 微软雅黑
            'C:/Windows/Fonts/simsun.ttc',  # Windows 宋体
            'C:/Windows/Fonts/simkai.ttf',  # Windows 楷体
            '/System/Library/Fonts/PingFang.ttc',  # macOS
            '/System/Library/Fonts/STHeiti Light.ttc',  # macOS
            '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',  # Linux
            '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',  # Linux 文泉驿
            '/usr/share/fonts/truetype/arphic/uming.ttc',  # Linux
        ]

        font = None
        for path in font_paths:
            if os.path.exists(path):
                try:
                    font = ImageFont.truetype(path, size)
                    print(f"✅ 加载中文字体: {path}")
                    break
                except Exception as e:
                    print(f"⚠️ 字体加载失败 {path}: {e}")
                    continue

        if font is None:
            print("⚠️ 未找到中文字体，将使用默认字体（可能显示为方框）")
            font = ImageFont.load_default()

        self._font_cache[size] = font
        return font

    def draw_chinese_labels_pil(self, image, detections, font_size=20):
        """
        使用 PIL 在图像上绘制中文标签（完美支持中文）

        参数:
            image: OpenCV 图像 (BGR格式)
            detections: 检测结果列表
            font_size: 字体大小

        返回:
            绘制了中文标签的图像 (BGR格式)
        """
        if not detections:
            return image

        # OpenCV BGR -> RGB -> PIL
        img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(img_rgb)
        draw = ImageDraw.Draw(img_pil)

        # 获取字体
        font = self._get_chinese_font(font_size)

        for det in detections:
            x1, y1, x2, y2 = det['bbox']

            # 获取中文标签
            chinese_name = det.get('chinese_name', det.get('class_name', '缺陷'))
            confidence = det.get('confidence', 0)
            label = f"{chinese_name} {confidence:.2f}"

            # 获取颜色
            cls_id = det.get('class_id', 0)
            color = self.class_colors[cls_id % len(self.class_colors)]
            # PIL 颜色是 RGB 格式
            color_rgb = (color[2], color[1], color[0])  # BGR -> RGB

            # 绘制边界框
            draw.rectangle([x1, y1, x2, y2], outline=color_rgb, width=3)

            # 获取文字大小
            try:
                bbox = draw.textbbox((x1, y1), label, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            except:
                # 兼容旧版 PIL
                text_width, text_height = draw.textsize(label, font=font)

            # 计算文字背景位置
            text_x = x1
            text_y = y1 - text_height - 5

            # 如果文字超出图像顶部，显示在框的下方
            if text_y < 0:
                text_y = y2 + 5

            # 绘制文字背景
            draw.rectangle(
                [text_x, text_y, text_x + text_width + 10, text_y + text_height + 5],
                fill=color_rgb
            )

            # 绘制文字（白色或黑色，根据背景亮度）
            # 计算亮度，决定文字颜色
            brightness = (color[0] * 0.299 + color[1] * 0.587 + color[2] * 0.114)
            text_color = (0, 0, 0) if brightness > 128 else (255, 255, 255)

            draw.text((text_x + 5, text_y + 2), label, fill=text_color, font=font)

        # PIL -> RGB -> OpenCV BGR
        result = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        return result

    def draw_chinese_labels_opencv(self, image, detections):
        """
        使用 OpenCV 绘制标签（备选方案，仅支持英文）
        """
        result_image = image.copy()

        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            chinese_name = det.get('chinese_name', det.get('class_name', '缺陷'))
            confidence = det.get('confidence', 0)
            cls_id = det.get('class_id', 0)

            color = self.class_colors[cls_id % len(self.class_colors)]
            cv2.rectangle(result_image, (x1, y1), (x2, y2), color, 2)

            # 使用英文标签（OpenCV 不支持中文）
            label = f"{chinese_name}: {confidence:.2f}"

            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.6
            thickness = 2
            (text_w, text_h), _ = cv2.getTextSize(label, font, font_scale, thickness)

            label_y = y1 - 10
            if label_y - text_h < 0:
                label_y = y2 + text_h + 10

            cv2.rectangle(result_image, (x1, label_y - text_h - 5), (x1 + text_w + 10, label_y + 5), color, -1)
            cv2.putText(result_image, label, (x1 + 5, label_y), font, font_scale, (255, 255, 255), thickness)

        return result_image

    def load_model(self):
        """加载模型"""
        try:
            if self.model_path.exists():
                self.model = YOLO(str(self.model_path))
                print(f"✅ 模型加载成功: {self.model_path}")
            else:
                print(f"⚠️ 未找到模型: {self.model_path}，使用默认模型")
                self.model = YOLO('yolo11n.pt')

            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
            print(f"使用设备: {self.device}")

        except Exception as e:
            print(f"❌ 模型加载失败: {e}")
            raise

    def detect_image(self, image, conf_threshold=0.25, save_result=True):
        """检测单张图片（使用 PIL 支持中文显示）"""
        start_time = time.time()

        if isinstance(image, (str, Path)):
            image = cv2.imread(str(image))
            if image is None:
                raise ValueError(f"无法读取图片: {image}")

        results = self.model(image, conf=conf_threshold)

        detections = []

        # 确保中文名称存在
        if not hasattr(self, 'chinese_names') or not self.chinese_names:
            self.chinese_names = ['裂纹', '夹杂物', '斑块', '麻点', '氧化皮', '划痕']

        for r in results:
            boxes = r.boxes
            if boxes is not None:
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])

                    # 🔴 获取中文名称
                    if 0 <= cls_id < len(self.chinese_names):
                        chinese_name = self.chinese_names[cls_id]
                    else:
                        chinese_name = f"类别{cls_id}"

                    detection = {
                        'bbox': [x1, y1, x2, y2],
                        'confidence': conf,
                        'class_id': cls_id,
                        'class_name': self.class_names[cls_id] if cls_id < len(self.class_names) else f"class_{cls_id}",
                        'chinese_name': chinese_name
                    }
                    detections.append(detection)

        # 使用 PIL 绘制中文标签（推荐）
        try:
            result_image = self.draw_chinese_labels_pil(image, detections, font_size=20)
            print(f"✅ 使用 PIL 绘制中文标签成功")
        except Exception as e:
            print(f"⚠️ PIL 绘制失败: {e}，使用 OpenCV 备选方案")
            result_image = self.draw_chinese_labels_opencv(image, detections)

        self.update_stats(detections)

        return {
            'image': result_image,
            'detections': detections,
            'count': len(detections),
            'time': time.time() - start_time
        }

    def detect_video_frame(self, frame, conf_threshold=0.25):
        """检测视频帧（使用 PIL 支持中文显示）"""
        results = self.model(frame, conf=conf_threshold)

        detections = []

        for r in results:
            boxes = r.boxes
            if boxes is not None:
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])

                    if cls_id < len(self.chinese_names):
                        chinese_name = self.chinese_names[cls_id]
                    else:
                        chinese_name = f"类别{cls_id}"

                    detection = {
                        'bbox': [x1, y1, x2, y2],
                        'confidence': conf,
                        'class_id': cls_id,
                        'class_name': self.class_names[cls_id] if cls_id < len(self.class_names) else f"class_{cls_id}",
                        'chinese_name': chinese_name
                    }
                    detections.append(detection)

        # 使用 PIL 绘制中文标签
        try:
            result_frame = self.draw_chinese_labels_pil(frame, detections, font_size=16)
        except Exception as e:
            print(f"⚠️ 视频帧 PIL 绘制失败: {e}，使用 OpenCV 备选方案")
            result_frame = self.draw_chinese_labels_opencv(frame, detections)

        return result_frame, detections

    def update_stats(self, detections):
        """更新统计"""
        self.stats['processed_images'] += 1
        self.stats['total_detections'] += len(detections)
        for d in detections:
            cls_id = d['class_id']
            self.stats['class_counts'][cls_id] = self.stats['class_counts'].get(cls_id, 0) + 1

    def get_stats(self):
        return self.stats

    def reset_stats(self):
        self.stats = {
            'total_detections': 0,
            'processed_images': 0,
            'class_counts': {i: 0 for i in range(6)}
        }


class DetectionThread(QThread):
    """检测线程"""
    frame_ready = pyqtSignal(object, list)
    finished = pyqtSignal()

    def __init__(self, detector, source_type='camera', source=0, conf_threshold=0.25):
        super().__init__()
        self.detector = detector
        self.source_type = source_type
        self.source = source
        self.conf_threshold = conf_threshold
        self.is_running = True

    def run(self):
        try:
            if self.source_type == 'image':
                result = self.detector.detect_image(self.source, self.conf_threshold)
                self.frame_ready.emit(result['image'], result['detections'])
            elif self.source_type in ['video', 'camera']:
                cap = cv2.VideoCapture(self.source)
                while self.is_running and cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        break
                    result_frame, detections = self.detector.detect_video_frame(frame, self.conf_threshold)
                    self.frame_ready.emit(result_frame, detections)
                cap.release()
        except Exception as e:
            print(f"检测线程错误: {e}")
        self.finished.emit()

    def stop(self):
        self.is_running = False