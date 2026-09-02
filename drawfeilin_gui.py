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
    '长通孔孔径': 'float',
    '通孔孔径最大值': 'float',
    '拼网列分割数': 'int',
    '拼网行分割数': 'int',
    '是否绘制通孔层': 'bool',
    '是否绘制长通孔DXF文件': 'bool',
    '根据通孔绘制PAD': 'bool',
    '是否绘制MARK标识': 'bool',
    '是否镜像图层': 'bool',
    '是否切割线内缩': 'bool',
    '长通孔模式是否镜像': 'bool',
}


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
            option_type = OPTION_TYPES.get(option, 'text')
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
        self._output_files = []

        self._build_ui()
        self._poll_queue()

        base_dir = app_dir()
        self.workdir_var.set(base_dir)
        default_config = os.path.join(base_dir, 'config.ini')
        if os.path.isfile(default_config):
            self.config_path_var.set(default_config)
        self._load_config(quiet=True)

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

    # ------------------------------------------------------------ 配置编辑

    def _load_config(self, quiet=False):
        path = self.config_path_var.get().strip()
        if not os.path.isfile(path):
            self.status_var.set('配置文件不存在: %s' % path)
            if not quiet:
                messagebox.showwarning('配置文件不存在', path)
            return False
        try:
            data = read_ini(path)
        except Exception as exc:
            self.status_var.set('读取配置失败')
            messagebox.showerror('读取配置失败', str(exc))
            return False
        self.data = data
        self._rebuild_tabs(data)
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
        for section, options in data.items():
            if section.isdigit():
                continue
            frame, section_vars = self._build_section_form(
                self.notebook, options)
            self.section_vars[section] = section_vars
            self.notebook.add(frame, text=_tab_title(section))

        if digit_sections:
            self._build_block_tab(data, digit_sections)

    def _build_section_form(self, parent, options):
        """在 parent 内构建一个区块的可滚动表单，返回 (frame, 选项变量字典)。"""
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

        section_vars = {}
        for row, (option, value) in enumerate(options.items()):
            ttk.Label(inner, text=option).grid(
                row=row, column=0, sticky='w', padx=6, pady=3)
            option_type = OPTION_TYPES.get(option, 'text')
            if option_type == 'bool':
                var = tk.StringVar(value=value)
                box = ttk.Combobox(
                    inner, textvariable=var, values=YES_NO,
                    width=8, state='readonly')
                box.grid(row=row, column=1, sticky='w', padx=6, pady=3)
            else:
                var = tk.StringVar(value=value)
                entry = ttk.Entry(inner, textvariable=var, width=72)
                entry.grid(row=row, column=1, sticky='w', padx=6, pady=3)
            section_vars[option] = var

        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        return frame, section_vars

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
            frame, section_vars = self._build_section_form(
                holder, data[section])
            self.section_vars[section] = section_vars
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
        if self.running:
            return
        workdir = self.workdir_var.get().strip()
        config_path = self.config_path_var.get().strip()
        if not os.path.isdir(workdir):
            messagebox.showwarning('目录不存在', '请选择有效的工作目录。')
            return
        if not os.path.isfile(config_path):
            messagebox.showwarning('配置文件不存在', '请选择有效的 config.ini 文件。')
            return
        if not self.section_vars:
            if not self._load_config(quiet=True):
                return
        if not self._save_config_silently():
            return

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
            return

        self._log('=' * 50)
        self._log('开始生成...')
        self._log('工作目录: %s' % workdir)
        self._log('配置文件: %s' % config_path)
        self._set_running(True)
        thread = threading.Thread(
            target=self._run_worker, args=(workdir, config_path), daemon=True)
        thread.start()

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

    def _run_worker(self, workdir, config_path):
        old_stdout, old_stderr = sys.stdout, sys.stderr
        writer = QueueWriter(self.log_queue)
        sys.stdout = writer
        sys.stderr = writer
        before = self._file_snapshot(workdir)
        try:
            result = drawfeilin.main(workdir, config_path)
            after = self._file_snapshot(workdir)
            outputs = sorted(self._detect_new_files(before, after))
            self.log_queue.put(('done', (result, outputs)))
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
