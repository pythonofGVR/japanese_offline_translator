# 日文离线翻译器

Windows x64 / CPU 离线字幕与文档批量翻译。支持日文 → 简体中文、繁体中文、英文。

打开便携目录中的 `JapaneseTranslator.exe`，添加文件或文件夹，选择模型并开始翻译。双击已完成文件进入可编辑的原译对照。详见 [使用指南](USER_GUIDE.md)。

支持 SRT、ASS、SSA、VTT、LRC、TXT、Markdown、DOCX 和可提取文本的 PDF。原始输入不修改；结果按语言后缀命名，默认冲突自动编号。两档 MIT 许可 M2M100 INT8 模型随最终 ZIP 提供，运行时不调用网络和外部 API。

开发：Python 3.13 x64，项目 `.venv`，依赖固定在 `requirements.lock.txt`。`python scripts/prepare_models.py` 准备并验证模型；`python -m pytest -q` 测试；`python scripts/build.py` 生成带模型与许可的 onedir 和 ZIP。构建会执行打包后 EXE 的真实翻译与离线测试。

验收证据见 `reports/ACCEPTANCE.md`、`reports/source-offline.json`、`reports/frozen-offline.json`。完整需求保存在 `docs/REQUIREMENTS.md`。跨主机、旧 CPU 和干净 Windows 环境必须另行验证，不能由本机打包成功推定。
