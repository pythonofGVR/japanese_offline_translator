# v1.1.2 完整离线安装

从本版本 GitHub Release 的 Assets 下载以下所有文件，放在同一个文件夹：

- `JapaneseTranslatorSetup.exe`
- 所有 `JapaneseTranslatorSetup-*.bin` 数据文件（不能遗漏任何一个）
- `SHA256SUMS.txt`（建议核对完整性）

默认的 “Source code.zip / tar.gz” 是开发源码，不含大模型，不能用于直接离线运行。请下载上面的完整安装文件。

文件下载完整后，可以复制到另一台断网 Windows 电脑，双击 `JapaneseTranslatorSetup.exe` 安装。无需 Python、CUDA Toolkit、API Key 或再次联网下载模型。
安装程序自带两个 M2M100 INT8 模型、分词器、Windows 运行库与 NVIDIA cuBLAS；采用分卷数据文件是为了符合 GitHub 单个文件大小限制，未省略任何必需资源。

运行要求：Windows 10/11 x64、CPU 支持 SSE 4.1；建议至少 8 GB 可用内存和 6 GB 可用磁盘空间。GPU 可选，仅支持 NVIDIA CUDA GPU，需有兼容 CUDA 12 的显卡驱动；未检测到兼容 GPU、驱动/运行库不可用或显存不足时自动回退 CPU。Intel/AMD GPU 不提供本版本的 GPU 加速。

运行后可选择 CPU 或 GPU 优先。线程数 1–min(32,逻辑处理器数)，默认 min(4,上限)；搜索宽度 1–10，默认 3，可点击恢复默认参数。
“文件编辑”页可直接打开字幕、TXT、Markdown、DOCX，无需原文或校对记录。保存前自动创建 `.bak` 备份；字幕时间轴和控制标记受保护，DOCX 保留基本格式。

仓库及完整版本下载：https://github.com/pythonofGVR/japanese_offline_translator/releases/tag/v1.1.2
仓库当前公开，可直接从 Release 下载；下载完整后，安装和翻译均不需要 GitHub 登录或互联网。
