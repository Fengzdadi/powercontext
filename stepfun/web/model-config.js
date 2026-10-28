// Embedding model definition shared by the browser app and the Node scripts.
export const MODEL = {
  // ONNX export of intfloat/multilingual-e5-small (MIT, 118M params, 100 languages incl. zh/en),
  // pinned to an exact Hugging Face revision.
  repo: "Xenova/multilingual-e5-small",
  revision: "761b726dd34fb83930e26aab4e9ac3899aa1fa78",
  upstream: "intfloat/multilingual-e5-small@614241f622f53c4eeff9890bdc4f31cfecc418b3",
  dim: 384,
  maxTokens: 512,
  // E5 is trained with asymmetric prefixes; mean pooling + L2 normalisation, compared by cosine.
  queryPrefix: "query: ",
  passagePrefix: "passage: ",
  // File per precision, as Transformers.js resolves `dtype`.
  files: {
    fp32: "onnx/model.onnx",
    fp16: "onnx/model_fp16.onnx",
    int8: "onnx/model_int8.onnx",
  },
  // Same layout, written by scripts/quantize.py from the FP32 file (selected with ?source=local).
  // Same weights and vector space as `repo`, so knowledge bases are shared between the two sources.
  localRepo: "local/multilingual-e5-small",
  // Default precision per backend: FP16 runs natively on WebGPU (shader-f16); on WASM, INT8 is a 3.6x
  // smaller download than FP32 at about the same speed (bench/results/final__report.md).
  defaults: { webgpu: "fp16", wasm: "int8" },
};
