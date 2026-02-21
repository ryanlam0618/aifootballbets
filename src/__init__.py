"""
AI 足球分析系統 - 核心模組

此包包含系統的核心功能模組：
- data_modules: 數據獲取與處理
- llm_clients: LLM 客戶端整合
- networking_llm: 聯網 LLM 功能
- finance: 資金管理與記錄
- math_models: 數學預測模型 (整合版 v7.0)
"""

__version__ = "7.0.0"
__author__ = "AI Football Betting System"

# 匯出常用類別和函數
from .data_modules import HistoryRepo, RealOddsFetcher, OddsPoint, LEAGUE_OPTIONS
from .llm_clients import llm
from .finance import calculate_kelly_stake, ExcelLogger

# 整合後的數學模型 (v7.0)
from .math_models import (
    # 進球模型
    PoissonModel,
    NegativeBinomialModel,
    DixonColesModel,
    OptimizedDixonColes,
    # 評分系統
    EloSystem,
    Glicko2System,
    DynamicKEloSystem,
    # 蒙地卡羅
    MonteCarloSimulator,
    MonteCarloSimulatorV3,
    # 陣容與資金
    LineupModel,
    ConfidenceKelly,
    KellyResult,
    # 工具函數
    calculate_kelly_stake,
)

__all__ = [
    # 數據模組
    'HistoryRepo',
    'RealOddsFetcher',
    'OddsPoint',
    'LEAGUE_OPTIONS',
    # LLM
    'llm',
    # 資金管理
    'calculate_kelly_stake',
    'ExcelLogger',
    # 數學模型 - 進球預測
    'PoissonModel',
    'NegativeBinomialModel',
    'DixonColesModel',
    'OptimizedDixonColes',
    # 數學模型 - 評分系統
    'EloSystem',
    'Glicko2System',
    'DynamicKEloSystem',
    # 數學模型 - 蒙地卡羅
    'MonteCarloSimulator',
    'MonteCarloSimulatorV3',
    # 數學模型 - 其他
    'LineupModel',
    'ConfidenceKelly',
    'KellyResult',
]
