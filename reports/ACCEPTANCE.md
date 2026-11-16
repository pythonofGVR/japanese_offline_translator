# 交付与验收报告

日期：2026-11-16。项目：Japanese Offline Translator（日文离线翻译器）。

## 交付范围

已实现真实 Windows 中文 GUI、本地 CPU 双模型、字幕与文档批量翻译、递归导入、输出目录管理、结构校验、缓存、任务恢复、暂停/继续/取消、质量检查与条件重译、对照编辑保存、单条重译、完整便携 ZIP。安装程序状态见本报告末尾的发行验证记录。

运行时不调用任何翻译 API，不下载模型，不需要 Python、Hugging Face 账户或 API Key。构建阶段下载与运行阶段明确分离。两个模型使用 MIT 许可的固定版本 INT8 转换权重；权重按上游 LFS SHA256 验证，全部资源按本地 manifest 再次验证。

## 实际文件

- 项目：`D:\JapaTran\japanese_offline_translator`
- 程序：`D:\JapaTran\japanese_offline_translator\dist\JapaneseTranslator\JapaneseTranslator.exe`
- 便携包：`D:\JapaTran\japanese_offline_translator\dist\JapaneseTranslatorPortable.zip`
- 安装程序：`D:\JapaTran\japanese_offline_translator\dist\JapaneseTranslatorSetup.exe`
- 模型：`D:\JapaTran\japanese_offline_translator\dist\JapaneseTranslator\models\fast`、`quality`
- 用户指南：项目根目录 `USER_GUIDE.md`，便携目录中也有副本。
- 许可：`LICENSES.md`、便携目录 `licenses/`、各模型目录 `LICENSE` 和原始模型卡。
- 校验清单：`dist\SHA256SUMS.txt`。

## 测试矩阵

PASS 表示已实际执行；PARTIAL 表示仍有明确限制；BLOCKED 表示没有相应验证环境。机器翻译流程通过不代表所有句子语义准确。

|项目|状态|证据与边界|
|---|---|---|
|自动化测试|PASS|32 项，`unit-tests.xml`；含格式、编码、文件保护、GUI 控件、质量规则、取消/暂停|
|两个模型真实 CPU 翻译|PASS|`source-offline.json`；每个模型 10 条原创样本，另测繁体与英文|
|SRT 单文件与多文件|PASS|两个模型均翻译完整文件；子目录内 CP932 SRT 也实际处理|
|ASS / SSA / VTT / LRC|PASS|条目数、时间轴/关键字段、标签与重建结果校验|
|TXT / Markdown / DOCX / PDF|PASS|真实翻译；DOCX 表格与粗体保留，Markdown 代码/链接目标保留，PDF 日文先验证可提取|
|递归、多层目录、输出目录排除|PASS|自动测试和真实文件扫描；跳过链接、已生成译文与不支持类型|
|默认系统文档路径|PASS|Windows SHGetFolderPathW 获取实际 Documents；路径解析自动测试|
|自定义目录与保留子目录|PASS|双模型真实文件输出；未覆盖原始输入|
|冲突与原文保护|PASS|独占预留、自动编号/跳过、原子创建拒绝已有目标；逐文件检查原始字节不变|
|非法字幕与扫描 PDF|PASS|明确报错；批处理单文件失败后继续处理下一文件|
|UTF-8 / BOM / UTF-16 / CP932 / Shift-JIS|PASS|自动解码测试；CP932 文件真实模型集成测试|
|质量检测与自动重译|PASS|假名、重复、长度、数字、币种规则；异常候选按检查分数择优；保留首次/最终译文|
|语义正确性与上下文连贯性|PARTIAL|仍有误译；没有实现跨字幕语义上下文模型、术语库或全局人名一致性约束|
|人工校对与单条重译|PASS|`gui-e2e.json`；真实 worker、原生 Qt 窗口、编辑保存、单条真实推理|
|UI 响应与暂停继续|PASS|真实推理期间事件循环仍运行；暂停在安全边界生效|
|缓存、取消、失败隔离|PASS|`stress.json`；实际缓存命中不再调用推理，不同语言不串缓存；取消不留下最终或临时输出|
|一万条字幕压力测试|PASS|10,000 条重复原创字幕，约 0.67 秒；只有一条不同原文，不能作为普通语料吞吐率|
|任务恢复|PARTIAL|持久化任务列表与片段缓存；文件级恢复，不支持逐 token 或当前原生推理状态恢复|
|源码离线运行|PASS|24 项实际文件/切换检查；联网函数禁止后加载两个模型、翻译、切换、保存|
|打包 EXE 离线运行|PASS|`frozen-offline.json`；同样 24 项检查|
|ZIP 与独立中文/空格路径|PASS|CRC 全部校验；`relocated-offline.json`；清空开发运行环境变量，PATH 仅系统目录|
|打包原生 GUI|PASS|`frozen-gui.png`；中文目录中的实际 EXE 正常启动、模型就绪、正常关闭|
|可选 Windows 安装程序|PASS|Inno Setup 6.4.3 编译；实际安装后双模型离线检查见 `installed-offline.json`|
|完整物理断网/系统级防火墙隔离|BLOCKED|已禁 Python socket 的 connect/connect_ex/create_connection/getaddrinfo；未关闭整机网络，也未防火墙阻断原生库|
|干净 Windows / 其他主机 / Windows 10 / AMD CPU|BLOCKED|没有独立测试设备或虚拟机；不能从本机通过推定跨主机兼容性|
|扫描 PDF OCR|未实现|扫描版明确提示，未内置 OCR|

## 模型与性能

本机 Windows 11 22631 x64，Intel Core i9-13900H，14 核/20 线程，约 31.63 GiB 物理内存。CPU INT8，推理线程 4，beam 3，自动优化。模型加载后翻译 10 条原创测试句；参考译文用于人工检查，没有使用 BLEU/chrF，也没有宣称标准基准优势。

|模型|完整目录大小|源码加载耗时|10 句耗时|采样峰值进程 RSS|
|---|---:|---:|---:|---:|
|M2M100 418M INT8|494,258,959 bytes|0.612 秒|1.629 秒|665,608,192 bytes|
|M2M100 1.2B INT8|1,253,246,395 bytes|1.474 秒|2.691 秒|1,494,233,088 bytes|

数值来自 `source-offline.json`，不是系统最低内存要求。加载时间未包含发行校验工具的完整哈希扫描。RSS 每 20 ms 采样，可能漏掉更短的瞬时峰值。

中文软件目录使用字节/内存加载，避免 SentencePiece/CTranslate2 的 Windows 原生路径编码限制。独立中文目录测试中，快速/质量模型的峰值 RSS 约 1.08 / 2.56 GiB，详见 `relocated-offline.json`。内存不足时仍应使用小模型或把程序放到纯英文路径。

## 实际质量观察

- “今日は晴れです。”：小模型输出“今天是清洁的。”，大模型输出“今天是晴朗的。”。小模型有明显词义错误，规则没有发现这一语义错误。
- 长句“昨日買った本を電車の中で読んでいたら…”：两个模型均把“坐过站”译为类似“走过了下车站”，语义仍不够准确。
- “この商品の価格は1000円です。谢谢。”：小模型输出“1000元”，保留“日元币种可能丢失”人工核对警告；重译没有改善时不会伪造修复成功。大模型输出“1000日元”。
- 重复语气词没有统一删除；样本中两个模型都保留了部分犹豫表达。不同表达仍需逐句人工判断。
- 大模型在本次部分样本更好，但未建立统计上的普遍优势。建议需要准确性的内容使用质量模式并校对。

## 已知限制与后续优先项

复杂 Markdown 扩展语法、嵌套 HTML、数学公式、复杂 ASS 特效和高级 DOCX 域/文本框并未全覆盖。DOCX 按 run 翻译保留格式，跨 run 的语句可能不连贯。PDF 输出纯文本，不复刻排版；缺少可靠 Unicode 映射的 PDF 也可能提取为乱码。自动编码检测不保证总是正确，可以手选编码。

质量分数是异常规则计数，不是语义准确性评分。没有实现跨条目上下文推理、人名术语库、专业翻译记忆库和 OCR。后续优先增加可信的日中评测集、术语约束、跨 run 分句和独立 Windows 10/11 验证。

本次使用固定版本、已公开转换的 fairseq INT8 权重，没有在本机重新执行权重转换。另提供可选的 `scripts/convert_models.py` 与独立转换依赖清单；其参数接口和语法已检查，但没有下载训练框架并执行这一替代转换路径，属于未验证增强工具。

源码、测试和配置已纳入独立 Git 仓库并推送至私有仓库 https://github.com/pythonofGVR/japanese_offline_translator ，任务分支为 `codex/offline-translator`。模型、依赖环境、构建工具、临时输出和原有用户字幕均不进入仓库。最终提交号以交付回复和本地 Git log 为准。
