# 离线模型

构建阶段运行 `python scripts/prepare_models.py` 下载固定版本模型；如需代理，设置当前终端的 HTTPS_PROXY。
运行时只读本地目录，不联网下载，不调用外部翻译 API。
模型文件不进 Git（约 1.75 GB）；完整便携包必须包括 fast/ 与 quality/，以及各自 manifest.json、许可和分词器。
`scripts/build.py` 会校验全部文件 SHA256，并调用打包后的程序实际翻译；缺失或验证失败时拒绝生成发行 ZIP。
