WebGPU 是浏览器中新一代的 GPU 编程接口，可以执行通用计算着色器。端侧推理框架（如 ONNX Runtime Web）利用 WebGPU 把矩阵乘法等算子放到显卡上执行，批量向量化时吞吐通常比 CPU 高一个数量级。

并不是所有设备和浏览器都支持 WebGPU：旧版浏览器、被禁用 GPU 的环境或驱动不受支持时，navigator.gpu 可能不存在，或 requestAdapter() 返回空值。此时应用应当自动降级到 WebAssembly（WASM）后端。WASM 在 CPU 上运行，借助 SIMD 指令和多线程（需要跨源隔离以启用 SharedArrayBuffer）也能获得不错的性能，尤其适合单条查询这类小批量计算。
