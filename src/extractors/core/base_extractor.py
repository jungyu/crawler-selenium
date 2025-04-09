#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
基礎提取器模組

定義基本的提取器接口和共用功能。

主要功能：
- 元素等待和查找
- 頁面導航和滾動
- 截圖和源碼保存
- 統計信息收集
- 工具類整合

使用示例：
    from src.extractors.core import BaseExtractor
    
    class MyExtractor(BaseExtractor):
        def extract(self, config):
            # 等待元素出現
            element = self.wait_for_element(By.ID, "target")
            
            # 提取數據
            data = element.text
            
            # 返回結果
            return data
"""

import logging
import random
import time
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union, Set

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from ..config import ExtractionConfig
from ..utils.text_cleaner import TextCleaner
from ..utils.url_normalizer import URLNormalizer
from ..utils.html_cleaner import HTMLCleaner
from ..utils.date_parser import DateParser
from ..utils.number_parser import NumberParser


class BaseExtractor(ABC):
    """基礎提取器抽象類
    
    定義共用方法和抽象接口，提供基本的提取功能。
    
    Attributes:
        driver: Selenium WebDriver實例
        base_url: 基礎URL
        logger: 日誌記錄器
        default_timeout: 默認等待超時時間
        visited_urls: 已訪問的URL集合
        text_cleaner: 文本清理工具
        url_normalizer: URL標準化工具
        html_cleaner: HTML清理工具
        date_parser: 日期解析工具
        number_parser: 數字解析工具
        extracted_items_count: 已提取項目數
        extracted_fields_count: 已提取字段數
        extraction_errors_count: 提取錯誤數
    """
    
    def __init__(
        self, 
        driver: Optional[webdriver.Remote] = None, 
        base_url: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        timeout: int = 10
    ):
        """
        初始化基礎提取器
        
        Args:
            driver: Selenium WebDriver實例
            base_url: 基礎URL，用於URL標準化
            logger: 日誌記錄器
            timeout: 默認等待超時時間(秒)
        """
        self.driver = driver
        self.base_url = base_url
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.default_timeout = timeout
        
        # 用於追蹤訪問過的URL
        self.visited_urls: Set[str] = set()
        
        # 初始化工具類
        self.text_cleaner = TextCleaner()
        self.url_normalizer = URLNormalizer()
        self.html_cleaner = HTMLCleaner(base_url)
        self.date_parser = DateParser()
        self.number_parser = NumberParser()
        
        # 統計計數
        self.extracted_items_count = 0
        self.extracted_fields_count = 0
        self.extraction_errors_count = 0
    
    def set_driver(self, driver: webdriver.Remote) -> None:
        """
        設置WebDriver實例
        
        Args:
            driver: Selenium WebDriver實例
        """
        self.driver = driver
        self.logger.info("WebDriver已更新")
    
    def set_base_url(self, base_url: str) -> None:
        """
        設置基礎URL
        
        Args:
            base_url: 基礎URL
        """
        self.base_url = base_url
        self.html_cleaner.set_base_url(base_url)
        self.logger.info(f"基礎URL已更新: {base_url}")
    
    def reset_statistics(self) -> None:
        """重置統計計數"""
        self.extracted_items_count = 0
        self.extracted_fields_count = 0
        self.extraction_errors_count = 0
        self.visited_urls.clear()
        self.logger.debug("提取統計已重置")
    
    def get_statistics(self) -> Dict[str, int]:
        """
        獲取統計信息
        
        Returns:
            包含統計信息的字典
        """
        return {
            "extracted_items": self.extracted_items_count,
            "extracted_fields": self.extracted_fields_count,
            "extraction_errors": self.extraction_errors_count,
            "visited_urls": len(self.visited_urls)
        }
    
    def wait_for_element(
        self, 
        by: By, 
        selector: str, 
        timeout: Optional[int] = None,
        parent: Optional[WebElement] = None
    ) -> Optional[WebElement]:
        """
        等待元素出現
        
        Args:
            by: 定位方式
            selector: 選擇器
            timeout: 超時時間(秒)
            parent: 父元素
            
        Returns:
            找到的元素，如果超時則返回None
        """
        if not self.driver:
            self.logger.warning("WebDriver未初始化")
            return None
        
        try:
            wait = WebDriverWait(self.driver, timeout or self.default_timeout)
            if parent:
                return wait.until(EC.presence_of_element_located((by, selector)), parent)
            return wait.until(EC.presence_of_element_located((by, selector)))
        except TimeoutException:
            self.logger.warning(f"等待元素超時: {by}={selector}")
            return None
        except Exception as e:
            self.logger.error(f"等待元素出錯: {str(e)}")
            return None
    
    def wait_for_elements(
        self, 
        by: By, 
        selector: str, 
        timeout: Optional[int] = None,
        parent: Optional[WebElement] = None
    ) -> List[WebElement]:
        """
        等待多個元素出現
        
        Args:
            by: 定位方式
            selector: 選擇器
            timeout: 超時時間(秒)
            parent: 父元素
            
        Returns:
            找到的元素列表
        """
        if not self.driver:
            self.logger.warning("WebDriver未初始化")
            return []
        
        try:
            wait = WebDriverWait(self.driver, timeout or self.default_timeout)
            if parent:
                return wait.until(EC.presence_of_all_elements_located((by, selector)), parent)
            return wait.until(EC.presence_of_all_elements_located((by, selector)))
        except TimeoutException:
            self.logger.warning(f"等待元素超時: {by}={selector}")
            return []
        except Exception as e:
            self.logger.error(f"等待元素出錯: {str(e)}")
            return []
    
    def wait_for_clickable(
        self, 
        by: By, 
        selector: str, 
        timeout: Optional[int] = None
    ) -> Optional[WebElement]:
        """
        等待元素可點擊
        
        Args:
            by: 定位方式
            selector: 選擇器
            timeout: 超時時間(秒)
            
        Returns:
            可點擊的元素，如果超時則返回None
        """
        if not self.driver:
            self.logger.warning("WebDriver未初始化")
            return None
        
        try:
            wait = WebDriverWait(self.driver, timeout or self.default_timeout)
            return wait.until(EC.element_to_be_clickable((by, selector)))
        except TimeoutException:
            self.logger.warning(f"等待元素可點擊超時: {by}={selector}")
            return None
        except Exception as e:
            self.logger.error(f"等待元素可點擊出錯: {str(e)}")
            return None
    
    def safe_click(self, element: WebElement, retries: int = 3) -> bool:
        """
        安全點擊元素
        
        Args:
            element: 要點擊的元素
            retries: 重試次數
            
        Returns:
            是否點擊成功
        """
        if not self.driver:
            self.logger.warning("WebDriver未初始化")
            return False
        
        for i in range(retries):
            try:
                # 嘗試直接點擊
                element.click()
                return True
            except Exception as e:
                self.logger.warning(f"直接點擊失敗 (嘗試 {i+1}/{retries}): {str(e)}")
                
                try:
                    # 嘗試滾動到元素
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                    time.sleep(0.5)
                    
                    # 使用JavaScript點擊
                    self.driver.execute_script("arguments[0].click();", element)
                    return True
                except Exception as js_e:
                    self.logger.warning(f"JavaScript點擊失敗 (嘗試 {i+1}/{retries}): {str(js_e)}")
                    
                    if i == retries - 1:
                        self.logger.error("所有點擊嘗試均失敗")
                        return False
                    
                    # 短暫延遲後重試
                    time.sleep(1)
        
        return False
    
    def navigate_to_url(self, url: str, timeout: Optional[int] = None) -> bool:
        """
        導航到指定URL
        
        Args:
            url: 目標URL
            timeout: 超時時間(秒)
            
        Returns:
            是否導航成功
        """
        if not self.driver:
            self.logger.warning("WebDriver未初始化")
            return False
        
        try:
            self.logger.info(f"導航到: {url}")
            self.driver.set_page_load_timeout(timeout or self.default_timeout)
            self.driver.get(url)
            self._wait_for_page_load(timeout)
            return True
        except TimeoutException:
            self.logger.error(f"頁面加載超時: {url}")
            return False
        except Exception as e:
            self.logger.error(f"導航失敗: {str(e)}")
            return False
    
    def _wait_for_page_load(self, timeout: Optional[int] = None) -> None:
        """
        等待頁面加載完成
        
        Args:
            timeout: 超時時間(秒)
        """
        if not self.driver:
            return
        
        try:
            wait = WebDriverWait(self.driver, timeout or self.default_timeout)
            wait.until(lambda driver: driver.execute_script("return document.readyState") == "complete")
        except TimeoutException:
            self.logger.warning("等待頁面加載超時")
        except Exception as e:
            self.logger.error(f"等待頁面加載出錯: {str(e)}")
    
    def random_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        """
        隨機延遲
        
        Args:
            min_seconds: 最小延遲時間(秒)
            max_seconds: 最大延遲時間(秒)
        """
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
    
    def scroll_page(self, direction: str = "down", amount: int = 300) -> None:
        """
        滾動頁面
        
        Args:
            direction: 滾動方向 ("up", "down", "top", "bottom")
            amount: 滾動距離(像素)
        """
        if not self.driver:
            self.logger.warning("WebDriver未初始化")
            return
        
        try:
            if direction == "down":
                self.driver.execute_script(f"window.scrollBy(0, {amount});")
            elif direction == "up":
                self.driver.execute_script(f"window.scrollBy(0, -{amount});")
            elif direction == "top":
                self.driver.execute_script("window.scrollTo(0, 0);")
            elif direction == "bottom":
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except Exception as e:
            self.logger.error(f"滾動頁面失敗: {str(e)}")
    
    def take_screenshot(self, filepath: Optional[str] = None) -> Optional[str]:
        """
        截取頁面截圖
        
        Args:
            filepath: 保存路徑
            
        Returns:
            截圖文件路徑，如果失敗則返回None
        """
        if not self.driver:
            self.logger.warning("WebDriver未初始化")
            return None
        
        try:
            if not filepath:
                # 生成默認文件名
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filepath = f"screenshot_{timestamp}.png"
            
            # 確保目錄存在
            os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
            
            # 截圖
            self.driver.save_screenshot(filepath)
            self.logger.info(f"截圖已保存: {filepath}")
            return filepath
        except Exception as e:
            self.logger.error(f"截圖失敗: {str(e)}")
            return None
    
    def save_page_source(self, filepath: Optional[str] = None) -> Optional[str]:
        """
        保存頁面源碼
        
        Args:
            filepath: 保存路徑
            
        Returns:
            源碼文件路徑，如果失敗則返回None
        """
        if not self.driver:
            self.logger.warning("WebDriver未初始化")
            return None
        
        try:
            if not filepath:
                # 生成默認文件名
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filepath = f"page_source_{timestamp}.html"
            
            # 確保目錄存在
            os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
            
            # 保存源碼
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            
            self.logger.info(f"頁面源碼已保存: {filepath}")
            return filepath
        except Exception as e:
            self.logger.error(f"保存頁面源碼失敗: {str(e)}")
            return None
    
    def execute_script(self, script: str, *args) -> Any:
        """
        執行JavaScript腳本
        
        Args:
            script: JavaScript腳本
            *args: 腳本參數
            
        Returns:
            腳本執行結果
        """
        if not self.driver:
            self.logger.warning("WebDriver未初始化")
            return None
        
        try:
            return self.driver.execute_script(script, *args)
        except Exception as e:
            self.logger.error(f"執行腳本失敗: {str(e)}")
            return None
    
    def is_page_valid(self) -> bool:
        """
        檢查頁面是否有效
        
        Returns:
            頁面是否有效
        """
        if not self.driver:
            return False
        
        try:
            # 檢查頁面標題
            title = self.driver.title.lower()
            invalid_titles = ["error", "404", "not found", "forbidden"]
            if any(t in title for t in invalid_titles):
                return False
            
            # 檢查頁面內容
            body = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            invalid_texts = ["error", "404", "not found", "forbidden", "access denied"]
            if any(t in body for t in invalid_texts):
                return False
            
            return True
        except Exception as e:
            self.logger.error(f"檢查頁面有效性失敗: {str(e)}")
            return False
    
    @abstractmethod
    def extract(self, config: Any) -> Any:
        """
        提取數據的抽象方法
        
        Args:
            config: 提取配置
            
        Returns:
            提取的數據
        """
        pass