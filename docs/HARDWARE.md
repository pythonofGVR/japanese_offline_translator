# 验证设备与运行时要求

实际设备：Windows 11 x64 10.0.22631，Intel Core i9-13900H（14 核 / 20 逻辑处理器），物理内存 33,960,448,000 bytes；所有测量均为 CPU INT8、4 个推理线程。

CTranslate2 官方硬件文档：https://opennmt.net/CTranslate2/hardware_support.html
本次构建查阅的原文要求：`x86-64 processors supporting at least SSE 4.1`。
预编译 x86-64 二进制自动选择 AVX、AVX2、AVX512 和适用的 MKL/oneDNN 后端。
这不是在所有旧设备上实测的承诺。Windows 10、AMD CPU、干净系统和无开发工具的其他主机尚未实测。

已检查 CTranslate2 原生库的 PE 导入：依赖 libiomp5md、MSVCP140、VCRUNTIME140/140_1 和 Windows UCRT；便携包收集了所需 VC++ 动态库。CPU 发行版不包含 cuDNN。最终是否能在某个目标系统运行仍应以实际测试为准。
