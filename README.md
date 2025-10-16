# 信息图数据收集和处理工具

这是一个高质量、多样化的真实信息图（infographic）数据收集和处理工具，实现了从数据收集到质量控制再到数据提取的完整流水线。

## 功能特性

### 1. 双源数据收集策略
- **专业网站爬取**: 从Statista、Visual Capitalist等专业网站收集高质量信息图
- **搜索引擎API**: 通过Google和Bing图片搜索API收集遵循知识共享协议的图片

### 2. 严格的质量控制
- **文件哈希去重**: 基于MD5哈希值去除完全重复的文件
- **感知哈希去重**: 使用Perceptual Hashing技术识别视觉相似的图片
- **CLIP相似度去重**: 利用CLIP模型计算语义相似度，去除高度相似的图像
- **图片质量验证**: 检查图片尺寸、格式、文件大小等基本质量指标

### 3. 多步验证数据提取
- **双模型并行提取**: 使用Gemini-2.0-Flash和GPT-4o-mini并行提取表格数据
- **一致性检查**: 仅当两个模型输出一致时自动接受结果
- **仲裁机制**: 对于不一致情况，使用GPT-4o进行仲裁
- **人工标注**: 当所有模型无法达成一致时，转入人工标注流程

## 项目结构

```
realInfographicTool/
├── main.py                 # 主入口文件
├── config.yaml            # 配置文件
├── requirements.txt       # 依赖包列表
├── .env.example          # 环境变量示例
├── README.md             # 项目说明
├── guide.md              # 项目指南
├── src/                  # 源代码目录
│   ├── __init__.py
│   ├── utils.py          # 工具函数
│   ├── data_collector.py # 数据收集模块
│   ├── quality_controller.py # 质量控制模块
│   └── data_extractor.py # 数据提取模块
└── data/                 # 数据目录（自动创建）
    ├── raw_images/       # 原始图片
    ├── processed_images/ # 处理后图片
    ├── extracted_data/   # 提取的数据
    ├── human_annotation/ # 人工标注
    └── logs/            # 日志文件
```

## 安装和配置

### 1. 环境要求
- Python 3.8+
- CUDA支持的GPU（可选，用于CLIP模型加速）

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 配置API密钥
1. 复制环境变量示例文件：
```bash
cp .env.example .env
```

2. 编辑`.env`文件，填入你的API密钥：
- OpenAI API密钥（用于GPT模型）
- Google AI API密钥（用于Gemini模型）
- Bing搜索API密钥（用于Bing图片搜索）
- Google自定义搜索API密钥和搜索引擎ID（用于Google图片搜索）

### 4. 配置参数
编辑`config.yaml`文件，根据需要调整各种参数：
- 数据收集参数（搜索关键词、最大结果数等）
- 质量控制阈值（相似度阈值、图片尺寸要求等）
- 数据提取参数（模型选择、温度参数等）

## 使用方法

### 命令行界面

#### 1. 运行完整流水线
```bash
python main.py pipeline --max-images 1000
```

#### 2. 单独运行各个步骤

**数据收集**:
```bash
# 从所有源收集
python main.py collect --source all --max-images 1000

# 仅从专业网站收集
python main.py collect --source professional --max-images 500

# 仅从搜索引擎收集
python main.py collect --source search --max-images 500
```

**质量控制**:
```bash
python main.py filter --input-dir ./data/raw_images
```

**数据提取**:
```bash
python main.py extract --input-dir ./data/processed_images
```

### 程序化使用

```python
from src.data_collector import DataCollector
from src.quality_controller import QualityController
from src.data_extractor import DataExtractor
import yaml

# 加载配置
with open('config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 数据收集
collector = DataCollector(config)
collector.collect_from_professional_sites(500)
collector.collect_from_search_engines(500)

# 质量控制
controller = QualityController(config)
controller.process_images()

# 数据提取
extractor = DataExtractor(config)
extractor.extract_data()
```

## 输出结果

### 1. 处理后的图片
- 位置：`./data/processed_images/`
- 格式：去重后的高质量信息图

### 2. 提取的数据
- JSON格式：`./data/extracted_data/`目录下的单个结果文件
- CSV格式：`./data/extracted_data/extracted_tables.csv`汇总文件
- 汇总报告：`./data/extracted_data/extraction_summary.json`

### 3. 人工标注任务
- 位置：`./data/human_annotation/`
- 包含需要人工处理的图片和任务描述文件

## 性能优化建议

1. **GPU加速**: 如果有CUDA支持的GPU，CLIP模型会自动使用GPU加速
2. **批处理**: 调整`config.yaml`中的`batch_size`参数优化内存使用
3. **并发处理**: 根据API限制调整请求延迟参数
4. **存储优化**: 定期清理中间文件，保留最终结果

## 成本控制

1. **API调用优化**: 
   - 图片会自动压缩以减少token消耗
   - 使用较便宜的模型进行初步提取
   - 仅在必要时使用高级模型仲裁

2. **人工标注最小化**:
   - 通过优化模型参数减少不一致情况
   - 当前配置下约13.4%的图片需要人工标注

## 故障排除

### 常见问题

1. **API密钥错误**: 检查`.env`文件中的API密钥是否正确
2. **网络连接问题**: 确保网络连接稳定，可能需要代理设置
3. **内存不足**: 减少批处理大小或使用更小的CLIP模型
4. **Chrome驱动问题**: 确保Chrome浏览器已安装，webdriver-manager会自动下载驱动

### 日志查看
日志文件位于`./logs/infographic_tool.log`，包含详细的运行信息和错误信息。

## 许可证

本项目遵循MIT许可证。收集的图片数据请遵循相应的版权和许可证要求。

## 贡献

欢迎提交Issue和Pull Request来改进这个工具。

## 更新日志

### v1.0.0
- 初始版本发布
- 实现完整的数据收集、质量控制和数据提取流水线
- 支持多种数据源和API
- 集成多模型验证机制