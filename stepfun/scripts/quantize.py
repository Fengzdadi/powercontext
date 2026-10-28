"""Reproduce the FP16 and INT8 variants of the embedding model from its FP32 ONNX export, then measure
file size, compression ratio and output fidelity (cosine to the FP32 embeddings) with ONNX Runtime on CPU.

    npm run quantize        # = bash scripts/quantize.sh -> uv run with pinned packages

Inputs : models/Xenova/multilingual-e5-small/onnx/model.onnx (npm run fetch-model)
Outputs: models/local/multilingual-e5-small/  same layout as the Hugging Face repo, so the app can load
                                              it with ?source=local
         bench/results/quantize.json          sizes, ratios, recipe, fidelity

Recipe (the same one Transformers.js uses for its prebuilt model_int8.onnx / model_fp16.onnx):
  INT8  ONNX Runtime dynamic quantisation. MatMul weights -> INT8, symmetric, per tensor, full range
        (MatMulInteger + DynamicQuantizeLinear; activations are quantised to UINT8 at run time).
        Embedding tables (Gather) -> UINT8 per tensor. Activation x activation MatMuls (QK^T, attn x V)
        stay FP32 (MatMulConstBOnly). No calibration data is needed.
  FP16  onnxconverter-common float16 conversion of every FP32 initializer and op, keeping FP32 graph
        inputs/outputs (keep_io_types) so callers are unchanged.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time

import numpy as np
import onnx
import onnxruntime as ort
from onnxconverter_common import float16
from onnxruntime.quantization import QuantType, quantize_dynamic
from tokenizers import Tokenizer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def file_info(path):
    return {"path": os.path.relpath(path, ROOT), "bytes": os.path.getsize(path), "sha256": sha256(path)}


def quantize_int8(src, dst):
    quantize_dynamic(
        model_input=src,
        model_output=dst,
        weight_type=QuantType.QInt8,
        per_channel=False,
        reduce_range=False,
        op_types_to_quantize=["MatMul", "Gather"],
        extra_options={"EnableSubgraph": True, "MatMulConstBOnly": True},
    )


def convert_fp16(src, dst):
    model = float16.convert_float_to_float16(onnx.load(src), keep_io_types=True)
    # onnxconverter-common 1.16 relabels the output of the graph's internal Cast (attention mask ->
    # float) as float16 but leaves the node's `to` at float, which ONNX Runtime rejects. Point it at
    # float16, as in the prebuilt model_fp16.onnx.
    fp16_values = {v.name for v in model.graph.value_info if v.type.tensor_type.elem_type == onnx.TensorProto.FLOAT16}
    for node in model.graph.node:
        if node.op_type == "Cast" and node.output[0] in fp16_values:
            for attr in node.attribute:
                if attr.name == "to" and attr.i == onnx.TensorProto.FLOAT:
                    attr.i = onnx.TensorProto.FLOAT16
    onnx.save(model, dst)


def fidelity_texts(n_passages):
    """Mixed zh/en texts from the documented eval set: every query plus an evenly spaced passage sample."""
    def read(name):
        with open(os.path.join(ROOT, "eval", "data", name), encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    queries = ["query: " + q["text"] for q in read("queries.jsonl")]
    corpus = read("corpus.jsonl")
    step = max(1, len(corpus) // n_passages)
    passages = ["passage: " + d["title"] + "\n" + d["text"] for d in corpus[::step][:n_passages]]
    return queries + passages


def embed(session, tokenizer, texts, batch=16):
    names = {i.name for i in session.get_inputs()}
    out = []
    for i in range(0, len(texts), batch):
        enc = tokenizer.encode_batch(texts[i : i + batch])
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        feeds = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in names:
            feeds["token_type_ids"] = np.zeros_like(ids)
        hidden = session.run(None, feeds)[0].astype(np.float32)
        m = mask[..., None].astype(np.float32)
        pooled = (hidden * m).sum(1) / np.clip(m.sum(1), 1e-9, None)  # mean pooling, as E5 prescribes
        out.append(pooled / np.linalg.norm(pooled, axis=1, keepdims=True))
    return np.concatenate(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=os.path.join(ROOT, "models", "Xenova", "multilingual-e5-small"))
    ap.add_argument("--out", default=os.path.join(ROOT, "models", "local", "multilingual-e5-small"))
    ap.add_argument("--passages", type=int, default=160, help="eval passages used for the fidelity check")
    ap.add_argument("--skip-build", action="store_true", help="only measure files that already exist")
    args = ap.parse_args()

    fp32 = os.path.join(args.src, "onnx", "model.onnx")
    if not os.path.exists(fp32):
        sys.exit(f"missing {fp32}: run `npm run fetch-model` first")
    os.makedirs(os.path.join(args.out, "onnx"), exist_ok=True)
    # tokenizer and config files are unchanged by quantisation
    for name in os.listdir(args.src):
        if os.path.isfile(os.path.join(args.src, name)):
            shutil.copy2(os.path.join(args.src, name), os.path.join(args.out, name))

    ours = {"int8": os.path.join(args.out, "onnx", "model_int8.onnx"), "fp16": os.path.join(args.out, "onnx", "model_fp16.onnx")}
    build_s = {}
    if not args.skip_build:
        for dtype, fn in (("int8", quantize_int8), ("fp16", convert_fp16)):
            t = time.perf_counter()
            fn(fp32, ours[dtype])
            build_s[dtype] = round(time.perf_counter() - t, 2)
            print(f"built {os.path.relpath(ours[dtype], ROOT)} in {build_s[dtype]} s")

    variants = {
        "fp32": fp32,
        "fp16 (prebuilt)": os.path.join(args.src, "onnx", "model_fp16.onnx"),
        "int8 (prebuilt)": os.path.join(args.src, "onnx", "model_int8.onnx"),
        "fp16 (this script)": ours["fp16"],
        "int8 (this script)": ours["int8"],
    }
    variants = {k: v for k, v in variants.items() if os.path.exists(v)}
    base_bytes = os.path.getsize(fp32)
    sizes = {}
    for name, path in variants.items():
        info = file_info(path)
        info["ratio"] = round(base_bytes / info["bytes"], 3)  # compression ratio vs FP32
        info["reduction_pct"] = round(100 * (1 - info["bytes"] / base_bytes), 1)
        sizes[name] = info
        print(f"{name:20s} {info['bytes']:>12,d} B  {info['bytes'] / 2**20:7.1f} MiB  x{info['ratio']:.2f}")

    tokenizer = Tokenizer.from_file(os.path.join(args.src, "tokenizer.json"))
    tokenizer.enable_truncation(512)
    tokenizer.enable_padding(pad_id=1, pad_token="<pad>")  # XLM-R pad id
    texts = fidelity_texts(args.passages)
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    vecs, fidelity = {}, {}
    for name, path in variants.items():
        try:
            t = time.perf_counter()
            sess = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
            vecs[name] = embed(sess, tokenizer, texts)
            elapsed = time.perf_counter() - t
        except Exception as e:  # e.g. an op without a CPU kernel for this precision
            fidelity[name] = {"error": str(e).splitlines()[0][:300]}
            print(f"{name}: {fidelity[name]['error']}")
            continue
        cos = (vecs[name] * vecs["fp32"]).sum(1)
        fidelity[name] = {
            "texts": len(texts),
            "cos_mean": round(float(cos.mean()), 6),
            "cos_min": round(float(cos.min()), 6),
            "cos_p5": round(float(np.percentile(cos, 5)), 6),
            "cpu_seconds": round(elapsed, 2),
        }
        print(f"{name:20s} cosine to fp32: mean {cos.mean():.5f}  min {cos.min():.5f}  ({elapsed:.1f} s on CPU)")
    for a, b in (("int8 (prebuilt)", "int8 (this script)"), ("fp16 (prebuilt)", "fp16 (this script)")):
        if a in vecs and b in vecs:
            c = (vecs[a] * vecs[b]).sum(1)
            fidelity[f"{b} vs {a}"] = {"cos_mean": round(float(c.mean()), 6), "cos_min": round(float(c.min()), 6)}

    result = {
        "model": "Xenova/multilingual-e5-small@761b726dd34fb83930e26aab4e9ac3899aa1fa78 (ONNX export of intfloat/multilingual-e5-small)",
        "recipe": {
            "int8": "onnxruntime.quantization.quantize_dynamic(weight_type=QInt8, per_channel=False, reduce_range=False, "
            "op_types_to_quantize=[MatMul, Gather], extra_options={EnableSubgraph: True, MatMulConstBOnly: True})",
            "fp16": "onnxconverter_common.float16.convert_float_to_float16(keep_io_types=True)",
        },
        "build_seconds": build_s,
        "sizes": sizes,
        "fidelity": fidelity,
        "fidelity_texts": "eval/data: all queries ('query: ' prefix) + evenly spaced passages ('passage: ' prefix)",
        "versions": {"python": sys.version.split()[0], "onnx": onnx.__version__, "onnxruntime": ort.__version__, "numpy": np.__version__},
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    os.makedirs(os.path.join(ROOT, "bench", "results"), exist_ok=True)
    with open(os.path.join(ROOT, "bench", "results", "quantize.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("wrote bench/results/quantize.json")


if __name__ == "__main__":
    main()
