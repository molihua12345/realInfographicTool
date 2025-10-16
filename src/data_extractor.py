"""数据提取模块"""

import os
import json
import base64
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger
from PIL import Image
import pandas as pd
from tqdm import tqdm
import openai
import google.generativeai as genai

from .utils import rate_limit_delay


class DataExtractor:
    """数据提取器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.extraction_config = config['data_extraction']
        self.api_config = config['api']
        self.storage_config = config['storage']
        
        # 设置路径
        base_dir = Path(self.storage_config['base_dir'])
        self.processed_images_dir = base_dir / self.storage_config['subdirs']['processed_images']
        self.extracted_data_dir = base_dir / self.storage_config['subdirs']['extracted_data']
        self.human_annotation_dir = base_dir / self.storage_config['subdirs']['human_annotation']
        
        # 创建输出目录
        self.extracted_data_dir.mkdir(parents=True, exist_ok=True)
        self.human_annotation_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化API客户端
        self._setup_api_clients()
        
        # 统计信息
        self.stats = {
            'total_images': 0,
            'successful_extractions': 0,
            'consensus_achieved': 0,
            'arbitrator_used': 0,
            'human_annotation_needed': 0,
            'failed_extractions': 0
        }
    
    def _setup_api_clients(self) -> None:
        """设置API客户端"""
        # OpenAI客户端
        openai_key = self.api_config.get('openai', {}).get('api_key')
        if openai_key and openai_key != "your_openai_api_key_here":
            openai.api_key = openai_key
            base_url = self.api_config.get('openai', {}).get('base_url')
            if base_url:
                openai.base_url = base_url
        
        # Google AI客户端
        google_key = self.api_config.get('google', {}).get('api_key')
        if google_key and google_key != "your_google_api_key_here":
            genai.configure(api_key=google_key)
    
    def extract_data(self, input_dir: Path = None) -> None:
        """提取数据"""
        if input_dir is None:
            input_dir = self.processed_images_dir
        
        logger.info(f"开始数据提取，输入目录: {input_dir}")
        
        # 获取所有图片文件
        image_files = self._get_image_files(input_dir)
        self.stats['total_images'] = len(image_files)
        
        if not image_files:
            logger.warning("未找到图片文件")
            return
        
        logger.info(f"找到 {len(image_files)} 个图片文件")
        
        # 处理每张图片
        results = []
        for image_path in tqdm(image_files, desc="提取数据"):
            try:
                result = self._process_single_image(image_path)
                if result:
                    results.append(result)
                    self.stats['successful_extractions'] += 1
                else:
                    self.stats['failed_extractions'] += 1
            except Exception as e:
                logger.error(f"处理图片失败: {image_path}, 错误: {e}")
                self.stats['failed_extractions'] += 1
        
        # 保存汇总结果
        self._save_summary_results(results)
        
        # 输出统计信息
        self._print_stats()
    
    def _get_image_files(self, directory: Path) -> List[Path]:
        """获取目录中的所有图片文件"""
        image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}
        image_files = []
        
        for file_path in directory.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                image_files.append(file_path)
        
        return sorted(image_files)
    
    def _process_single_image(self, image_path: Path) -> Optional[Dict[str, Any]]:
        """处理单张图片"""
        logger.debug(f"处理图片: {image_path}")
        
        # 编码图片
        image_base64 = self._encode_image(image_path)
        if not image_base64:
            return None
        
        # 步骤1: 使用两个主要模型并行提取
        primary_results = self._extract_with_primary_models(image_base64)
        
        # 步骤2: 检查一致性
        consensus_result = self._check_consensus(primary_results)
        
        if consensus_result:
            # 达成一致
            self.stats['consensus_achieved'] += 1
            result = {
                'image_path': str(image_path),
                'extraction_method': 'consensus',
                'data': consensus_result,
                'confidence': 'high'
            }
        else:
            # 步骤3: 使用仲裁模型
            arbitrator_result = self._extract_with_arbitrator(image_base64, primary_results)
            
            if arbitrator_result:
                self.stats['arbitrator_used'] += 1
                result = {
                    'image_path': str(image_path),
                    'extraction_method': 'arbitrator',
                    'data': arbitrator_result,
                    'confidence': 'medium'
                }
            else:
                # 步骤4: 需要人工标注
                self.stats['human_annotation_needed'] += 1
                result = self._prepare_for_human_annotation(image_path, primary_results)
        
        # 保存单个结果
        self._save_single_result(image_path, result)
        
        return result
    
    def _encode_image(self, image_path: Path) -> Optional[str]:
        """编码图片为base64"""
        try:
            with Image.open(image_path) as img:
                # 转换为RGB模式
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # 调整大小以减少token消耗
                max_size = 1024
                if max(img.size) > max_size:
                    ratio = max_size / max(img.size)
                    new_size = tuple(int(dim * ratio) for dim in img.size)
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                # 保存为临时文件并编码
                import io
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=85)
                image_bytes = buffer.getvalue()
                
                return base64.b64encode(image_bytes).decode('utf-8')
                
        except Exception as e:
            logger.error(f"编码图片失败: {image_path}, 错误: {e}")
            return None
    
    def _extract_with_primary_models(self, image_base64: str) -> List[Dict[str, Any]]:
        """使用主要模型提取数据"""
        results = []
        
        for model_config in self.extraction_config['models']['primary']:
            try:
                if model_config['provider'] == 'openai':
                    result = self._extract_with_openai(model_config['name'], image_base64)
                elif model_config['provider'] == 'google':
                    result = self._extract_with_google(model_config['name'], image_base64)
                else:
                    logger.warning(f"不支持的提供商: {model_config['provider']}")
                    continue
                
                if result:
                    results.append({
                        'model': model_config['name'],
                        'provider': model_config['provider'],
                        'data': result
                    })
                    
            except Exception as e:
                logger.error(f"模型 {model_config['name']} 提取失败: {e}")
        
        return results
    
    def _extract_with_openai(self, model_name: str, image_base64: str) -> Optional[Dict[str, Any]]:
        """使用OpenAI模型提取数据"""
        try:
            prompt = self._get_extraction_prompt()
            
            response = openai.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                temperature=self.extraction_config['extraction_params']['temperature'],
                max_tokens=2000
            )
            
            content = response.choices[0].message.content
            return self._parse_extraction_result(content)
            
        except Exception as e:
            logger.error(f"OpenAI提取失败: {e}")
            return None
    
    def _extract_with_google(self, model_name: str, image_base64: str) -> Optional[Dict[str, Any]]:
        """使用Google模型提取数据"""
        try:
            model = genai.GenerativeModel(model_name)
            
            # 准备图片数据
            import io
            image_data = base64.b64decode(image_base64)
            image = Image.open(io.BytesIO(image_data))
            
            prompt = self._get_extraction_prompt()
            
            response = model.generate_content(
                [prompt, image],
                generation_config=genai.types.GenerationConfig(
                    temperature=self.extraction_config['extraction_params']['temperature']
                )
            )
            
            return self._parse_extraction_result(response.text)
            
        except Exception as e:
            logger.error(f"Google提取失败: {e}")
            return None
    
    def _get_extraction_prompt(self) -> str:
        """获取数据提取提示词"""
        return """
请分析这张信息图，提取其中的表格数据。请按照以下JSON格式返回结果：

{
    "title": "图表标题",
    "description": "图表描述",
    "data_type": "数据类型（如：统计数据、时间序列、分类数据等）",
    "tables": [
        {
            "table_title": "表格标题",
            "headers": ["列标题1", "列标题2", ...],
            "rows": [
                ["数据1", "数据2", ...],
                ["数据1", "数据2", ...]
            ],
            "units": "数据单位（如适用）",
            "notes": "备注信息（如适用）"
        }
    ],
    "source": "数据来源（如果可见）",
    "confidence": "提取置信度（high/medium/low）"
}

注意事项：
1. 如果图片中没有明确的表格数据，请在tables字段中返回空数组
2. 尽量保持数据的原始格式和精度
3. 如果某些信息不可见或不确定，请标注为"N/A"
4. 只返回JSON格式的结果，不要包含其他文字说明
"""
    
    def _parse_extraction_result(self, content: str) -> Optional[Dict[str, Any]]:
        """解析提取结果"""
        try:
            # 尝试提取JSON部分
            content = content.strip()
            
            # 查找JSON开始和结束位置
            start_idx = content.find('{')
            end_idx = content.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = content[start_idx:end_idx]
                return json.loads(json_str)
            else:
                logger.warning("未找到有效的JSON格式")
                return None
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"解析提取结果失败: {e}")
            return None
    
    def _check_consensus(self, results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """检查模型结果一致性"""
        if len(results) < 2:
            return None
        
        # 简单的一致性检查：比较表格数量和基本结构
        first_result = results[0]['data']
        
        for result in results[1:]:
            if not self._compare_extraction_results(first_result, result['data']):
                return None
        
        # 如果达成一致，返回第一个结果
        return first_result
    
    def _compare_extraction_results(self, result1: Dict[str, Any], result2: Dict[str, Any]) -> bool:
        """比较两个提取结果的相似性"""
        if not result1 or not result2:
            return False
        
        # 比较表格数量
        tables1 = result1.get('tables', [])
        tables2 = result2.get('tables', [])
        
        if len(tables1) != len(tables2):
            return False
        
        # 比较每个表格的结构
        for table1, table2 in zip(tables1, tables2):
            headers1 = table1.get('headers', [])
            headers2 = table2.get('headers', [])
            rows1 = table1.get('rows', [])
            rows2 = table2.get('rows', [])
            
            # 检查列数和行数
            if len(headers1) != len(headers2) or len(rows1) != len(rows2):
                return False
        
        return True
    
    def _extract_with_arbitrator(self, image_base64: str, primary_results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """使用仲裁模型提取数据"""
        arbitrator_config = self.extraction_config['models']['arbitrator']
        
        try:
            if arbitrator_config['provider'] == 'openai':
                return self._extract_with_openai(arbitrator_config['name'], image_base64)
            elif arbitrator_config['provider'] == 'google':
                return self._extract_with_google(arbitrator_config['name'], image_base64)
            else:
                logger.warning(f"不支持的仲裁模型提供商: {arbitrator_config['provider']}")
                return None
                
        except Exception as e:
            logger.error(f"仲裁模型提取失败: {e}")
            return None
    
    def _prepare_for_human_annotation(self, image_path: Path, primary_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """准备人工标注"""
        # 复制图片到人工标注目录
        annotation_image_path = self.human_annotation_dir / image_path.name
        import shutil
        shutil.copy2(image_path, annotation_image_path)
        
        # 创建标注任务文件
        annotation_task = {
            'image_path': str(annotation_image_path),
            'original_path': str(image_path),
            'primary_results': primary_results,
            'status': 'pending',
            'instructions': '请人工提取此图片中的表格数据，参考AI模型的提取结果'
        }
        
        task_file = self.human_annotation_dir / f"{image_path.stem}_task.json"
        with open(task_file, 'w', encoding='utf-8') as f:
            json.dump(annotation_task, f, ensure_ascii=False, indent=2)
        
        return {
            'image_path': str(image_path),
            'extraction_method': 'human_annotation_needed',
            'task_file': str(task_file),
            'confidence': 'pending'
        }
    
    def _save_single_result(self, image_path: Path, result: Dict[str, Any]) -> None:
        """保存单个提取结果"""
        output_file = self.extracted_data_dir / f"{image_path.stem}_result.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    
    def _save_summary_results(self, results: List[Dict[str, Any]]) -> None:
        """保存汇总结果"""
        summary_file = self.extracted_data_dir / "extraction_summary.json"
        
        summary = {
            'total_processed': len(results),
            'statistics': self.stats,
            'results': results
        }
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        # 同时保存为CSV格式（如果有表格数据）
        self._save_as_csv(results)
    
    def _save_as_csv(self, results: List[Dict[str, Any]]) -> None:
        """保存为CSV格式"""
        try:
            csv_data = []
            
            for result in results:
                if result.get('data') and result['data'].get('tables'):
                    for i, table in enumerate(result['data']['tables']):
                        table_data = {
                            'image_path': result['image_path'],
                            'extraction_method': result['extraction_method'],
                            'confidence': result['confidence'],
                            'table_index': i,
                            'table_title': table.get('table_title', ''),
                            'headers': json.dumps(table.get('headers', []), ensure_ascii=False),
                            'rows': json.dumps(table.get('rows', []), ensure_ascii=False),
                            'units': table.get('units', ''),
                            'notes': table.get('notes', '')
                        }
                        csv_data.append(table_data)
            
            if csv_data:
                df = pd.DataFrame(csv_data)
                csv_file = self.extracted_data_dir / "extracted_tables.csv"
                df.to_csv(csv_file, index=False, encoding='utf-8-sig')
                logger.info(f"CSV文件已保存: {csv_file}")
                
        except Exception as e:
            logger.error(f"保存CSV文件失败: {e}")
    
    def _print_stats(self) -> None:
        """打印统计信息"""
        logger.info("数据提取统计信息:")
        logger.info(f"  处理图片总数: {self.stats['total_images']}")
        logger.info(f"  成功提取: {self.stats['successful_extractions']}")
        logger.info(f"  模型达成一致: {self.stats['consensus_achieved']}")
        logger.info(f"  使用仲裁模型: {self.stats['arbitrator_used']}")
        logger.info(f"  需要人工标注: {self.stats['human_annotation_needed']}")
        logger.info(f"  提取失败: {self.stats['failed_extractions']}")
        
        if self.stats['total_images'] > 0:
            success_rate = (self.stats['successful_extractions'] / self.stats['total_images']) * 100
            human_rate = (self.stats['human_annotation_needed'] / self.stats['total_images']) * 100
            logger.info(f"  成功率: {success_rate:.2f}%")
            logger.info(f"  人工标注率: {human_rate:.2f}%")
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self.stats.copy()