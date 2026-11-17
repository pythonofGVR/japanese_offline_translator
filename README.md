# 日文离线翻译器 v1.1.1

Windows x64 本地日文翻译：CPU 或可选 NVIDIA CUDA GPU，GPU 不可用自动回退 CPU。运行时不联网，不需要 Python、CUDA Toolkit、账户或 API Key。

## 下载完整应用

[打开 v1.1.1 完整离线发行页](https://github.com/pythonofGVR/japanese_offline_translator/releases/tag/v1.1.1)

在 Assets 中下载 JapaneseTranslatorSetup.exe、所有 JapaneseTranslatorSetup-*.bin 和 SHA256SUMS.txt，放在同一个文件夹，再双击 EXE 安装。数据文件包含两个模型和 CPU/GPU 运行库，不能遗漏。GitHub 默认的 Source code ZIP 仅供开发，不是可直接运行的软件。

仓库当前公开，可从 Release 下载完整文件；下载完整后可复制到另一台断网 Windows 电脑安装，无需再次联网。详见 docs/INSTALL_OFFLINE.md。

## 功能

- 日文到简体中文、繁体中文、英文；M2M100 418M / 1.2B INT8 双模型。
- 批量文件、递归文件夹、SRT/ASS/SSA/VTT/LRC、TXT/Markdown/DOCX、可提取文本的 PDF。
- 保留原文，输出自动编号，字幕结构校验；缓存、暂停/继续、取消、任务恢复。
- 异常质量检测和条件重译、人工对照校对；独立译文文件编辑与自动备份。
- CPU 线程数 1–min(32,逻辑处理器数)，默认 min(4,上限)；搜索宽度 1–10，默认 3；可恢复默认参数。
- v1.1.1 修复 SRT 翻译完成却未保存的问题；单句失败隔离、有限重试和单行原文兜底（最多 42 个可见字符），任务中显示具体原因和保留条数。
- 翻译输出目录仅含译文；含原文的校对记录留在本机应用数据目录，不复制或移动原字幕。

机器翻译仍可能误译。规则检测不能代替语义校对，尚未实现 OCR 与跨字幕上下文推理。

## 开发与构建

Python 3.13 x64；新建 .venv，安装 requirements.lock.txt 后 pip install -e . --no-build-isolation。
运行 python scripts/prepare_models.py 准备并核验模型，python -m jot 启动，python -m pytest -q 测试。
使用 Inno Setup 6.4.3，将 ISCC.exe 放到 tools/inno6/。python scripts/build.py 会构建完整 CPU/GPU 运行目录、验证冻结 EXE 的实际 CPU/GPU/自动回退及文件编辑，再生成分卷离线安装包并实际安装验证。

源码以 Git 分支与版本标签保留；大模型和二进制通过 GitHub Release 分发。最终清理不删除已有用户字幕或本机配置缓存。软件许可详见 LICENSES.md，验收证据见 reports/v1.1-*.json、reports/v1.1-tests.xml。

本机清理后的精简布局为 JapaneseTranslator（可直接运行）、OfflineInstaller（跨机离线安装文件）和必要的 Git 版本元数据。需要继续开发时，在项目根目录运行 git sparse-checkout disable 恢复源码，再重新创建开发虚拟环境。原有字幕与用户提示文档保留。

## 本机精简运行布局（2026-11-17）

- `JapaneseTranslator/JapaneseTranslator.exe`：可直接启动；完整模型与 CPU/GPU 运行库均在此目录。
- `OfflineInstaller/`：安装 EXE、全部四个 BIN 数据卷、安装说明与 SHA256；跨机使用时全部一起复制。
- 开发环境、构建工具、旧包、重复模型和测试产物已清理，源码在 Git 历史与 GitHub 中保留，可用 `git sparse-checkout disable` 恢复。
- 清理后已在没有项目虚拟环境的情况下，再次通过 CPU、GPU、无 GPU 回退三组运行检查，每组 26 项。
- 原有字幕、用户提示文档、用户配置与翻译结果未删除。
