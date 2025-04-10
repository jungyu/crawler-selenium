#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
基於架構的 Google 搜尋爬蟲範例
此範例展示如何使用專案提供的核心組件和提取器模組來實現搜尋結果爬取
"""

import os
import sys
import time
import logging
import json
import re  # 新增 re 模組的導入
from typing import Dict, List, Any, Optional

# 添加專案根目錄到 Python 路徑
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 現在可以導入專案模組
from src.core.config_loader import ConfigLoader
from src.core.webdriver_manager import WebDriverManager
from src.core.template_crawler import TemplateCrawler
from src.extractors import (
    ListExtractor,
    CaptchaHandler,
    PaginationHandler,
    StorageHandler
)
from src.extractors.core.detail_extractor import DetailExtractor
from src.extractors.config import ListExtractionConfig, ExtractionConfig
from src.core.crawler_state_manager import CrawlerStateManager

# 在其他導入之後添加
from selenium.webdriver.common.by import By


class GoogleSearchCrawler(TemplateCrawler):
    """Google 搜尋爬蟲，繼承自模板爬蟲"""
    
    def __init__(self, config_path: str):
        # 設置日誌記錄器
        self.logger = self._setup_logger()
        self.logger.info("初始化 Google 搜尋爬蟲")
        
        # 使用 ConfigLoader 載入配置
        self.config_loader = ConfigLoader(logger=self.logger)
        self.config = self.config_loader.load_config(config_path)
        
        # 設置更詳細的日誌層級
        if self.config.get("advanced_settings", {}).get("debug_mode", False):
            self.logger.setLevel(logging.DEBUG)
            self.logger.info("已啟用調試模式")
            
            # 添加 Selenium 的詳細日誌
            selenium_logger = logging.getLogger('selenium')
            selenium_logger.setLevel(logging.INFO)
            if not selenium_logger.handlers:
                # 創建處理器
                handler = logging.StreamHandler()
                formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
                handler.setFormatter(formatter)
                selenium_logger.addHandler(handler)
        
        # 初始化 WebDriver 管理器
        self.webdriver_manager = None
        self.driver = None
        
        # 結果存儲
        self.all_results = []
        self.detail_results = []
        
        # 初始化狀態管理器
        self.state_manager = CrawlerStateManager(
            crawler_id="google_search",
            config=self.config,
            state_dir=os.path.join(os.path.dirname(__file__), "..", "state"),
            log_level=logging.DEBUG if self.config.get("advanced_settings", {}).get("debug_mode", False) else logging.INFO
        )
        
        self.logger.info("Google 搜尋爬蟲初始化完成")
    
    # 在 _setup_logger 方法中修改
    def _setup_logger(self) -> logging.Logger:
        """設置日誌記錄器"""
        logger = logging.getLogger("GoogleSearchCrawler")
        logger.setLevel(logging.INFO)
        
        # 創建控制台處理器
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
        return logger

    def setup(self) -> bool:
        """
        設置爬蟲環境
        
        Returns:
            設置是否成功
        """
        try:
            self.logger.info("啟動 WebDriver")
            
            # 更新 WebDriverManager 的配置
            # 確保配置中包含所需的瀏覽器選項
            browser_config = self.config.get("browser", {})
            browser_config.update({
                "headless": False,  # 非無頭模式，可以看到驗證碼
                "disable_images": False,  # 確保加載圖片
                "page_load_timeout": 30,  # 增加超時時間
                "implicit_wait": 10  # 設置隱式等待時間
            })
            
            # 更新主配置中的瀏覽器配置
            self.config["browser"] = browser_config
            
            # 確保配置包含詳情頁設置
            if "detail_page" not in self.config:
                self.config["detail_page"] = {}
            self.config["detail_page"]["enabled"] = True
            
            # 初始化 WebDriverManager 與配置
            self.webdriver_manager = WebDriverManager(config=self.config, logger=self.logger)
            
            # 創建 WebDriver
            self.driver = self.webdriver_manager.create_driver()
            
            if not self.driver:
                self.logger.error("無法創建 WebDriver")
                return False
            
            # 初始化提取器
            self.list_extractor = ListExtractor(
                driver=self.driver,
                logger=self.logger
            )
            
            # 初始化詳情頁提取器
            self.detail_extractor = DetailExtractor(
                driver=self.driver,
                logger=self.logger,
                base_url=self.config.get("base_url", "https://www.google.com"),
                timeout=20
            )
            
            # 初始化特定處理器
            self.captcha_handler = CaptchaHandler(
                driver=self.driver, 
                logger=self.logger
            )
            
            # 初始化分頁處理器
            self.pagination_handler = PaginationHandler(
                driver=self.driver,
                logger=self.logger
            )
            
            # 初始化存儲處理器
            self.storage_handler = StorageHandler(logger=self.logger)
            
            return True
            
        except Exception as e:
            self.logger.error(f"設置爬蟲環境失敗: {str(e)}")
            return False

    def run(self) -> bool:
        """
        執行爬蟲任務
        
        Returns:
            爬蟲是否成功執行
        """
        try:
            if not self.setup():
                return False
            
            # 嘗試恢復上次的狀態
            saved_state = self.state_manager.get_state()
            if saved_state:
                self.logger.info("發現已保存的狀態，嘗試恢復...")
                self.all_results = saved_state.get("all_results", [])
                self.detail_results = saved_state.get("detail_results", [])
                current_page = saved_state.get("current_page", 1)
                self.logger.info(f"已恢復狀態：當前頁面 {current_page}，已有 {len(self.all_results)} 條結果")
            else:
                current_page = 1
                self.logger.info("未發現已保存的狀態，從頭開始爬取")
                
            # 打開搜尋頁面
            base_url = self.config.get("base_url", "https://www.google.com")
            self.logger.info(f"訪問 {self.config.get('site_name', 'Google')} 首頁: {base_url}")
            self.driver.get(base_url)
            
            # 執行搜尋
            search_keyword = self.config.get("search", {}).get("keyword", "Google")
            success = self.perform_search(search_keyword)
            if not success:
                self.logger.error("執行搜尋操作失敗")
                return False
            
            # 爬取多個頁面
            max_pages = self.config.get("pagination", {}).get("max_pages", 1)
            
            all_search_results = []  # 收集所有頁面的搜索結果
            
            while current_page <= max_pages:
                self.logger.info(f"處理第 {current_page} 頁")
                
                # 解析當前頁面結果
                page_results = self.extract_search_results()
                
                if not page_results:
                    self.logger.warning(f"第 {current_page} 頁未提取到結果")
                    break
                    
                self.all_results.extend(page_results)
                all_search_results.extend(page_results)  # 添加到總結果
                
                self.logger.info(f"第 {current_page} 頁找到 {len(page_results)} 條結果")
                
                # 保存當前狀態
                self.state_manager.save_state({
                    "current_page": current_page,
                    "all_results": self.all_results,
                    "detail_results": self.detail_results
                })
                
                # 檢查是否需要繼續下一頁
                if current_page >= max_pages or not self.has_next_page():
                    break
                
                # 前往下一頁
                self.logger.info(f"前往第 {current_page + 1} 頁...")
                if not self.go_to_next_page():
                    self.logger.warning("無法前往下一頁，結束爬取")
                    break
                
                current_page += 1
                
                # 頁面間延遲
                between_pages_delay = self.config.get("delays", {}).get("between_pages", 2)
                time.sleep(between_pages_delay)
            
            # 修改: 強制啟用詳情頁提取
            if all_search_results:
                self.logger.info("開始提取詳情頁內容...")
                # 確保 detail_page.enabled 設置為 True
                if "detail_page" not in self.config:
                    self.config["detail_page"] = {}
                self.config["detail_page"]["enabled"] = True
                self.extract_detail_pages(all_search_results)
            
            # 保存結果
            self.save_results()
            
            # 標記任務完成
            self.state_manager.mark_completed()
            
            self.logger.info(f"完成爬取 {current_page} 頁，共 {len(self.all_results)} 條結果，{len(self.detail_results)} 個詳情頁")
            return True
            
        except Exception as e:
            self.logger.error(f"爬蟲執行失敗: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            self.handle_error()
            return False
            
        finally:
            self.cleanup()

    def perform_search(self, keyword: str) -> bool:
        """
        執行搜尋操作
        
        Args:
            keyword: 搜尋關鍵字
            
        Returns:
            是否成功執行搜尋
        """
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            
            # 獲取搜尋框配置
            search_box_xpath = self.config.get("search_page", {}).get("search_box_xpath", "//textarea[@name='q']")
            
            # 找到搜尋框並輸入關鍵詞
            self.logger.info(f"搜尋關鍵詞: {keyword}")
            
            # 使用正確的參數順序調用 wait_for_element 方法
            search_box = self.list_extractor.wait_for_element(
                By.XPATH,  # 第一個參數是 by
                search_box_xpath,  # 第二個參數是 selector
                timeout=10
            )
            
            if not search_box:
                self.logger.error(f"找不到搜尋框元素: {search_box_xpath}")
                # 嘗試更多選擇器
                alternative_selectors = [
                    "//input[@name='q']", 
                    "//input[@title='搜尋']",
                    "//textarea[@title='搜尋']"
                ]
                for selector in alternative_selectors:
                    self.logger.info(f"嘗試備用搜尋框選擇器: {selector}")
                    search_box = self.list_extractor.wait_for_element(By.XPATH, selector, timeout=5)
                    if search_box:
                        self.logger.info(f"使用備用選擇器 {selector} 找到搜尋框")
                        break
                        
                if not search_box:
                    self.logger.error("所有選擇器都找不到搜尋框，無法繼續")
                    return False
            
            # 清除並輸入搜尋關鍵詞
            search_box.clear()
            search_box.send_keys(keyword)
            
            # 嘗試提交搜尋
            try:
                search_box.send_keys(Keys.RETURN)
            except:
                try:
                    search_box.submit()
                except:
                    self.logger.warning("無法使用常規方法提交搜尋，嘗試使用JavaScript點擊")
                    self.driver.execute_script("document.querySelector('form[action*=\"search\"]').submit();")
            
            # 等待搜尋結果載入
            result_container_xpath = self.config.get("search_page", {}).get("result_container_xpath", "//div[@id='search']")
            
            # 使用正確的參數順序調用 wait_for_element 方法
            result_container = self.list_extractor.wait_for_element(
                By.XPATH,  # 第一個參數是 by
                result_container_xpath,  # 第二個參數是 selector
                timeout=15
            )
            
            if not result_container:
                self.logger.warning(f"未找到結果容器: {result_container_xpath}")
                # 嘗試更多備用容器選擇器
                alternative_containers = [
                    "//div[@id='rso']",
                    "//div[@id='main']",
                    "//div[@id='center_col']",
                    "//div[contains(@class, 'g')]"
                ]
                
                for selector in alternative_containers:
                    self.logger.info(f"嘗試備用結果容器選擇器: {selector}")
                    result_container = self.list_extractor.wait_for_element(By.XPATH, selector, timeout=5)
                    if result_container:
                        self.logger.info(f"使用備用選擇器 {selector} 找到結果容器")
                        break
            
            # 如果還是找不到，我們等待一段時間然後繼續
            if not result_container:
                self.logger.warning("無法找到任何結果容器，等待頁面完全載入後繼續")
                # 等待頁面載入
                time.sleep(5)
            
            # 頁面載入延遲
            page_load_delay = self.config.get("delays", {}).get("page_load", 1)
            time.sleep(page_load_delay)
            
            return True
            
        except Exception as e:
            self.logger.error(f"執行搜尋操作失敗: {str(e)}")
            return False

    def extract_detail_pages(self, search_results: List[Dict[str, Any]]) -> None:
        """
        提取搜尋結果中的詳情頁面數據
        
        Args:
            search_results: 搜尋結果列表
        """
        # 獲取詳情頁配置
        detail_config = self.config.get("detail_page", {})
        
        # 強制啟用詳情頁面提取
        detail_config["enabled"] = True
        
        # 初始化詳情結果列表
        self.detail_results = []
        
        # 獲取最大處理數量
        max_details = detail_config.get("max_details_per_page", 3)
        details_to_process = search_results[:max_details]

        self.logger.info(f"準備提取 {len(details_to_process)} 個詳情頁")

        for index, result in enumerate(details_to_process):
            try:
                # 確保從搜尋結果中獲取詳情頁URL
                url = result.get("link")
                if not url:
                    # 嘗試從其他可能的字段獲取URL
                    url = result.get("url") or result.get("href")
                    if not url:
                        self.logger.warning(f"結果 #{index} 缺少 URL，跳過")
                        continue

                self.logger.info(f"訪問詳情頁 #{index+1}: {url}")

                # 使用 NavigateToPage 函數訪問頁面並處理可能的錯誤
                success = self._navigate_to_detail_page(url, detail_config.get("page_load_delay", 3))
                if not success:
                    self.logger.warning(f"詳情頁 #{index+1} 導航失敗，跳過")
                    # 添加基本信息
                    error_detail = {
                        "title": result.get("title", ""),
                        "link": url,
                        "description": result.get("description", ""),
                        "_search_result": result,
                        "extraction_status": "navigation_failed"
                    }
                    self.detail_results.append(error_detail)
                    continue
                
                # 檢查並處理可能的驗證碼
                if detail_config.get("check_captcha", True):
                    captcha_detected = self._check_and_handle_captcha()
                    if captcha_detected:
                        self.logger.info("驗證碼處理完成，繼續提取")
                
                # 展開需要展開的區塊
                expand_sections = detail_config.get("expand_sections", [])
                if expand_sections:
                    self.detail_extractor.expand_sections(expand_sections)
                    # 展開後等待內容加載
                    time.sleep(1)
                
                # 如果沒有設置容器xpath，使用更通用的選擇器
                container_xpath = detail_config.get("container_xpath", "//body")
                
                try:
                    self.logger.info(f"正在使用容器: {container_xpath} 提取詳情頁內容")
                    
                    # 使用 DetailExtractor 提取詳情頁內容
                    detail_data = self.detail_extractor.extract_detail_page(
                        detail_config=detail_config,
                        container_xpath=container_xpath
                    )
                    
                    # 提取圖片（如果配置了）
                    if detail_config.get("extract_images", False):
                        images_container = detail_config.get("images_container_xpath", container_xpath)
                        images = self.detail_extractor.extract_images(images_container)
                        if images:
                            detail_data["images"] = images
                            self.logger.info(f"提取到 {len(images)} 張圖片")
                    
                    # 添加搜尋結果資訊
                    detail_data["_search_result"] = result
                    detail_data["title"] = detail_data.get("title") or result.get("title", "")
                    detail_data["link"] = url
                    detail_data["extraction_status"] = "success"
                    
                    # 添加到詳情結果列表
                    self.detail_results.append(detail_data)
                    
                    # 保存當前狀態
                    self.state_manager.save_state({
                        "current_page": self.state_manager.get_state().get("current_page", 1),
                        "all_results": self.all_results,
                        "detail_results": self.detail_results
                    })
                    
                    self.logger.info(f"詳情頁 #{index+1} 提取成功，字段數: {len(detail_data)}")
                    
                except Exception as e:
                    self.logger.error(f"提取詳情頁 #{index+1} 內容時出錯: {str(e)}")
                    # 添加基本信息
                    error_detail = {
                        "title": result.get("title", ""),
                        "link": url,
                        "_search_result": result,
                        "extraction_status": "error",
                        "error_message": str(e)
                    }
                    self.detail_results.append(error_detail)
                    
            except Exception as e:
                self.logger.error(f"處理詳情頁 #{index+1} 時出錯: {str(e)}")
                import traceback
                self.logger.error(traceback.format_exc())
                
                # 即使出錯也添加基本信息
                error_detail = {
                    "title": result.get("title", "") if 'result' in locals() else f"未知標題 #{index+1}",
                    "link": url if 'url' in locals() else "未知URL",
                    "extraction_status": "exception",
                    "error_message": str(e)
                }
                self.detail_results.append(error_detail)
        
        # 添加 save_results 方法來保存結果

    def _navigate_to_detail_page(self, url: str, wait_time: int = 3) -> bool:
        """
        導航到詳情頁面並處理可能的錯誤
        
        Args:
            url: 詳情頁URL
            wait_time: 頁面載入後等待時間
            
        Returns:
            是否成功導航
        """
        try:
            # 儲存當前URL以備返回
            original_url = self.driver.current_url
            
            # 訪問詳情頁
            self.driver.get(url)
            
            # 等待頁面載入
            time.sleep(wait_time)
            
            # 檢查頁面是否成功載入（URL是否變更）
            if self.driver.current_url == original_url:
                self.logger.warning(f"導航失敗，URL未變更: {url}")
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"導航到詳情頁面 {url} 失敗: {str(e)}")
            return False

    def _is_page_valid(self) -> bool:
        """
        檢查當前頁面是否有效
        
        Returns:
            頁面是否有效
        """
        try:
            # 檢查頁面標題
            title = self.driver.title.lower()
            body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            
            invalid_patterns = ["404", "not found", "error", "無法連接", "不存在", "服務暫停"]
            
            # 檢查標題是否含有錯誤關鍵字
            for pattern in invalid_patterns:
                if pattern in title:
                    self.logger.warning(f"頁面標題包含無效關鍵字: '{pattern}'")
                    return False
            
            # 檢查是否有主要內容
            if len(body_text) < 100:  # 太短的內容可能是錯誤頁面
                self.logger.warning("頁面內容過短，可能是錯誤頁面")
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"檢查頁面有效性時出錯: {str(e)}")
            return False

    def _check_and_handle_captcha(self) -> bool:
        """
        檢查並處理可能的驗證碼
        
        Returns:
            是否檢測到驗證碼
        """
        try:
            # 檢查常見的驗證碼標記
            captcha_selectors = [
                "//div[contains(@class, 'g-recaptcha')]",
                "//iframe[contains(@src, 'recaptcha')]",
                "//div[contains(text(), '驗證')]",
                "//div[contains(text(), 'captcha')]"
            ]
            
            for selector in captcha_selectors:
                captcha_elements = self.driver.find_elements(By.XPATH, selector)
                if captcha_elements and any(el.is_displayed() for el in captcha_elements):
                    self.logger.warning("檢測到驗證碼，需手動處理...")
                    
                    # 截圖
                    screenshot_path = f"captcha_{int(time.time())}.png"
                    self.driver.save_screenshot(screenshot_path)
                    self.logger.info(f"驗證碼截圖已保存至: {screenshot_path}")
                    
                    # 等待手動處理
                    input("請手動解決驗證碼，完成後按 Enter 繼續...")
                    
                    return True
                    
            return False
            
        except Exception as e:
            self.logger.error(f"檢查驗證碼時出錯: {str(e)}")
            return False

    def extract_search_results(self) -> List[Dict[str, Any]]:
        self.logger.info("開始提取搜索結果...")
        
        # 打印頁面標題，幫助調試
        try:
            self.logger.info(f"當前頁面標題: {self.driver.title}")
        except:
            pass
            
        # 手動處理驗證碼
        if "recaptcha" in self.driver.page_source.lower() or "驗證" in self.driver.page_source:
            self.logger.warning("頁面可能需要驗證，請手動解決驗證碼")
            self.driver.save_screenshot("captcha_needed.png")
            # 給予足夠時間進行手動處理
            time.sleep(30)

        # 使用配置中的參數
        container_xpath = self.config.get("list_page", {}).get("container_xpath", "//div[@id='search']")
        item_xpath = self.config.get("list_page", {}).get("item_xpath", "//div[contains(@class, 'N54PNb')]")
        fields = self.config.get("list_page", {}).get("fields", {})
        max_items = self.config.get("advanced_settings", {}).get("max_results_per_page", 10)
        
        # 將原始字段配置轉換為 ExtractionConfig 對象字典
        field_configs = {}
        for field_name, field_config_dict in fields.items():
            field_configs[field_name] = ExtractionConfig(
                xpath=field_config_dict.get("xpath"),
                type=field_config_dict.get("type", "text"),
                attribute=field_config_dict.get("attribute"),
                default=field_config_dict.get("default"),
                fallback_xpath=field_config_dict.get("fallback_xpath"),
                max_length=field_config_dict.get("max_length")
            )
        
        # 創建 ListExtractionConfig 對象（移除不支援的 source_name 參數）
        config = ListExtractionConfig(
            container_xpath=container_xpath,
            item_xpath=item_xpath,
            fields=field_configs,
            max_items=max_items,
            wait_time=5.0,
            scroll_after_load=True
        )
        
        # 添加別名：將 field_configs 設置為 fields 的別名
        setattr(config, 'field_configs', config.fields)
        
        # 設置 extraction_delay 屬性
        setattr(config, 'extraction_delay', 0.5)
        
        # 添加缺少的 source_name 屬性
        setattr(config, 'source_name', self.config.get('site_name', 'Google Search'))
        
        # 添加調試日誌
        self.logger.info(f"開始提取搜尋結果，container_xpath={container_xpath}, item_xpath={item_xpath}")
        
        try:
            # 嘗試提取結果
            results = self.list_extractor.extract(config)
            self.logger.info(f"已提取 {len(results)} 條搜尋結果")
            
            # 為結果添加元數據
            for result in results:
                if '_metadata' not in result:
                    result['_metadata'] = {}
                result['_metadata']['site'] = self.config.get('site_name', 'Google Search')
                result['_metadata']['timestamp'] = int(time.time())
            
            # 如果沒有結果，嘗試更多選擇器
            if not results:
                self.logger.warning("未找到結果，嘗試更多 Google 選擇器...")
                
                # 嘗試更廣泛的 Google 搜尋選擇器
                alternative_selectors = [
                    "//div[@id='rso']/div",  
                    "//div[@id='search']//div[@class='g']", 
                    "//div[@id='search']//div[contains(@class, 'g')]",
                    "//div[contains(@class, 'yuRUbf')]/..",
                    "//div[@id='search']//div[@jscontroller]",  # 更通用選擇器
                    "//div[@id='search']//div[contains(@class, 'v7W49e')]",
                    "//div[@id='search']//div[contains(@class, 'MjjYud')]",
                    "//div[@id='search']//a[h3]/..",  # 包含h3的鏈接父元素
                    "//div[@id='center_col']//div[.//h3]"  # 包含h3的任何div
                ]
                
                for alt_selector in alternative_selectors:
                    self.logger.info(f"嘗試選擇器: {alt_selector}")
                    # 檢查選擇器能找到的元素數量
                    elements = self.driver.find_elements(By.XPATH, alt_selector)
                    self.logger.info(f"選擇器 {alt_selector} 找到 {len(elements)} 個元素")
                    
                    if elements:
                        config.item_xpath = alt_selector
                        # 更新別名
                        setattr(config, 'field_configs', config.fields)
                        results = self.list_extractor.extract(config)
                        if results:
                            self.logger.info(f"使用選擇器 {alt_selector} 找到 {len(results)} 條結果")
                            break
            
            return results or []
            
        except Exception as e:
            self.logger.error(f"提取搜尋結果時發生錯誤: {str(e)}")
            import traceback
            self.logger.debug(traceback.format_exc())
            
            # 保存頁面源碼以便調試
            try:
                with open("debug_page_source.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                self.logger.info("已保存頁面源碼到 debug_page_source.html")
            except:
                pass
                
            return []

    def has_next_page(self) -> bool:
        """
        檢查是否有下一頁
        
        Returns:
            是否存在下一頁
        """
        next_button_xpath = self.config.get("pagination", {}).get("next_button_xpath", "//a[@id='pnnext']")
        
        if not next_button_xpath:
            return False
        
        # 直接檢查元素是否存在
        try:
            elements = self.driver.find_elements(By.XPATH, next_button_xpath)
            return len(elements) > 0
        except Exception as e:
            self.logger.error(f"檢查下一頁時出錯: {str(e)}")
            return False

    def go_to_next_page(self) -> bool:
        """前往下一頁"""
        next_button_xpath = self.config.get("pagination", {}).get("next_button_xpath", "//a[@id='pnnext']")
        between_pages_delay = self.config.get("delays", {}).get("between_pages", 2)
        
        self.logger.info(f"嘗試點擊下一頁按鈕: {next_button_xpath}")
        
        try:
            # 使用 JavaScript 點擊
            elements = self.driver.find_elements(By.XPATH, next_button_xpath)
            if elements:
                # 滾動到按鈕位置
                self.driver.execute_script("arguments[0].scrollIntoView(true);", elements[0])
                time.sleep(1)  # 等待滾動完成
                
                # 使用 JavaScript 點擊
                self.driver.execute_script("arguments[0].click();", elements[0])
                self.logger.info("已使用 JavaScript 點擊下一頁按鈕")
                time.sleep(between_pages_delay)
                return True
            else:
                self.logger.warning("找不到下一頁按鈕")
                return False
        except Exception as e:
            self.logger.error(f"前往下一頁時出錯: {str(e)}")
            return False

    def save_results(self) -> None:
        """
        保存爬取結果到檔案
        """
        try:
            # 創建輸出目錄
            output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
            os.makedirs(output_dir, exist_ok=True)
            
            # 獲取當前時間戳
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            
            # 保存搜尋結果
            if self.all_results:
                search_results_file = os.path.join(output_dir, f"google_搜尋_results_{timestamp}.json")
                with open(search_results_file, "w", encoding="utf-8") as f:
                    json.dump(self.all_results, f, ensure_ascii=False, indent=2)
                self.logger.info(f"搜尋結果已保存至: {search_results_file}")
                
            # 保存詳情頁結果
            if self.detail_results:
                details_file = os.path.join(output_dir, f"google_搜尋_details_{timestamp}.json")
                with open(details_file, "w", encoding="utf-8") as f:
                    json.dump(self.detail_results, f, ensure_ascii=False, indent=2)
                self.logger.info(f"詳情頁結果已保存至: {details_file}")
                
        except Exception as e:
            self.logger.error(f"保存結果失敗: {str(e)}")

    def _sanitize_dict(self, d: Dict) -> Dict:
        """處理字典對象，確保可序列化"""
        result = {}
        for k, v in d.items():
            if isinstance(v, (str, int, float, bool, type(None))):
                result[k] = v
            elif isinstance(v, (list, tuple)):
                result[k] = self._sanitize_list(v)
            elif isinstance(v, dict):
                result[k] = self._sanitize_dict(v)
            else:
                result[k] = str(v)
        return result

    def _sanitize_list(self, lst: List) -> List:
        """處理列表對象，確保可序列化"""
        result = []
        for item in lst:
            if isinstance(item, (str, int, float, bool, type(None))):
                result.append(item)
            elif isinstance(item, (list, tuple)):
                result.append(self._sanitize_list(item))
            elif isinstance(item, dict):
                result.append(self._sanitize_dict(item))
            else:
                result.append(str(item))
        return result

        if hasattr(self, 'detail_extractor') and self.detail_extractor:
            stats = self.detail_extractor.get_statistics()
            self.logger.info(f"詳情頁提取統計: {stats}")

    def handle_error(self) -> None:
        """處理錯誤，保存錯誤頁面截圖和源碼"""
        if not self.driver:
            return
            
        # 檢查是否需要保存錯誤頁面
        if not self.config.get("advanced_settings", {}).get("save_error_page", False):
            return
            
        try:
            # 獲取錯誤頁面保存目錄
            error_dir = self.config.get("advanced_settings", {}).get("error_page_dir", "../debug")
            os.makedirs(error_dir, exist_ok=True)
            
            # 生成檔案名
            timestamp = int(time.time())
            filename_base = f"error_{timestamp}"
            
            # 儲存截圖
            screenshot_path = os.path.join(error_dir, f"{filename_base}.png")
            self.driver.save_screenshot(screenshot_path)
            
            # 儲存頁面源碼
            html_path = os.path.join(error_dir, f"{filename_base}.html")
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
                
            self.logger.info(f"已儲存錯誤頁面: 截圖={screenshot_path}, HTML={html_path}")
        except Exception as e:
            self.logger.error(f"儲存錯誤頁面失敗: {str(e)}")

    def cleanup(self) -> None:
        """清理資源，關閉瀏覽器"""
        if self.driver:
            self.logger.info("關閉瀏覽器...")
            self.driver.quit()
            self.driver = None
        
        # 清理狀態管理器
        if hasattr(self, 'state_manager'):
            self.state_manager.cleanup()
        
        self.logger.info("爬蟲程序已完成")

    def handle_captcha(self, xpath: str) -> bool:
        """處理驗證碼，給用戶足夠時間手動解決"""
        try:
            if self.captcha_handler.detect_captcha(xpath):
                self.logger.warning("檢測到驗證碼，請手動解決...")
                
                # 增加足夠的等待時間讓用戶解決驗證碼
                # 用戶有 30 秒的時間來解決驗證碼
                time.sleep(30)
                
                self.logger.info("恢復爬蟲操作...")
                return True
                
            return False
        except Exception as e:
            self.logger.error(f"處理驗證碼時出錯: {str(e)}")
            return False


def main() -> None:
    """主函數：執行 Google 搜尋爬蟲"""
    # 取得配置文件路徑
    config_path = os.path.join(os.path.dirname(__file__), "basic_google_search.json")
    
    # 檢查配置文件是否存在
    if not os.path.exists(config_path):
        print(f"錯誤: 配置文件不存在 - {config_path}")
        sys.exit(1)
    
    # 創建爬蟲實例
    crawler = GoogleSearchCrawler(config_path)
    
    # 執行爬蟲
    success = crawler.run()
    
    # 顯示執行結果
    if success:
        print("爬蟲成功完成!")
    else:
        print("爬蟲執行失敗!")
        sys.exit(1)


if __name__ == "__main__":
    main()