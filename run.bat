@echo off
chcp 65001 >nul
echo ========================================
echo 信息图数据收集和处理工具
echo ========================================
echo.

:: 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

:: 检查是否存在虚拟环境
if not exist "venv" (
    echo 创建虚拟环境...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo 错误: 创建虚拟环境失败
        pause
        exit /b 1
    )
)

:: 激活虚拟环境
echo 激活虚拟环境...
call venv\Scripts\activate.bat

:: 检查是否需要安装依赖
if not exist "venv\installed.flag" (
    echo 安装依赖包...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo 错误: 安装依赖失败
        pause
        exit /b 1
    )
    echo. > venv\installed.flag
)

:: 检查配置文件
if not exist ".env" (
    if exist ".env.example" (
        echo 复制环境变量示例文件...
        copy ".env.example" ".env"
        echo 请编辑 .env 文件配置API密钥
    )
)

:: 显示菜单
:menu
echo.
echo ========================================
echo 请选择操作:
echo 1. 运行基础测试
echo 2. 运行使用示例
echo 3. 运行完整流水线 (100张图片)
echo 4. 仅数据收集
echo 5. 仅质量控制
echo 6. 仅数据提取
echo 7. 查看帮助
echo 8. 退出
echo ========================================
set /p choice=请输入选择 (1-8): 

if "%choice%"=="1" (
    echo 运行基础测试...
    python test_basic.py
    goto menu
) else if "%choice%"=="2" (
    echo 运行使用示例...
    python example_usage.py
    goto menu
) else if "%choice%"=="3" (
    echo 运行完整流水线...
    python main.py pipeline --max-images 100
    goto menu
) else if "%choice%"=="4" (
    echo 运行数据收集...
    python main.py collect --source all --max-images 50
    goto menu
) else if "%choice%"=="5" (
    echo 运行质量控制...
    python main.py filter
    goto menu
) else if "%choice%"=="6" (
    echo 运行数据提取...
    python main.py extract
    goto menu
) else if "%choice%"=="7" (
    echo 显示帮助...
    python main.py --help
    goto menu
) else if "%choice%"=="8" (
    echo 退出程序
    goto end
) else (
    echo 无效选择，请重新输入
    goto menu
)

:end
echo 感谢使用信息图数据处理工具！
pause