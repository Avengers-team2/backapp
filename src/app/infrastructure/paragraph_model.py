import os
from pathlib import Path

import joblib
import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# 두 모델(상아 RoBERTa + 희수 TF-IDF) 확률을 평균 내는 앙상블


# ─────────────────────────────────────────
# 상아 RoBERTa 모델
# ─────────────────────────────────────────
_tokenizer = None
_model = None

MAX_LENGTH = 128  # 학습 때와 같은 값


def _load():
    global _tokenizer, _model

    if _model is not None:
        return _tokenizer, _model

    model_dir = os.getenv("PARAGRAPH_MODEL_DIR")
    if not model_dir:
        raise RuntimeError("PARAGRAPH_MODEL_DIR가 없습니다")

    _tokenizer = AutoTokenizer.from_pretrained(model_dir)
    _model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    _model.eval()
    return (_tokenizer, _model)


def _roberta_probs(paragraphs: list[str]) -> tuple[list[str], np.ndarray]:
    tokenizer, model = _load()
    inputs = tokenizer(
                paragraphs,
                truncation=True,
                max_length=MAX_LENGTH,
                padding=True,
                return_tensors="pt"
                )
    with torch.no_grad():
        probs = model(**inputs).logits.softmax(dim=1).numpy()

    labels = [model.config.id2label[i] for i in range(probs.shape[1])]
    return labels, probs


# ─────────────────────────────────────────
# 희수 TF-IDF 모델
# ─────────────────────────────────────────
TFIDF_MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "report_ai" / "tfidf_logreg.joblib"

_tfidf = None


def _load_tfidf():
    global _tfidf

    if _tfidf is not None:
        return _tfidf

    if not TFIDF_MODEL_PATH.exists():
        raise RuntimeError(f"TF-IDF 모델 파일이 없습니다: {TFIDF_MODEL_PATH}")

    _tfidf = joblib.load(TFIDF_MODEL_PATH)
    return _tfidf


def _tfidf_probs(paragraphs: list[str]) -> tuple[list[str], np.ndarray]:
    pipe = _load_tfidf()
    probs = pipe.predict_proba(paragraphs)
    labels = [str(c) for c in pipe.classes_]   # scikit-learn은 라벨을 알파벳순으로 정렬함
    return labels, probs


# ─────────────────────────────────────────
# 앙상블: 라벨 이름 기준으로 맞춰서 평균
# ─────────────────────────────────────────
def predict_paragraphs(paragraphs: list[str]) -> list[tuple[str, float]]:
    r_labels, r_probs = _roberta_probs(paragraphs)
    t_labels, t_probs = _tfidf_probs(paragraphs)

    # TF-IDF 열 순서를 RoBERTa 라벨 순서로 다시 배열 (인덱스 그대로 더하면 다른 라벨끼리 더해짐)
    order = [t_labels.index(label) for label in r_labels]
    t_probs = t_probs[:, order]

    probs = (r_probs + t_probs) / 2
    best_ids = probs.argmax(axis=1)

    results = []
    for row, i in zip(probs, best_ids):
        results.append((r_labels[i], round(float(row[i]), 4)))

    return results
