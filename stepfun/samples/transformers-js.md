Transformers.js is a JavaScript library from Hugging Face that runs pretrained models directly in the browser or in Node.js. Models are exported to the ONNX format and executed by ONNX Runtime Web, which provides a WebGPU execution provider for GPUs and a WebAssembly provider for CPUs.

For text embeddings, a feature-extraction model turns each sentence into a fixed-size vector. Mean pooling over token states followed by L2 normalisation gives vectors that can be compared with cosine similarity. Model files are downloaded once and cached by the browser, so later page loads start much faster.
