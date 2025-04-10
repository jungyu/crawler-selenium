#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
驗證碼服務模組

提供驗證碼處理的核心功能，包括：
1. 驗證碼檢測
2. 驗證碼識別
3. 驗證碼處理
4. 結果驗證
"""

import time
import os
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from src.core.utils import (
    BrowserUtils,
    Logger,
    URLUtils,
    DataProcessor,
    ErrorHandler,
    ConfigUtils,
    ImageUtils,
    AudioUtils,
    TextUtils
)

from ..types import CaptchaResult

@dataclass
class CaptchaResult:
    """驗證碼處理結果數據類"""
    success: bool
    text: Optional[str] = None
    confidence: Optional[float] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class CaptchaService:
    """驗證碼服務類"""
    
    def __init__(self, browser: WebDriver, config: Dict[str, Any]):
        """
        初始化驗證碼服務
        
        Args:
            browser: WebDriver 實例
            config: 配置字典
        """
        self.browser = browser
        self.config = config
        
        # 初始化工具類
        self.logger = Logger(__name__)
        self.error_handler = ErrorHandler()
        self.config_utils = ConfigUtils()
        self.browser_utils = BrowserUtils(self.browser)
        self.url_utils = URLUtils()
        self.data_processor = DataProcessor()
        self.image_utils = ImageUtils()
        self.audio_utils = AudioUtils()
        self.text_utils = TextUtils()
        
        # 初始化配置
        self._init_service()
        
    def _init_service(self):
        """初始化服務配置"""
        try:
            # 設置超時和重試
            self.timeout = self.config.get('timeout', 30)
            self.retry_count = self.config.get('retry_count', 3)
            
            # 設置目錄
            self.temp_dir = self.config.get('temp_dir', 'temp')
            self.result_dir = self.config.get('result_dir', 'results')
            
            # 創建目錄
            for dir_path in [self.temp_dir, self.result_dir]:
                os.makedirs(dir_path, exist_ok=True)
                
            # 初始化狀態
            self.service_status = {
                'current_type': None,
                'retry_count': 0,
                'success_count': 0,
                'failure_count': 0,
                'start_time': None,
                'end_time': None,
                'duration': None
            }
            
            # 初始化緩存
            self.result_cache = {}
            
        except Exception as e:
            self.logger.error(f"初始化服務失敗: {str(e)}")
            raise
            
    def detect_captcha(self, selectors: List[str]) -> Optional[WebElement]:
        """
        檢測驗證碼元素
        
        Args:
            selectors: 選擇器列表
            
        Returns:
            Optional[WebElement]: 驗證碼元素
        """
        try:
            for selector in selectors:
                element = self.browser_utils.find_element(
                    self.browser,
                    By.CSS_SELECTOR,
                    selector,
                    timeout=self.timeout
                )
                if element:
                    self.logger.info(f"檢測到驗證碼元素: {selector}")
                    return element
                    
            self.logger.warning("未檢測到驗證碼元素")
            return None
            
        except Exception as e:
            self.logger.error(f"檢測驗證碼失敗: {str(e)}")
            return None
            
    def solve_image_captcha(self, element: WebElement) -> CaptchaResult:
        """
        處理圖像驗證碼
        
        Args:
            element: 驗證碼元素
            
        Returns:
            CaptchaResult: 處理結果
        """
        try:
            # 更新狀態
            self.service_status['current_type'] = 'image'
            self.service_status['start_time'] = datetime.now()
            
            # 獲取圖像
            image = self.browser_utils.get_element_screenshot(element)
            if not image:
                raise Exception("無法獲取驗證碼圖像")
                
            # 保存原始圖像
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            raw_path = Path(self.temp_dir) / f"raw_{timestamp}.png"
            self.image_utils.save_image(image, raw_path)
            
            # 預處理圖像
            processed = self.image_utils.preprocess_image(image)
            if not processed:
                raise Exception("圖像預處理失敗")
                
            # 保存處理後的圖像
            processed_path = Path(self.temp_dir) / f"processed_{timestamp}.png"
            self.image_utils.save_image(processed, processed_path)
            
            # 識別文本
            text = self.text_utils.recognize_text(processed)
            if not text:
                raise Exception("文本識別失敗")
                
            # 更新狀態
            self.service_status['end_time'] = datetime.now()
            self.service_status['duration'] = (
                self.service_status['end_time'] - 
                self.service_status['start_time']
            ).total_seconds()
            
            # 返回結果
            result = CaptchaResult(
                success=True,
                solution=text,
                duration=self.service_status['duration'],
                metadata={
                    'raw_image': str(raw_path),
                    'processed_image': str(processed_path),
                    'timestamp': timestamp
                }
            )
            
            # 更新緩存
            self.result_cache[timestamp] = result
            
            self.logger.info(f"圖像驗證碼處理成功: {text}")
            return result
            
        except Exception as e:
            self.logger.error(f"處理圖像驗證碼失敗: {str(e)}")
            return CaptchaResult(
                success=False,
                error=str(e)
            )
            
    def solve_audio_captcha(self, element: WebElement) -> CaptchaResult:
        """
        處理音頻驗證碼
        
        Args:
            element: 驗證碼元素
            
        Returns:
            CaptchaResult: 處理結果
        """
        try:
            # 更新狀態
            self.service_status['current_type'] = 'audio'
            self.service_status['start_time'] = datetime.now()
            
            # 獲取音頻
            audio = self.browser_utils.get_element_audio(element)
            if not audio:
                raise Exception("無法獲取驗證碼音頻")
                
            # 保存原始音頻
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            raw_path = Path(self.temp_dir) / f"raw_{timestamp}.mp3"
            self.audio_utils.save_audio(audio, raw_path)
            
            # 預處理音頻
            processed = self.audio_utils.preprocess_audio(audio)
            if not processed:
                raise Exception("音頻預處理失敗")
                
            # 保存處理後的音頻
            processed_path = Path(self.temp_dir) / f"processed_{timestamp}.wav"
            self.audio_utils.save_audio(processed, processed_path)
            
            # 識別文本
            text = self.audio_utils.recognize_speech(processed)
            if not text:
                raise Exception("語音識別失敗")
                
            # 更新狀態
            self.service_status['end_time'] = datetime.now()
            self.service_status['duration'] = (
                self.service_status['end_time'] - 
                self.service_status['start_time']
            ).total_seconds()
            
            # 返回結果
            result = CaptchaResult(
                success=True,
                solution=text,
                duration=self.service_status['duration'],
                metadata={
                    'raw_audio': str(raw_path),
                    'processed_audio': str(processed_path),
                    'timestamp': timestamp
                }
            )
            
            # 更新緩存
            self.result_cache[timestamp] = result
            
            self.logger.info(f"音頻驗證碼處理成功: {text}")
            return result
            
        except Exception as e:
            self.logger.error(f"處理音頻驗證碼失敗: {str(e)}")
            return CaptchaResult(
                success=False,
                error=str(e)
            )
            
    def clear_cache(self):
        """清理緩存"""
        try:
            self.result_cache = {}
            self.logger.info("服務緩存已清理")
        except Exception as e:
            self.logger.error(f"清理緩存失敗: {str(e)}")

    @handle_error(error_types=(ValidationError,))
    def validate_result(
        self,
        result: CaptchaResult,
        min_confidence: float = 0.8
    ) -> bool:
        """
        驗證處理結果
        
        Args:
            result: 處理結果
            min_confidence: 最小可信度
            
        Returns:
            是否有效
        """
        try:
            # 檢查成功標誌
            if not result.success:
                return False
                
            # 檢查文本
            if not result.text:
                return False
                
            # 檢查可信度
            if result.confidence < min_confidence:
                return False
                
            # 驗證文本
            if not self.text_processor.validate_text(result.text):
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"結果驗證失敗: {str(e)}")
            raise ValidationError(f"結果驗證失敗: {str(e)}") 