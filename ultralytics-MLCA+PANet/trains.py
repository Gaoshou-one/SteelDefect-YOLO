# trains-MLCA-PANet.py
"""
MLCA + PANet 特征融合训练脚本
"""

import os

os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

from ultralytics import YOLO
import torch
from pathlib import Path


def main():
    print("=" * 60)
    print("YOLOv11n + MLCA + PANet 训练")
    print("=" * 60)

    # 检查设备
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"使用设备: {device}")

    if device == 'cuda':
        torch.cuda.empty_cache()
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"显存: {torch.cuda.get_device_properties(0).total_memory / 1024 ** 3:.1f} GB")

    # 使用 MLCA + PANet 配置
    model = YOLO('ultralytics/cfg/models/11/yolo11n-mlca-pan.yaml')
    print(f"✅ 使用模型: YOLOv11n + MLCA + PANet")

    # 数据集配置
    data_yaml = 'data.yaml'

    if not Path(data_yaml).exists():
        print(f"❌ 数据集不存在: {data_yaml}")
        return

    print(f"✅ 使用数据集: {data_yaml}")

    # 训练参数
    results = model.train(
        # 数据配置
        data=data_yaml,

        # 训练轮数
        epochs=200,

        # 批次大小
        batch=12,

        # 输入尺寸
        imgsz=640,

        # 设备
        device=device,

        # 优化器
        optimizer='AdamW',
        lr0=0.0005,
        lrf=0.005,
        weight_decay=0.0005,

        # 预热
        warmup_epochs=5,
        warmup_momentum=0.8,
        warmup_bias_lr=0.1,

        # 数据增强
        degrees=15.0,
        translate=0.15,
        scale=0.6,
        shear=5.0,
        fliplr=0.5,
        flipud=0.0,
        hsv_h=0.02,
        hsv_s=0.8,
        hsv_v=0.5,
        mosaic=1.0,
        mixup=0.3,
        copy_paste=0.1,

        # 损失权重
        box=7.5,
        cls=0.5,
        dfl=1.5,

        # 保存设置
        project='trains-MLCA-PANet/train-LSKA',
        name='mlca_pan',
        exist_ok=True,

        # 其他
        patience=60,
        pretrained=True,
        verbose=True,
        plots=True,
        workers=4,
        cache=False,
        amp=True,
        val=True,
        save_period=10,
    )

    print("\n" + "=" * 60)
    print("✅ 训练完成！")
    print("=" * 60)

    # 最佳模型路径
    best_model_path = Path('runs/train-LSKA/mlca_pan/weights/best.pt')
    print(f"\n📁 最佳模型: {best_model_path.absolute()}")

    # 验证模型
    print("\n📊 验证模型性能...")
    metrics = model.val()

    print(f"\n📈 模型性能指标:")
    print(f"  mAP50: {metrics.box.map50:.4f}")
    print(f"  mAP50-95: {metrics.box.map:.4f}")
    print(f"  Precision: {metrics.box.p:.4f}")
    print(f"  Recall: {metrics.box.r:.4f}")

    # 保存性能指标
    with open('runs/train-LSKA/mlca_pan/metrics.txt', 'w') as f:
        f.write(f"mAP50: {metrics.box.map50:.4f}\n")
        f.write(f"mAP50-95: {metrics.box.map:.4f}\n")
        f.write(f"Precision: {metrics.box.p:.4f}\n")
        f.write(f"Recall: {metrics.box.r:.4f}\n")

    print("\n训练完成！")


if __name__ == "__main__":
    main()