#!/usr/bin/env python3
"""분류기 — 사전학습 인코더 + 직접 쓴 헤드.

`AutoModelForSequenceClassification` 을 쓰면 한 줄로 끝나지만, 그러면
**모델 안에서 무슨 일이 일어나는지 안 보인다.** 헤드를 직접 붙인다.

── 왜 [CLS] 가 아니라 평균 풀링인가 ─────────────────────────────────────
DistilBERT 는 BERT 와 달리 NSP(다음문장예측)로 학습되지 않아서 [CLS] 토큰이
문장 전체를 대표하도록 훈련된 적이 없다. 짧은 헤드라인에서는 **패딩을 뺀
토큰 평균**이 경험적으로 더 안정적이다. 둘 다 돌려보고 고를 수 있게 남겨둔다.
"""
import torch
import torch.nn as nn
from transformers import AutoModel

ENCODER = "distilbert-base-uncased"   # 66M. M2/8GB 에서 배치 16이 편하게 돈다


class HeadlineClassifier(nn.Module):
    def __init__(self, encoder=ENCODER, n_classes=3, dropout=0.2, pool="mean"):
        super().__init__()
        # 🔴 MPS 에서는 어텐션을 eager 로 강제한다.
        # transformers 5.x 는 기본으로 SDPA(scaled_dot_product_attention)를 쓰는데,
        # MPS 구현이 **드롭아웃을 지원하지 않아** 학습 중에 터진다:
        #   NotImplementedError: scaled_dot_product_attention for MPS does not support dropout
        # 어텐션 드롭아웃을 0 으로 꺼도 돌긴 하지만 그건 정규화를 하나 빼는 것이다.
        # eager 는 조금 느릴 뿐 의미가 같아서 이쪽을 택한다.
        attn = "eager" if torch.backends.mps.is_available() else None
        self.encoder = AutoModel.from_pretrained(
            encoder, **({"attn_implementation": attn} if attn else {}))
        h = self.encoder.config.hidden_size
        self.pool = pool
        self.drop = nn.Dropout(dropout)
        self.fc = nn.Linear(h, n_classes)

    def forward(self, ids, mask):
        out = self.encoder(input_ids=ids, attention_mask=mask).last_hidden_state
        if self.pool == "cls":
            v = out[:, 0]
        else:
            # 🔴 패딩 토큰을 평균에 넣으면 짧은 문장일수록 0 쪽으로 끌려간다.
            # 마스크를 곱해 **실제 토큰만** 평균낸다.
            m = mask.unsqueeze(-1).float()
            v = (out * m).sum(1) / m.sum(1).clamp(min=1e-9)
        return self.fc(self.drop(v))

    def freeze_encoder(self, upto=None):
        """인코더를 얼린다. 데이터가 적을 때 과적합을 늦추는 가장 싼 방법이다.
        upto 를 주면 하위 N개 층만 얼린다(상위 층은 과제에 맞춰 움직이게)."""
        if upto is None:
            for p in self.encoder.parameters():
                p.requires_grad = False
            return
        for p in self.encoder.embeddings.parameters():
            p.requires_grad = False
        for layer in self.encoder.transformer.layer[:upto]:
            for p in layer.parameters():
                p.requires_grad = False
