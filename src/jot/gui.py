import dataclasses
import os
from pathlib import Path
import traceback

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QFont, QColor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QPushButton, QLabel, QComboBox, QSpinBox, QLineEdit, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QFileDialog, QMessageBox, QProgressBar, QPlainTextEdit, QTabWidget, QSplitter, QScrollArea)

from .engine import Engine, MODEL_NAMES, model_status
from .formats import SUPPORTED
from .jobs import InputFile, Settings, Control, Cancelled, scan, translate_file, save_review, source_hash
from .paths import user_data, default_output, read_json, write_json

class Worker(QThread):
    message = Signal(str)
    file_state = Signal(int, str, object)
    progress = Signal(int, int)
    single_result = Signal(int, object)

    def __init__(self, items, settings, control, single=None):
        super().__init__()
        self.items, self.settings, self.control, self.single = items, settings, control, single

    def run(self):
        engine = None
        try:
            engine = Engine()
            self.message.emit(f'正在加载 {MODEL_NAMES[self.settings.model]} · CPU / {self.settings.threads} 线程')
            engine.load(self.settings.model, self.settings.threads)
            self.message.emit(f'模型已加载，用时 {engine.load_seconds:.2f} 秒')
            if self.single is not None:
                row, text, markdown = self.single
                result = engine.translate([text], self.settings.language, self.settings.quality, self.settings.beam, markdown=markdown, boundary=self.control.boundary, force=True)
                self.single_result.emit(row, result)
                return
            for index, item in self.items:
                self.control.boundary()
                self.file_state.emit(index, '翻译中', {})
                try:
                    result = translate_file(item, self.settings, engine, self.control, lambda a,b: self.progress.emit(a,b))
                    self.file_state.emit(index, result['status'], result)
                except Cancelled:
                    self.file_state.emit(index, '已取消', {})
                    raise
                except Exception as exc:
                    self.file_state.emit(index, '失败', {'reason': str(exc)})
                    self.message.emit(f'{Path(item.path).name}：{exc}')
        except Cancelled:
            self.message.emit('任务已安全取消。已完成文件保留，未完成文件可重新开始。')
        except Exception as exc:
            self.message.emit(f'任务错误：{exc}')
            for index, _ in self.items:
                self.file_state.emit(index, '失败', {'reason': str(exc)})
        finally:
            if engine:
                engine.close()

class ScanWorker(QThread):
    result = Signal(object, object)
    error = Signal(str)

    def __init__(self, folder, recursive, output, extensions):
        super().__init__()
        self.args = folder, recursive, output, extensions

    def run(self):
        try:
            self.result.emit(*scan(*self.args))
        except Exception as exc:
            self.error.emit(str(exc))

def item(text, editable=False):
    cell = QTableWidgetItem(str(text))
    if not editable:
        cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return cell

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('日文离线翻译器')
        self.resize(1280, 860)
        self.setMinimumSize(1000, 700)
        self.setAcceptDrops(True)
        self.inputs, self.results, self.states = [], {}, {}
        self.worker, self.scanner, self.review_result = None, None, None
        self.review_dirty = False
        self.config_path, self.session_path = user_data()/'settings.json', user_data()/'session.json'
        config = read_json(self.config_path, {})
        main = QWidget()
        self.setCentralWidget(main)
        outer = QVBoxLayout(main)
        outer.setContentsMargins(24, 20, 24, 20)
        title = QLabel('日文离线翻译器')
        title.setObjectName('title')
        outer.addWidget(title)
        subtitle = QLabel('本地 CPU 翻译 · 保留原文件 · 字幕与文档批量处理')
        subtitle.setObjectName('muted')
        outer.addWidget(subtitle)
        split = QSplitter()
        outer.addWidget(split, 1)
        settings_panel = QWidget()
        settings_panel.setMaximumWidth(320)
        settings_panel.setMinimumWidth(265)
        settings_layout = QVBoxLayout(settings_panel)
        settings_layout.setContentsMargins(0, 18, 18, 0)
        heading = QLabel('翻译设置')
        heading.setObjectName('heading')
        settings_layout.addWidget(heading)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setVerticalSpacing(10)
        self.model = QComboBox()
        self.model.addItem('快速模式 · M2M100 418M', 'fast')
        self.model.addItem('质量模式 · M2M100 1.2B', 'quality')
        self.model_status = QLabel()
        self.model_status.setWordWrap(True)
        self.model_status.setObjectName('muted')
        self.language = QComboBox()
        for label, value in [('简体中文','zh-CN'),('繁體中文','zh-TW'),('English','en')]:
            self.language.addItem(label, value)
        self.quality = QComboBox()
        for label,value in [('标准翻译（不重译）','standard'),('自动质量优化','auto'),('质量优先（更多检查）','best')]:
            self.quality.addItem(label,value)
        self.encoding = QComboBox()
        for name in ['auto','utf-8-sig','utf-16','cp932','shift_jis']:
            self.encoding.addItem('自动检测' if name == 'auto' else name, name)
        self.threads = QSpinBox()
        self.threads.setRange(1, max(1, os.cpu_count() or 1))
        self.threads.setValue(4)
        self.beam = QSpinBox()
        self.beam.setRange(1, 10)
        self.beam.setValue(3)
        self.conflict = QComboBox()
        self.conflict.addItem('重名时自动编号（不覆盖）', 'rename')
        self.conflict.addItem('跳过已有同名文件', 'skip')
        for label,control in [('翻译模型',self.model),('',self.model_status),('目标语言',self.language),('质量等级',self.quality),('文本编码',self.encoding),('CPU 线程数',self.threads),('搜索宽度（越高越慢）',self.beam),('文件冲突',self.conflict)]:
            form.addRow(label,control)
        settings_layout.addLayout(form)
        self.output = QLineEdit()
        self.output.setPlaceholderText(str(default_output()))
        self.output.setToolTip('留空时保存到系统文档目录下 JapaneseTranslatorOutput')
        settings_layout.addWidget(QLabel('输出目录（留空使用默认目录）'))
        settings_layout.addWidget(self.output)
        self.output_button = QPushButton('选择输出目录…')
        self.output_button.clicked.connect(self.choose_output)
        settings_layout.addWidget(self.output_button)
        self.preserve = QCheckBox('保留输入文件夹的子目录结构')
        self.preserve.setChecked(True)
        self.recursive = QCheckBox('添加文件夹时扫描子目录')
        self.recursive.setChecked(True)
        settings_layout.addWidget(self.preserve)
        settings_layout.addWidget(self.recursive)
        self.filter = QComboBox()
        self.filter.addItem('全部支持类型', sorted(SUPPORTED))
        self.filter.addItem('仅字幕', ['.srt','.ass','.ssa','.vtt','.lrc'])
        self.filter.addItem('仅文档', ['.txt','.md','.docx','.pdf'])
        settings_layout.addWidget(self.filter)
        settings_layout.addStretch()
        self.open_output = QPushButton('打开输出目录')
        self.open_output.clicked.connect(lambda: self.open_folder())
        settings_layout.addWidget(self.open_output)
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        settings_scroll.setMinimumWidth(290)
        settings_scroll.setMaximumWidth(340)
        settings_scroll.setWidget(settings_panel)
        split.addWidget(settings_scroll)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 18, 0, 0)
        buttons = QHBoxLayout()
        self.add_button = QPushButton('添加文件…')
        self.folder_button = QPushButton('添加文件夹…')
        self.remove_button = QPushButton('移除选中')
        self.clear_button = QPushButton('清空列表')
        for b, callback in [(self.add_button,self.choose_files),(self.folder_button,self.choose_folder),(self.remove_button,self.remove_selected),(self.clear_button,self.clear_files)]:
            buttons.addWidget(b)
            b.clicked.connect(callback)
        right_layout.addLayout(buttons)
        self.tabs = QTabWidget()
        right_layout.addWidget(self.tabs, 1)
        self.files = QTableWidget(0, 4)
        self.files.setHorizontalHeaderLabels(['文件 / 拖放文件到此窗口','类型','大小','状态'])
        self.files.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.files.setColumnWidth(1,65)
        self.files.setColumnWidth(2,90)
        self.files.setColumnWidth(3,100)
        self.files.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.files.setAlternatingRowColors(True)
        self.files.doubleClicked.connect(self.show_review)
        self.tabs.addTab(self.files,'任务列表')
        review_panel = QWidget()
        rv = QVBoxLayout(review_panel)
        self.review_label = QLabel('双击已完成文件，查看原文与译文。译文列可直接编辑。')
        self.review_label.setWordWrap(True)
        rv.addWidget(self.review_label)
        self.review = QTableWidget(0,5)
        self.review.setHorizontalHeaderLabels(['序号 / 时间','日文原文','首次译文 / 缓存结果','当前译文（可编辑）','检查提示'])
        for col in (1,2,3):
            self.review.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeMode.Stretch)
        self.review.setColumnWidth(0,150)
        self.review.setColumnWidth(4,130)
        self.review.itemChanged.connect(lambda _: setattr(self,'review_dirty',True))
        rv.addWidget(self.review)
        review_controls = QHBoxLayout()
        self.retranslate_button = QPushButton('重译选中条目')
        self.save_button = QPushButton('保存校对结果')
        self.load_review_button = QPushButton('打开历史校对记录…')
        for b,callback in [(self.retranslate_button,self.retranslate),(self.save_button,self.save_edits),(self.load_review_button,self.open_review)]:
            review_controls.addWidget(b)
            b.clicked.connect(callback)
        rv.addLayout(review_controls)
        self.tabs.addTab(review_panel,'结果校对')
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1500)
        self.tabs.addTab(self.log,'运行日志')
        self.summary = QLabel('添加文件或文件夹，然后开始翻译。')
        right_layout.addWidget(self.summary)
        self.total_progress = QProgressBar()
        self.total_progress.setFormat('文件 %v / %m')
        self.unit_progress = QProgressBar()
        self.unit_progress.setFormat('当前文件片段 %v / %m')
        self.total_progress.setRange(0,1)
        self.total_progress.setValue(0)
        self.unit_progress.setRange(0,1)
        self.unit_progress.setValue(0)
        right_layout.addWidget(self.total_progress)
        right_layout.addWidget(self.unit_progress)
        actions = QHBoxLayout()
        self.start_button = QPushButton('开始翻译 / 重试未完成项')
        self.start_button.setObjectName('primary')
        self.pause_button = QPushButton('暂停')
        self.cancel_button = QPushButton('取消')
        for b,callback in [(self.start_button,self.start),(self.pause_button,self.pause),(self.cancel_button,self.cancel)]:
            actions.addWidget(b)
            b.clicked.connect(callback)
        right_layout.addLayout(actions)
        split.addWidget(right)
        split.setStretchFactor(1,1)
        for name in ('model','language','quality','encoding','conflict'):
            control = getattr(self,name)
            control.setCurrentIndex(max(0,control.findData(config.get(name,Settings().__dict__.get(name)))))
        self.output.setText(config.get('output',''))
        self.threads.setValue(config.get('threads',4))
        self.beam.setValue(config.get('beam',3))
        self.preserve.setChecked(config.get('preserve',True))
        self.model.currentIndexChanged.connect(self.refresh_model)
        self.refresh_model()
        self.busy(False)
        self.restore_session()

    def settings(self):
        return Settings(**{n:getattr(self,n).currentData() for n in ('model','language','quality','encoding','conflict')},output=self.output.text().strip(),threads=self.threads.value(),beam=self.beam.value(),preserve=self.preserve.isChecked())

    def refresh_model(self):
        ready,size = model_status(self.model.currentData())
        memory = '约 2–4 GB' if self.model.currentData()=='fast' else '约 4–8 GB'
        self.model_status.setText(f'{"模型就绪" if ready else "模型缺失或下载未完成"} · {size/1024**3:.2f} GB\nCPU · 内存估计 {memory}（非最低保证）')

    def busy(self, value):
        for widget in (self.add_button,self.folder_button,self.remove_button,self.clear_button,self.model,self.language,self.quality,self.encoding,self.threads,self.beam,self.conflict,self.output,self.output_button,self.preserve,self.recursive,self.filter,self.start_button,self.save_button,self.retranslate_button,self.load_review_button):
            widget.setEnabled(not value)
        self.pause_button.setEnabled(value)
        self.cancel_button.setEnabled(value)
        self.review.setEnabled(not value)

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self,'选择输出目录',self.output.text())
        if path:
            self.output.setText(path)

    def choose_files(self):
        files,_ = QFileDialog.getOpenFileNames(self,'添加日文字幕或文档','','支持的文件 ('+' '.join('*'+s for s in sorted(SUPPORTED))+')')
        self.add_inputs([InputFile(f) for f in files])

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self,'选择输入文件夹')
        if path:
            self.scan_folder(path)

    def scan_folder(self,path):
        if self.worker or self.scanner:
            return
        self.busy(True)
        self.pause_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.summary.setText('正在扫描文件夹…')
        self.scanner = ScanWorker(path,self.recursive.isChecked(),self.output.text(),self.filter.currentData())
        self.scanner.result.connect(self.scanned)
        self.scanner.error.connect(lambda e: QMessageBox.warning(self,'扫描失败',e))
        self.scanner.finished.connect(self.scan_finished)
        self.scanner.start()

    def scanned(self,files,skipped):
        self.add_inputs(files)
        self.log.appendPlainText(f'扫描完成：支持 {len(files)} 个，跳过 {len(skipped)} 个（不支持、已翻译或链接）')

    def scan_finished(self):
        self.scanner.deleteLater()
        self.scanner=None
        self.busy(False)

    def add_inputs(self,files):
        known={str(Path(i.path).resolve()).casefold() for i in self.inputs}
        self.files.setUpdatesEnabled(False)
        for entry in files:
            path=Path(entry.path)
            key=str(path.resolve()).casefold()
            if not path.is_file() or path.suffix.lower() not in SUPPORTED or key in known:
                continue
            known.add(key)
            row=len(self.inputs)
            self.inputs.append(entry)
            self.files.insertRow(row)
            for col,value in enumerate((path.name,path.suffix,f'{path.stat().st_size/1024:.1f} KB','待处理')):
                self.files.setItem(row,col,item(value))
            self.files.item(row,0).setToolTip(str(path))
            self.states[row]='待处理'
        self.files.setUpdatesEnabled(True)
        self.update_summary()
        self.persist()

    def remove_selected(self):
        removed={i.row() for i in self.files.selectionModel().selectedRows()}
        entries=[(e,self.states.get(i,'待处理'),self.results.get(i)) for i,e in enumerate(self.inputs) if i not in removed]
        self.clear_files()
        for e,state,result in entries:
            self.add_inputs([e])
            self.file_state(len(self.inputs)-1,state,result or {})

    def clear_files(self):
        self.inputs,self.results,self.states=[],{},{}
        self.files.setRowCount(0)
        self.update_summary()
        self.persist()

    def start(self):
        if not self.inputs:
            QMessageBox.information(self,'尚未添加文件','请添加字幕、文档或文件夹。')
            return
        if not self.discard_edits():
            return
        settings=self.settings()
        if not model_status(settings.model)[0]:
            QMessageBox.warning(self,'模型不可用','请等待构建完成，或使用包含两个完整模型的便携包。')
            return
        jobs=[(i,e) for i,e in enumerate(self.inputs) if self.states.get(i) not in ('已完成','已跳过')]
        if not jobs:
            QMessageBox.information(self,'全部任务已完成','如需更换模型或语言重新翻译，请清空列表后重新添加。')
            return
        write_json(self.config_path,dataclasses.asdict(settings))
        self.control=Control()
        self.worker=Worker(jobs,settings,self.control)
        self.connect_worker()
        self.busy(True)
        self.worker.start()

    def connect_worker(self):
        self.worker.message.connect(self.log.appendPlainText)
        self.worker.file_state.connect(self.file_state)
        self.worker.progress.connect(self.unit_update)
        self.worker.single_result.connect(self.single_done)
        self.worker.finished.connect(self.finished)

    def file_state(self,index,state,result):
        if index>=len(self.inputs):
            return
        self.states[index]=state
        if result:
            self.results[index]=result
        self.files.item(index,3).setText(state)
        self.files.item(index,3).setToolTip(result.get('reason','') if result else '')
        self.update_summary()
        self.persist()

    def unit_update(self,done,total):
        self.unit_progress.setRange(0,max(1,total))
        self.unit_progress.setValue(done if total else 1)

    def update_summary(self):
        success=sum(s=='已完成' for s in self.states.values())
        failed=sum(s=='失败' for s in self.states.values())
        terminal=sum(s in ('已完成','失败','已跳过','已取消') for s in self.states.values())
        self.summary.setText(f'共 {len(self.inputs)} 个文件 · 成功 {success} · 失败 {failed} · 双击已完成项进入校对')
        self.total_progress.setRange(0,max(1,len(self.inputs)))
        self.total_progress.setValue(terminal)

    def pause(self):
        if not self.worker:
            return
        if self.control.running.is_set():
            self.control.running.clear()
            self.pause_button.setText('继续')
            self.log.appendPlainText('将在当前推理批次结束后暂停。')
        else:
            self.control.running.set()
            self.pause_button.setText('暂停')

    def cancel(self):
        if self.worker:
            self.control.cancel()
            self.log.appendPlainText('正在取消，将在当前推理批次结束后停止。')

    def finished(self):
        self.worker.deleteLater()
        self.worker=None
        self.busy(False)
        self.pause_button.setText('暂停')
        self.persist()

    def discard_edits(self):
        return not self.review_dirty or QMessageBox.question(self,'尚有未保存修改','放弃当前校对修改并继续？')==QMessageBox.StandardButton.Yes

    def show_review(self):
        if self.worker or not self.discard_edits():
            return
        result=self.results.get(self.files.currentRow())
        if not result or result.get('status')!='已完成':
            return
        self.fill_review(result)

    def fill_review(self,result):
        self.review_result=result
        self.review.blockSignals(True)
        self.review.setRowCount(len(result['rows']))
        for r,row in enumerate(result['rows']):
            for c,value in enumerate((row['label'],row['source'],row['initial'],row['target'],'；'.join(row['warnings']))):
                self.review.setItem(r,c,item(value,c==3))
            self.review.setRowHeight(r,76)
            if row['warnings']:
                self.review.item(r,4).setBackground(QColor('#fff2cc'))
        self.review.blockSignals(False)
        self.review_dirty=False
        self.review_label.setText(f'{Path(result["source"]).name}\n输出：{result["output"]}\n'+ '；'.join(result.get('warnings',[])))
        self.tabs.setCurrentIndex(1)

    def open_review(self):
        if not self.discard_edits():
            return
        path,_=QFileDialog.getOpenFileName(self,'打开校对记录',str(self.output.text() or default_output()),'校对记录 (*.review.json)')
        if path:
            result=read_json(path,{})
            if result.get('rows') and result.get('source_hash'):
                self.fill_review(result)
            else:
                QMessageBox.warning(self,'记录无效','不是有效的校对记录。')

    def save_edits(self):
        if not self.review_result:
            return
        try:
            targets=[self.review.item(r,3).text() for r in range(self.review.rowCount())]
            save_review(self.review_result,targets)
            self.review_dirty=False
            self.log.appendPlainText('校对已保存：'+self.review_result['output'])
            self.statusBar().showMessage('校对结果已保存',5000)
        except Exception as exc:
            QMessageBox.warning(self,'保存失败',str(exc))

    def retranslate(self):
        row=self.review.currentRow()
        if row<0 or not self.review_result:
            return
        settings=Settings(**self.review_result['settings'])
        self.control=Control()
        self.worker=Worker([],settings,self.control,single=(row,self.review_result['rows'][row]['source'],Path(self.review_result['source']).suffix.lower()=='.md'))
        self.connect_worker()
        self.busy(True)
        self.worker.start()

    def single_done(self,row,result):
        target,initial,flags=result
        self.review.item(row,3).setText(target[0])
        self.review.item(row,4).setText('；'.join(flags[0]))
        self.review_result['rows'][row]['warnings']=flags[0]
        self.review_dirty=True

    def open_folder(self):
        path=Path(self.output.text() or default_output())
        path.mkdir(parents=True,exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def persist(self):
        entries=[dict(path=e.path,root=e.root,state=self.states.get(i,'待处理'),review=(self.results.get(i,{}).get('output','')+'.review.json') if self.results.get(i,{}).get('output') else '') for i,e in enumerate(self.inputs)]
        write_json(self.session_path,entries)

    def restore_session(self):
        saved=read_json(self.session_path,[])
        for entry in saved:
            if not Path(entry.get('path','')).is_file():
                continue
            self.add_inputs([InputFile(entry['path'],entry.get('root',''))])
            index=len(self.inputs)-1
            result=read_json(entry.get('review',''),{})
            if result.get('status')=='已完成' and Path(result.get('output','')).is_file() and result.get('source_hash')==source_hash(entry['path']):
                self.file_state(index,'已完成',result)
        if saved:
            self.log.appendPlainText('已恢复上次任务列表。未完成文件可重新开始；片段缓存会复用。')

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and not self.worker and not self.scanner:
            event.acceptProposedAction()

    def dropEvent(self,event):
        paths=[Path(u.toLocalFile()) for u in event.mimeData().urls()]
        self.add_inputs([InputFile(str(p)) for p in paths if p.is_file()])
        folders=[p for p in paths if p.is_dir()]
        if folders:
            self.scan_folder(str(folders[0]))
        event.acceptProposedAction()

    def closeEvent(self,event):
        if self.worker or self.scanner:
            QMessageBox.information(self,'任务仍在运行','请先取消翻译并等待当前批次结束，或等待扫描完成。')
            event.ignore()
            return
        if not self.discard_edits():
            event.ignore()
            return
        write_json(self.config_path,dataclasses.asdict(self.settings()))
        self.persist()
        event.accept()

STYLE = '''
QWidget { font-family: "Microsoft YaHei UI", "Segoe UI"; font-size: 13px; color: #202e3e; }
QMainWindow { background: #f3f5f8; }
QLabel#title { font-size: 25px; font-weight: 600; }
QLabel#heading { font-size: 16px; font-weight: 600; margin-bottom: 10px; }
QLabel#muted { color: #526278; }
QPushButton { background: #ffffff; border: 1px solid #b8c4d2; border-radius: 5px; padding: 8px 10px; }
QPushButton:hover { background: #e8eff8; border-color: #577ba9; }
QPushButton:pressed { background: #dbe7f7; }
QPushButton:focus { border: 2px solid #235b9c; }
QPushButton#primary { background: #245b94; color: white; border-color: #245b94; font-weight: 600; }
QPushButton#primary:hover { background: #184b82; }
QPushButton:disabled { background: #e8ecf1; color: #687789; border-color: #d1d8e2; }
QLineEdit, QComboBox, QSpinBox { background: white; padding: 6px; border: 1px solid #b8c4d2; border-radius: 4px; min-height: 18px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 2px solid #245b94; }
QTableWidget, QPlainTextEdit { background: white; alternate-background-color: #f5f7fa; border: 1px solid #cbd4e0; gridline-color: #e4e9f0; selection-background-color: #dbe9fb; selection-color: #173957; }
QHeaderView::section { background: #eaf0f6; padding: 9px 6px; border: 0; border-right: 1px solid #d4dce6; font-weight: 600; }
QTabWidget::pane { border: 0; }
QTabBar::tab { padding: 10px 20px; background: #e8edf3; color: #44576c; }
QTabBar::tab:selected { background: white; color: #184c84; font-weight: 600; }
QProgressBar { border: 1px solid #b9c5d3; border-radius: 3px; background: white; text-align: center; min-height: 20px; }
QProgressBar::chunk { background: #8cb5df; }
QCheckBox { padding: 4px 0; }
QSplitter::handle { background: #dbe2eb; width: 1px; }
'''

def launch():
    app=QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    window=MainWindow()
    window.show()
    return app.exec()
