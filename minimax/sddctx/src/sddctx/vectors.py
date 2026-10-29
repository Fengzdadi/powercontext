"""本地确定性向量：词与字符 n-gram 的特征哈希（feature hashing），L2 归一化。

不需要下载模型、不依赖外部服务，同一段文本在任何机器上得到同一个向量。它补充 IK 分词的全文检索：
中文按字符二元/三元组切分，不受分词粒度影响；英文标识符按下划线拆开，例如 `year_from` → year, from。
它不是语义模型，同义改写的召回能力有限，详见 README 的“已知限制”。
"""

from __future__ import annotations

import hashlib
import math
import re

DIM = 256
_WORD = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*")
_CJK_RUN = re.compile(r"[一-鿿]+")


def _features(text: str) -> dict[str, float]:
    text = text.lower()
    features: dict[str, float] = {}
    for word in _WORD.findall(text):
        features["w:" + word] = features.get("w:" + word, 0.0) + 1.0
        if "_" in word:
            for part in word.split("_"):
                features["w:" + part] = features.get("w:" + part, 0.0) + 0.5
    for run in _CJK_RUN.findall(text):
        for n, weight in ((2, 1.0), (3, 0.5)):
            for i in range(len(run) - n + 1):
                key = "c:" + run[i : i + n]
                features[key] = features.get(key, 0.0) + weight
        if len(run) == 1:
            features["c:" + run] = features.get("c:" + run, 0.0) + 0.5
    return features


def embed(text: str) -> list[float]:
    vector = [0.0] * DIM
    for feature, weight in _features(text).items():
        digest = int.from_bytes(hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest(), "big")
        sign = 1.0 if digest >> 63 == 0 else -1.0
        scaled = 1.0 + math.log(weight) if weight >= 1 else weight
        vector[digest % DIM] += sign * scaled
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        vector[0] = 1.0
        return vector
    return [x / norm for x in vector]


def literal(vector: list[float]) -> str:
    """seekdb VECTOR 列的字面量写法：'[x1,x2,...]'。"""
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"
