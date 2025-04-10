#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
驗證碼模組

提供爬蟲系統的驗證碼處理功能，包括：
- 驗證碼檢測
- 驗證碼識別
- 驗證碼處理
"""

from .detector import CaptchaDetector
from .recognizer import CaptchaRecognizer
from .handler import CaptchaHandler

__version__ = '1.0.0'
__author__ = 'Aaron Yu (https://github.com/jungyu), Claude AI, Cursor AI'
__license__ = 'MIT'

__all__ = [
    'CaptchaDetector',
    'CaptchaRecognizer',
    'CaptchaHandler'
]
