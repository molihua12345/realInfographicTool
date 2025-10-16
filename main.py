#!/usr/bin/env python3
"""
信息图数据收集和处理工具
主入口文件
"""

import click
import yaml
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv

from src.data_collector import DataCollector
from src.quality_controller import QualityController
from src.data_extractor import DataExtractor
from src.utils import setup_logging, create_directories


def load_config(config_path: str = "config.yaml") -> dict:
    """加载配置文件"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


@click.group()
@click.option('--config', '-c', default='config.yaml', help='配置文件路径')
@click.pass_context
def cli(ctx, config):
    """信息图数据收集和处理工具"""
    # 加载环境变量
    load_dotenv()
    
    # 加载配置
    ctx.ensure_object(dict)
    ctx.obj['config'] = load_config(config)
    
    # 设置日志
    setup_logging(ctx.obj['config']['logging'])
    
    # 创建目录结构
    create_directories(ctx.obj['config']['storage'])
    
    logger.info("信息图数据处理工具已启动")


@cli.command()
@click.option('--source', '-s', type=click.Choice(['professional', 'search', 'all']), 
              default='all', help='数据源类型')
@click.option('--max-images', '-m', default=1000, help='最大收集图片数量')
@click.pass_context
def collect(ctx, source, max_images):
    """收集信息图数据"""
    config = ctx.obj['config']
    collector = DataCollector(config)
    
    logger.info(f"开始收集数据，源类型: {source}, 最大数量: {max_images}")
    
    if source in ['professional', 'all']:
        collector.collect_from_professional_sites(max_images // 2 if source == 'all' else max_images)
    
    if source in ['search', 'all']:
        collector.collect_from_search_engines(max_images // 2 if source == 'all' else max_images)
    
    logger.info("数据收集完成")


@cli.command()
@click.option('--input-dir', '-i', help='输入图片目录')
@click.pass_context
def filter(ctx, input_dir):
    """质量控制和去重"""
    config = ctx.obj['config']
    controller = QualityController(config)
    
    if not input_dir:
        input_dir = Path(config['storage']['base_dir']) / config['storage']['subdirs']['raw_images']
    
    logger.info(f"开始质量控制，输入目录: {input_dir}")
    controller.process_images(input_dir)
    logger.info("质量控制完成")


@cli.command()
@click.option('--input-dir', '-i', help='输入图片目录')
@click.pass_context
def extract(ctx, input_dir):
    """提取表格数据"""
    config = ctx.obj['config']
    extractor = DataExtractor(config)
    
    if not input_dir:
        input_dir = Path(config['storage']['base_dir']) / config['storage']['subdirs']['processed_images']
    
    logger.info(f"开始数据提取，输入目录: {input_dir}")
    extractor.extract_data(input_dir)
    logger.info("数据提取完成")


@cli.command()
@click.option('--max-images', '-m', default=1000, help='最大处理图片数量')
@click.pass_context
def pipeline(ctx, max_images):
    """运行完整流水线"""
    logger.info("开始运行完整数据处理流水线")
    
    # 数据收集
    ctx.invoke(collect, source='all', max_images=max_images)
    
    # 质量控制
    ctx.invoke(filter)
    
    # 数据提取
    ctx.invoke(extract)
    
    logger.info("完整流水线执行完成")


if __name__ == '__main__':
    cli()