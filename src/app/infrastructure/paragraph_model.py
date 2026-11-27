import os
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

_tokenizer = None
_model = None

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


MAX_LENGTH = 128  # 학습 때와 같은 값

def predict_paragraphs(paragraphs: list[str]) -> list[tuple[str, float]]:
    tokenizer, model = _load()
    inputs = tokenizer(
                paragraphs,
                truncation=True,
                max_length=MAX_LENGTH,
                padding=True,
                return_tensors="pt"
                )
    with torch.no_grad():
        logits = model(**inputs).logits
        probs = logits.softmax(dim=1)
        best_probs, best_ids = probs.max(dim=1)
        results = []

        for i, p in zip(best_ids, best_probs):
            label = model.config.id2label[i.item()] 
            prob = round(p.item(), 4)
            results.append((label, prob))

        return results