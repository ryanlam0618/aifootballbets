# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

try:
    from src.advanced_models import (
        ExponentialDecayXGForecaster,
        BayesianGoalModel,
        TeamFormLSTM,
        BettingRLAgent,
        XGOTEfficiencyModel,
        DefensiveQualityModel,
        ShotPositionModel
    )
    print('✅ advanced_models imports OK')

    from src.math_models_v3 import (
        StackingEnsemble,
        DutchingCalculator,
        PortfolioKelly,
        XGBoostModel,
        RandomForestModel,
        GradientBoostingModel,
        LogisticRegressionModel
    )
    print('✅ math_models_v3 imports OK')

    from src.model_evaluation import (
        CrossValidator,
        Backtester,
        ModelMonitor,
        DataValidator
    )
    print('✅ model_evaluation imports OK')

    from src.feature_engineering import (
        FeatureEngineer,
        TimeSeriesFeatureGenerator
    )
    print('✅ feature_engineering imports OK')

    from src.corner_models import (
        CornerPredictionModel,
        CornerValueBetModel
    )
    print('✅ corner_models imports OK')

    print()
    print('All imports successful!')
except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()
