"""数据收集模块"""

import os
import requests
import time
from pathlib import Path
from typing import Dict, List, Any
from urllib.parse import urljoin, urlparse
from loguru import logger
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

from .utils import download_image, rate_limit_delay, safe_filename, validate_image


class DataCollector:
    """数据收集器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.storage_config = config['storage']
        self.collection_config = config['data_collection']
        self.api_config = config['api']
        
        # 设置保存路径
        self.raw_images_dir = Path(self.storage_config['base_dir']) / self.storage_config['subdirs']['raw_images']
        self.raw_images_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化统计
        self.stats = {
            'total_collected': 0,
            'professional_sites': 0,
            'search_engines': 0,
            'failed_downloads': 0
        }
    
    def collect_from_professional_sites(self, max_images: int) -> None:
        """从专业网站收集信息图"""
        logger.info("开始从专业网站收集信息图")
        
        collected = 0
        for site_url in self.collection_config['professional_sites']:
            if collected >= max_images:
                break
                
            try:
                site_collected = self._scrape_professional_site(
                    site_url, 
                    max_images - collected
                )
                collected += site_collected
                self.stats['professional_sites'] += site_collected
                
                # 延迟以避免被封
                rate_limit_delay(self.collection_config['search_params']['delay_between_requests'])
                
            except Exception as e:
                logger.error(f"从网站 {site_url} 收集失败: {e}")
        
        logger.info(f"从专业网站收集完成，共收集 {collected} 张图片")
    
    def collect_from_search_engines(self, max_images: int) -> None:
        """从搜索引擎收集信息图"""
        logger.info("开始从搜索引擎收集信息图")
        
        collected = 0
        queries = self.collection_config['search_params']['query_templates']
        
        for query in queries:
            if collected >= max_images:
                break
            
            for engine in self.collection_config['search_engines']:
                if collected >= max_images:
                    break
                
                try:
                    engine_collected = self._search_images(
                        engine, 
                        query, 
                        min(max_images - collected, 
                            self.collection_config['search_params']['max_results_per_query'])
                    )
                    collected += engine_collected
                    self.stats['search_engines'] += engine_collected
                    
                    # 延迟
                    rate_limit_delay(self.collection_config['search_params']['delay_between_requests'])
                    
                except Exception as e:
                    logger.error(f"从搜索引擎 {engine} 搜索 '{query}' 失败: {e}")
        
        logger.info(f"从搜索引擎收集完成，共收集 {collected} 张图片")
    
    def _scrape_professional_site(self, site_url: str, max_images: int) -> int:
        """爬取专业网站"""
        logger.info(f"开始爬取网站: {site_url}")
        
        # 设置Chrome选项
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        collected = 0
        
        try:
            # 初始化WebDriver
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            try:
                driver.get(site_url)
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # 查找图片元素
                img_elements = driver.find_elements(By.TAG_NAME, "img")
                
                for img_element in img_elements[:max_images]:
                    if collected >= max_images:
                        break
                    
                    try:
                        img_url = img_element.get_attribute("src")
                        if not img_url:
                            continue
                        
                        # 转换为绝对URL
                        img_url = urljoin(site_url, img_url)
                        
                        # 检查是否可能是信息图
                        if self._is_likely_infographic(img_url, img_element):
                            if self._download_and_validate_image(img_url, f"professional_{collected}"):
                                collected += 1
                    
                    except Exception as e:
                        logger.debug(f"处理图片元素失败: {e}")
                        continue
            
            finally:
                driver.quit()
        
        except Exception as e:
            logger.error(f"爬取网站 {site_url} 失败: {e}")
        
        return collected
    
    def _search_images(self, engine: str, query: str, max_results: int) -> int:
        """搜索图片"""
        logger.info(f"使用 {engine} 搜索: {query}")
        
        if engine == 'google':
            return self._google_image_search(query, max_results)
        elif engine == 'bing':
            return self._bing_image_search(query, max_results)
        else:
            logger.warning(f"不支持的搜索引擎: {engine}")
            return 0
    
    def _google_image_search(self, query: str, max_results: int) -> int:
        """Google图片搜索"""
        try:
            api_key = self.api_config['google_search']['api_key']
            cx = self.api_config['google_search']['cx']
            
            if not api_key or api_key == "your_google_search_api_key_here":
                logger.warning("Google搜索API密钥未配置")
                return 0
            
            collected = 0
            start_index = 1
            
            while collected < max_results and start_index <= 100:  # Google API限制
                url = "https://www.googleapis.com/customsearch/v1"
                params = {
                    'key': api_key,
                    'cx': cx,
                    'q': query,
                    'searchType': 'image',
                    'start': start_index,
                    'num': min(10, max_results - collected),
                    'rights': 'cc_publicdomain,cc_attribute,cc_sharealike,cc_noncommercial,cc_nonderived'
                }
                
                response = requests.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                items = data.get('items', [])
                
                if not items:
                    break
                
                for item in items:
                    if collected >= max_results:
                        break
                    
                    img_url = item.get('link')
                    if img_url and self._download_and_validate_image(img_url, f"google_{collected}"):
                        collected += 1
                
                start_index += len(items)
                rate_limit_delay(1)  # API速率限制
            
            return collected
            
        except Exception as e:
            logger.error(f"Google图片搜索失败: {e}")
            return 0
    
    def _bing_image_search(self, query: str, max_results: int) -> int:
        """Bing图片搜索"""
        try:
            api_key = self.api_config['bing']['api_key']
            
            if not api_key or api_key == "your_bing_search_api_key_here":
                logger.warning("Bing搜索API密钥未配置")
                return 0
            
            collected = 0
            offset = 0
            
            while collected < max_results:
                url = "https://api.bing.microsoft.com/v7.0/images/search"
                headers = {'Ocp-Apim-Subscription-Key': api_key}
                params = {
                    'q': query,
                    'count': min(50, max_results - collected),
                    'offset': offset,
                    'license': 'public'
                }
                
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                
                data = response.json()
                images = data.get('value', [])
                
                if not images:
                    break
                
                for image in images:
                    if collected >= max_results:
                        break
                    
                    img_url = image.get('contentUrl')
                    if img_url and self._download_and_validate_image(img_url, f"bing_{collected}"):
                        collected += 1
                
                offset += len(images)
                rate_limit_delay(1)  # API速率限制
            
            return collected
            
        except Exception as e:
            logger.error(f"Bing图片搜索失败: {e}")
            return 0
    
    def _is_likely_infographic(self, img_url: str, img_element=None) -> bool:
        """判断是否可能是信息图"""
        # 基于URL的简单判断
        infographic_keywords = [
            'infographic', 'chart', 'graph', 'data', 'statistic', 
            'visualization', 'diagram', 'report'
        ]
        
        url_lower = img_url.lower()
        for keyword in infographic_keywords:
            if keyword in url_lower:
                return True
        
        # 基于元素属性的判断
        if img_element:
            alt_text = img_element.get_attribute("alt") or ""
            title_text = img_element.get_attribute("title") or ""
            
            combined_text = (alt_text + " " + title_text).lower()
            for keyword in infographic_keywords:
                if keyword in combined_text:
                    return True
        
        return True  # 默认认为可能是信息图
    
    def _download_and_validate_image(self, img_url: str, prefix: str) -> bool:
        """下载并验证图片"""
        try:
            # 生成文件名
            parsed_url = urlparse(img_url)
            filename = f"{prefix}_{safe_filename(parsed_url.path.split('/')[-1])}"
            if not filename.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                filename += '.jpg'
            
            save_path = self.raw_images_dir / filename
            
            # 避免重复下载
            if save_path.exists():
                return False
            
            # 下载图片
            if download_image(img_url, save_path):
                # 验证图片
                if validate_image(save_path, self.config['quality_control']['image_filters']):
                    self.stats['total_collected'] += 1
                    return True
                else:
                    save_path.unlink(missing_ok=True)
                    return False
            else:
                self.stats['failed_downloads'] += 1
                return False
                
        except Exception as e:
            logger.debug(f"下载图片失败: {img_url}, 错误: {e}")
            self.stats['failed_downloads'] += 1
            return False
    
    def get_stats(self) -> Dict[str, int]:
        """获取收集统计信息"""
        return self.stats.copy()