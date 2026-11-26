"""model_weight3.pth 불러오기와 분기 계산 (서비스에서만 쓰는 부분)."""
import pickle
from pathlib import Path

import xgboost as xgb

CATEGORICAL = ["서비스_업종_코드", "상권_구분_코드", "상권_변화_지표"]
WEIGHTS_PATH = Path(__file__).resolve().parent / "model_weight3.pth"


def shift_quarter(code: str, n: int) -> str:
    """분기 코드를 n 분기 뒤로. 예: shift_quarter('20254', 1) -> '20261'"""
    idx = int(code[:4]) * 4 + (int(code[4]) - 1) + n
    return f"{idx // 4}{idx % 4 + 1}"


def load_weights(path=WEIGHTS_PATH):
    """-> {'sales': {h: 회귀}, 'closure': {h: 분류}, 'cold_sales': {h: 회귀}, 'cold_closure': {h: 분류},
           'feature_columns', 'cold_columns', 'cat_levels', 'latest_features_csv', ...}
    pickle 파일이라 믿을 수 있는 파일만 열 것."""
    with open(path, "rb") as f:
        b = pickle.load(f)
    for kind, cls in (("sales", xgb.XGBRegressor), ("closure", xgb.XGBClassifier), ("cold_sales", xgb.XGBRegressor), ("cold_closure", xgb.XGBClassifier)):
        models = {}
        for h, raw in b[kind].items():
            m = cls()
            m.load_model(bytearray(raw))
            models[h] = m
        b[kind] = models
    return b
