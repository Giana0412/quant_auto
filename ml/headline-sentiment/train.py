#!/usr/bin/env python3
"""학습 루프 — 직접 쓴다.

HuggingFace `Trainer` 를 쓰면 다섯 줄로 끝나지만 **PyTorch 를 배우는 게 목적**이라
루프를 손으로 쓴다. 여기 들어있는 것들:
  · Dataset / DataLoader · 디바이스 이동(MPS) · forward → loss → backward → step
  · 선형 워밍업 스케줄러 · 그래디언트 클리핑 · 클래스 가중 · 조기 종료 · 체크포인트

── 🔴 8GB M2 에서의 선택 ────────────────────────────────────────────────
· DistilBERT(66M) + 배치 16 + max_len 64. 이 조합이 스왑 없이 돈다
· MPS 는 float16 autocast 지원이 들쭉날쭉해서 **fp32 로 간다**. 속도보다 안정
· num_workers=0 — 8GB 에서 워커를 띄우면 토크나이즈된 텐서가 복제돼 메모리가 터진다

── 🔴 작은 데이터에서 지켜야 할 것 ──────────────────────────────────────
헤드라인 수천 건으로 66M 파라미터를 다 흔들면 **1에폭 만에 외워버린다.**
· 기본으로 하위 4개 층을 얼린다(`--freeze 4`)
· 검증 손실이 좋아지지 않으면 **조기 종료**하고, 가장 좋았던 체크포인트를 쓴다
· 매 에폭 테스트셋을 보지 **않는다** — 보면 그게 또 하나의 검증셋이 된다

실행:
  python train.py                      # 기본
  python train.py --epochs 6 --lr 3e-5
  python train.py --freeze 0           # 전체 파인튜닝(과적합 주의)
  python train.py --pool cls
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from transformers import AutoTokenizer

from baseline import report
from data import Headlines, describe, load, make_labels, split
from model import ENCODER, HeadlineClassifier

HERE = Path(__file__).resolve().parent
CKPT = HERE / "runs"


def pick_device():
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def linear_warmup(optimizer, warmup, total):
    """선형 워밍업 후 선형 감쇠. 트랜스포머 파인튜닝의 사실상 표준이다 —
    초반에 큰 LR 로 때리면 사전학습된 가중치가 망가진다(catastrophic forgetting)."""
    def f(step):
        if step < warmup:
            return step / max(1, warmup)
        return max(0.0, (total - step) / max(1, total - warmup))
    return torch.optim.lr_scheduler.LambdaLR(optimizer, f)


@torch.no_grad()
def evaluate(model, loader, device, lossf):
    model.eval()
    tot, n, ys, ps = 0.0, 0, [], []
    for ids, mask, y in loader:
        ids, mask, y = ids.to(device), mask.to(device), y.to(device)
        logit = model(ids, mask)
        tot += float(lossf(logit, y)) * len(y)
        n += len(y)
        ys.append(y.cpu().numpy())
        ps.append(logit.argmax(-1).cpu().numpy())
    return tot / max(1, n), np.concatenate(ys), np.concatenate(ps)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--lr", type=float, default=3e-5)
    p.add_argument("--max-len", type=int, default=64)
    p.add_argument("--freeze", type=int, default=4, help="하위 N개 층 동결")
    p.add_argument("--pool", default="mean", choices=["mean", "cls"])
    p.add_argument("--patience", type=int, default=2)
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()

    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    device = pick_device()
    print(f"[환경] device={device} · encoder={ENCODER} · seed={a.seed}")

    rows = load()
    tr, va, te = split(rows)
    tr, (va, te), bounds = make_labels(tr, [va, te])
    print(f"[데이터] 라벨 경계(훈련셋 3분위): {bounds[0]:+.2f}% / {bounds[1]:+.2f}%")
    for n_, r in (("훈련", tr), ("검증", va), ("테스트", te)):
        describe(n_, r)

    tok = AutoTokenizer.from_pretrained(ENCODER)
    dl_tr = DataLoader(Headlines(tr, tok, a.max_len), batch_size=a.batch,
                       shuffle=True, num_workers=0)
    dl_va = DataLoader(Headlines(va, tok, a.max_len), batch_size=a.batch * 2,
                       num_workers=0)
    dl_te = DataLoader(Headlines(te, tok, a.max_len), batch_size=a.batch * 2,
                       num_workers=0)

    model = HeadlineClassifier(pool=a.pool).to(device)
    if a.freeze:
        model.freeze_encoder(upto=a.freeze)
    n_train = sum(p_.numel() for p_ in model.parameters() if p_.requires_grad)
    print(f"[모델] 학습 대상 파라미터 {n_train/1e6:.1f}M "
          f"/ 전체 {sum(p_.numel() for p_ in model.parameters())/1e6:.1f}M")

    # 🔴 클래스 가중. 3분위로 잘라도 훈련셋 분포는 정확히 1/3씩이 아니고,
    # 검증·테스트는 훈련셋 경계를 쓰므로 더 기운다. 가중을 안 주면 모델이
    # 다수 클래스만 찍어 정확도를 올리는 **가장 게으른 해**로 수렴한다.
    cnt = np.bincount([r["y"] for r in tr], minlength=3)
    w = torch.tensor(len(tr) / (3 * np.maximum(cnt, 1)), dtype=torch.float, device=device)
    print(f"[손실] 클래스 분포 {cnt.tolist()} → 가중 {[round(float(x),2) for x in w]}")
    lossf = nn.CrossEntropyLoss(weight=w)

    opt = torch.optim.AdamW([p_ for p_ in model.parameters() if p_.requires_grad],
                            lr=a.lr, weight_decay=0.01)
    total = len(dl_tr) * a.epochs
    sched = linear_warmup(opt, warmup=int(total * 0.1), total=total)

    CKPT.mkdir(exist_ok=True)
    best, best_ep, bad = float("inf"), -1, 0
    hist = []
    for ep in range(1, a.epochs + 1):
        model.train()
        t0, run, seen = time.time(), 0.0, 0
        for i, (ids, mask, y) in enumerate(dl_tr, 1):
            ids, mask, y = ids.to(device), mask.to(device), y.to(device)
            logit = model(ids, mask)
            loss = lossf(logit, y)

            opt.zero_grad(set_to_none=True)   # set_to_none 이 메모리·속도 모두 낫다
            loss.backward()
            # 🔴 클리핑 없으면 작은 배치에서 가끔 그래디언트가 튀어 손실이 NaN 이 된다
            torch.nn.utils.clip_grad_norm_(
                [p_ for p_ in model.parameters() if p_.requires_grad], 1.0)
            opt.step()
            sched.step()

            run += float(loss) * len(y)
            seen += len(y)
            if i % 20 == 0:
                print(f"\r  ep{ep} {i}/{len(dl_tr)} loss {run/seen:.4f}"
                      f" lr {sched.get_last_lr()[0]:.2e}", end="")

        vl, vy, vp = evaluate(model, dl_va, device, lossf)
        vacc = float((vy == vp).mean())
        dt = time.time() - t0
        print(f"\r  ep{ep}  훈련손실 {run/seen:.4f}  검증손실 {vl:.4f}"
              f"  검증정확도 {vacc:.1%}  ({dt:.0f}초)")
        hist.append(dict(epoch=ep, train_loss=run / seen, val_loss=vl, val_acc=vacc))

        if vl < best - 1e-4:
            best, best_ep, bad = vl, ep, 0
            torch.save(model.state_dict(), CKPT / "best.pt")
        else:
            bad += 1
            if bad >= a.patience:
                print(f"  → 검증손실이 {bad}에폭 개선 없음. 조기 종료")
                break

    print(f"\n[최종] 최고 검증손실 ep{best_ep} ({best:.4f}) 체크포인트를 불러온다")
    model.load_state_dict(torch.load(CKPT / "best.pt", map_location=device))
    _, ty, tp = evaluate(model, dl_te, device, lossf)
    res = report(f"DistilBERT · 테스트셋 (ep{best_ep})", ty, tp)

    (CKPT / "history.json").write_text(json.dumps(
        dict(args=vars(a), bounds=bounds, history=hist, test=res),
        ensure_ascii=False, indent=2))
    print(f"\n  기록 → {CKPT/'history.json'}")
    print("  🔴 `python baseline.py` 의 사전 성적과 **같은 테스트셋**이다. 비교할 것.")


if __name__ == "__main__":
    main()
