"""
AI 足球分析系統 - 核心模組

此包包含系統的核心功能模組：
- data_modules: 數據獲取與處理
- llm_clients: LLM 客戶端整合
- networking_llm: 聯網 LLM 功能
- finance: 資金管理與記錄
- math_models: 數學預測模型
- math_models_v2: 進階數學模型
"""

__version__ = "6.0.0"
__author__ = "AI Football Betting System"

# 匯出常用類別和函數
from .data_modules import HistoryRepo, RealOddsFetcher, OddsPoint, LEAGUE_OPTIONS
from .llm_clients import llm
from .finance import calculate_kelly_stake, ExcelLogger
from .math_models import PoissonModel, MonteCarloSimulator, DixonColesModel
from .math_models_v2 import OptimizedDixonColes, Glicko2System, LineupModel

__all__ = [
    'HistoryRepo',
    'RealOddsFetcher',
    'OddsPoint',
    'LEAGUE_OPTIONS',
    'llm',
    'calculate_kelly_stake',
    'ExcelLogger',
    'PoissonModel',
    'MonteCarloSimulator',
    'DixonColesModel',
    'OptimizedDixonColes',
    'Glicko2System',
    'LineupModel',
]
