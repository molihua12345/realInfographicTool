"""质量控制模块"""

import os
import shutil
from pathlib import Path
from typing import Dict, List, Any, Tuple, Set
from collections import defaultdict
from loguru import logger
from PIL import Image
import imagehash
import torch
import clip
import numpy as np
from tqdm import tqdm

from .utils import validate_image, get_file_hash, batch_process


class QualityController:
    """质量控制器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.quality_config = config['quality_control']
        self.storage_config = config['storage']
        
        # 设置路径
        base_dir = Path(self.storage_config['base_dir'])
        self.raw_images_dir = base_dir / self.storage_config['subdirs']['raw_images']
        self.processed_images_dir = base_dir / self.storage_config['subdirs']['processed_images']
        self.processed_images_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化CLIP模型
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.clip_model = None
        self.clip_preprocess = None
        
        # 统计信息
        self.stats = {
            'total_input': 0,
            'invalid_images': 0,
            'duplicate_by_hash': 0,
            'duplicate_by_phash': 0,
            'duplicate_by_clip': 0,
            'final_output': 0
        }
    
    def _load_clip_model(self) -> None:
        """加载CLIP模型"""
        if self.clip_model is None:
            logger.info("加载CLIP模型...")
            model_name = self.quality_config['clip']['model_name']
            self.clip_model, self.clip_preprocess = clip.load(model_name, device=self.device)
            logger.info(f"CLIP模型已加载到 {self.device}")
    
    def process_images(self, input_dir: Path = None) -> None:
        """处理图片质量控制"""
        if input_dir is None:
            input_dir = self.raw_images_dir
        
        logger.info(f"开始质量控制处理，输入目录: {input_dir}")
        
        # 获取所有图片文件
        image_files = self._get_image_files(input_dir)
        self.stats['total_input'] = len(image_files)
        
        if not image_files:
            logger.warning("未找到图片文件")
            return
        
        logger.info(f"找到 {len(image_files)} 个图片文件")
        
        # 步骤1: 基础验证和文件哈希去重
        valid_images = self._basic_validation_and_hash_dedup(image_files)
        
        # 步骤2: 感知哈希去重
        phash_filtered = self._perceptual_hash_dedup(valid_images)
        
        # 步骤3: CLIP相似度去重
        final_images = self._clip_similarity_dedup(phash_filtered)
        
        # 步骤4: 复制到输出目录
        self._copy_final_images(final_images)
        
        # 输出统计信息
        self._print_stats()
    
    def _get_image_files(self, directory: Path) -> List[Path]:
        """获取目录中的所有图片文件"""
        image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}
        image_files = []
        
        for file_path in directory.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                image_files.append(file_path)
        
        return image_files
    
    def _basic_validation_and_hash_dedup(self, image_files: List[Path]) -> List[Path]:
        """基础验证和文件哈希去重"""
        logger.info("执行基础验证和文件哈希去重...")
        
        valid_images = []
        seen_hashes = set()
        
        for image_path in tqdm(image_files, desc="基础验证"):
            try:
                # 验证图片
                if not validate_image(image_path, self.quality_config['image_filters']):
                    self.stats['invalid_images'] += 1
                    continue
                
                # 计算文件哈希
                file_hash = get_file_hash(image_path)
                if file_hash in seen_hashes:
                    self.stats['duplicate_by_hash'] += 1
                    continue
                
                seen_hashes.add(file_hash)
                valid_images.append(image_path)
                
            except Exception as e:
                logger.debug(f"处理图片失败: {image_path}, 错误: {e}")
                self.stats['invalid_images'] += 1
        
        logger.info(f"基础验证完成，保留 {len(valid_images)} 张图片")
        return valid_images
    
    def _perceptual_hash_dedup(self, image_files: List[Path]) -> List[Path]:
        """感知哈希去重"""
        logger.info("执行感知哈希去重...")
        
        # 计算所有图片的感知哈希
        image_hashes = []
        valid_images = []
        
        for image_path in tqdm(image_files, desc="计算感知哈希"):
            try:
                with Image.open(image_path) as img:
                    # 转换为RGB模式
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    # 计算感知哈希
                    phash = imagehash.phash(img)
                    image_hashes.append((image_path, phash))
                    valid_images.append(image_path)
                    
            except Exception as e:
                logger.debug(f"计算感知哈希失败: {image_path}, 错误: {e}")
        
        # 去重
        filtered_images = self._filter_by_phash(image_hashes)
        
        logger.info(f"感知哈希去重完成，保留 {len(filtered_images)} 张图片")
        return filtered_images
    
    def _filter_by_phash(self, image_hashes: List[Tuple[Path, Any]]) -> List[Path]:
        """基于感知哈希过滤重复图片"""
        threshold = self.quality_config['phash']['threshold']
        filtered_images = []
        processed_hashes = []
        
        for image_path, phash in image_hashes:
            is_duplicate = False
            
            for _, existing_hash in processed_hashes:
                if phash - existing_hash <= threshold:
                    is_duplicate = True
                    self.stats['duplicate_by_phash'] += 1
                    break
            
            if not is_duplicate:
                filtered_images.append(image_path)
                processed_hashes.append((image_path, phash))
        
        return filtered_images
    
    def _clip_similarity_dedup(self, image_files: List[Path]) -> List[Path]:
        """CLIP相似度去重"""
        logger.info("执行CLIP相似度去重...")
        
        if len(image_files) <= 1:
            return image_files
        
        # 加载CLIP模型
        self._load_clip_model()
        
        # 批量处理图片
        batch_size = self.quality_config['clip']['batch_size']
        
        # 计算所有图片的CLIP特征
        all_features = []
        valid_images = []
        
        for i in tqdm(range(0, len(image_files), batch_size), desc="计算CLIP特征"):
            batch_files = image_files[i:i + batch_size]
            batch_features, batch_valid = self._compute_clip_features_batch(batch_files)
            
            all_features.extend(batch_features)
            valid_images.extend(batch_valid)
        
        if not all_features:
            logger.warning("没有成功计算CLIP特征的图片")
            return []
        
        # 基于相似度去重
        filtered_images = self._filter_by_clip_similarity(valid_images, all_features)
        
        logger.info(f"CLIP相似度去重完成，保留 {len(filtered_images)} 张图片")
        return filtered_images
    
    def _compute_clip_features_batch(self, image_files: List[Path]) -> Tuple[List[torch.Tensor], List[Path]]:
        """批量计算CLIP特征"""
        features = []
        valid_images = []
        
        batch_images = []
        batch_paths = []
        
        for image_path in image_files:
            try:
                with Image.open(image_path) as img:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    # 预处理图片
                    processed_img = self.clip_preprocess(img)
                    batch_images.append(processed_img)
                    batch_paths.append(image_path)
                    
            except Exception as e:
                logger.debug(f"预处理图片失败: {image_path}, 错误: {e}")
        
        if batch_images:
            try:
                # 批量计算特征
                with torch.no_grad():
                    image_tensor = torch.stack(batch_images).to(self.device)
                    batch_features = self.clip_model.encode_image(image_tensor)
                    batch_features = batch_features / batch_features.norm(dim=-1, keepdim=True)
                
                for i, feature in enumerate(batch_features):
                    features.append(feature.cpu())
                    valid_images.append(batch_paths[i])
                    
            except Exception as e:
                logger.error(f"批量计算CLIP特征失败: {e}")
        
        return features, valid_images
    
    def _filter_by_clip_similarity(self, image_files: List[Path], features: List[torch.Tensor]) -> List[Path]:
        """基于CLIP相似度过滤重复图片"""
        threshold = self.quality_config['clip']['similarity_threshold']
        filtered_images = []
        filtered_features = []
        
        for i, (image_path, feature) in enumerate(zip(image_files, features)):
            is_duplicate = False
            
            for existing_feature in filtered_features:
                # 计算余弦相似度
                similarity = torch.cosine_similarity(feature.unsqueeze(0), existing_feature.unsqueeze(0))
                
                if similarity.item() > threshold:
                    is_duplicate = True
                    self.stats['duplicate_by_clip'] += 1
                    break
            
            if not is_duplicate:
                filtered_images.append(image_path)
                filtered_features.append(feature)
        
        return filtered_images
    
    def _copy_final_images(self, image_files: List[Path]) -> None:
        """复制最终图片到输出目录"""
        logger.info(f"复制 {len(image_files)} 张图片到输出目录...")
        
        for i, image_path in enumerate(tqdm(image_files, desc="复制图片")):
            try:
                # 生成新的文件名
                new_filename = f"processed_{i:06d}{image_path.suffix}"
                output_path = self.processed_images_dir / new_filename
                
                # 复制文件
                shutil.copy2(image_path, output_path)
                self.stats['final_output'] += 1
                
            except Exception as e:
                logger.error(f"复制图片失败: {image_path}, 错误: {e}")
    
    def _print_stats(self) -> None:
        """打印统计信息"""
        logger.info("质量控制统计信息:")
        logger.info(f"  输入图片总数: {self.stats['total_input']}")
        logger.info(f"  无效图片: {self.stats['invalid_images']}")
        logger.info(f"  文件哈希重复: {self.stats['duplicate_by_hash']}")
        logger.info(f"  感知哈希重复: {self.stats['duplicate_by_phash']}")
        logger.info(f"  CLIP相似度重复: {self.stats['duplicate_by_clip']}")
        logger.info(f"  最终输出: {self.stats['final_output']}")
        
        if self.stats['total_input'] > 0:
            retention_rate = (self.stats['final_output'] / self.stats['total_input']) * 100
            logger.info(f"  保留率: {retention_rate:.2f}%")
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self.stats.copy()