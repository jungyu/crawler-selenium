#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import logging
import threading
import queue
from typing import Dict, List, Optional, Any, Union, Callable

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, 
    NoSuchElementException, 
    StaleElementReferenceException
)

from .webdriver_manager import WebDriverManager
from .template_crawler import TemplateCrawler
from ..utils.logger import setup_logger
from ..utils.error_handler import retry_on_exception, handle_exception
from ..anti_detection.anti_detection_manager import AntiDetectionManager
from ..captcha.captcha_manager import CaptchaManager
from ..state.crawler_state_manager import CrawlerStateManager
from ..persistence.data_persistence_manager import DataPersistenceManager


class CrawlerEngine:
    """
    爬蟲引擎，負責協調各個組件的工作。
    提供多線程爬取、任務隊列管理、錯誤處理等功能。
    """
    
    def __init__(
        self,
        config_file: str = "config/config.json",
        log_level: int = logging.INFO
    ):
        """
        初始化爬蟲引擎
        
        Args:
            config_file: 配置文件路徑
            log_level: 日誌級別
        """
        self.logger = setup_logger(__name__, log_level)
        self.logger.info(f"初始化爬蟲引擎，配置: {config_file}")
        
        # 載入配置
        from ..utils.config_loader import ConfigLoader
        self.config = ConfigLoader.load_config(config_file)
        self.engine_config = self.config.get("engine_config", {})
        
        # 任務隊列和結果
        self.task_queue = queue.Queue()
        self.result_queue = queue.Queue()
        
        # 線程池
        self.threads = []
        self.max_threads = self.engine_config.get("max_threads", 1)
        self.active_threads = 0
        
        # 運行狀態
        self.is_running = False
        self.stop_requested = False
        
        # 統計信息
        self.stats = {
            "tasks_total": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "items_scraped": 0,
            "start_time": None,
            "end_time": None
        }
        
        # 初始化數據持久化管理器
        persistence_config = self.config.get("persistence_config", {})
        self.data_manager = DataPersistenceManager(persistence_config)
        
        # 狀態鎖
        self.thread_lock = threading.Lock()
        self.logger.info("爬蟲引擎初始化完成")
    
    def add_task(self, template_file: str, task_config: Dict = None):
        """
        添加爬蟲任務
        
        Args:
            template_file: 模板文件路徑
            task_config: 任務配置，可以覆蓋默認配置
        """
        task = {
            "template_file": template_file,
            "config": task_config or {},
            "id": os.path.basename(template_file).replace(".json", "")
        }
        
        with self.thread_lock:
            self.stats["tasks_total"] += 1
        
        self.task_queue.put(task)
        self.logger.info(f"添加任務: {task['id']}")
    
    def add_tasks_from_directory(self, directory: str, filter_pattern: str = "*.json"):
        """
        從目錄中添加所有匹配的模板文件作為任務
        
        Args:
            directory: 模板目錄路徑
            filter_pattern: 文件過濾模式
        """
        import glob
        template_files = glob.glob(os.path.join(directory, filter_pattern))
        
        if not template_files:
            self.logger.warning(f"在目錄 {directory} 中沒有找到匹配 {filter_pattern} 的文件")
            return
        
        self.logger.info(f"從目錄 {directory} 添加 {len(template_files)} 個任務")
        
        for template_file in template_files:
            self.add_task(template_file)
    
    def _worker(self):
        """工作線程函數，處理任務隊列中的任務"""
        while not self.stop_requested:
            # 獲取任務，如果隊列為空，等待1秒後重試
            try:
                task = self.task_queue.get(block=True, timeout=1)
            except queue.Empty:
                if self.stop_requested:
                    break
                continue
            
            with self.thread_lock:
                self.active_threads += 1
            
            self.logger.info(f"開始處理任務: {task['id']}")
            
            # 初始化任務狀態
            task_result = {
                "id": task["id"],
                "template_file": task["template_file"],
                "success": False,
                "error": None,
                "items_count": 0,
                "start_time": time.time(),
                "end_time": None
            }
            
            try:
                # 創建模板爬蟲實例
                crawler = TemplateCrawler(
                    template_file=task["template_file"],
                    config_file=self.config.get("config_file", "config/config.json"),
                    log_level=self.logger.level
                )
                
                # 檢查是否需要恢復爬取
                if self.engine_config.get("resume_crawling", True):
                    data = crawler.resume_crawl(
                        max_pages=task["config"].get("max_pages"),
                        max_items=task["config"].get("max_items")
                    )
                else:
                    data = crawler.crawl(
                        max_pages=task["config"].get("max_pages"),
                        max_items=task["config"].get("max_items")
                    )
                
                # 更新任務結果
                task_result["success"] = True
                task_result["items_count"] = len(data)
                
                with self.thread_lock:
                    self.stats["tasks_completed"] += 1
                    self.stats["items_scraped"] += len(data)
                
                self.logger.info(f"任務 {task['id']} 完成，爬取了 {len(data)} 個項目")
            
            except Exception as e:
                task_result["success"] = False
                task_result["error"] = str(e)
                
                with self.thread_lock:
                    self.stats["tasks_failed"] += 1
                
                self.logger.error(f"任務 {task['id']} 失敗: {str(e)}")
            
            finally:
                # 標記任務完成時間
                task_result["end_time"] = time.time()
                
                # 將結果加入結果隊列
                self.result_queue.put(task_result)
                
                # 標記任務完成
                self.task_queue.task_done()
                
                with self.thread_lock:
                    self.active_threads -= 1
    
    def start(self, wait: bool = False):
        """
        啟動爬蟲引擎，開始處理任務
        
        Args:
            wait: 是否等待所有任務完成
        """
        if self.is_running:
            self.logger.warning("爬蟲引擎已經在運行")
            return
        
        self.is_running = True
        self.stop_requested = False
        self.stats["start_time"] = time.time()
        
        self.logger.info(f"啟動爬蟲引擎，最大線程數: {self.max_threads}")
        
        # 創建工作線程
        for i in range(self.max_threads):
            thread = threading.Thread(target=self._worker, name=f"Crawler-Worker-{i}")
            thread.daemon = True
            thread.start()
            self.threads.append(thread)
        
        # 如果需要等待所有任務完成
        if wait:
            self.logger.info("等待所有任務完成")
            self.task_queue.join()
            self.stop()
    
    def stop(self):
        """停止爬蟲引擎"""
        if not self.is_running:
            return
        
        self.logger.info("停止爬蟲引擎")
        self.stop_requested = True
        
        # 等待所有線程結束
        for thread in self.threads:
            if thread.is_alive():
                thread.join(timeout=10)
        
        self.threads = []
        self.is_running = False
        self.stats["end_time"] = time.time()
        
        self.logger.info("爬蟲引擎已停止")
    
    def get_status(self) -> Dict:
        """獲取爬蟲引擎狀態"""
        with self.thread_lock:
            status = {
                "is_running": self.is_running,
                "active_threads": self.active_threads,
                "queued_tasks": self.task_queue.qsize(),
                "completed_results": self.result_queue.qsize(),
                "stats": self.stats.copy()
            }
            
            # 計算運行時間
            if self.stats["start_time"]:
                end_time = self.stats["end_time"] or time.time()
                status["runtime_seconds"] = end_time - self.stats["start_time"]
            
            return status
    
    def get_results(self, clear: bool = False) -> List[Dict]:
        """
        獲取所有已完成任務的結果
        
        Args:
            clear: 是否清空結果隊列
            
        Returns:
            任務結果列表
        """
        results = []
        
        # 將結果隊列中的所有項目取出
        while not self.result_queue.empty():
            results.append(self.result_queue.get())
            self.result_queue.task_done()
        
        # 如果不需要清空結果，將結果重新放回隊列
        if not clear:
            for result in results:
                self.result_queue.put(result)
        
        return results
    
    def wait_for_tasks(self, timeout: float = None) -> bool:
        """
        等待所有任務完成
        
        Args:
            timeout: 超時時間（秒），None表示無限等待
            
        Returns:
            是否所有任務都已完成
        """
        try:
            self.task_queue.join(timeout=timeout)
            return True
        except queue.Empty:
            return False
    
    def run_crawler(self, template_file: str, config: Dict = None) -> Dict:
        """
        直接運行單個爬蟲任務，不使用線程池
        
        Args:
            template_file: 模板文件路徑
            config: 任務配置
            
        Returns:
            爬取結果
        """
        task_id = os.path.basename(template_file).replace(".json", "")
        self.logger.info(f"直接運行爬蟲任務: {task_id}")
        
        config = config or {}
        result = {
            "id": task_id,
            "template_file": template_file,
            "success": False,
            "error": None,
            "items_count": 0,
            "start_time": time.time(),
            "end_time": None,
            "data": []
        }
        
        try:
            # 創建模板爬蟲實例
            crawler = TemplateCrawler(
                template_file=template_file,
                config_file=self.config.get("config_file", "config/config.json"),
                log_level=self.logger.level
            )
            
            # 執行爬取
            if self.engine_config.get("resume_crawling", True):
                data = crawler.resume_crawl(
                    max_pages=config.get("max_pages"),
                    max_items=config.get("max_items")
                )
            else:
                data = crawler.crawl(
                    max_pages=config.get("max_pages"),
                    max_items=config.get("max_items")
                )
            
            # 更新結果
            result["success"] = True
            result["items_count"] = len(data)
            result["data"] = data
            
            # 保存數據到持久化管理器
            if data and config.get("save_data", True):
                self.data_manager.save_data(task_id, data)
                
            self.logger.info(f"任務 {task_id} 完成，爬取了 {len(data)} 個項目")
        
        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            
            # 提供完整的異常堆疊信息以便調試
            self.logger.error(f"任務 {task_id} 失敗: {str(e)}", exc_info=True)
        
        finally:
            # 標記完成時間
            result["end_time"] = time.time()
        
        return result