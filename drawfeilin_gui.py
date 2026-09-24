# -*- coding: utf-8 -*-
"""drawfeilin 图形界面（GUI）入口。

功能：
    1. 选择工作目录与 config.ini；
    2. 可视化编辑配置（DEFAULT / EXTRA / LONGTHROUGHHOLE / 拼网区块 1..10）；
    3. 一键运行 drawfeilin 核心程序，实时显示日志；
    4. 运行结束后列出生成的 DXF/TXT/DRL 文件，并可打开输出目录。

运行方式：
    python drawfeilin_gui.py
    （打包后为 drawfeilin.exe，无需 Python 环境）
"""

import os
import re
import sys
import queue
import shutil
import threading
import time
import traceback
import configparser
import html
import tempfile

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import openpyxl
except Exception:  # pragma: no cover - 运行环境缺依赖时提示
    openpyxl = None

# 保证无论从哪个目录启动都能找到同目录下的核心模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import drawfeilin  # noqa: E402


# ============================================================================
# 路径工具（区分开发环境与打包后的 exe）
# ============================================================================

def app_dir():
    """返回程序所在目录；打包为 exe 后返回 exe 所在目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path):
    """返回打包资源（如 README.md）的绝对路径，开发与 exe 环境通用。"""
    if getattr(sys, 'frozen', False):
        base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


# ============================================================================
# 轻量 Markdown -> HTML（纯标准库，供使用说明在外部浏览器打开）
# ============================================================================

_MD_INLINE = re.compile(
    r'(\*\*[^*]+\*\*|`[^`]*`|\[([^\]]+)\]\(([^)]*)\))')
_MD_HEADING = re.compile(r'^(#{1,6})\s*(.*)$')
_MD_BULLET = re.compile(r'^(\s*)[*\-+]\s+(.*)$')
_MD_ORDERED = re.compile(r'^(\s*)(\d+)[.)]\s+(.*)$')
_MD_HR = re.compile(r'^\s*(?:---|\*\*\*|___)\s*$')

_USAGE_CSS = """
body { font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
       max-width: 900px; margin: 24px auto; padding: 0 24px;
       color: #222; line-height: 1.75; }
h1, h2, h3, h4, h5, h6 { color: #0b57d0; margin: 1.4em 0 .5em; }
h2 { border-bottom: 1px solid #dde; padding-bottom: 4px; }
pre { background: #f5f5f5; border: 1px solid #ddd; border-radius: 6px;
      padding: 12px 14px; overflow-x: auto; font-size: 13px; }
code { background: #f0f0f0; padding: 1px 5px; border-radius: 3px;
       font-family: Consolas, "Courier New", monospace; }
pre code { background: none; padding: 0; }
ul, ol { padding-left: 28px; }
li { margin: 4px 0; }
hr { border: none; border-top: 1px solid #ddd; margin: 22px 0; }
a { color: #0b57d0; }
"""


def _inline_html(text):
    """把一行中的 **粗体**、`行内代码`、[文字](链接) 转成 HTML。"""

    def replace(match):
        token = match.group(1)
        if token.startswith('**'):
            return '<strong>%s</strong>' % html.escape(token[2:-2], quote=False)
        if token.startswith('`'):
            return '<code>%s</code>' % html.escape(token[1:-1], quote=False)
        return '<a href="%s">%s</a>' % (
            html.escape(match.group(3), quote=True),
            html.escape(match.group(2), quote=False))

    parts = []
    pos = 0
    for match in _MD_INLINE.finditer(text):
        parts.append(html.escape(text[pos:match.start()], quote=False))
        parts.append(replace(match))
        pos = match.end()
    parts.append(html.escape(text[pos:], quote=False))
    return ''.join(parts)


def markdown_to_html(content):
    """把 README 的 Markdown 内容转成 HTML 片段（不含页面外壳）。"""
    out = []
    list_stack = []

    def close_lists(depth=0):
        while len(list_stack) > depth:
            out.append('</%s>' % list_stack.pop())

    lines = content.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        # 代码围栏
        if stripped.startswith('```'):
            close_lists()
            index += 1
            block = []
            while index < len(lines) and not lines[index].strip().startswith('```'):
                block.append(lines[index])
                index += 1
            index += 1  # 跳过结束围栏
            if block:
                out.append(
                    '<pre><code>%s</code></pre>'
                    % html.escape('\n'.join(block), quote=False))
            continue

        # 标题（兼容 # 后无空格）
        match = _MD_HEADING.match(line)
        if match:
            close_lists()
            title = match.group(2).strip()
            if title:
                level = len(match.group(1))
                out.append(
                    '<h%d>%s</h%d>' % (level, _inline_html(title), level))
            index += 1
            continue

        # 分隔线
        if _MD_HR.match(line):
            close_lists()
            out.append('<hr>')
            index += 1
            continue

        # 无序列表（含前导空格的多级列表）
        match = _MD_BULLET.match(line)
        if match:
            level = 1 if len(match.group(1)) else 0
            close_lists(level)
            if len(list_stack) == level:
                out.append('<ul>')
                list_stack.append('ul')
            out.append('<li>%s</li>' % _inline_html(match.group(2).strip()))
            index += 1
            continue

        # 有序列表
        match = _MD_ORDERED.match(line)
        if match:
            level = 1 if len(match.group(1)) else 0
            close_lists(level)
            if len(list_stack) == level:
                out.append('<ol>')
                list_stack.append('ol')
            out.append('<li>%s</li>' % _inline_html(match.group(3).strip()))
            index += 1
            continue

        # 空行 / 普通段落
        close_lists()
        if stripped:
            out.append('<p>%s</p>' % _inline_html(stripped))
        index += 1

    close_lists()
    return '\n'.join(out)


def build_usage_html(content):
    """把 README 内容包成带样式的完整 HTML 页面。"""
    body = markdown_to_html(content)
    return (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<title>drawfeilin 使用说明</title>\n'
        '<style>%s</style>\n</head>\n<body>\n%s\n</body>\n</html>\n'
        % (_USAGE_CSS, body))


def write_usage_html(content):
    """把使用说明 HTML 写入临时文件，返回文件路径。"""
    fd, path = tempfile.mkstemp(
        suffix='.html', prefix='drawfeilin_usage_')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(build_usage_html(content))
    return path


# ============================================================================
# 配置读写与校验（与界面无关，便于测试）
# ============================================================================

YES_NO = ('Yes', 'No')

# 选项名称 -> 控件/校验类型；未列出的选项一律按文本处理
OPTION_TYPES = {
    '图案全局缩放比例': 'float',
    '图案原点X坐标': 'float',
    '图案原点Y坐标': 'float',
    '瓷体X方向收缩率': 'float',
    '瓷体Y方向收缩率': 'float',
    '内部图案X方向中心收缩率': 'float',
    '内部图案Y方向中心收缩率': 'float',
    '放缩率数量': 'int',
    'X方向放缩率差值': 'float',
    'Y方向放缩率差值': 'float',
    '产品设计x方向长度': 'float',
    '产品设计y方向长度': 'float',
    '菲林x方向阵列列数': 'int',
    '菲林y方向阵列列数': 'int',
    '引出端x方向延伸距离': 'float',
    '引出端y方向延伸距离': 'float',
    '切割线x方向偏移距离': 'float',
    '切割线y方向偏移距离': 'float',
    'MARK旋转角度': 'int',
    'MARK的X方向偏移': 'float',
    'MARK的Y方向偏移': 'float',
    'MARK文字高度': 'float',
    '通孔孔径': 'float',
    'PAD孔径': 'float',
    '点网孔径': 'float',
    '假引孔阈值': 'float',
    '定位孔孔径': 'float',
    '长通孔孔径': 'float',
    '拼网列分割数': 'int',
    '拼网行分割数': 'int',
    '是否输出LDI': 'bool',
    '是否开孔阵列满': 'bool',
    '是否旋转90度': 'bool',
    '90度旋转方向': '逆时针|顺时针',
    '图案来源': '原图|编辑总图',
    '通孔层是否增加点网': 'bool',
    '是否引出端增绘': 'bool',
    '是否启用': 'bool',
    '默认最小间距': 'float',
    '默认最小留边量': 'float',
    '是否绘制通孔层': 'bool',
    '是否绘制长通孔DXF文件': 'bool',
    '根据通孔绘制PAD': 'bool',
    '是否绘制MARK标识': 'bool',
    '是否镜像图层': 'bool',
    '是否切割线内缩': 'bool',
    '长通孔模式是否镜像': 'bool',
}


def _option_type(name):
    """按配置存储名查询控件类型（兼容 configparser 对 ASCII 的小写化）。"""
    if name in OPTION_TYPES:
        return OPTION_TYPES[name]
    lowered = name.lower()
    for key, value in OPTION_TYPES.items():
        if key.lower() == lowered:
            return value
    return None


# “全局设置”页签字段（大小写不敏感匹配，兼容 configparser 小写化）
GLOBAL_SETTING_KEYS = [
    '图案全局缩放比例',
    '图案原点X坐标',
    '图案原点Y坐标',
    '切割线x方向偏移距离',
    '切割线y方向偏移距离',
    '菲林英寸',
    '不做多种放缩的图层',
]

# “通孔”页签字段
HOLE_SETTING_KEYS = [
    '是否绘制通孔层',
    '根据通孔绘制PAD',
    '通孔孔径',
    'PAD孔径',
    '点网孔径',
    '假引孔阈值',
    '定位孔孔径',
]

# 属于 DEFAULT 但归“长通孔”页签展示的字段
LONGHOLE_DEFAULT_KEYS = [
    '是否绘制长通孔DXF文件',
]

# 不在界面显示、也不写回配置的字段（功能已停用或改由成型参数表提供）
HIDDEN_DEFAULT_KEYS = [
    '假引孔孔径',
    '引出端绘制长度',
    '引出端绘制宽度',
]

# 拼网区块页签不再显示的字段（仍可由 config.ini 手工配置，核心保留读取）
BLOCK_HIDDEN_FIELDS = [
    '需要做xy方向延伸的图层',
    '图层与通孔配对(实际)',
    '需要绘制假引的图层',
    '绘制假引孔的图层',
]

# “MARK设置”页签字段
MARK_SETTING_KEYS = [
    'MARK旋转角度',
    'MARK的X方向偏移',
    'MARK的Y方向偏移',
    'MARK文字高度',
    'MARK标识',
    '表示放缩率的MARK标识',
    '拼网区块x方向MARK标识',
    '拼网区块y方向MARK标识',
    '是否绘制MARK标识',
]

# 无 config.ini 启动时“全局设置”页签显示的内置默认值
DEFAULT_GLOBAL_VALUES = {
    '图案全局缩放比例': '1',
    '图案原点X坐标': '0.0',
    '图案原点Y坐标': '0.0',
    '切割线x方向偏移距离': '50',
    '切割线y方向偏移距离': '50',
    '菲林英寸': '6',
    '不做多种放缩的图层': 'Mark|Outline',
}


def _in_keys(option, key_list):
    """大小写不敏感地判断 option 是否属于 key_list。"""
    lowered = option.lower()
    return any(key.lower() == lowered for key in key_list)


def read_ini(path):
    """读取 utf-8-sig 编码的 INI 文件，返回 {区块: {选项: 值}}。"""
    parser = configparser.ConfigParser()
    with open(path, 'r', encoding='utf-8-sig') as f:
        parser.read_file(f)
    result = {}
    if parser.defaults():
        result['DEFAULT'] = dict(parser.defaults())
    for section in parser.sections():
        result[section] = dict(parser._sections[section])
    return result


def validate_option(name, value, option_type):
    """校验单个配置值，返回错误说明；无错误返回 None。"""
    if value == '':
        # 未使用的拼网区块等场景允许留空，核心程序只在用到时才读取
        return None
    if option_type == 'bool':
        return None if value in YES_NO else '只能填写 Yes 或 No'
    if option_type == 'int':
        try:
            int(value)
        except (TypeError, ValueError):
            return '必须填写整数'
        return None
    if option_type == 'float':
        try:
            float(value)
        except (TypeError, ValueError):
            return '必须填写数字'
        return None
    return None


def validate_config(data):
    """校验整份配置，返回 [(区块, 选项, 错误说明), ...]。"""
    errors = []
    for section, options in data.items():
        for option, value in options.items():
            option_type = _option_type(option) or 'text'
            error = validate_option(option, value, option_type)
            if error:
                errors.append((section, option, error))
    return errors


def write_ini(path, data):
    """以 utf-8-sig 写回 INI（覆盖前生成 .bak 备份）。"""
    try:
        shutil.copy2(path, path + '.bak')
    except OSError:
        pass  # 备份失败不阻止保存
    parser = configparser.ConfigParser()
    for section, options in data.items():
        parser[section] = options
    with open(path, 'w', encoding='utf-8-sig', newline='\r\n') as f:
        parser.write(f)


# ============================================================================
# 日志输出重定向（把核心程序的 print 送入队列，由主线程刷新界面）
# ============================================================================

class QueueWriter(object):
    """把 write 的内容放入队列，供 GUI 主线程轮询显示。"""

    def __init__(self, log_queue):
        self.log_queue = log_queue

    def write(self, text):
        if text and text.strip():
            self.log_queue.put(('log', text))

    def flush(self):
        pass


def _tab_title(section):
    """区块名 -> 页签标题。"""
    if section == 'DEFAULT':
        return '基础参数'
    if section == 'EXTRA':
        return '扩展参数'
    if section == 'LONGTHROUGHHOLE':
        return '长通孔'
    if section.isdigit():
        return '拼网区块 %s' % section
    return section


# ============================================================================
# 主界面
# ============================================================================

class App(object):
    """drawfeilin GUI 主窗口。"""

    def __init__(self, root):
        self.root = root
        self.workdir_var = tk.StringVar()
        self.config_path_var = tk.StringVar()
        self.status_var = tk.StringVar(value='就绪')
        self.log_queue = queue.Queue()
        self.running = False
        self.section_vars = {}
        self.data = {}
        self.config_loaded = False
        self._output_files = []
        # 导入的成型参数表（仅本次会话有效）：{'order': [...], 'pairs': {...}}
        self.form_layout = None
        self.form_layout_source = ''

        self._build_ui()
        self._poll_queue()

        base_dir = app_dir()
        self.workdir_var.set(base_dir)
        default_config = os.path.join(base_dir, 'config.ini')
        if os.path.isfile(default_config):
            self.config_path_var.set(default_config)
            if not self._load_config(quiet=True):
                self._start_without_config()
        else:
            self._start_without_config()

    def _start_without_config(self):
        """无 config.ini 启动：只显示“全局设置”页签并带内置默认值。"""
        placeholder = {'DEFAULT': dict(DEFAULT_GLOBAL_VALUES)}
        self.data = placeholder
        self.config_loaded = False
        self._rebuild_tabs(placeholder)
        self.status_var.set('未加载配置文件，可手动载入')

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        self.root.title('drawfeilin 菲林自动绘制工具')
        self.root.geometry('960x780')
        self.root.minsize(820, 640)

        # ---- 主菜单 ----
        menubar = tk.Menu(self.root)

        ring_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label='定位孔配置', menu=ring_menu)
        self.ring_menu = ring_menu
        self.ring_mode_var = tk.StringVar(value=drawfeilin.POSITION_RING_MODE)
        for mode in ('4H', '5H'):
            ring_menu.add_radiobutton(
                label=mode,
                value=mode,
                variable=self.ring_mode_var,
                command=lambda m=mode: drawfeilin.set_position_ring_mode(m))

        sx_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label='盛雄开孔模式', menu=sx_menu)
        self.sx_menu = sx_menu
        self.sx_mode_var = tk.IntVar(value=drawfeilin.SHENGXIONG_MODE)
        for mode in (1, 2):
            sx_menu.add_radiobutton(
                label='模式%d' % mode,
                value=mode,
                variable=self.sx_mode_var,
                command=lambda m=mode: drawfeilin.set_shengxiong_mode(m))

        source_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label='图案来源', menu=source_menu)
        self.source_menu = source_menu
        self.pattern_source_var = tk.StringVar(value='编辑总图')
        for mode in ('原图', '编辑总图'):
            source_menu.add_radiobutton(
                label=mode,
                value=mode,
                variable=self.pattern_source_var,
                command=self._on_pattern_source_changed)

        self.root.config(menu=menubar)

        main = ttk.Frame(self.root, padding=8)
        main.pack(fill='both', expand=True)

        # ---- 文件设置 ----
        file_frame = ttk.LabelFrame(main, text='文件设置', padding=8)
        file_frame.pack(fill='x', pady=(0, 6))

        ttk.Label(file_frame, text='工作目录:').grid(
            row=0, column=0, sticky='w', padx=(0, 6), pady=3)
        self.workdir_entry = ttk.Entry(file_frame, textvariable=self.workdir_var)
        self.workdir_entry.grid(row=0, column=1, sticky='ew', pady=3)
        ttk.Button(file_frame, text='浏览...', command=self._choose_workdir).grid(
            row=0, column=2, padx=(6, 0), pady=3)

        ttk.Label(file_frame, text='配置文件:').grid(
            row=1, column=0, sticky='w', padx=(0, 6), pady=3)
        self.config_path_entry = ttk.Entry(
            file_frame, textvariable=self.config_path_var)
        self.config_path_entry.grid(row=1, column=1, sticky='ew', pady=3)
        ttk.Button(file_frame, text='浏览...', command=self._choose_config).grid(
            row=1, column=2, padx=(6, 0), pady=3)

        file_frame.columnconfigure(1, weight=1)

        # ---- 配置编辑 ----
        config_frame = ttk.LabelFrame(main, text='配置编辑', padding=4)
        config_frame.pack(fill='both', expand=True, pady=(0, 6))

        toolbar = ttk.Frame(config_frame)
        toolbar.pack(fill='x', padx=4, pady=(4, 2))
        ttk.Button(toolbar, text='保存配置', command=self._save_config).pack(
            side='left', padx=(0, 6))
        ttk.Button(toolbar, text='重新加载', command=self._reload_config).pack(
            side='left')
        ttk.Button(toolbar, text='使用说明', command=self._show_usage).pack(
            side='left', padx=(6, 0))
        ttk.Label(
            toolbar,
            text='提示：拼网区块编号与工作目录中的数字文件夹一一对应',
            foreground='gray').pack(side='right')

        self.notebook = ttk.Notebook(config_frame)
        self.notebook.pack(fill='both', expand=True, padx=4, pady=(0, 4))

        # ---- 运行区 ----
        run_frame = ttk.LabelFrame(main, text='运行', padding=8)
        run_frame.pack(fill='both', expand=False)

        controls = ttk.Frame(run_frame)
        controls.pack(fill='x', pady=(0, 4))
        self.run_button = ttk.Button(
            controls, text='开始生成', command=self._on_run)
        self.run_button.pack(side='left', padx=(0, 6))
        self.preview_button = ttk.Button(
            controls, text='输出总图', command=self._on_preview)
        self.preview_button.pack(side='left', padx=(0, 6))
        self.edit_button = ttk.Button(
            controls, text='生成编辑用总图', command=self._on_edit_overview)
        self.edit_button.pack(side='left', padx=(0, 6))
        self.import_table_button = ttk.Button(
            controls, text='导入成型参数表…', command=self._choose_form_table)
        self.import_table_button.pack(side='left', padx=(0, 6))
        self.rules_button = ttk.Button(
            controls, text='设计规则检查', command=self._on_check_rules)
        self.rules_button.pack(side='left', padx=(0, 6))
        self.open_dir_button = ttk.Button(
            controls, text='打开输出目录', command=self._open_workdir)
        self.open_dir_button.pack(side='left', padx=(0, 12))
        self.progress = ttk.Progressbar(
            controls, mode='indeterminate', length=180)
        self.progress.pack(side='left', padx=(0, 12))
        ttk.Label(controls, textvariable=self.status_var).pack(side='left')

        log_pane = ttk.Panedwindow(run_frame, orient='vertical')
        log_pane.pack(fill='both', expand=True)

        log_frame = ttk.LabelFrame(log_pane, text='运行日志', padding=4)
        log_pane.add(log_frame, weight=3)
        self.log_text = tk.Text(log_frame, height=10, wrap='word', state='disabled')
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side='left', fill='both', expand=True)
        log_scroll.pack(side='right', fill='y')

        output_frame = ttk.LabelFrame(log_pane, text='生成的文件', padding=4)
        log_pane.add(output_frame, weight=2)
        self.output_tree = ttk.Treeview(
            output_frame, columns=('name',), show='headings', height=5)
        self.output_tree.heading('name', text='文件名')
        self.output_tree.column('name', width=760)
        output_scroll = ttk.Scrollbar(output_frame, command=self.output_tree.yview)
        self.output_tree.configure(yscrollcommand=output_scroll.set)
        self.output_tree.pack(side='left', fill='both', expand=True)
        output_scroll.pack(side='right', fill='y')
        self.output_tree.bind('<Double-1>', self._open_selected_file)

    # ------------------------------------------------------------ 文件选择

    def _choose_workdir(self):
        selected = filedialog.askdirectory(
            title='选择工作目录', initialdir=self.workdir_var.get() or os.getcwd())
        if selected:
            self.workdir_var.set(selected)
            config_in_workdir = os.path.join(selected, 'config.ini')
            if os.path.isfile(config_in_workdir):
                self.config_path_var.set(config_in_workdir)
            self._load_config(quiet=True)

    def _choose_config(self):
        selected = filedialog.askopenfilename(
            title='选择配置文件 config.ini',
            initialdir=os.path.dirname(
                self.config_path_var.get() or os.getcwd()),
            filetypes=[('配置文件', '*.ini'), ('所有文件', '*.*')])
        if selected:
            self.config_path_var.set(selected)
            self._load_config(quiet=True)

    # ------------------------------------------------------- 成型参数表导入

    @staticmethod
    def _parse_form_table(path):
        """读取“成型参数信息填写表”，返回 {'order':[], 'pairs':{}, 'rows':n}。"""
        if openpyxl is None:
            raise RuntimeError('当前环境缺少 openpyxl，无法读取 xlsx 文件。')
        workbook = openpyxl.load_workbook(
            path, read_only=True, data_only=True)
        # 表名不限：按顺序查找含 “层数名称/通孔模式” 表头的工作表，
        # 兼容旧表头 “丝网号/通孔模式说明”。
        header_pairs = (
            ('层数名称', '通孔模式'),
            ('丝网号', '通孔模式说明'),
        )
        sheet_rows = None
        header_row = None
        col_layer = col_mode = None
        for sheet in workbook.worksheets:
            rows = [tuple(r) for r in sheet.iter_rows(values_only=True)]
            for pair in header_pairs:
                for index, row in enumerate(rows[:5]):
                    layer_col = mode_col = None
                    for col, cell in enumerate(row):
                        text = '' if cell is None else str(cell).strip()
                        if text == pair[0] and layer_col is None:
                            layer_col = col
                        elif text == pair[1] and mode_col is None:
                            mode_col = col
                    if layer_col is not None and mode_col is not None:
                        sheet_rows = rows
                        header_row = index
                        col_layer, col_mode = layer_col, mode_col
                        break
                if header_row is not None:
                    break
            if header_row is not None:
                break
        workbook.close()
        if header_row is None:
            raise ValueError(
                'Excel 中找不到 层数名称/通孔模式（或旧表头 '
                '丝网号/通孔模式说明）表头。')

        order = []
        pairs = {}
        layout_rows = []
        for row in sheet_rows[header_row + 1:]:
            if col_layer >= len(row):
                continue
            layer = row[col_layer]
            if layer is None:
                continue
            layer = str(layer).strip()
            if not layer:
                continue
            mode = ''
            if col_mode < len(row) and row[col_mode] is not None:
                mode = str(row[col_mode]).strip()
            order.append(layer)
            hole = None if mode in ('4H', '5H', '') else mode
            pairs[layer] = hole
            layout_rows.append((layer, hole))
        if not order:
            raise ValueError('“成型参数信息填写表”中没有可用的丝网号行。')
        return {'order': order, 'pairs': pairs,
                'rows': layout_rows, 'count': len(order)}

    def _choose_form_table(self):
        if openpyxl is None:
            messagebox.showerror(
                '缺少依赖',
                '当前程序缺少 openpyxl 库，无法读取 xlsx 成型参数表。')
            return
        path = filedialog.askopenfilename(
            title='选择成型参数表（xlsx）',
            initialdir=os.path.dirname(
                self.config_path_var.get() or os.getcwd()),
            filetypes=[('Excel 工作簿', '*.xlsx'), ('所有文件', '*.*')])
        if not path:
            return
        try:
            layout = self._parse_form_table(path)
        except Exception as exc:
            messagebox.showerror('导入失败', str(exc))
            return
        self.form_layout = {
            'order': layout['order'],
            'pairs': layout['pairs'],
            'rows': layout['rows'],
        }
        self.form_layout_source = os.path.basename(path)
        self.status_var.set(
            '已按成型参数表排图: %s（%d 行）'
            % (self.form_layout_source, layout['count']))
        self._log(
            '已导入成型参数表 %s，共 %d 行，按表格顺序/配对输出总图。'
            % (self.form_layout_source, layout['count']))

    def _config_pair_map(self, section):
        """解析某个数字区块配置里的 图层与通孔配对(实际)。"""
        options = self.data.get(section, {})
        value = options.get('图层与通孔配对(实际)', '') or ''
        result = {}
        for group in str(value).split(','):
            group = group.strip()
            if not group or '|' not in group:
                continue
            layer, hole = group.split('|', 1)
            result[layer.strip()] = (hole or '').strip() or None
        return result

    def _form_mismatch_lines(self):
        """表格配对与当前配置不一致的行；没有差异返回空列表。"""
        if not self.form_layout:
            return []
        workdir = self.workdir_var.get().strip()
        if not workdir or not os.path.isdir(workdir):
            return []
        lines = []
        digit_dirs = sorted(
            name for name in os.listdir(workdir)
            if os.path.isdir(os.path.join(workdir, name)) and name.isdigit())
        for folder in digit_dirs:
            if folder not in self.data:
                continue
            conf = self._config_pair_map(folder)
            folder_path = os.path.join(workdir, folder)
            files = {
                os.path.splitext(name)[0] for name in os.listdir(folder_path)
                if name.lower().endswith('.dxf')}
            for layer in self.form_layout['order']:
                if layer not in files:
                    continue
                table_hole = self.form_layout['pairs'].get(layer)
                conf_hole = conf.get(layer)
                if table_hole != conf_hole:
                    lines.append(
                        '区块%s 图层 %s：表格=%s，配置文件=%s'
                        % (folder, layer,
                           table_hole or '无配对',
                           conf_hole or '无配对'))
        return lines

    def _warn_form_mismatch(self):
        if not self.form_layout:
            return
        lines = self._form_mismatch_lines()
        if not lines:
            return
        shown = lines[:20]
        suffix = '\n…共 %d 处差异' % len(lines) if len(lines) > 20 else ''
        messagebox.showwarning(
            '成型参数表与配置不一致',
            '表格中的通孔配对与配置文件不一致，仍将按表格顺序与配对生成总图：\n\n'
            + '\n'.join(shown) + suffix)

    # ------------------------------------------------------------ 配置编辑

    def _load_config(self, quiet=False):
        path = self.config_path_var.get().strip()
        if not os.path.isfile(path):
            self.config_loaded = False
            self.status_var.set('配置文件不存在: %s' % path)
            if not quiet:
                messagebox.showwarning('配置文件不存在', path)
            return False
        try:
            data = read_ini(path)
        except Exception as exc:
            self.config_loaded = False
            self.status_var.set('读取配置失败')
            messagebox.showerror('读取配置失败', str(exc))
            return False
        # 旧配置缺少新增开关时，界面也显示“是否引出端增绘 = No”
        extra = data.setdefault('EXTRA', {})
        extra.setdefault('是否引出端增绘', 'No')
        extra.setdefault('90度旋转方向', '逆时针')
        extra.setdefault('通孔层是否增加点网', 'Yes')
        extra.setdefault('图案来源', '编辑总图')
        design = data.setdefault('设计规则', {})
        design.setdefault('是否启用', 'Yes')
        design.setdefault('默认最小间距', '0.1')
        design.setdefault('默认最小留边量', '0.05')
        design.setdefault('图层规则', '')
        self.data = data
        self.config_loaded = True
        self._rebuild_tabs(data)
        source = extra.get('图案来源', '编辑总图')
        if source not in ('原图', '编辑总图'):
            source = '编辑总图'
        self.pattern_source_var.set(source)
        self.status_var.set('配置已加载: %s' % path)
        return True

    def _rebuild_tabs(self, data):
        for child in self.notebook.winfo_children():
            child.destroy()
        self.section_vars = {}
        self.block_frames = {}
        self.block_combo = None
        self.block_holder = None

        digit_sections = [section for section in data if section.isdigit()]
        default_options = data.get('DEFAULT', {})

        def is_in(key, key_list):
            return _in_keys(key, key_list)

        def add_tab(text, entries):
            if entries:
                self.notebook.add(
                    self._build_option_form(self.notebook, entries),
                    text=text)

        # 常用页签：基础参数 / 通孔，随后是扩展参数
        if default_options:
            base_entries = [
                (key, value, 'DEFAULT')
                for key, value in default_options.items()
                if not is_in(key, GLOBAL_SETTING_KEYS)
                and not is_in(key, MARK_SETTING_KEYS)
                and not is_in(key, HOLE_SETTING_KEYS)
                and not is_in(key, LONGHOLE_DEFAULT_KEYS)
                and not is_in(key, HIDDEN_DEFAULT_KEYS)]
            hole_entries = [
                (key, value, 'DEFAULT')
                for key, value in default_options.items()
                if is_in(key, HOLE_SETTING_KEYS)]
            mark_entries = [
                (key, value, 'DEFAULT')
                for key, value in default_options.items()
                if is_in(key, MARK_SETTING_KEYS)]
            add_tab('基础参数', base_entries)
            add_tab('通孔', hole_entries)
        else:
            mark_entries = []

        # 扩展参数 + 其它未识别段（按配置顺序）
        for section, options in data.items():
            if section in ('DEFAULT', 'LONGTHROUGHHOLE', '设计规则') or \
                    section.isdigit():
                continue
            entries = [
                (key, value, section) for key, value in options.items()]
            add_tab(_tab_title(section), entries)

        if digit_sections:
            self._build_block_tab(data, digit_sections)

        # 不常用页签后置：MARK设置 / 设计规则 / 长通孔
        add_tab('MARK设置', mark_entries)
        design_options = data.get('设计规则', {})
        add_tab(
            '设计规则',
            [(key, value, '设计规则')
             for key, value in design_options.items()])
        longhole_entries = [
            (key, value, 'LONGTHROUGHHOLE')
            for key, value in data.get('LONGTHROUGHHOLE', {}).items()]
        longhole_entries.extend([
            (key, value, 'DEFAULT')
            for key, value in default_options.items()
            if is_in(key, LONGHOLE_DEFAULT_KEYS)])
        add_tab('长通孔', longhole_entries)

        # 全局设置移到最右侧
        if default_options:
            global_entries = [
                (key, value, 'DEFAULT')
                for key, value in default_options.items()
                if is_in(key, GLOBAL_SETTING_KEYS)]
            add_tab('全局设置', global_entries)

        self._select_default_tab()

    def _select_default_tab(self):
        """默认激活“基础参数”页签；不存在时激活第一个。"""
        count = self.notebook.index('end')
        for index in range(count):
            if self.notebook.tab(index, 'text') == '基础参数':
                self.notebook.select(index)
                return
        if count > 0:
            self.notebook.select(0)

    def _build_option_form(self, parent, entries):
        """在 parent 内构建可滚动表单，并把每个选项变量登记到对应 config 段。

        entries: [(选项名, 值, 所属 config 段), ...]
        """
        frame = ttk.Frame(parent)
        canvas = tk.Canvas(frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            frame, orient='vertical', command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind(
            '<Configure>',
            lambda e, c=canvas: c.configure(scrollregion=c.bbox('all')))
        canvas.create_window((0, 0), window=inner, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind(
            '<MouseWheel>',
            lambda e, c=canvas: c.yview_scroll(
                int(-e.delta / 120), 'units'))

        for row, (option, value, section) in enumerate(entries):
            ttk.Label(inner, text=option).grid(
                row=row, column=0, sticky='w', padx=6, pady=3)
            option_type = _option_type(option) or 'text'
            if option_type == 'bool':
                var = tk.StringVar(value=value)
                box = ttk.Combobox(
                    inner, textvariable=var, values=YES_NO,
                    width=8, state='readonly')
                box.grid(row=row, column=1, sticky='w', padx=6, pady=3)
            elif option_type and '|' in option_type:
                choices = option_type.split('|')
                var = tk.StringVar(
                    value=value if value in choices else choices[0])
                box = ttk.Combobox(
                    inner, textvariable=var, values=choices,
                    width=10, state='readonly')
                box.grid(row=row, column=1, sticky='w', padx=6, pady=3)
            else:
                var = tk.StringVar(value=value)
                entry = ttk.Entry(inner, textvariable=var, width=72)
                entry.grid(row=row, column=1, sticky='w', padx=6, pady=3)
            self.section_vars.setdefault(section, {})[option] = var

        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        return frame

    def _active_block_numbers(self, data):
        """返回当前 拼网列/行分割数 范围内且配置中真实存在的区块号列表。"""
        digit_sections = [section for section in data if section.isdigit()]
        if not digit_sections:
            return []
        try:
            col = int(data.get('EXTRA', {}).get('拼网列分割数', '') or 1)
            row = int(data.get('EXTRA', {}).get('拼网行分割数', '') or 1)
            limit = max(col, 1) * max(row, 1)
        except (TypeError, ValueError):
            limit = len(digit_sections)
        return [
            str(i) for i in range(1, limit + 1) if str(i) in digit_sections]

    def _show_block(self, section):
        """只显示指定区块的表单，其余隐藏。"""
        for name, frame in self.block_frames.items():
            if name == section:
                frame.pack(fill='both', expand=True)
            else:
                frame.pack_forget()

    def _on_block_selected(self, _event=None):
        section = self.block_combo.get()
        if section in self.block_frames:
            self._show_block(section)

    def _build_block_tab(self, data, digit_sections):
        """构建“拼网区块”页签：顶部下拉选择区块，下方叠层显示表单。"""
        outer = ttk.Frame(self.notebook)
        header = ttk.Frame(outer)
        header.pack(fill='x', padx=6, pady=4)
        ttk.Label(header, text='选择区块:').pack(side='left', padx=(0, 6))
        combo = ttk.Combobox(header, state='readonly', width=10)
        combo.pack(side='left')
        combo.bind('<<ComboboxSelected>>', self._on_block_selected)
        ttk.Label(
            header,
            text='区块编号与工作目录中的数字文件夹一一对应',
            foreground='gray').pack(side='left', padx=(12, 0))

        holder = ttk.Frame(outer)
        holder.pack(fill='both', expand=True, padx=2, pady=(0, 2))

        self.block_combo = combo
        self.block_holder = holder
        self.block_frames = {}
        for section in digit_sections:
            entries = [
                (key, value, section)
                for key, value in data[section].items()
                if not _in_keys(key, BLOCK_HIDDEN_FIELDS)]
            frame = self._build_option_form(holder, entries)
            self.block_frames[section] = frame

        active = self._active_block_numbers(data)
        combo['values'] = active
        if active:
            combo.set(active[0])
            self._show_block(active[0])
        self.notebook.add(outer, text='拼网区块')

    def _refresh_block_dropdown(self, data=None):
        """保存后按新的拼网行/列分割数刷新下拉范围。"""
        if not hasattr(self, 'block_combo') or self.block_combo is None:
            return
        data = data if data is not None else self._collect_config()
        active = self._active_block_numbers(data)
        self.block_combo['values'] = active
        current = self.block_combo.get()
        if active and current not in active:
            self.block_combo.set(active[0])
            self._show_block(active[0])

    def _collect_config(self):
        data = {}
        for section, section_vars in self.section_vars.items():
            data[section] = {
                option: var.get().strip() for option, var in section_vars.items()}
        return data

    def _save_config(self):
        data = self._collect_config()
        errors = validate_config(data)
        if errors:
            details = '\n'.join(
                '[%s] %s: %s' % (section, option, error)
                for section, option, error in errors[:20])
            messagebox.showerror('配置有误', '请先修正以下内容:\n\n' + details)
            return False
        path = self.config_path_var.get().strip()
        if not path:
            messagebox.showwarning('未选择配置文件', '请先选择 config.ini 文件。')
            return False
        try:
            write_ini(path, data)
        except Exception as exc:
            messagebox.showerror('保存失败', str(exc))
            return False
        self.data = data
        self._refresh_block_dropdown(data)
        messagebox.showinfo('保存成功', '配置已保存到:\n%s' % path)
        return True

    def _reload_config(self):
        self._load_config()

    def _on_pattern_source_changed(self):
        """菜单切换“图案来源”：同步配置项并写回 config.ini。"""
        value = self.pattern_source_var.get()
        self.data.setdefault('EXTRA', {})['图案来源'] = value
        var = (self.section_vars.get('EXTRA') or {}).get('图案来源')
        if var is not None:
            var.set(value)
        path = self.config_path_var.get().strip()
        if self.config_loaded and os.path.isfile(path):
            data = self._collect_config()
            data.setdefault('EXTRA', {})['图案来源'] = value
            if validate_config(data):
                self._log(
                    '提示：配置中有未通过校验的内容，'
                    '“图案来源”将在下次保存配置时写入文件。')
            else:
                try:
                    write_ini(path, data)
                    self.data = data
                except Exception as exc:
                    self._log('保存“图案来源”失败: %s' % exc)
        self._log('图案来源已切换为: %s' % value)
        self.status_var.set('图案来源: %s' % value)

    def _show_usage(self):
        """生成网页版使用说明并在默认浏览器中打开。"""
        readme_path = resource_path('README.md')
        if not os.path.isfile(readme_path):
            messagebox.showwarning(
                '未找到使用说明',
                'README.md 文件不存在：\n%s' % readme_path)
            return
        try:
            with open(readme_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except OSError as exc:
            messagebox.showerror('无法读取使用说明', str(exc))
            return
        try:
            html_path = write_usage_html(content)
        except OSError as exc:
            messagebox.showerror('无法生成使用说明网页', str(exc))
            return
        try:
            os.startfile(html_path)
        except OSError as exc:
            messagebox.showerror('无法打开浏览器', str(exc))

    # ---------------------------------------------------------------- 运行

    def _on_run(self):
        preflight = self._preflight()
        if preflight is None:
            return
        workdir, config_path = preflight
        self._warn_form_mismatch()

        self._log('=' * 50)
        self._log('开始生成...')
        self._log('工作目录: %s' % workdir)
        self._log('配置文件: %s' % config_path)
        if self.form_layout:
            self._log('总图排图: 按成型参数表 %s' % self.form_layout_source)
        self._set_running(True)
        thread = threading.Thread(
            target=self._run_worker,
            args=(workdir, config_path, self.form_layout),
            daemon=True)
        thread.start()

    def _on_preview(self):
        preflight = self._preflight()
        if preflight is None:
            return
        workdir, config_path = preflight
        self._warn_form_mismatch()

        self._log('=' * 50)
        self._log('输出总图（预览）...')
        self._log('工作目录: %s' % workdir)
        self._log('配置文件: %s' % config_path)
        if self.form_layout:
            self._log('总图排图: 按成型参数表 %s' % self.form_layout_source)
        else:
            self._log('总图排图: 按配置文件默认顺序')
        self._set_running(True)
        thread = threading.Thread(
            target=self._run_overview_worker,
            args=(workdir, config_path, self.form_layout),
            daemon=True)
        thread.start()

    def _on_edit_overview(self):
        preflight = self._preflight()
        if preflight is None:
            return
        workdir, config_path = preflight
        self._log('=' * 50)
        self._log('生成编辑用总图（原图 100% 复制，供 CAD 修改）...')
        self._log('工作目录: %s' % workdir)
        self._log('配置文件: %s' % config_path)
        if self.form_layout:
            self._log('排布: 按成型参数表 %s' % self.form_layout_source)
        else:
            self._log('排布: 按配置文件配对与文件顺序')
        self._set_running(True)
        thread = threading.Thread(
            target=self._run_edit_overview_worker,
            args=(workdir, config_path, self.form_layout),
            daemon=True)
        thread.start()

    def _on_check_rules(self):
        preflight = self._preflight()
        if preflight is None:
            return
        workdir, config_path = preflight
        self._log('=' * 50)
        self._log('设计规则检查...')
        self._log('工作目录: %s' % workdir)
        self._log('配置文件: %s' % config_path)
        self._set_running(True)
        thread = threading.Thread(
            target=self._run_rules_worker,
            args=(workdir, config_path),
            daemon=True)
        thread.start()

    def _preflight(self):
        """公共运行前校验；通过返回 (workdir, config_path)，否则返回 None。"""
        if self.running:
            return None
        workdir = self.workdir_var.get().strip()
        config_path = self.config_path_var.get().strip()
        if not os.path.isdir(workdir):
            messagebox.showwarning('目录不存在', '请选择有效的工作目录。')
            return None
        if not self.config_loaded:
            if not os.path.isfile(config_path) or not self._load_config(quiet=True):
                messagebox.showwarning(
                    '未载入配置文件', '请先载入配置文件后再运行。')
                return None
        if not os.path.isfile(config_path):
            messagebox.showwarning('配置文件不存在', '请选择有效的 config.ini 文件。')
            return None
        if not self._save_config_silently():
            return None

        # 运行前检查：数字文件夹数量应与 拼网列分割数 x 拼网行分割数 一致
        try:
            extra = self.data.get('EXTRA', {})
            expected = int(extra['拼网列分割数']) * int(extra['拼网行分割数'])
        except (KeyError, ValueError):
            messagebox.showerror('配置错误', '缺少或无法解析 拼网列分割数 / 拼网行分割数。')
            return
        digit_dirs = [
            item for item in os.listdir(workdir)
            if os.path.isdir(os.path.join(workdir, item)) and item.isdigit()]
        if len(digit_dirs) != expected:
            messagebox.showwarning(
                '文件夹数量不匹配',
                '工作目录中的数字文件夹数量为 %d，配置要求 %d 个。\n'
                '请检查工作目录或 拼网列/行分割数 设置。'
                % (len(digit_dirs), expected))
            return None
        return workdir, config_path

    def _save_config_silently(self):
        data = self._collect_config()
        errors = validate_config(data)
        if errors:
            details = '\n'.join(
                '[%s] %s: %s' % (section, option, error)
                for section, option, error in errors[:20])
            messagebox.showerror('配置有误', '请先修正以下内容:\n\n' + details)
            return False
        try:
            write_ini(self.config_path_var.get().strip(), data)
        except Exception as exc:
            messagebox.showerror('保存失败', str(exc))
            return False
        self.data = data
        self._refresh_block_dropdown(data)
        return True

    def _run_worker(self, workdir, config_path, layout=None):
        old_stdout, old_stderr = sys.stdout, sys.stderr
        writer = QueueWriter(self.log_queue)
        sys.stdout = writer
        sys.stderr = writer
        before = self._file_snapshot(workdir)
        try:
            result = drawfeilin.main(
                workdir, config_path, overview_layout=layout)
            after = self._file_snapshot(workdir)
            outputs = sorted(self._detect_new_files(before, after))
            self.log_queue.put(('done', (result, outputs)))
        except Exception:
            self.log_queue.put(('error', traceback.format_exc()))
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    def _run_overview_worker(self, workdir, config_path, layout):
        old_stdout, old_stderr = sys.stdout, sys.stderr
        writer = QueueWriter(self.log_queue)
        sys.stdout = writer
        sys.stderr = writer
        try:
            paths = drawfeilin.generate_overview(
                workdir, config_path, layout) or []
            relative = [
                os.path.relpath(path, workdir) for path in paths]
            self.log_queue.put(('preview_done', relative))
        except Exception:
            self.log_queue.put(('error', traceback.format_exc()))
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    def _run_rules_worker(self, workdir, config_path):
        old_stdout, old_stderr = sys.stdout, sys.stderr
        writer = QueueWriter(self.log_queue)
        sys.stdout = writer
        sys.stderr = writer
        try:
            report = drawfeilin.check_design_rules(workdir, config_path)
            if report:
                self.log_queue.put(
                    ('rules_done', os.path.relpath(report, workdir)))
            else:
                self.log_queue.put(('rules_done', None))
        except Exception:
            self.log_queue.put(('error', traceback.format_exc()))
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    def _run_edit_overview_worker(self, workdir, config_path, layout=None):
        old_stdout, old_stderr = sys.stdout, sys.stderr
        writer = QueueWriter(self.log_queue)
        sys.stdout = writer
        sys.stderr = writer
        try:
            paths = drawfeilin.generate_edit_overview(
                workdir, config_path, layout) or []
            relative = [os.path.relpath(path, workdir) for path in paths]
            self.log_queue.put(('edit_done', relative))
        except Exception:
            self.log_queue.put(('error', traceback.format_exc()))
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    @staticmethod
    def _file_snapshot(workdir):
        snapshot = {}
        for name in os.listdir(workdir):
            path = os.path.join(workdir, name)
            try:
                snapshot[name] = os.path.getmtime(path)
            except OSError:
                continue
        return snapshot

    @staticmethod
    def _detect_new_files(before, after):
        return {
            name for name, mtime in after.items()
            if name.endswith(('.dxf', '.txt', '.drl'))
            and (name not in before or mtime > before[name])}

    def _set_running(self, running):
        self.running = running
        state = 'disabled' if running else 'normal'
        self.run_button.configure(state=state)
        self.preview_button.configure(state=state)
        self.edit_button.configure(state=state)
        self.import_table_button.configure(state=state)
        self.rules_button.configure(state=state)
        self.open_dir_button.configure(state=state)
        if running:
            self.status_var.set('正在生成...')
            self.progress.start(12)
        else:
            self.progress.stop()

    # ------------------------------------------------------------- 队列轮询

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == 'log':
                    self._log(payload, timestamp=False)
                elif kind == 'done':
                    result, outputs = payload
                    self._set_running(False)
                    if outputs:
                        self._set_output_files(outputs)
                        self.status_var.set('完成，共生成 %d 个文件' % len(outputs))
                        self._log('完成，共生成 %d 个文件:' % len(outputs))
                        for name in outputs:
                            self._log('  - ' + name)
                    elif result == 0:
                        self.status_var.set('未生成文件（输入检查未通过，见日志）')
                        self._log('未生成文件（输入检查未通过，见日志）')
                    else:
                        self.status_var.set('完成（未检测到新文件）')
                        self._log('完成（未检测到新文件）')
                elif kind == 'preview_done':
                    outputs = payload
                    self._set_running(False)
                    if outputs:
                        self._set_output_files(outputs)
                        self.status_var.set(
                            '总图已生成: %s' % outputs[0])
                        self._log('总图已生成:')
                        for name in outputs:
                            self._log('  - ' + name)
                        first = os.path.join(
                            self.workdir_var.get().strip(), outputs[0])
                        try:
                            os.startfile(first)  # noqa: S606
                        except OSError as exc:
                            self._log('自动打开失败: %s' % exc)
                    else:
                        self.status_var.set(
                            '未生成总图（输入检查未通过，见日志）')
                        self._log('未生成总图（输入检查未通过，见日志）')
                elif kind == 'rules_done':
                    self._set_running(False)
                    if payload:
                        self._set_output_files([payload])
                        self.status_var.set('设计规则检查完成: %s' % payload)
                        self._log('设计规则检查报告: ' + payload)
                    else:
                        self.status_var.set(
                            '设计规则检查未完成（见日志）')
                elif kind == 'edit_done':
                    outputs = payload
                    self._set_running(False)
                    if outputs:
                        self._set_output_files(outputs)
                        self.status_var.set(
                            '编辑用总图已生成: %s' % outputs[0])
                        self._log('编辑用总图已生成（可在 CAD 中按原图层名修改）:')
                        for name in outputs:
                            self._log('  - ' + name)
                        first = os.path.join(
                            self.workdir_var.get().strip(), outputs[0])
                        try:
                            os.startfile(first)  # noqa: S606
                        except OSError as exc:
                            self._log('自动打开失败: %s' % exc)
                    else:
                        self.status_var.set(
                            '未生成编辑用总图（输入检查未通过，见日志）')
                        self._log('未生成编辑用总图（输入检查未通过，见日志）')
                elif kind == 'error':
                    self._set_running(False)
                    self.status_var.set('运行出错，见日志')
                    self._log(payload)
                    messagebox.showerror('运行出错', '见运行日志中的详细信息。')
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    # ------------------------------------------------------------ 工具方法

    def _log(self, text, timestamp=True):
        self.log_text.configure(state='normal')
        if timestamp:
            self.log_text.insert('end', '[%s] %s\n' % (
                time.strftime('%H:%M:%S'), text))
        else:
            self.log_text.insert('end', text + '\n')
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def _set_output_files(self, outputs):
        self._output_files = outputs
        for item in self.output_tree.get_children():
            self.output_tree.delete(item)
        for name in outputs:
            self.output_tree.insert('', 'end', values=(name,))

    def _open_workdir(self):
        workdir = self.workdir_var.get().strip()
        if not os.path.isdir(workdir):
            messagebox.showwarning('目录不存在', workdir)
            return
        try:
            os.startfile(workdir)  # noqa: S606 - Windows only, user initiated
        except OSError as exc:
            messagebox.showerror('无法打开目录', str(exc))

    def _open_selected_file(self, _event):
        selection = self.output_tree.selection()
        if not selection:
            return
        name = self.output_tree.item(selection[0], 'values')[0]
        path = os.path.join(self.workdir_var.get().strip(), name)
        if not os.path.isfile(path):
            messagebox.showwarning('文件不存在', path)
            return
        try:
            os.startfile(path)  # noqa: S606 - Windows only, user initiated
        except OSError as exc:
            messagebox.showerror('无法打开文件', str(exc))


def main_gui():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    try:
        main_gui()
    except Exception:
        detail = traceback.format_exc()
        log_path = os.path.join(app_dir(), 'drawfeilin_error.log')
        try:
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(time.strftime('[%Y-%m-%d %H:%M:%S]\n'))
                f.write(detail)
                f.write('\n')
        except OSError:
            pass
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror('drawfeilin 启动失败', detail)
            root.destroy()
        except Exception:
            pass
