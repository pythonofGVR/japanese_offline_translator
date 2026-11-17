# 许可与第三方组件

应用自有源代码按根目录 LICENSE（MIT）发布。模型、Qt、Python 与其他库各自适用其许可证。

|组件|许可|分发方式|
|---|---|---|
|facebook M2M100 418M / 1.2B|MIT（两个官方模型卡均声明）|随包提供固定版本的 INT8 权重、词表、SentencePiece、原模型卡和 fairseq MIT 许可|
|JustFrederik 转换权重|MIT（模型卡）|仓库及 revision 记录在 models/*/manifest.json；模型二进制按上游 LFS SHA256 校验|
|CTranslate2|MIT|动态库，完整声明由构建脚本收集|
|NVIDIA cuBLAS 12.6.4.1|NVIDIA CUDA Toolkit EULA / cuBLAS Supplement|仅分发 Attachment A 允许的未修改 cublas64_12.dll 与 cublasLt64_12.dll；仅用于 NVIDIA GPU；附完整许可|
|PySide6 / Qt Essentials|LGPL-3.0 / GPL-3.0 / 商业许可的多重许可，采用 LGPL 路径|仅使用 QtCore、QtGui、QtWidgets 动态库，未修改库本身；不使用 GPL-only 模块|
|Shiboken6|LGPL-3.0 / GPL-3.0 / 商业许可|动态库，保留声明|
|SentencePiece|Apache-2.0|保留声明|
|OpenCC Python reimplementation|Apache-2.0|包含本地字典和声明|
|python-docx|MIT|保留声明|
|pypdf|BSD-3-Clause|保留声明|
|lxml|BSD-3-Clause（另含 libxml2/libxslt 的 MIT 声明）|保留包内全部许可|
|charset-normalizer|MIT|保留声明|
|NumPy|BSD-3-Clause，另有随包组件许可|保留包内全部许可|
|Python|PSF / 历史许可|保留 Python 许可|
|PyInstaller|GPL-2.0-or-later + bootloader exception|例外允许分发本应用，保留许可；构建工具不是运行时服务|
|Inno Setup 6.4.3|Inno Setup License（允许商业使用与分发，保留声明）|仅用于编译可选安装包；许可全文随包提供|

精确版本与原始许可证文件在便携包 licenses/ 内。构建脚本自动从安装包元数据复制声明，不把本表代替全文。

Qt 动态库位于 `_internal/PySide6/`，可以替换为 ABI 兼容的修改版本。不得限制用户为调试对 LGPL 组件的修改而进行逆向工程的权利。完整应用源代码和重建脚本可从 https://github.com/pythonofGVR/japanese_offline_translator/tree/v1.1.1 获取（也可下载本版本 Source code），方便更换 Qt / PySide6 后重建。软件未采用加密、签名锁定或静态链接来阻止替换 LGPL 库。

Qt / PySide6 对应版本与来源：

- https://download.qt.io/official_releases/QtForPython/ （对应 PySide6-Essentials 版本的源码）
- https://download.qt.io/official_releases/qt/ （对应 Qt 版本源码与构建资料）
- https://code.qt.io/cgit/pyside/pyside-setup.git/
- https://code.qt.io/cgit/qt/qtbase.git/
- 对应本次版本的源码：https://github.com/qt/qtbase/tree/v6.12.0 ，https://github.com/qt/pyside-pyside-setup/tree/v6.12.0
- https://www.gnu.org/licenses/lgpl-3.0.html
- https://doc.qt.io/qt-6/lgpl.html

未分发 Microsoft 字体；界面使用 Windows 自带字体。Microsoft Visual C++ Runtime DLL 的再分发依照其随附条款；构建时收集依赖，不对旧设备或全新系统作未经验证的兼容性保证。如系统提示缺少运行库，请使用 Microsoft 官方 x64 Visual C++ Redistributable（https://aka.ms/vs/17/release/vc_redist.x64.exe）。
