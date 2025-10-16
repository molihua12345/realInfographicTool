"""工具函数模块"""

import os
import hashlib
from pathlib import Path
from typing import Dict, Any, List
from loguru import logger
import requests
from PIL import Image
import time


def setup_logging(logging_config: Dict[str, Any]) -> None:
    """设置日志配置"""
    logger.remove()  # 移除默认处理器
    
    # 控制台输出
    logger.add(
        sink=lambda msg: print(msg, end=""),
        level=logging_config['level'],
        format=logging_config['format']
    )
    
    # 文件输出
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    logger.add(
        sink=log_dir / "infographic_tool.log",
        level=logging_config['level'],
        format=logging_config['format'],
        rotation=logging_config['rotation'],
        retention=logging_config['retention'],
        encoding="utf-8"
    )


def create_directories(storage_config: Dict[str, Any]) -> None:
    """创建必要的目录结构"""
    base_dir = Path(storage_config['base_dir'])
    
    for subdir in storage_config['subdirs'].values():
        dir_path = base_dir / subdir
        dir_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"创建目录: {dir_path}")


def download_image(url: str, save_path: Path, timeout: int = 30) -> bool:
    """下载图片"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=timeout, stream=True)
        response.raise_for_status()
        
        # 检查内容类型
        content_type = response.headers.get('content-type', '')
        if not content_type.startswith('image/'):
            logger.warning(f"URL不是图片类型: {url}")
            return False
        
        # 保存图片
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # 验证图片
        try:
            with Image.open(save_path) as img:
                img.verify()
            logger.debug(f"成功下载图片: {save_path}")
            return True
        except Exception as e:
            logger.warning(f"图片验证失败: {save_path}, 错误: {e}")
            save_path.unlink(missing_ok=True)
            return False
            
    except Exception as e:
        logger.error(f"下载图片失败: {url}, 错误: {e}")
        return False


def get_file_hash(file_path: Path) -> str:
    """计算文件MD5哈希值"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def validate_image(image_path: Path, config: Dict[str, Any]) -> bool:
    """验证图片是否符合要求"""
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            
            # 检查尺寸
            if width < config['min_width'] or height < config['min_height']:
                return False
            
            # 检查文件大小
            file_size_mb = image_path.stat().st_size / (1024 * 1024)
            if file_size_mb > config['max_file_size_mb']:
                return False
            
            # 检查格式
            file_ext = image_path.suffix.lower().lstrip('.')
            if file_ext not in config['allowed_formats']:
                return False
            
            return True
            
    except Exception as e:
        logger.warning(f"图片验证失败: {image_path}, 错误: {e}")
        return False


def rate_limit_delay(delay_seconds: float) -> None:
    """速率限制延迟"""
    if delay_seconds > 0:
        time.sleep(delay_seconds)


def safe_filename(filename: str) -> str:
    """生成安全的文件名"""
    # 移除或替换不安全字符
    unsafe_chars = '<>:"/\\|?*'
    for char in unsafe_chars:
        filename = filename.replace(char, '_')
    
    # 限制长度
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:200-len(ext)] + ext
    
    return filename


def batch_process(items: List[Any], batch_size: int, process_func, *args, **kwargs):
    """批量处理数据"""
    results = []
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        batch_results = process_func(batch, *args, **kwargs)
        results.extend(batch_results)
    return results