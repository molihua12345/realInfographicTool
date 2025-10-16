#!/usr/bin/env python3
"""
使用示例脚本
展示如何使用信息图数据处理工具的各个功能
"""

import sys
from pathlib import Path
import yaml
from loguru import logger

# 添加src目录到路径
sys.path.append(str(Path(__file__).parent / 'src'))

from src.data_collector import DataCollector
from src.quality_controller import QualityController
from src.data_extractor import DataExtractor
from src.utils import setup_logging, create_directories


def load_config():
    """加载配置文件"""
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        return None


def example_data_collection(config, max_images=50):
    """数据收集示例"""
    logger.info(f"=== 数据收集示例 (最多{max_images}张图片) ===")
    
    try:
        collector = DataCollector(config)
        
        # 从搜索引擎收集少量图片作为示例
        logger.info("从搜索引擎收集图片...")
        collector.collect_from_search_engines(max_images)
        
        # 获取统计信息
        stats = collector.get_stats()
        logger.info(f"收集统计: {stats}")
        
        return stats['total_collected'] > 0
        
    except Exception as e:
        logger.error(f"数据收集失败: {e}")
        return False


def example_quality_control(config):
    """质量控制示例"""
    logger.info("=== 质量控制示例 ===")
    
    try:
        controller = QualityController(config)
        
        # 处理原始图片
        logger.info("开始质量控制处理...")
        controller.process_images()
        
        # 获取统计信息
        stats = controller.get_stats()
        logger.info(f"质量控制统计: {stats}")
        
        return stats['final_output'] > 0
        
    except Exception as e:
        logger.error(f"质量控制失败: {e}")
        return False


def example_data_extraction(config):
    """数据提取示例"""
    logger.info("=== 数据提取示例 ===")
    
    try:
        extractor = DataExtractor(config)
        
        # 提取数据
        logger.info("开始数据提取...")
        extractor.extract_data()
        
        # 获取统计信息
        stats = extractor.get_stats()
        logger.info(f"数据提取统计: {stats}")
        
        return stats['total_images'] > 0
        
    except Exception as e:
        logger.error(f"数据提取失败: {e}")
        return False


def example_full_pipeline(config, max_images=20):
    """完整流水线示例"""
    logger.info(f"=== 完整流水线示例 (最多{max_images}张图片) ===")
    
    success_steps = 0
    total_steps = 3
    
    # 步骤1: 数据收集
    logger.info("步骤1: 数据收集")
    if example_data_collection(config, max_images):
        success_steps += 1
        logger.success("✓ 数据收集完成")
    else:
        logger.error("✗ 数据收集失败")
    
    # 步骤2: 质量控制
    logger.info("\n步骤2: 质量控制")
    if example_quality_control(config):
        success_steps += 1
        logger.success("✓ 质量控制完成")
    else:
        logger.error("✗ 质量控制失败")
    
    # 步骤3: 数据提取
    logger.info("\n步骤3: 数据提取")
    if example_data_extraction(config):
        success_steps += 1
        logger.success("✓ 数据提取完成")
    else:
        logger.error("✗ 数据提取失败")
    
    # 总结
    logger.info(f"\n流水线完成: {success_steps}/{total_steps} 步骤成功")
    
    if success_steps == total_steps:
        logger.success("🎉 完整流水线执行成功！")
        
        # 显示输出文件位置
        base_dir = Path(config['storage']['base_dir'])
        logger.info("\n输出文件位置:")
        logger.info(f"  处理后图片: {base_dir / config['storage']['subdirs']['processed_images']}")
        logger.info(f"  提取数据: {base_dir / config['storage']['subdirs']['extracted_data']}")
        logger.info(f"  人工标注: {base_dir / config['storage']['subdirs']['human_annotation']}")
    
    return success_steps == total_steps


def check_api_configuration(config):
    """检查API配置"""
    logger.info("=== API配置检查 ===")
    
    api_config = config.get('api', {})
    configured_apis = []
    missing_apis = []
    
    # 检查各个API
    apis_to_check = [
        ('openai', 'OpenAI API'),
        ('google', 'Google AI API'),
        ('bing', 'Bing搜索API'),
        ('google_search', 'Google搜索API')
    ]
    
    for api_key, api_name in apis_to_check:
        api_data = api_config.get(api_key, {})
        key = api_data.get('api_key', '')
        
        if key and not key.startswith('your_'):
            configured_apis.append(api_name)
        else:
            missing_apis.append(api_name)
    
    if configured_apis:
        logger.info("已配置的API:")
        for api in configured_apis:
            logger.info(f"  ✓ {api}")
    
    if missing_apis:
        logger.warning("未配置的API:")
        for api in missing_apis:
            logger.warning(f"  ⚠ {api}")
        logger.info("\n提示: 在config.yaml中配置API密钥以使用完整功能")
    
    return len(configured_apis) > 0


def main():
    """主函数"""
    logger.info("信息图数据处理工具 - 使用示例")
    logger.info("=" * 60)
    
    # 加载配置
    config = load_config()
    if not config:
        logger.error("无法加载配置文件，退出")
        return False
    
    # 设置日志和目录
    setup_logging(config['logging'])
    create_directories(config['storage'])
    
    # 检查API配置
    has_api = check_api_configuration(config)
    
    if not has_api:
        logger.warning("\n⚠ 没有配置API密钥，某些功能可能无法正常工作")
        logger.info("建议先配置至少一个API密钥再运行示例")
        
        response = input("\n是否继续运行示例？(y/N): ")
        if response.lower() != 'y':
            logger.info("退出示例")
            return False
    
    logger.info("\n" + "=" * 60)
    
    # 运行示例
    try:
        # 可以选择运行单个示例或完整流水线
        logger.info("选择运行模式:")
        logger.info("1. 完整流水线示例 (推荐)")
        logger.info("2. 仅数据收集示例")
        logger.info("3. 仅质量控制示例")
        logger.info("4. 仅数据提取示例")
        
        choice = input("\n请选择 (1-4, 默认1): ").strip() or "1"
        
        if choice == "1":
            return example_full_pipeline(config)
        elif choice == "2":
            return example_data_collection(config)
        elif choice == "3":
            return example_quality_control(config)
        elif choice == "4":
            return example_data_extraction(config)
        else:
            logger.error("无效选择")
            return False
            
    except KeyboardInterrupt:
        logger.info("\n用户中断，退出示例")
        return False
    except Exception as e:
        logger.error(f"运行示例时发生错误: {e}")
        return False


if __name__ == '__main__':
    success = main()
    
    if success:
        logger.success("\n✅ 示例运行完成！")
        logger.info("\n下一步:")
        logger.info("  - 查看生成的数据文件")
        logger.info("  - 配置更多API密钥以获得更好效果")
        logger.info("  - 调整config.yaml中的参数")
        logger.info("  - 使用 python main.py --help 查看更多选项")
    else:
        logger.error("\n❌ 示例运行失败")
        logger.info("\n故障排除:")
        logger.info("  - 运行 python test_basic.py 检查基础配置")
        logger.info("  - 检查网络连接")
        logger.info("  - 确保API密钥正确配置")
    
    sys.exit(0 if success else 1)