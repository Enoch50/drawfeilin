# coding:utf-8
"""Film drawing automation script.

This module automates the process of drawing PCB film patterns from DXF files.
It reads design parameters from a configuration file and generates complete
film design files with cutting lines, positioning marks, and drill patterns.
"""
import os
import sys
import re
import random
import time
import configparser
import copy
import math
from math import sqrt

try:
    import shapely
    from shapely.geometry import LineString, Polygon
    from shapely.ops import nearest_points, unary_union
    from shapely.strtree import STRtree
    from shapely.validation import make_valid
except Exception:  # pragma: no cover - 运行环境缺依赖时给出提示
    shapely = None

# ============================================================================
# Module-level Constants
# ============================================================================

# Film specification constants
FILM_6_INCH_RING_DISTANCE = 122.4
FILM_6_INCH_RING_RADIUS = 0.3
FILM_8_INCH_RING_DISTANCE = 171.68
FILM_8_INCH_RING_RADIUS = 0.215
FILM_DEFAULT_RING_RADIUS = 0.215
INCHES_TO_MM = 25.4

# Coordinate conversion constant
COORDINATE_SCALE = 1000  # Scale factor for converting coordinates

# Default film parameters
DEFAULT_RING_OFFSET = 3.8
DEFAULT_LENGTH_OF_CROSS = 1.5
DEFAULT_CUTLINE_LENGTH = 3.0
DEFAULT_CUTLINE_WIDTH = 0.08
DEFAULT_RING_WIDTH = 0.1
DEFAULT_FIFTH_RING_OFFSET = 4.0

# 总图中相邻图层外框之间的净间距（mm），同时用于图案行与上方通孔行的行距
OVERVIEW_GAP = 1.0

# 设计规则检查默认值（mm）
DESIGN_RULE_SECTION = '设计规则'
DEFAULT_MIN_SPACING = 0.1
DEFAULT_MIN_CLEARANCE = 0.05


def _is_pad_layer(name):
    """PAD 层名称以 H 或 P 开头（如 H1、P2）。"""
    return bool(name) and name[:1].upper() in ('H', 'P')


def _is_pure_pointnet(layer):
    """纯点网层：层名以 P 开头（无需切割线与十字架）。"""
    return bool(layer) and layer[:1].upper() == 'P'


def _pad_layer_diameter(layer):
    """点网层圆直径：H 开头按 PAD孔径，其余（P 点网）按点网孔径。"""
    if layer and layer[:1].upper() == 'H':
        return globalconfig.PADDIAMETER
    return globalconfig.POINTNET_DIAMETER


def _auto_pointnet_name(hole_layer):
    """通孔层 Vn 自动对应 Pn；无法取号时返回 None。"""
    match = re.match(r'^[Vv](\d+)$', str(hole_layer or '').strip())
    return 'P' + match.group(1) if match else None


def _hole_layers_from_files(readfilelist, source=None):
    """取本区块实际存在的通孔层名（V 开头）。

    source 不为 None（编辑用总图来源）时按编辑总图的图层取。
    """
    if source:
        return [name for name in source.get('layers', {})
                if name[:1].upper() == 'V']
    layers = []
    for path in readfilelist:
        name = os.path.splitext(os.path.basename(path))[0]
        if name[:1].upper() == 'V':
            layers.append(name)
    return layers


def _ring_diameter(polyline):
    """圆环直径：取顶点包围盒较小边（与开孔模式孔径口径一致）。"""
    xs = [p[0] for p in polyline]
    ys = [p[1] for p in polyline]
    return min(max(xs) - min(xs), max(ys) - min(ys))


def _is_fake_hole_ring(polyline):
    """V 层中直径小于“假引孔阈值”的圆视为人工假引孔。"""
    return _ring_diameter(polyline) < globalconfig.DUMMYHOLE_THRESHOLD - 1e-6


def _design_diams_for(feature, holelayer, count):
    """取一行带各孔的“原图孔径”列表；缺失或长度不符时返回 None。"""
    diams = getattr(feature, 'hole_band_design_diams', None) or {}
    values = diams.get(holelayer)
    if not values or len(values) != count:
        return None
    return list(values)


def _filter_fake_rings(hole_rings, design_diams=None):
    """剔除假引孔圆环：优先按原图孔径判定，缺少时按当前孔径判定。"""
    if design_diams is not None:
        return [ring for ring, diam in zip(hole_rings, design_diams)
                if diam >= globalconfig.DUMMYHOLE_THRESHOLD - 1e-6]
    return [ring for ring in hole_rings if not _is_fake_hole_ring(ring)]


def _circle_ring(cx, cy, radius, sectors=48):
    """把圆离散成闭合圆环多段线（含首尾重合点）。"""
    points = []
    for k in range(sectors):
        ang = 2 * math.pi * k / sectors
        points.append([cx + radius * math.cos(ang),
                       cy + radius * math.sin(ang)])
    points.append([cx + radius, cy])
    return points


def _read_dxf_text(path):
    """读取 DXF 文本，兼容 utf-8 / GBK 与无法解码的异常情况。"""
    for encoding in ('utf-8-sig', 'gbk'):
        try:
            with open(path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, 'r', errors='replace') as f:
        return f.read()


# 设计外框尺寸判定容差（mm）
DESIGN_FRAME_TOL = 0.01


class EditOverviewError(ValueError):
    """编辑用总图缺失/版式不符/无法定位等需要中文提示并中止的错误。"""


# File extension constants
DXF_EXTENSION = '.dxf'
TEXT_EXTENSION = '.txt'
DRL_EXTENSION = '.drl'

# Positioning-ring mode: '4H' (no fifth ring) or '5H' (includes fifth ring)
POSITION_RING_MODE = '4H'

# Shengxiong hole film mode: 1 (two-layer circles) or 2 (tiered, original)
SHENGXIONG_MODE = 1


def set_position_ring_mode(mode):
    """Set positioning-ring mode to '4H' or '5H'.

    '5H' reproduces the original buildringlist/buildringholelist output;
    '4H' drops the entries that use FIFTH_RING_OFFSET.
    """
    global POSITION_RING_MODE
    if mode not in ('4H', '5H'):
        raise ValueError("mode must be '4H' or '5H'")
    POSITION_RING_MODE = mode


def set_shengxiong_mode(mode):
    """Set shengxiong hole film mode to 1 or 2."""
    global SHENGXIONG_MODE
    if mode not in (1, 2):
        raise ValueError('mode must be 1 or 2')
    SHENGXIONG_MODE = mode


def _app_dir():
    """Return the directory containing the running app.

    Returns the executable's directory when frozen by PyInstaller, otherwise
    the directory of this script.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class Globalconfig(object):
    """Read and manage configuration from config.ini file.
    
    This class loads all parameters required for film pattern generation,
    including material properties, array dimensions, and output settings.
    
    Raises:
        FileNotFoundError: If config.ini cannot be found.
        ValueError: If required configuration parameters are missing or invalid.
    """
    configfilename = 'config.ini'

    @staticmethod
    def _parse_layer_pairs(value, label):
        """解析 “A|B,A|B” 形式的配对文本；空值返回空字典。"""
        result = {}
        text = (value or '').strip()
        if not text:
            return result
        for index, group in enumerate(text.split(','), start=1):
            group = group.strip()
            if not group:
                continue
            if '|' not in group:
                raise ValueError(
                    '%s 第 %d 组缺少“|”：%s' % (label, index, group))
            key, hole = group.split('|', 1)
            key = key.strip()
            hole = hole.strip()
            if not key or not hole:
                raise ValueError(
                    '%s 第 %d 组格式错误：%s' % (label, index, group))
            result[key] = hole
        return result

    def __init__(self, config_path=None):

        self.config = configparser.ConfigParser()
        if config_path is None:
            config_path = os.path.join(_app_dir(), 'config.ini')
        with open(config_path, 'r', encoding='utf-8-sig') as configfile:
            self.config.read_file(configfile)
        self.GLOBAL_RATIO = self.config.getfloat('DEFAULT', '图案全局缩放比例')
        self.X_OFFSET = self.config.getfloat('DEFAULT', '图案原点X坐标')
        self.Y_OFFSET = self.config.getfloat('DEFAULT', '图案原点Y坐标')
        self.X_OUTLINE_RATIO = self.config.getfloat('DEFAULT', '瓷体X方向收缩率')
        self.Y_OUTLINE_RATIO = self.config.getfloat('DEFAULT', '瓷体Y方向收缩率')
        self.X_INNER_RATIO = self.config.getfloat('DEFAULT', '内部图案X方向中心收缩率')
        self.Y_INNER_RATIO = self.config.getfloat('DEFAULT', '内部图案Y方向中心收缩率')
        self.RATIO_NUM = self.config.getint('DEFAULT', '放缩率数量')
        self.X_RATIO_DIFF = self.config.getfloat('DEFAULT', 'X方向放缩率差值')
        self.Y_RATIO_DIFF = self.config.getfloat('DEFAULT', 'Y方向放缩率差值')
        self.X_LENGTH = self.config.getfloat('DEFAULT', '产品设计x方向长度')
        self.Y_LENGTH = self.config.getfloat('DEFAULT', '产品设计y方向长度')
        self.X_ARRAY_NUM = self.config.getint('DEFAULT', '菲林x方向阵列列数')
        self.Y_ARRAY_NUM = self.config.getint('DEFAULT', '菲林y方向阵列列数')
        self.X_EXTENDED_LENGTH = self.config.getfloat('DEFAULT', '引出端x方向延伸距离')
        self.Y_EXTENDED_LENGTH = self.config.getfloat('DEFAULT', '引出端y方向延伸距离')
        self.CUTLINE_X_OFFSET = self.config.getfloat('DEFAULT', '切割线x方向偏移距离')
        self.CUTLINE_Y_OFFSET = self.config.getfloat('DEFAULT', '切割线y方向偏移距离')
        self.NAME_OF_FEILIN = self.config.get('DEFAULT', '菲林名称')
        self.JUSTCOPYLIST = tuple(
            self.config.get(
                'DEFAULT',
                '不做多种放缩的图层').split('|'))
        self.AUTHOR_NAME = self.config.get('DEFAULT', '菲林转化者姓名')
        self.MARK_ROTATION_ANGLE = self.config.getint('DEFAULT', 'MARK旋转角度')
        self.MARK_X_OFFSET = self.config.getfloat('DEFAULT', 'MARK的X方向偏移')
        self.MARK_Y_OFFSET = self.config.getfloat('DEFAULT', 'MARK的Y方向偏移')
        self.FEILIN_INCH = self.config.getint('DEFAULT', '菲林英寸')
        self.MARK_HEIGHT = self.config.getfloat('DEFAULT', 'MARK文字高度')
        self.MARKNOTE = self.config.get('DEFAULT', 'MARK标识')
        self.markratiolist = tuple(
            self.config.get(
                'DEFAULT',
                '表示放缩率的MARK标识').split('|'))
        self.blockmark_x_list = tuple(
            self.config.get(
                'DEFAULT',
                '拼网区块x方向MARK标识').split('|'))
        self.blockmark_y_list = tuple(
            self.config.get(
                'DEFAULT',
                '拼网区块y方向MARK标识').split('|'))
        self.DRAWHOLE = self.config.getboolean('DEFAULT', '是否绘制通孔层')
        self.DRAWLONGHOLE = self.config.getboolean('DEFAULT', '是否绘制长通孔DXF文件')
        self.DRAWPAD = self.config.getboolean('DEFAULT', '根据通孔绘制PAD')
        self.DRAWMARKNOTE = self.config.getboolean('DEFAULT', '是否绘制MARK标识')
        self.HOLEDIAMETER = self.config.getfloat('DEFAULT', '通孔孔径')
        # PAD孔径：图案层内同圆 PAD 直径；点网孔径：P/H 点网层圆直径
        self.PADDIAMETER = self.config.getfloat(
            'DEFAULT', 'PAD孔径', fallback=0.12)
        self.POINTNET_DIAMETER = self.config.getfloat(
            'DEFAULT', '点网孔径', fallback=self.PADDIAMETER)
        self.DUMMYHOLE_DIAMETER = self.config.getfloat(
            'DEFAULT', '假引孔孔径', fallback=0.04)
        self.DUMMYHOLE_THRESHOLD = self.config.getfloat(
            'DEFAULT', '假引孔阈值', fallback=0.05)
        # 定位孔孔径：开孔模式定位孔圆的直径（默认 0.26mm）
        self.RING_HOLE_DIAMETER = self.config.getfloat(
            'DEFAULT', '定位孔孔径', fallback=0.26)
        self.LEAD_DRAW_LENGTH = self.config.getfloat(
            'DEFAULT', '引出端绘制长度', fallback=self.X_EXTENDED_LENGTH)
        self.LEAD_DRAW_WIDTH = self.config.getfloat(
            'DEFAULT', '引出端绘制宽度', fallback=0.07)

        self.LONGHOLELIST = []

        if self.DRAWLONGHOLE:
            self.LONGHOLELIST = tuple(
                self.config.get(
                    'LONGTHROUGHHOLE',
                    '长通孔列表').split('|'))
            self.LONGHOLEDIAMETER = self.config.getfloat(
                'LONGTHROUGHHOLE', '长通孔孔径')
            self.LONGHOLEMIRROR = self.config.getboolean(
                'LONGTHROUGHHOLE', '长通孔模式是否镜像')

        if self.config.get('EXTRA', '拼网列分割数') is not None:
            self.BLOCK_X_NUM = self.config.getint('EXTRA', '拼网列分割数')
        if self.config.get('EXTRA', '拼网行分割数') is not None:
            self.BLOCK_Y_NUM = self.config.getint('EXTRA', '拼网行分割数')

        self.IS_PATTERN_MIRROR = self.config.getboolean('EXTRA', '是否镜像图层')
        self.IS_CUTLINE_SHIFTIN = self.config.getboolean('EXTRA', '是否切割线内缩')
        self.LDI_ENABLED = self.config.getboolean(
            'EXTRA', '是否输出LDI', fallback=True)
        self.SHENGXIONG_ARRAY_FULL = self.config.getboolean(
            'EXTRA', '是否开孔阵列满', fallback=True)
        self.ROTATE_90 = self.config.getboolean(
            'EXTRA', '是否旋转90度', fallback=False)
        direction = str(self.config.get(
            'EXTRA', '90度旋转方向', fallback='逆时针') or '').strip()
        self.ROTATE_90_DIRECTION = (
            direction if direction in ('逆时针', '顺时针') else '逆时针')
        self.REDRAW_OWN_LEADS = self.config.getboolean(
            'EXTRA', '是否引出端增绘', fallback=False)
        self.ADD_POINTNET = self.config.getboolean(
            'EXTRA', '通孔层是否增加点网', fallback=True)
        source = str(self.config.get(
            'EXTRA', '图案来源', fallback='编辑总图') or '').strip()
        self.PATTERN_SOURCE = (
            source if source in ('原图', '编辑总图') else '编辑总图')

        self.BLOCK_NUM = self.BLOCK_X_NUM * self.BLOCK_Y_NUM
        self.EXTENDCOPYLIST = []
        self.layerholepairdictlist_actual = []
        self.pnlist = []
        self.holepadpairdictlist = []
        self.dummy_pairlist = []
        self.dummyhole_layerlist = []

        for i in range(0, self.BLOCK_X_NUM * self.BLOCK_Y_NUM):
            self.pnlist.append(self.config.get(str(i + 1), '型号名称'))
            section = str(i + 1)
            extend_text = self.config.get(
                section, '需要做xy方向延伸的图层', fallback='')
            self.EXTENDCOPYLIST.append(tuple(
                item.strip() for item in extend_text.split('|')
                if item.strip()))
            self.layerholepairdictlist_actual.append(
                self._parse_layer_pairs(
                    self.config.get(
                        section, '图层与通孔配对(实际)', fallback=''),
                    '图层与通孔配对(实际)'))

            self.holepadpairdictlist.append(
                self._parse_layer_pairs(
                    self.config.get(
                        section, '通孔与PAD配对', fallback=''),
                    '通孔与PAD配对'))

            # 额外假引与假引孔（每区块配置；缺失时为空）
            dummy_pairs = self.config.get(
                str(i + 1), '需要绘制假引的图层', fallback='').strip()
            pair_list = []
            for group in dummy_pairs.split(';'):
                parts = group.split('|')
                if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                    pair_list.append((parts[0].strip(), parts[1].strip()))
            self.dummy_pairlist.append(pair_list)
            dummy_hole_layers = self.config.get(
                str(i + 1), '绘制假引孔的图层', fallback='').strip()
            self.dummyhole_layerlist.append(tuple(
                item.strip() for item in dummy_hole_layers.split('|')
                if item.strip()))

        self.block_x_accumulationlist = [0]
        self.block_y_accumulationlist = [0]

        self.each_xblock_num = self.X_ARRAY_NUM // self.BLOCK_X_NUM
        self.leftblock_x_num = self.X_ARRAY_NUM % self.BLOCK_X_NUM

        self.each_yblock_num = self.Y_ARRAY_NUM // self.BLOCK_Y_NUM
        self.leftblock_y_num = self.Y_ARRAY_NUM % self.BLOCK_Y_NUM

        self.eachblock_x_list = [self.each_xblock_num] * self.BLOCK_X_NUM
        self.eachblock_y_list = [self.each_yblock_num] * self.BLOCK_Y_NUM

        for i in range(
                self.BLOCK_X_NUM -
                self.leftblock_x_num,
                self.BLOCK_X_NUM):
            self.eachblock_x_list[i] = self.eachblock_x_list[i] + 1

        for i in range(
                self.BLOCK_Y_NUM -
                self.leftblock_y_num,
                self.BLOCK_Y_NUM):
            self.eachblock_y_list[i] = self.eachblock_y_list[i] + 1

        for i in range(1, self.BLOCK_X_NUM):
            self.block_x_accumulationlist.append(
                self.block_x_accumulationlist[i - 1] + self.eachblock_x_list[i - 1])

        for i in range(1, self.BLOCK_Y_NUM):
            self.block_y_accumulationlist.append(
                self.block_y_accumulationlist[i - 1] + self.eachblock_y_list[i - 1])

        # Set film-specific parameters based on film size
        if self.FEILIN_INCH == 6:
            self.RING_DISTANCE = FILM_6_INCH_RING_DISTANCE
            self.RING_RADIUS = FILM_6_INCH_RING_RADIUS
        elif self.FEILIN_INCH == 8:
            self.RING_DISTANCE = FILM_8_INCH_RING_DISTANCE
            self.RING_RADIUS = FILM_8_INCH_RING_RADIUS
        else:
            self.RING_DISTANCE = self.FEILIN_INCH * INCHES_TO_MM - 30
            self.RING_RADIUS = FILM_DEFAULT_RING_RADIUS

        # Set standard parameters
        self.RING_OFFSET = DEFAULT_RING_OFFSET
        self.LENGTH_OF_CROSS = DEFAULT_LENGTH_OF_CROSS
        self.CUTLINE_LENGTH = DEFAULT_CUTLINE_LENGTH
        self.CUTLINE_WIDTH = DEFAULT_CUTLINE_WIDTH
        self.RING_WIDTH = DEFAULT_RING_WIDTH
        self.FIFTH_RING_OFFSET = DEFAULT_FIFTH_RING_OFFSET

        # Cache commonly used calculations to avoid repeated computation
        self.X_SCALED_LENGTH = self.X_LENGTH / self.X_OUTLINE_RATIO
        self.Y_SCALED_LENGTH = self.Y_LENGTH / self.Y_OUTLINE_RATIO

        self.X_BLANK = (self.RING_DISTANCE - self.X_SCALED_LENGTH * self.X_ARRAY_NUM) / 2
        self.Y_BLANK = (self.RING_DISTANCE - self.Y_SCALED_LENGTH * self.Y_ARRAY_NUM) / 2
        # 记录未旋转时的原始设计尺寸，供外框/总图使用
        self.ORIGINAL_X_LENGTH = self.X_LENGTH
        self.ORIGINAL_Y_LENGTH = self.Y_LENGTH
        self.ORIGINAL_X_ARRAY_NUM = self.X_ARRAY_NUM
        self.ORIGINAL_Y_ARRAY_NUM = self.Y_ARRAY_NUM

    def _recompute_block_layout(self):
        """按当前行列数重新计算分块与空白参数（旋转互换后调用）。"""
        self.X_SCALED_LENGTH = self.X_LENGTH / self.X_OUTLINE_RATIO
        self.Y_SCALED_LENGTH = self.Y_LENGTH / self.Y_OUTLINE_RATIO
        self.X_BLANK = (self.RING_DISTANCE -
                        self.X_SCALED_LENGTH * self.X_ARRAY_NUM) / 2
        self.Y_BLANK = (self.RING_DISTANCE -
                        self.Y_SCALED_LENGTH * self.Y_ARRAY_NUM) / 2
        self.block_x_accumulationlist = [0]
        self.block_y_accumulationlist = [0]
        self.each_xblock_num = self.X_ARRAY_NUM // self.BLOCK_X_NUM
        self.leftblock_x_num = self.X_ARRAY_NUM % self.BLOCK_X_NUM
        self.each_yblock_num = self.Y_ARRAY_NUM // self.BLOCK_Y_NUM
        self.leftblock_y_num = self.Y_ARRAY_NUM % self.BLOCK_Y_NUM
        self.eachblock_x_list = [self.each_xblock_num] * self.BLOCK_X_NUM
        self.eachblock_y_list = [self.each_yblock_num] * self.BLOCK_Y_NUM
        for i in range(
                self.BLOCK_X_NUM - self.leftblock_x_num,
                self.BLOCK_X_NUM):
            self.eachblock_x_list[i] = self.eachblock_x_list[i] + 1
        for i in range(
                self.BLOCK_Y_NUM - self.leftblock_y_num,
                self.BLOCK_Y_NUM):
            self.eachblock_y_list[i] = self.eachblock_y_list[i] + 1
        for i in range(1, self.BLOCK_X_NUM):
            self.block_x_accumulationlist.append(
                self.block_x_accumulationlist[i - 1] +
                self.eachblock_x_list[i - 1])
        for i in range(1, self.BLOCK_Y_NUM):
            self.block_y_accumulationlist.append(
                self.block_y_accumulationlist[i - 1] +
                self.eachblock_y_list[i - 1])

    def swap_film_axes(self):
        """旋转 90° 时整体互换设计 X/Y 参数并重算派生值。"""
        self._swap_backup = (
            self.X_LENGTH, self.Y_LENGTH,
            self.X_ARRAY_NUM, self.Y_ARRAY_NUM,
            self.X_OFFSET, self.Y_OFFSET,
            self.X_OUTLINE_RATIO, self.Y_OUTLINE_RATIO,
            self.X_INNER_RATIO, self.Y_INNER_RATIO,
            self.X_RATIO_DIFF, self.Y_RATIO_DIFF,
            self.X_EXTENDED_LENGTH, self.Y_EXTENDED_LENGTH,
            self.CUTLINE_X_OFFSET, self.CUTLINE_Y_OFFSET,
        )
        (self.X_LENGTH, self.Y_LENGTH,
         self.X_ARRAY_NUM, self.Y_ARRAY_NUM,
         self.X_OFFSET, self.Y_OFFSET,
         self.X_OUTLINE_RATIO, self.Y_OUTLINE_RATIO,
         self.X_INNER_RATIO, self.Y_INNER_RATIO,
         self.X_RATIO_DIFF, self.Y_RATIO_DIFF,
         self.X_EXTENDED_LENGTH, self.Y_EXTENDED_LENGTH,
         self.CUTLINE_X_OFFSET, self.CUTLINE_Y_OFFSET) = (
            self.Y_LENGTH, self.X_LENGTH,
            self.Y_ARRAY_NUM, self.X_ARRAY_NUM,
            self.Y_OFFSET, self.X_OFFSET,
            self.Y_OUTLINE_RATIO, self.X_OUTLINE_RATIO,
            self.Y_INNER_RATIO, self.X_INNER_RATIO,
            self.Y_RATIO_DIFF, self.X_RATIO_DIFF,
            self.Y_EXTENDED_LENGTH, self.X_EXTENDED_LENGTH,
            self.CUTLINE_Y_OFFSET, self.CUTLINE_X_OFFSET)
        self._recompute_block_layout()

    def restore_film_axes(self):
        backup = getattr(self, '_swap_backup', None)
        if not backup:
            return
        (self.X_LENGTH, self.Y_LENGTH,
         self.X_ARRAY_NUM, self.Y_ARRAY_NUM,
         self.X_OFFSET, self.Y_OFFSET,
         self.X_OUTLINE_RATIO, self.Y_OUTLINE_RATIO,
         self.X_INNER_RATIO, self.Y_INNER_RATIO,
         self.X_RATIO_DIFF, self.Y_RATIO_DIFF,
         self.X_EXTENDED_LENGTH, self.Y_EXTENDED_LENGTH,
         self.CUTLINE_X_OFFSET, self.CUTLINE_Y_OFFSET) = backup
        self._recompute_block_layout()
        self._swap_backup = None


class Feilinhole():
    """feilin hole class
    """

    def __init__(self):

        # self.holepolylinearraydict=self.holepolylinedictarraycopy()
        self.holepolylinearraydict = {}

    def calculate_center_positions(self, holepolylinelist):
        """Calculate center positions of hole polylines.
        
        Computes the geometric center of each polyline, adjusting for film
        size and coordinate system offset.
        
        Args:
            holepolylinelist: List of polylines representing holes
            
        Returns:
            List of [center_x, center_y] positions
        """
        center_pos_list = []
        for poly in holepolylinelist:
            # Calculate average position of all vertices
            center_pos_x = sum(pos[0] for pos in poly) / len(poly)
            center_pos_y = sum(pos[1] for pos in poly) / len(poly)
            
            # Apply coordinate offset based on film inch size
            offset_x = globalconfig.CUTLINE_X_OFFSET
            offset_y = globalconfig.CUTLINE_Y_OFFSET
            
            if globalconfig.FEILIN_INCH != 6:
                offset_x += globalconfig.RING_DISTANCE / 2
                offset_y += globalconfig.RING_DISTANCE / 2
            
            center_pos_list.append([center_pos_x - offset_x, center_pos_y - offset_y])
        return center_pos_list

    def get_hole_count(self):
        """Get the total number of holes in all layers.
        
        Returns:
            Total count of hole positions
            
        Raises:
            AttributeError: If hole position list hasn't been initialized
        """
        if not hasattr(self, 'holeposlist'):
            return 0
        return len(self.holeposlist)

    def add_block_holes(self, holepolylinedict, blockcount):
        """Add hole polylines for a new block to the storage.
        
        Args:
            holepolylinedict: Dictionary mapping layer names to polyline lists
            blockcount: Sequential index of the block being processed
        """
        for e in holepolylinedict:
            if e in list(self.holepolylinearraydict.keys()):
                self.holepolylinearraydict[e].extend(
                    holepolylinedict[e])
            else:
                self.holepolylinearraydict[e] = holepolylinedict[e]

    def holepolylinedictarraycopy(self, holepolylinedict):
        holepolylinearraydict = {}
        for e in holepolylinedict:  # 对通孔图层多段线字典进行遍历，将里面的多段线向上阵列
            holepolylinedataset = []
            for row in range(0,
                             globalconfig.eachblock_y_list[self.block_y_count]):
                holepolylinedataset.extend(
                    datasetjustcopy(
                        holepolylinedict[e],
                        1,
                        1,
                        0,
                        globalconfig.Y_LENGTH /
                        globalconfig.Y_OUTLINE_RATIO *
                        row))
            holepolylinearraydict[e] = holepolylinedataset
        return holepolylinearraydict

    def outputholepos(self, output_dir=None):
        """输出通孔模式说明与各通孔层坐标文件。

        盛雄开孔模式为模式1 时只输出“通孔模式说明.txt”，不输出各通孔层 txt。
        """

        def make_path(name):
            return os.path.join(output_dir, name) if output_dir else name

        holenotefile = open(
            make_path(
                globalconfig.NAME_OF_FEILIN +
                '通孔模式说明' +
                '.txt'),
            'w')  # 输出通孔模式说明
        holenotefile.write("各通孔文件通孔数一览表(不包括5H):\n")
        for e in self.holepolylinearraydict:
            centerposlist = sorted(
                self.calculate_center_positions(
                    self.holepolylinearraydict[e]))
            holenotefile.write(
                "通孔层    " +
                e +
                "    一共有通孔    " +
                '{:d}'.format(
                    len(centerposlist)) +
                "    个\n")  # 输出每一通孔层的中心点数。即对应通孔数量
            if SHENGXIONG_MODE == 1:
                continue  # 模式1：不输出各通孔层坐标 txt
            holeposfile = open(
                make_path(
                    globalconfig.NAME_OF_FEILIN + '-' + e + '.txt'),
                'w')
            holeposfile.write("T01\nM25\n")
            for pos in centerposlist:
                holeposfile.write(
                    'X{:.0f}Y{:.0f}\n'.format(
                        pos[0] * 1000,
                        pos[1] * 1000))  # 要格式化输出，所以先要乘以1000，然后输出小数点前的部分
            if globalconfig.FEILIN_INCH == 6:
                holeposfile.write(
                    "M01\nR0M02X0\nM02\nM01\nR0M02Y0\nM02\nM08\nT02\nX-61200Y-61200\nX61200Y61200\nX-61200Y61200\nX61200Y-61200\nX-61200Y65200\nM30\n")
            else:
                holeposfile.write(
                    "M01\nR0M02X0\nM02\nM01\nR0M02Y0\nM02\nM08\nT02\nX-85840Y-85840\nX85840Y85840\nX-85840Y85840\nX85840Y-85840\nX-85840Y89840\nM30\n")
            holeposfile.close()
        holenotefile.close()

    def outputlongholepos(self, output_dir=None):
        def make_path(name):
            return os.path.join(output_dir, name) if output_dir else name

        for e in self.holepolylinearraydict:
            if e in globalconfig.LONGHOLELIST:
                longholeposfile = open(
                    make_path(
                        globalconfig.NAME_OF_FEILIN +
                        '-' + e + '(长通孔)' + '.drl'),
                    'w')
                longholeposfile.write(
                    'M48\nMETRIC\nVER,1\nFMAT,2\nT01C{:.3f}F042B423S6H2000\n'.format(
                        globalconfig.LONGHOLEDIAMETER))  # 内部通孔
                longholeposfile.write('T02C0.2F042B423S6H2000\n')  # 定位孔
                longholeposfile.write('T03C3.175F042B423S6H2000\n')  # 定位孔
                longholeposfile.write('%\n')
                longholeposfile.write('T01\n')
                centerposlist = sorted(
                    self.calculaterlongholecenterposlist_kai(e))
                for pos in centerposlist:
                    longholeposfile.write(
                        'X{:0.0f}Y{:0.0f}\n'.format(
                            pos[0] * 1000,
                            pos[1] * 1000))  # 要格式化输出，所以先要乘以1000，然后输出小数点前的部分
                if globalconfig.FEILIN_INCH == 6:
                    longholeposfile.write('T02\n')
                    if not globalconfig.LONGHOLEMIRROR:
                        longholeposfile.write(
                            "X015000Y015000\nX137400Y015000\nX137400Y137400\nX015000Y137400\nX015000Y141400\n")
                    else:
                        longholeposfile.write(
                            "X015000Y015000\nX137400Y015000\nX137400Y137400\nX015000Y137400\nX137400Y141400\n")
                    longholeposfile.write('T03\n')
                    if not globalconfig.LONGHOLEMIRROR:
                        longholeposfile.write(
                            'X060000Y009000\nX009000Y060000\nX060000Y143400\nX143400Y060000\n')
                    else:
                        longholeposfile.write(
                            'X009000Y060000\nX092400Y009000\nX143400Y060000\nX092400Y143400\n')
                else:
                    longholeposfile.write('T02\n')
                    longholeposfile.write(
                        "X015660Y015660\nX187340Y015660\nX187340Y187340\nX015660Y187340\nX015660Y191340\n")
                    longholeposfile.write('T03\n')
                    longholeposfile.write(
                        'X005660Y085660\nX085660Y005660\nX197340Y085660\nX085660Y197340\n')
                longholeposfile.write('M30')
                longholeposfile.close()

    # 输出长通孔drl文件坐标,坐标原点为默认值
    def calculaterlongholecenterposlist(self, holelayer):
        center_pos_list = []
        for poly in self.holepolylinearraydict[holelayer]:
            center_pos_x = 0
            center_pos_y = 0
            for pos in poly:  # 通过累加各多段线顶点坐标值，然后除以多段线的顶点数，计算出其中心点的坐标
                center_pos_x = center_pos_x + pos[0]
                center_pos_y = center_pos_y + pos[1]
            center_pos_x = center_pos_x / len(poly)
            center_pos_y = center_pos_y / len(poly)
            center_pos_list.append([center_pos_x, center_pos_y])
        return center_pos_list

    # 输出长通孔drl文件坐标,坐标原点为左下角定位孔-15,-15处
    def calculaterlongholecenterposlist_kai(self, holelayer):
        center_pos_list = []
        for poly in self.holepolylinearraydict[holelayer]:
            center_pos_x = 0
            center_pos_y = 0
            for pos in poly:  # 通过累加各多段线顶点坐标值，然后除以多段线的顶点数，计算出其中心点的坐标
                center_pos_x = center_pos_x + pos[0]
                center_pos_y = center_pos_y + pos[1]
            if globalconfig.FEILIN_INCH == 6:
                if not globalconfig.LONGHOLEMIRROR:
                    center_pos_x = center_pos_x / \
                        len(poly) - globalconfig.CUTLINE_X_OFFSET + 15
                    center_pos_y = center_pos_y / \
                        len(poly) - globalconfig.CUTLINE_Y_OFFSET + 15
                else:
                    center_pos_x = 122.4 - \
                        (center_pos_x / len(poly) - globalconfig.CUTLINE_X_OFFSET) + 15
                    center_pos_y = center_pos_y / \
                        len(poly) - globalconfig.CUTLINE_Y_OFFSET + 15
            else:
                if not globalconfig.LONGHOLEMIRROR:
                    center_pos_x = center_pos_x / \
                        len(poly) - globalconfig.CUTLINE_X_OFFSET + 15.66
                    center_pos_y = center_pos_y / \
                        len(poly) - globalconfig.CUTLINE_Y_OFFSET + 15.66
                else:
                    center_pos_x = 171.68 - \
                        (center_pos_x / len(poly) - globalconfig.CUTLINE_X_OFFSET) + 15.66
                    center_pos_y = center_pos_y / \
                        len(poly) - globalconfig.CUTLINE_Y_OFFSET + 15.66
            center_pos_list.append([center_pos_x, center_pos_y])
        return center_pos_list

    def calculateholecenterposlist(self, polylinelist):
        center_pos_list = []
        for poly in polylinelist:
            center_pos_x = 0
            center_pos_y = 0
            for pos in poly:  # 通过累加各多段线顶点坐标值，然后除以多段线的顶点数，计算出其中心点的坐标
                center_pos_x = center_pos_x + pos[0]
                center_pos_y = center_pos_y + pos[1]
            center_pos_x = center_pos_x / len(poly)
            center_pos_y = center_pos_y / len(poly)
            center_pos_list.append([center_pos_x, center_pos_y])
        return center_pos_list


class Feilin_dxfpolyline():
    """each block dxf polyline info class
    """

    def __init__(self, blocknum):
        # self.layercount=len(readfilelist)
        # self.readfilelist=readfilelist
        # self.dictlist={}
        self.x_ratiolist = []
        self.y_ratiolist = []
        # self.polylinedatasetdict=self.extractpoylinefromdxf()
        # self.holepolylinedict={}
        # self.layernamelist=list(self.polylinedatasetdict.viewkeys())
        # self.layernamelist.append("Cutline")   #这里会包括Cutline以及其他除通孔层的图层
        self.hole_list = []
        self.feilin_list = []
        self.layernamelist = []
        self.blocklist = []
        self.layerholepairlist = []
        self.eachrationumlistlist = []
        self.blocknum = blocknum
        self.calculatexyratio()

    def extractpoylinefromdxf(self, readfilelist):
        d = {}
        for readfile in readfilelist:  # 将readfilelist中的文件逐个按照程序进行读取分析
            filetoread = open(
                readfile, 'r', encoding='utf-8', errors='replace')
            layername = filetoread.name.split("\\")[-1].split(".")[0]
            # newfilename=filetoread.name.split('.')[0]+'.txt'
            # readme.write(newfilename)
            # filetowrite=file(newfilename,'w')
            # writefilelist.append(newfilename)
            x = 0  # x坐标
            y = 0  # y坐标
            dataset = []  # 多段线坐标数组
            counter = 0
            xflag = 0  # 以下x、y、poly、end flag表示下一次读取行是否进入表示该变量的行。1为是，0为否。
            yflag = 0
            polyflag = 0
            endflag = 0
            polyline = []  # 多段线各顶点坐标构成的数组

            for line in filetoread.readlines():
                counter += 1
                # pattern1~5正则表达式判断是否进入标志行
                pattern1 = re.compile('AcDbPolyline')
                pattern2 = re.compile(r'\s{1}10')
                pattern3 = re.compile(r'\s{1}20')
                pattern4 = re.compile(r'\s{2}0')
                pattern5 = re.compile('ENDSEC')
                polymatch = pattern1.match(line)
                xmatch = pattern2.match(line)
                ymatch = pattern3.match(line)
                endmatch = pattern4.match(line)
                finalmatch = pattern5.match(line)
                # 实体定义部分结束，将最后一组多段线的顶点坐标数组加入dataset，dataset是该图形中所有多段线的集合
                if finalmatch and polyflag == 1 and endflag == 1:
                    polyflag = 0
                    dataset.append(polyline)
                    # print(dataset)                                          #打印测试，输出坐标
                    #readme.write('polyline has ended!!!')
                if polyflag == 1 and xflag == 1 and endflag == 0:  # 读取X坐标
                    x = float(line)
                    xflag = 0
                if polyflag == 1 and yflag == 1 and endflag == 0:  # 读取Y坐标
                    y = float(line)
                    yflag = 0
                    polyline.append([x, y])
                if polyflag == 1 and len(
                        polyline) > 1 and endflag == 1:  # 读取所有多段线坐标后，将坐标数组加入dataset内
                    dataset.append(polyline)
                    polyline = []
                    endflag = 0
                if endmatch:
                    endflag = 1
                if polymatch:  # 进入多段线部分，重置其他flag为0。
                    polyflag = 1
                    endflag = 0
                    xflag = 0
                    yflag = 0
                if xmatch:
                    xflag = 1
                if ymatch:
                    yflag = 1

            d[layername] = dataset
        d["Outline"] = [[[globalconfig.X_LENGTH / 2, globalconfig.Y_LENGTH / 2], [globalconfig.X_LENGTH / 2, -globalconfig.Y_LENGTH / 2],
                         [-globalconfig.X_LENGTH / 2, -globalconfig.Y_LENGTH / 2], [-globalconfig.X_LENGTH / 2, globalconfig.Y_LENGTH / 2]]]
        return d

    def extractpoylinefromR12dxf(
            self, blockcount, readfilelist, store_raw_circles=True):
        """读取一整个区块的 DXF 图层文件。

        通孔层与图案层是相互独立的文件，图层名即文件名（V* 开头为通孔层）；
        不再按几何从图案层中提取通孔。支持 POLYLINE / LWPOLYLINE / CIRCLE，
        圆弧段（bulge）在读取时离散成多段线小线段。
        """
        d = {}
        self.layer_frames = {}
        if store_raw_circles:
            self.raw_circles = {}
        for readfile in readfilelist:
            filetoread = open(readfile, 'r')
            layername = filetoread.name.split("\\")[-1].split(".")[0]
            dataset, circles = self._parse_dxf_entities(filetoread)
            filetoread.close()
            frame = self._strip_layer_frame(dataset, circles)
            self._center_layer_on_frame(dataset, circles, frame)
            self.layer_frames[layername] = frame
            if store_raw_circles:
                self.raw_circles[layername] = circles
            d[layername] = dataset
        ox = getattr(globalconfig, 'ORIGINAL_X_LENGTH',
                     globalconfig.X_LENGTH)
        oy = getattr(globalconfig, 'ORIGINAL_Y_LENGTH',
                     globalconfig.Y_LENGTH)
        d["Outline"] = [[[ox / 2, oy / 2],
                         [ox / 2, -oy / 2],
                         [-ox / 2, -oy / 2],
                         [-ox / 2, oy / 2]]]
        return d

    def load_block_layers(self, blockcount, readfilelist, source=None):
        """按来源载入区块图层数据。

        source 为 None 时读取原始分层 DXF 文件；否则使用编辑用总图解析
        结果（已含 layers/frames/circles，且坐标已按外框中心归零）。
        """
        if source is None:
            return self.extractpoylinefromR12dxf(blockcount, readfilelist)
        # 深拷贝：后续旋转/延伸等步骤会就地修改点坐标，
        # 同一来源会被总图与正式生成各用一次，必须互不影响。
        self.layer_frames = {
            layer: ([list(p) for p in frame] if frame else frame)
            for layer, frame in source.get('frames', {}).items()}
        self.raw_circles = {
            layer: [{'center': list(circle['center']),
                     'radius': circle['radius'],
                     'ring_index': circle['ring_index']}
                    for circle in circles]
            for layer, circles in source.get('circles', {}).items()}
        d = {
            layer: [[list(p) for p in polyline] for polyline in polylines]
            for layer, polylines in source.get('layers', {}).items()}
        ox = getattr(globalconfig, 'ORIGINAL_X_LENGTH',
                     globalconfig.X_LENGTH)
        oy = getattr(globalconfig, 'ORIGINAL_Y_LENGTH',
                     globalconfig.Y_LENGTH)
        d["Outline"] = [[[ox / 2, oy / 2],
                         [ox / 2, -oy / 2],
                         [-ox / 2, -oy / 2],
                         [-ox / 2, oy / 2]]]
        return d

    def extract_layers_from_edit_dxf(self, path):
        """解析“编辑用总图”（多图层 DXF），按组码 8 的图层名分组。

        编辑用总图把各图层按槽位排布（下排图案层、上排配对通孔层），
        每层自带设计外框；这里按“外框中心 = 原点”把每层平移回生成用的
        局部坐标，与原图路径的归一化完全一致。

        返回 {'layers': {图层: [多段线...]}, 'circles': {图层: [圆...]},
        'frames': {图层: 外框}}；圆信息中的 ring_index 已换算成该图层
        多段线列表内的下标。

        某图层缺少设计外框时抛出 EditOverviewError。
        """
        text = _read_dxf_text(path)
        dataset, circle_list, layer_of = self._parse_dxf_entities_raw(text)
        layers = {}
        circles = {}
        local_index_of = {}
        for global_index, (polyline, layername) in enumerate(
                zip(dataset, layer_of)):
            name = layername or '0'
            layer_polylines = layers.setdefault(name, [])
            circles.setdefault(name, [])
            local_index_of[global_index] = (name, len(layer_polylines))
            layer_polylines.append(polyline)
        for circle in circle_list:
            name = circle.get('layer') or '0'
            layers.setdefault(name, [])
            layer_circles = circles.setdefault(name, [])
            _name, local_index = local_index_of.get(
                circle['ring_index'], (name, len(layers[name])))
            layer_circles.append({
                'center': list(circle['center']),
                'radius': circle['radius'],
                'ring_index': local_index,
            })
        design_size = (
            getattr(globalconfig, 'ORIGINAL_X_LENGTH', globalconfig.X_LENGTH),
            getattr(globalconfig, 'ORIGINAL_Y_LENGTH', globalconfig.Y_LENGTH))
        frames = {}
        missing_frames = []
        for layer, layer_polylines in layers.items():
            frame = self._strip_layer_frame(
                layer_polylines, circles.get(layer, []), size=design_size)
            frames[layer] = frame
            if frame is None:
                missing_frames.append(layer)
                continue
            # 把该层平移回“外框中心 = 原点”（在编辑总图中的槽位偏移）
            self._center_layer_on_frame(
                layer_polylines, circles.get(layer, []), frame)
        if missing_frames:
            raise EditOverviewError(
                '编辑用总图中以下图层找不到设计外框'
                '（应为 %.4f×%.4fmm 的闭合矩形），无法定位：%s\n'
                '请保留每层的设计外框后重新生成/重新运行。'
                % (design_size[0], design_size[1],
                   '、'.join(sorted(missing_frames))))
        return {'layers': layers, 'circles': circles, 'frames': frames}

    @classmethod
    def _center_layer_on_frame(cls, dataset, circles, frame):
        """把图层几何平移到“外框包围盒中心 = 原点”。

        若文件本身已以外框中心为原点（偏移≈0）则不做任何修改；
        无外框时保持原样。
        """
        if frame is None or len(frame) < 2:
            return
        xs = [p[0] for p in frame]
        ys = [p[1] for p in frame]
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        if abs(cx) < 1e-6 and abs(cy) < 1e-6:
            return
        # 外框若仍留在数据集内，只随数据平移一次，避免重复偏移
        frame_in_dataset = any(poly is frame for poly in dataset)
        for poly in dataset:
            for pos in poly:
                pos[0] -= cx
                pos[1] -= cy
        if not frame_in_dataset:
            for pos in frame:
                pos[0] -= cx
                pos[1] -= cy
        for circle in circles:
            circle['center'][0] -= cx
            circle['center'][1] -= cy

    @classmethod
    def _strip_layer_frame(cls, dataset, circles, size=None):
        """剔除图层文件中面积最大的闭合矩形外框，返回该外框。

        外框只是设计参考框，不应作为图案进入总菲林/开孔等输出。
        size 为 (宽, 高) 时只接受尺寸相符的轮廓（编辑用总图校验用）。
        """
        frame = None
        frame_index = None
        best_area = 0.0
        for i, poly in enumerate(dataset):
            if len(poly) < 4:
                continue
            if size is not None:
                width, height = cls._poly_bbox_size(poly)
                if abs(width - size[0]) > DESIGN_FRAME_TOL or \
                        abs(height - size[1]) > DESIGN_FRAME_TOL:
                    continue
            area = cls._polygon_area(poly)
            if area > best_area:
                best_area = area
                frame = poly
                frame_index = i
        if frame is not None:
            del dataset[frame_index]
            for circle in circles:
                if circle['ring_index'] > frame_index:
                    circle['ring_index'] -= 1
        return frame

    @staticmethod
    def _map_point(x, y):
        """按全局比例/原点/镜像把输入坐标映射到设计坐标。"""
        px = x / globalconfig.GLOBAL_RATIO - globalconfig.X_OFFSET
        py = y / globalconfig.GLOBAL_RATIO - globalconfig.Y_OFFSET
        if globalconfig.IS_PATTERN_MIRROR:
            px = -px
        return [px, py]

    @staticmethod
    def _bulge_points(p0, p1, bulge):
        """把一条带 bulge 的圆弧段离散成多段线点列（含两端点）。"""
        if abs(bulge) < 1e-12:
            return [p0, p1]
        theta = 4 * math.atan(bulge)
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        chord = math.hypot(dx, dy)
        if chord < 1e-12:
            return [p0, p1]
        radius = chord / (2 * math.sin(abs(theta) / 2))
        # 弦高容差 0.001mm：按圆心角步长离散
        tol = 0.001
        half = min(math.pi / 2, math.acos(max(-1.0, min(1.0, 1 - tol / max(radius, tol)))))
        step = 2 * half
        n = max(2, int(math.ceil(abs(theta) / step)))
        # 圆心：p0->p1 中垂线上，距离为 radius
        midx = (p0[0] + p1[0]) / 2
        midy = (p0[1] + p1[1]) / 2
        nx = -dy / chord
        ny = dx / chord
        dist = math.sqrt(max(0.0, radius * radius - (chord / 2) ** 2))
        cx1 = midx + nx * dist
        cy1 = midy + ny * dist
        candidates = [(cx1, cy1), (midx - nx * dist, midy - ny * dist)]
        chosen = None
        best_err = None
        for cx, cy in candidates:
            a0 = math.atan2(p0[1] - cy, p0[0] - cx)
            a1 = math.atan2(p1[1] - cy, p1[0] - cx)
            delta = a1 - a0
            while delta <= -math.pi:
                delta += 2 * math.pi
            while delta > math.pi:
                delta -= 2 * math.pi
            # 把角差还原为与 bulge 同向的完整扫掠角（可能超过 π）
            if bulge > 0:
                ccw = delta if delta > 0 else delta + 2 * math.pi
                err = abs(ccw - theta)
            else:
                cw = delta if delta < 0 else delta - 2 * math.pi
                err = abs(cw - theta)
            if best_err is None or err < best_err:
                best_err = err
                chosen = (cx, cy, a0, math.copysign(theta, bulge))
        if chosen is None:
            chosen = (cx1, cy1,
                      math.atan2(p0[1] - cy1, p0[0] - cx1),
                      math.copysign(theta, bulge))
        cx1, cy1, a0, sweep = chosen
        pts = [p0]
        for k in range(1, n):
            ang = a0 + sweep * k / n
            pts.append([cx1 + radius * math.cos(ang), cy1 + radius * math.sin(ang)])
        pts.append(p1)
        return pts

    def _parse_dxf_entities(self, filetoread):
        """解析单个 DXF 图层文件，返回 (多段线列表, 圆信息列表)。

        坐标按全局比例/原点/镜像映射到设计坐标；圆记录圆心、半径与圆环
        在多段线列表中的下标。
        """
        dataset, circles, _layer_of = self._parse_dxf_entities_raw(
            filetoread.read())
        mapped = [[self._map_point(x, y) for x, y in poly]
                  for poly in dataset]
        mapped_circles = []
        for circle in circles:
            center = self._map_point(circle['center'][0], circle['center'][1])
            radius = circle['radius'] / globalconfig.GLOBAL_RATIO
            index = circle['ring_index']
            mapped[index] = _circle_ring(center[0], center[1], radius)
            mapped_circles.append({
                'center': center,
                'radius': radius,
                'ring_index': index,
            })
        return mapped, mapped_circles

    def _parse_dxf_entities_raw(self, readcontent):
        """解析 DXF 文本中的 POLYLINE / LWPOLYLINE / CIRCLE（不做坐标映射）。

        返回 (多段线列表, 圆信息列表, 图层名列表)。圆信息含圆心、半径、
        圆环下标与所属图层，便于按图层分组还原（编辑用总图读回）。
        """
        dataset = []
        circles = []
        layer_of = []
        lines = readcontent.splitlines()
        recs = []
        i = 0
        while i < len(lines):
            try:
                code = int(lines[i].strip())
                val = lines[i + 1]
            except (ValueError, IndexError):
                i += 1
                continue
            recs.append((code, val))
            i += 2

        in_entities = False
        index = 0
        while index < len(recs):
            code, val = recs[index]
            if code == 2 and val.strip() == 'ENTITIES':
                in_entities = True
                index += 1
                continue
            if code == 0 and val.strip() == 'ENDSEC':
                in_entities = False
            if not in_entities:
                index += 1
                continue
            etype = val.strip()
            index += 1
            pairs = []
            while index < len(recs) and recs[index][0] != 0:
                pairs.append(recs[index])
                index += 1

            def getval(c):
                return next((v for cc, v in pairs if cc == c), None)

            layername = (getval(8) or '0').strip() or '0'

            if etype == 'POLYLINE':
                # 收集后续 VERTEX 子实体
                vertex_pairs = []
                while index < len(recs) and recs[index][0] == 0:
                    stype = recs[index][1].strip()
                    index += 1
                    if stype == 'SEQEND':
                        break
                    if stype == 'VERTEX':
                        vp = []
                        while index < len(recs) and recs[index][0] != 0:
                            vp.append(recs[index])
                            index += 1
                        vertex_pairs.append(vp)
                    else:
                        break
                polyline, bulge_list = self._polyline_from_vertices(vertex_pairs)
                polyline = self._tessellate_bulges(polyline, bulge_list)
                if len(polyline) > 1:
                    dataset.append(polyline)
                    layer_of.append(layername)
                continue

            if etype == 'LWPOLYLINE':
                polyline, bulge_list = self._lwpolyline_data(pairs)
                polyline = self._tessellate_bulges(polyline, bulge_list)
                if len(polyline) > 1:
                    dataset.append(polyline)
                    layer_of.append(layername)
                continue

            if etype == 'CIRCLE':
                try:
                    cx = float(getval(10))
                    cy = float(getval(20))
                    cr = float(getval(40))
                except (TypeError, ValueError):
                    continue
                ring_index = len(dataset)
                dataset.append(_circle_ring(cx, cy, cr))
                layer_of.append(layername)
                circles.append({
                    'center': [cx, cy],
                    'radius': cr,
                    'ring_index': ring_index,
                    'layer': layername,
                })
                continue

            if etype in ('ARC', 'LINE'):
                # 独立 ARC/LINE 暂不参与（设计圆弧通常已并入多段线）
                continue

            # 其它实体类型（TEXT/INSERT/POINT 等）忽略
            continue

        return dataset, circles, layer_of

    @staticmethod
    def _polyline_from_vertices(vertex_pairs):
        points = []
        bulges = []
        for vp in vertex_pairs:
            x = next((float(v) for c, v in vp if c == 10), None)
            y = next((float(v) for c, v in vp if c == 20), None)
            b = next((float(v) for c, v in vp if c == 42), 0.0)
            if x is None or y is None:
                continue
            points.append([x, y])
            bulges.append(b)
        return points, bulges

    @staticmethod
    def _lwpolyline_data(pairs):
        """按 LWPOLYLINE 组码解析顶点；每个顶点单独记录 bulge（缺省 0）。"""
        verts = []
        current = None
        closed = False
        for c, v in pairs:
            if c == 70:
                closed = int(v.strip()) & 1 == 1
            elif c == 10:
                current = {'x': float(v), 'y': None, 'b': 0.0}
                verts.append(current)
            elif c == 20 and current is not None and current['y'] is None:
                current['y'] = float(v)
            elif c == 42 and current is not None:
                current['b'] = float(v)
        clean = [[v['x'], v['y']] for v in verts if v['y'] is not None]
        if closed and len(clean) > 2 and clean[0] != clean[-1]:
            clean.append(list(clean[0]))
            # bulge 逐顶点存储：最后顶点的 bulge 表示闭合段
            seg_bulges = [v['b'] for v in verts]
            return clean, seg_bulges
        seg_bulges = [v['b'] for v in verts][:max(0, len(clean) - 1)]
        return clean, seg_bulges

    def _tessellate_bulges(self, points, bulges):
        if not points:
            return []
        out = [points[0]]
        for k in range(len(points) - 1):
            b = bulges[k] if k < len(bulges) else 0.0
            seg = self._bulge_points(points[k], points[k + 1], b)
            out.extend(seg[1:])
        return out

    def polylineisoutline(self, polyline):
        """
        """
        if len(polyline) == 4:
            xcenterpos = abs(
                polyline[0][0] +
                polyline[1][0] +
                polyline[2][0] +
                polyline[3][0])
            ycenterpos = abs(
                polyline[0][1] +
                polyline[1][1] +
                polyline[2][1] +
                polyline[3][1])

            xlength = abs(polyline[0][0]) + abs(polyline[1][0])
            ylength = abs(polyline[0][1]) + abs(polyline[1][1])

            if xcenterpos < 0.001 and ycenterpos < 0.001 and abs(
                xlength -
                globalconfig.X_LENGTH) < 0.001 and abs(
                ylength -
                    globalconfig.Y_LENGTH) < 0.001:
                return True
            else:
                return False
        else:
            return False

    def calculatexyratio(self):
        """
        """
        for i in range(0, globalconfig.RATIO_NUM):  # 计算放缩率列表
            self.x_ratiolist.append((globalconfig.X_INNER_RATIO -
                                     ((globalconfig.RATIO_NUM +
                                       1) //
                                      2 -
                                      1) *
                                     globalconfig.X_RATIO_DIFF) +
                                    i *
                                    globalconfig.X_RATIO_DIFF)
            self.y_ratiolist.append((globalconfig.Y_INNER_RATIO -
                                     ((globalconfig.RATIO_NUM +
                                       1) //
                                      2 -
                                      1) *
                                     globalconfig.Y_RATIO_DIFF) +
                                    i *
                                    globalconfig.Y_RATIO_DIFF)

    def polylinedictarraycopy(self, blockcount, polylinedatasetdict):  # d——原始图层多段线字典
        """input a polyline dict and array them by row
        """
        dictlist = []
        rationumaccumulationlist = []  # 放缩率数量累加列表

        block_x_count = blockcount % globalconfig.BLOCK_X_NUM
        block_y_count = blockcount // globalconfig.BLOCK_X_NUM

        # 区块的原点偏移量（相对于outline左下角）
        block_x_offset = globalconfig.block_x_accumulationlist[block_x_count] * \
            globalconfig.X_LENGTH / globalconfig.X_OUTLINE_RATIO
        block_y_offset = globalconfig.block_y_accumulationlist[block_y_count] * \
            globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO

        eachrationum = globalconfig.eachblock_x_list[block_x_count] // globalconfig.RATIO_NUM
        leftrationum = globalconfig.eachblock_x_list[block_x_count] % globalconfig.RATIO_NUM

        if eachrationum == 0:
            print("eachrationum==0,please reduce ratio num!")

        eachrationumlist = [eachrationum] * \
            globalconfig.RATIO_NUM  # 各个放缩率对应数量的列表

        for i in range((globalconfig.RATIO_NUM - 1) // 2 - (leftrationum - 1) // 2,
                       (globalconfig.RATIO_NUM - 1) // 2 - (leftrationum - 1) // 2 + leftrationum):
            eachrationumlist[i] = eachrationumlist[i] + \
                1  # 将整除后的余值加入到靠中间放缩率的方案中。

        rationumaccumulationlist.append(0)

        for i in range(1, globalconfig.RATIO_NUM):  # 计算放缩率数量累加列表
            rationumaccumulationlist.append(
                rationumaccumulationlist[i - 1] + eachrationumlist[i - 1])

        for i in range(0, globalconfig.RATIO_NUM):  # 每种放缩率
            for j in range(0, eachrationumlist[i]):  # 每种放缩率对应数量
                newdict = {}
                for e in polylinedatasetdict:  # 将字典中值即每一图层对应的多段线列表进行复制并移动到指定位置
                    newdict[e] = polylinedatasetarraycopy(
                        polylinedatasetdict[e],
                        self.x_ratiolist[i],
                        self.y_ratiolist[i],
                        globalconfig.CUTLINE_X_OFFSET +
                        globalconfig.X_BLANK +
                        (
                            rationumaccumulationlist[i] +
                            j +
                            0.5) *
                        globalconfig.X_LENGTH /
                        globalconfig.X_OUTLINE_RATIO +
                        block_x_offset,
                        globalconfig.CUTLINE_Y_OFFSET +
                        globalconfig.Y_BLANK +
                        0.5 *
                        globalconfig.Y_LENGTH /
                        globalconfig.Y_OUTLINE_RATIO +
                        block_y_offset,
                        e,
                        len(dictlist),
                        globalconfig.eachblock_x_list[block_x_count],
                        blockcount)
                dictlist.append(newdict)
        return dictlist, eachrationumlist

    def createnewblock(self, blockname, blockcount, readfilelist,
                       source=None):
        """createnewblock

        source 不为 None 时使用“编辑用总图”解析结果作为输入来源。
        """

        polylinedatasetdict = self.load_block_layers(
            blockcount, readfilelist, source)
        holepolylinedict = {}
        feilinpolylinedict = {}
        layernamelist = list(polylinedatasetdict.keys())
        # layernamelist.append("Cutline")   #这里会包括Cutline以及其他除通孔层的图层

        feilin_list = []
        hole_list = []

        for layername in layernamelist:  # 生成通孔以及菲林的名称列表
            if layername[0] == 'V' or layername[0] == 'v':
                hole_list.append(layername)
            elif layername != "Outline":
                feilin_list.append(layername)

        self.feilin_list = list(set(self.feilin_list + feilin_list))
        self.hole_list = list(set(self.hole_list + hole_list))

        self.layernamelist = list(set(self.feilin_list + self.hole_list))

        # PAD：图案层与对应通孔层“同圆心同直径”匹配
        # 注意：同一 V 层可能被多个图案层共用，需记录全部匹配对
        self.current_matched_pads = []
        if globalconfig.DRAWPAD:
            circles = getattr(self, 'raw_circles', {}) or {}
            for feilinlayer in feilin_list:
                hole_layer = globalconfig.layerholepairdictlist_actual[
                    blockcount].get(feilinlayer)
                if not hole_layer:
                    continue
                if self._circles_match(
                        circles.get(feilinlayer, []),
                        circles.get(hole_layer, [])):
                    self.current_matched_pads.append(
                        (feilinlayer, hole_layer))
            # 替换：移除图案层中被匹配的原圆环
            for feilinlayer, hole_layer in self.current_matched_pads:
                self._replace_matched_pads(
                    polylinedatasetdict, feilinlayer,
                    circles.get(feilinlayer, []),
                    circles.get(hole_layer, []))

        # 假引/假引孔/引出端拓宽基于原始设计坐标进行，
        # 完成后统一旋转，保证贴框判定与外框一致。
        self._hole_extra_count = {}
        self._apply_dummy_and_widen(polylinedatasetdict, blockcount)
        if globalconfig.ROTATE_90:
            self._rotate_geometry_90(polylinedatasetdict)

        dictlist, eachrationumlist = self.polylinedictarraycopy(
            blockcount, polylinedatasetdict)

        # 原图（设计）孔径：按“每列副本 × 每列孔数”的顺序与一行带对齐，
        # 供点网过滤（假引孔阈值按原图孔径判定）与盛雄开孔孔径计算使用。
        self.hole_band_design_diams = {}
        for holelayer in hole_list:
            design_diams = [
                _ring_diameter(poly)
                for poly in polylinedatasetdict.get(holelayer, [])]
            self.hole_band_design_diams[holelayer] = design_diams * len(dictlist)

        self.blocklist.append(dictlist)
        self.eachrationumlistlist.append(eachrationumlist)

        for feilinlayer in feilin_list:
            feilinpolylinelist = []
            for d in dictlist:
                feilinpolylinelist.extend(d[feilinlayer])
            feilinpolylinedict[feilinlayer] = feilinpolylinelist

        feilinpolylinelist = []
        for d in dictlist:
            feilinpolylinelist.extend(d["Outline"])
        feilinpolylinedict["Outline"] = feilinpolylinelist

        for holelayer in hole_list:  # 已经阵列好的第一行中每一层通孔多段线存入新的“通孔名称”-“一行中所有通孔多段线”的字典
            holepolylinelist = []
            for d in dictlist:
                holepolylinelist.extend(d[holelayer])
            holepolylinedict[holelayer] = holepolylinelist

        return eachrationumlist, holepolylinedict, feilinpolylinedict

    @staticmethod
    def _circles_match(list_a, list_b):
        """两组圆中是否存在圆心、直径都一致的同圆（容差 0.001mm）。"""
        for a in list_a:
            for b in list_b:
                if math.hypot(
                        a['center'][0] - b['center'][0],
                        a['center'][1] - b['center'][1]) <= 0.001 and \
                        abs(a['radius'] - b['radius']) <= 0.0005:
                    return True
        return False

    @staticmethod
    def _replace_matched_pads(
            polylinedatasetdict, layer, layer_circles, hole_circles):
        """把图案层里与通孔层匹配的原圆环替换成 PAD 圆环。

        PAD 圆环按“最终输出直径=PAD孔径”预置：半径乘收缩率后随缩放/阵列
        自动变成最终 PAD 尺寸（X/Y 收缩率一致时）。
        """
        if layer not in polylinedatasetdict:
            return
        remove_idx = set()
        matched_centers = []
        for a in layer_circles:
            for b in hole_circles:
                if math.hypot(
                        a['center'][0] - b['center'][0],
                        a['center'][1] - b['center'][1]) <= 0.001 and \
                        abs(a['radius'] - b['radius']) <= 0.0005:
                    remove_idx.add(a['ring_index'])
                    matched_centers.append(a['center'])
        if remove_idx:
            polylinedatasetdict[layer] = [
                p for i, p in enumerate(polylinedatasetdict[layer])
                if i not in remove_idx]
        radius = (globalconfig.PADDIAMETER / 2) * \
            globalconfig.X_OUTLINE_RATIO
        n = 48
        for cx, cy in matched_centers:
            ring = []
            for k in range(n):
                ang = 2 * math.pi * k / n
                ring.append([cx + radius * math.cos(ang),
                             cy + radius * math.sin(ang)])
            ring.append([cx + radius, cy])
            polylinedatasetdict[layer].append(ring)

    def _rotate_geometry_90(self, polylinedatasetdict):
        """把图案与通孔几何绕原点旋转 90°（方向由配置决定）。

        逆时针：(x, y) -> (-y, x)；顺时针：(x, y) -> (y, -x)。
        """
        clockwise = globalconfig.ROTATE_90_DIRECTION == '顺时针'
        for layer, plist in polylinedatasetdict.items():
            for poly in plist:
                for pos in poly:
                    if clockwise:
                        pos[0], pos[1] = pos[1], -pos[0]
                    else:
                        pos[0], pos[1] = -pos[1], pos[0]
        for circle_list in (getattr(self, 'raw_circles', {}) or {}).values():
            for circle in circle_list:
                cx, cy = circle['center'][0], circle['center'][1]
                if clockwise:
                    circle['center'][0], circle['center'][1] = cy, -cx
                else:
                    circle['center'][0], circle['center'][1] = -cy, cx

    @staticmethod
    def _polygon_area(points):
        area = 0.0
        n = len(points)
        for i in range(n):
            x1, y1 = points[i]
            x2, y2 = points[(i + 1) % n]
            area += x1 * y2 - x2 * y1
        return abs(area) / 2

    @staticmethod
    def _poly_bbox(points):
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return (min(xs), min(ys), max(xs), max(ys))

    @staticmethod
    def _poly_bbox_size(points):
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return (max(xs) - min(xs), max(ys) - min(ys))

    @classmethod
    def _find_layer_frame(cls, polylines, size=None):
        """找面积最大的闭合矩形轮廓作为该层设计外框。

        size 为 (宽, 高) 时只接受包围盒尺寸与之相符（容差
        DESIGN_FRAME_TOL）的轮廓，用于编辑用总图校验设计外框是否存在。
        """
        best = None
        best_area = 0.0
        for poly in polylines:
            if len(poly) < 4:
                continue
            if size is not None:
                width, height = cls._poly_bbox_size(poly)
                if abs(width - size[0]) > DESIGN_FRAME_TOL or \
                        abs(height - size[1]) > DESIGN_FRAME_TOL:
                    continue
            area = cls._polygon_area(poly)
            if area > best_area:
                best_area = area
                best = poly
        return best

    def _frame_of(self, layer, polylines):
        """优先取解析时剥离并保存的外框，找不到再在数据里找。"""
        frames = getattr(self, 'layer_frames', {}) or {}
        if frames.get(layer) is not None:
            return frames[layer]
        return self._find_layer_frame(polylines)

    @classmethod
    def _detect_leads(cls, polylines, frame):
        """找出图案轮廓与外框重合的每一段边线（引出端）。

        每一段“贴框线段”算一个引出端：线段两端点必须连续位于
        外框同一条边上，返回其中点、跨度与所在边。跨闭合点的
        贴框段会合并为一段。
        """
        if frame is None:
            return []
        x0, y0, x1, y1 = cls._poly_bbox(frame)
        tol = 0.005

        def edge_of(px, py):
            if abs(px - x0) <= tol:
                return 'L'
            if abs(px - x1) <= tol:
                return 'R'
            if abs(py - y0) <= tol:
                return 'B'
            if abs(py - y1) <= tol:
                return 'T'
            return None

        leads = []
        for poly in polylines:
            if poly is frame or len(poly) < 2:
                continue
            pts = list(poly)
            # 去掉末尾与起点重复的闭合点，再按环形找连续贴框段
            while len(pts) > 1 and pts[0] == pts[-1]:
                pts.pop()
            if len(pts) < 2:
                continue
            sides = [edge_of(p[0], p[1]) for p in pts]
            n = len(pts)
            runs = []
            i = 0
            while i < n:
                e = sides[i]
                if e is None:
                    i += 1
                    continue
                j = i
                while j + 1 < n and sides[j + 1] == e:
                    j += 1
                runs.append([e, i, j])
                i = j + 1
            # 首尾同边且闭合相接时，把跨闭合点的两段合并
            if len(runs) >= 2 and sides[0] is not None and \
                    sides[0] == sides[-1] and runs[0][1] == 0 and \
                    runs[-1][2] == n - 1:
                runs = [[runs[-1][0], runs[-1][1], runs[0][2]]] + runs[1:-1]
            for e, i, j in runs:
                if i == j:
                    continue  # 单点相切不算引出端
                a = pts[i]
                b = pts[j]
                span = math.hypot(b[0] - a[0], b[1] - a[1])
                if span < 1e-6:
                    continue
                leads.append({
                    'edge': e,
                    'a': a,
                    'b': b,
                    'mid': [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2],
                    'span': span,
                    'poly': poly,
                })
        return leads

    @classmethod
    def _lead_stub(cls, lead):
        """按配置生成引出端“贴框小段”矩形（闭合多段线）。

        矩形沿外框边方向长度 = 参考层实际贴边线段的长度；
        垂直向框内深度 = “引出端绘制宽度”。矩形贴框边与参考层
        贴边线段重合。
        """
        width = globalconfig.LEAD_DRAW_WIDTH
        inward = {'L': (1.0, 0.0), 'R': (-1.0, 0.0),
                  'B': (0.0, 1.0), 'T': (0.0, -1.0)}[lead['edge']]
        a = lead['a']
        b = lead['b']
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        span = lead['span']
        half_l = span / 2
        if span < 1e-12:
            tx, ty = (0.0, 1.0) if lead['edge'] in ('L', 'R') else (1.0, 0.0)
        else:
            tx, ty = dx / span, dy / span
        mx, my = lead['mid']
        return [
            [mx - tx * half_l, my - ty * half_l],
            [mx + tx * half_l, my + ty * half_l],
            [mx + tx * half_l + inward[0] * width,
             my + ty * half_l + inward[1] * width],
            [mx - tx * half_l + inward[0] * width,
             my - ty * half_l + inward[1] * width],
            [mx - tx * half_l, my - ty * half_l],
        ]

    @classmethod
    def _lead_stub_fixed(cls, lead):
        """生成“引出端增绘”矩形（闭合多段线）。

        沿外框边方向长度 = 引出端绘制长度，居中于贴框段中点；
        垂直向图案内深度 = 引出端绘制宽度。
        """
        half_l = globalconfig.LEAD_DRAW_LENGTH / 2
        half_w = globalconfig.LEAD_DRAW_WIDTH / 2
        inward = {'L': (1.0, 0.0), 'R': (-1.0, 0.0),
                  'B': (0.0, 1.0), 'T': (0.0, -1.0)}[lead['edge']]
        a = lead['a']
        b = lead['b']
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        span = lead['span']
        if span < 1e-12:
            tx, ty = (0.0, 1.0) if lead['edge'] in ('L', 'R') else (1.0, 0.0)
        else:
            tx, ty = dx / span, dy / span
        mx = lead['mid'][0] + inward[0] * half_w
        my = lead['mid'][1] + inward[1] * half_w
        return [
            [mx + tx * half_l + inward[0] * half_w,
             my + ty * half_l + inward[1] * half_w],
            [mx + tx * half_l - inward[0] * half_w,
             my + ty * half_l - inward[1] * half_w],
            [mx - tx * half_l - inward[0] * half_w,
             my - ty * half_l - inward[1] * half_w],
            [mx - tx * half_l + inward[0] * half_w,
             my - ty * half_l + inward[1] * half_w],
            [mx + tx * half_l + inward[0] * half_w,
             my + ty * half_l + inward[1] * half_w],
        ]

    @classmethod
    def _center(cls, poly):
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        # 去掉末尾与起点重复的闭合点，避免闭合点被重复加权
        if len(xs) > 1 and xs[0] == xs[-1] and ys[0] == ys[-1]:
            xs = xs[:-1]
            ys = ys[:-1]
        return [sum(xs) / len(xs), sum(ys) / len(ys)]

    @classmethod
    def _hole_items(cls, polylines):
        """把通孔圆环换算成 [(中心x, 中心y, 孔径)]，孔径取包围盒最小边。"""
        items = []
        for poly in polylines:
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            cx = sum(xs) / len(xs)
            cy = sum(ys) / len(ys)
            diam = min(max(xs) - min(xs), max(ys) - min(ys))
            items.append([cx, cy, diam])
        return items

    @classmethod
    def _has_same_center(cls, polylines, center, tol=0.0002):
        for poly in polylines:
            if len(poly) < 3:
                continue
            c = cls._center(poly)
            if abs(c[0] - center[0]) <= tol and abs(c[1] - center[1]) <= tol:
                return True
        return False

    def _add_dummy_holes(self, polylinedatasetdict, blockcount):
        """在列出层的引出端处画假引孔。

        假引孔圆心 = 引出端贴外框的位置向内偏移“引出端绘制宽度/2”。
        """
        hole_layers = globalconfig.dummyhole_layerlist[blockcount]
        if not hole_layers:
            return
        radius = globalconfig.DUMMYHOLE_DIAMETER / 2
        offset = globalconfig.LEAD_DRAW_WIDTH / 2
        n = 48
        for layer in hole_layers:
            if layer not in polylinedatasetdict:
                continue
            hole_layer = globalconfig.layerholepairdictlist_actual[
                blockcount].get(layer)
            if not hole_layer:
                continue
            target = polylinedatasetdict.setdefault(hole_layer, [])
            frame = self._frame_of(layer, polylinedatasetdict[layer])
            for lead in self._detect_leads(polylinedatasetdict[layer], frame):
                cx, cy = self._lead_hole_center(lead, frame, offset)
                if self._has_same_center(target, [cx, cy]):
                    continue
                ring = []
                for k in range(n):
                    ang = 2 * math.pi * k / n
                    ring.append([cx + radius * math.cos(ang),
                                 cy + radius * math.sin(ang)])
                ring.append([cx + radius, cy])
                target.append(ring)
                count = getattr(self, '_hole_extra_count', {})
                count[hole_layer] = count.get(hole_layer, 0) + 1

    @classmethod
    def _lead_hole_center(cls, lead, frame, offset):
        """假引孔圆心 = 贴框段中点沿框边法线向图案内偏移 offset。"""
        inward = {'L': (1.0, 0.0), 'R': (-1.0, 0.0),
                  'B': (0.0, 1.0), 'T': (0.0, -1.0)}[lead['edge']]
        return [lead['mid'][0] + inward[0] * offset,
                lead['mid'][1] + inward[1] * offset]

    def _add_dummy_copies(self, polylinedatasetdict, blockcount,
                          originals=None):
        """把参考层“自身的”贴框小段复制到目标层（不复制整条图形）。

        目标层同一贴框位置已有引出端或同中心图形时跳过。
        参考层若本身是另一组假引的目标层，也只取其原始引出端，
        不把程序后补的假引继续向下传递。
        “引出端增绘”开启时改用固定长宽矩形（同自身引出端增绘）。
        """
        for target, reference in globalconfig.dummy_pairlist[blockcount]:
            if target not in polylinedatasetdict or \
                    reference not in polylinedatasetdict:
                continue
            ref_polys = polylinedatasetdict[reference]
            if originals is not None and reference in originals:
                ref_polys = originals[reference]
            ref_frame = self._frame_of(
                reference, ref_polys)
            tgt_frame = self._frame_of(
                target, polylinedatasetdict[target])
            if ref_frame is None or tgt_frame is None:
                continue
            dx = tgt_frame[0][0] - ref_frame[0][0]
            dy = tgt_frame[0][1] - ref_frame[0][1]
            tgt_leads = self._detect_leads(
                polylinedatasetdict[target], tgt_frame)
            for lead in self._detect_leads(
                    ref_polys, ref_frame):
                ref_mid = [lead['mid'][0] + dx, lead['mid'][1] + dy]
                if any(abs(lt['mid'][0] - ref_mid[0]) <= 0.01 and
                       abs(lt['mid'][1] - ref_mid[1]) <= 0.01
                       for lt in tgt_leads):
                    continue
                # “引出端增绘”开启时，假引也按固定长宽矩形绘制
                if globalconfig.REDRAW_OWN_LEADS:
                    stub_src = self._lead_stub_fixed(lead)
                else:
                    stub_src = self._lead_stub(lead)
                stub = [[x + dx, y + dy]
                        for x, y in stub_src]
                c = self._center(stub)
                if self._has_same_center(
                        polylinedatasetdict[target], c, tol=0.002):
                    continue
                polylinedatasetdict[target].append(stub)

    def _redraw_own_leads(self, polylinedatasetdict, blockcount):
        """“引出端增绘”开关打开时，重画 xy 延伸层自身引出端矩形。"""
        if not globalconfig.REDRAW_OWN_LEADS:
            return
        for layer in globalconfig.EXTENDCOPYLIST[blockcount]:
            if layer not in polylinedatasetdict:
                continue
            frame = self._frame_of(layer, polylinedatasetdict[layer])
            for lead in self._detect_leads(polylinedatasetdict[layer], frame):
                stub = self._lead_stub_fixed(lead)
                center = self._center(stub)
                if not self._has_same_center(
                        polylinedatasetdict[layer], center, tol=0.002):
                    polylinedatasetdict[layer].append(stub)

    def _apply_dummy_and_widen(self, polylinedatasetdict, blockcount):
        """已停用：假引（假引矩形/引出端增绘/自动假引孔）改为人工重绘原图。

        相关函数（_add_dummy_holes/_add_dummy_copies/_redraw_own_leads）
        保留以便后续恢复，但不再参与生成。
        """
        return

    def _synthesize_pad_dataset(self, polylinedatasetdict, hole_layer,
                                pad_layer=None):
        """为没有图案文件的 H/P 层生成 PAD 圆环（按配对 V 层孔位）。

        只取正常孔径通孔圆，排除人工/程序假引孔；圆直径按 点网孔径 绘制。
        """
        rings = list(polylinedatasetdict.get(hole_layer, []))
        extra = getattr(self, '_hole_extra_count', {}).get(hole_layer, 0)
        if extra:
            rings = rings[:-extra]
        # 人工小孔径假引孔与程序自动假引孔都不参与点网 PAD 生成
        rings = [r for r in rings if not _is_fake_hole_ring(r)]
        # 总图中点网圆直径：H 层用 PAD孔径，P 层用点网孔径
        radius = _pad_layer_diameter(pad_layer or hole_layer) / 2
        dataset = []
        n = 48
        for ring in rings:
            points = list(ring)
            if len(points) > 1 and points[0] == points[-1]:
                points = points[:-1]
            if not points:
                continue
            cx = sum(p[0] for p in points) / len(points)
            cy = sum(p[1] for p in points) / len(points)
            poly = []
            for k in range(n):
                ang = 2 * math.pi * k / n
                poly.append([cx + radius * math.cos(ang),
                             cy + radius * math.sin(ang)])
            poly.append([cx + radius, cy])
            dataset.append(poly)
        return dataset

    def createlayerholepair(self, blockname, blockcount, readfilelist,
                            layer_order=None, pair_override=None,
                            layout_rows=None, extra_rows=None,
                            source=None):
        """生成“图层-通孔对应关系图”数据（含假引与假引孔）。

        layer_order：可选，总图从左到右的图层顺序（只保留实际存在的图案层）。
        pair_override：可选，图层→通孔层 映射；值为 None 表示该层无配对。
        layout_rows：可选，成型参数表的逐行 (图层, 通孔层或None) 列表，
            同名图层允许多列出现且每行使用自己的配对，文字逐行保留。
        source：可选，“编辑用总图”解析结果；为 None 时读取原图目录。
        缺省时按文件顺序与配置“图层与通孔配对(实际)”生成。
        """
        polylinedatasetdict = self.load_block_layers(
            blockcount, readfilelist, source)
        # 总图需要同步体现假引与假引孔，便于与原图核对；
        # 不旋转、不改 PAD。
        self._hole_extra_count = {}
        self._apply_dummy_and_widen(polylinedatasetdict, blockcount)
        layernamelist = list(polylinedatasetdict.keys())
        # layernamelist.append("Cutline")   #这里会包括Cutline以及其他除通孔层的图层

        feilin_list = []
        hole_list = []
        notepoints = []

        for layername in layernamelist:  # 生成通孔以及菲林的名称列表
            if layername[0] == 'V' or layername[0] == 'v':
                hole_list.append(layername)
            elif layername != "Outline":
                feilin_list.append(layername)

        if pair_override is not None:
            def hole_of(layer):
                return pair_override.get(layer)
        else:
            def hole_of(layer):
                return globalconfig.layerholepairdictlist_actual[
                    blockcount].get(layer)

        if layout_rows:
            rows = []
            for item in layout_rows:
                if not isinstance(item, (tuple, list)) or not item:
                    continue
                layer = item[0]
                if len(item) < 2:
                    continue
                hole = item[1]
                if layer in polylinedatasetdict and layer in feilin_list:
                    rows.append((layer, hole))
                elif _is_pad_layer(layer) and \
                        hole in polylinedatasetdict:
                    # H/P 层没有图案文件时，按配对 V 层孔位生成 PAD 圆
                    rows.append((layer, hole))
        elif layer_order:
            # 按成型参数表顺序排列，只保留本区块实际存在的图案层
            ordered = [
                name for name in layer_order
                if name in polylinedatasetdict and name in feilin_list]
            rows = [(layer, hole_of(layer)) for layer in ordered]
        else:
            ordered = list(feilin_list)
            rows = [(layer, hole_of(layer)) for layer in ordered]

        # 自动生成的 P 网等补充行（追加在末尾，按传入顺序）
        for item in extra_rows or []:
            if not isinstance(item, (tuple, list)) or len(item) < 2:
                continue
            layer, hole = item[0], item[1]
            if (layer, hole) in rows:
                continue
            if layer in polylinedatasetdict and layer in feilin_list:
                rows.append((layer, hole))
            elif _is_pad_layer(layer) and hole in polylinedatasetdict:
                rows.append((layer, hole))

        layerholepairdict = {}
        # 名称文字放在各自外框正下方，避免与外框/图案干涉
        note_height = 0.25 * globalconfig.Y_LENGTH
        note_y = -getattr(
            globalconfig,
            'ORIGINAL_Y_LENGTH',
            globalconfig.Y_LENGTH) / 2 - 1.3 * note_height
        orig_x = getattr(
            globalconfig, 'ORIGINAL_X_LENGTH', globalconfig.X_LENGTH)
        orig_y = getattr(
            globalconfig, 'ORIGINAL_Y_LENGTH', globalconfig.Y_LENGTH)
        # 上方通孔行：行距要容纳通孔层名称文字
        row_gap = OVERVIEW_GAP + note_height
        # 上方通孔行的行中心：图案外框顶边 + 行距 + 外框半高
        upper_y = orig_y + row_gap
        pattern_top = orig_y / 2
        extra_notes = []
        for count, (layer, hole_layer) in enumerate(rows):
            # 一字排开：所有图层沿 X 方向排在同一水平行
            slot_x = (orig_x + OVERVIEW_GAP) * count
            slot_y = 0.0
            if layer in polylinedatasetdict:
                layer_source = polylinedatasetdict[layer]
            else:
                layer_source = self._synthesize_pad_dataset(
                    polylinedatasetdict, hole_layer, pad_layer=layer)
            layerdataset = datasetjustcopy(
                layer_source, 1, 1, slot_x, slot_y)
            holedataset = []
            outlinedataset = datasetjustcopy(
                polylinedatasetdict["Outline"], 1, 1, slot_x, slot_y)
            if hole_layer and hole_layer in polylinedatasetdict:
                # 下方图案框内恢复绘制对应通孔层圆（原单行版式）
                lower_holedataset = datasetjustcopy(
                    polylinedatasetdict[hole_layer],
                    1, 1, slot_x, slot_y)
                # 上方单独绘制一行的通孔层，外框同尺寸
                upper_holedataset = datasetjustcopy(
                    polylinedatasetdict[hole_layer],
                    1, 1, slot_x, upper_y)
                holedataset = lower_holedataset + upper_holedataset
                hole_outline = datasetjustcopy(
                    polylinedatasetdict["Outline"],
                    1, 1, slot_x, upper_y)
                if "Outline" in list(layerholepairdict.keys()):
                    layerholepairdict["Outline"].extend(outlinedataset)
                    layerholepairdict["Outline"].extend(hole_outline)
                else:
                    layerholepairdict["Outline"] = list(outlinedataset)
                    layerholepairdict["Outline"].extend(hole_outline)
                if layer in list(layerholepairdict.keys()):
                    layerholepairdict[layer].extend(layerdataset)
                else:
                    layerholepairdict[layer] = layerdataset
                if hole_layer in list(
                        layerholepairdict.keys()):
                    layerholepairdict[hole_layer].extend(
                        holedataset)
                else:
                    layerholepairdict[hole_layer] = holedataset

                # 下排文字只保留图案层名（通孔层名在上排标注）
                notepoints.append((
                    layer,
                    [slot_x - len(layer) * note_height * 0.275,
                     note_y]))
                # 上方通孔框下方（两行之间）标注通孔层名
                extra_notes.append((
                    hole_layer,
                    [slot_x - len(hole_layer) * note_height * 0.275,
                     pattern_top + (row_gap - note_height) / 2]))
            else:
                if "Outline" in list(layerholepairdict.keys()):
                    layerholepairdict["Outline"].extend(outlinedataset)
                else:
                    layerholepairdict["Outline"] = outlinedataset
                if layer in list(layerholepairdict.keys()):
                    layerholepairdict[layer].extend(layerdataset)
                else:
                    layerholepairdict[layer] = layerdataset
                notepoints.append((
                    layer,
                    [slot_x - len(layer) * note_height * 0.275,
                     note_y]))

        return layerholepairdict, notepoints, extra_notes

    def outputfeilininfo(self, output_dir=None):
        """
        """
        filename = globalconfig.NAME_OF_FEILIN + '菲林说明文件' + '.txt'
        if output_dir:
            filename = os.path.join(output_dir, filename)
        info = open(filename, 'w')
        info.write(globalconfig.NAME_OF_FEILIN + "丝网设计转化报告\n")
        info.write(
            "转化时间:    " +
            time.strftime(
                '%Y-%m-%d %A %X',
                time.localtime(
                    time.time())) +
            "\n")
        info.write("转化人:     " + globalconfig.AUTHOR_NAME + "\n")

        info.write("丝网排列情况: \n")
        info.write("列     " +
                   str(globalconfig.X_ARRAY_NUM) +
                   "×" +
                   '{:.4f}'.format(round(globalconfig.X_LENGTH /
                                         globalconfig.X_OUTLINE_RATIO, 4)) +
                   "mm\n")
        info.write("行     " +
                   str(globalconfig.Y_ARRAY_NUM) +
                   "×" +
                   '{:.4f}'.format(round(globalconfig.Y_LENGTH /
                                         globalconfig.Y_OUTLINE_RATIO, 4)) +
                   "mm\n")
        info.write("瓷体X方向对应放缩率: " +
                   str(globalconfig.X_OUTLINE_RATIO) +
                   "    瓷体Y方向对应放缩率: " +
                   str(globalconfig.Y_OUTLINE_RATIO) +
                   "\n\n")
        if self.blocknum > 1:
            info.write("拼网方式区块划分:    \n")
            info.write("列方向一共有" + str(globalconfig.BLOCK_X_NUM) + "列\n")
            info.write("行方向一共有" + str(globalconfig.BLOCK_Y_NUM) + "行\n")
            info.write("一共有" + str(self.blocknum) + "套丝网拼网\n")

        for j in range(0, self.blocknum):
            info.write("第" + str(j + 1) + "套图纸对应P/N型号为" +
                       globalconfig.pnlist[j] + "\n")
            if self.blocknum > 1:
                info.write("位于拼网区块的第" + str((j % globalconfig.BLOCK_X_NUM) + 1) +
                           "列    第" + str((j // globalconfig.BLOCK_X_NUM) + 1) + "行\n")
            info.write(globalconfig.pnlist[j] +
                       "型号的图案占据了菲林" +
                       str(globalconfig.eachblock_x_list[j %
                                                         globalconfig.BLOCK_X_NUM]) +
                       "列     " +
                       str(globalconfig.eachblock_y_list[j //
                                                         globalconfig.BLOCK_X_NUM]) +
                       "行\n")
            info.write("其内部图案放缩方案有以下： \n")
            for i in range(0, globalconfig.RATIO_NUM):
                info.write("放缩方案" +
                           str(i +
                               1) +
                           "——x方向放缩率为    " +
                           '{:.3f}'.format(round(self.x_ratiolist[i], 3)) +
                           "    y方向放缩率为    " +
                           '{:.3f}'.format(round(self.y_ratiolist[i], 3)) +
                           "    对应这款型号的放缩方案数    " +
                           str(self.eachrationumlistlist[j][i] *
                               globalconfig.eachblock_y_list[j //
                                                             globalconfig.BLOCK_X_NUM]) +
                           "\n")
            info.write("1bar上的该型号的设计数量为" +
                       str(globalconfig.eachblock_y_list[j //
                                                         globalconfig.BLOCK_X_NUM] *
                           globalconfig.eachblock_x_list[j %
                                                         globalconfig.BLOCK_X_NUM]) +
                       "\n\n")

        #info.write("放缩方案 : "+str(ratiolist)+"\n")
        #info.write("每个放缩率一行对应数量 : "+str(eachrationumlist)+"\n")

        info.write("\n\n" + globalconfig.NAME_OF_FEILIN + "菲林检验标准\n")
        info.write("菲林切割线长度检验标准\n")
        info.write(
            "X方向切割线总长度:    " +
            '{:.4f}'.format(
                round(
                    globalconfig.X_LENGTH /
                    globalconfig.X_OUTLINE_RATIO *
                    globalconfig.X_ARRAY_NUM,
                    4)) +
            "mm\n")
        info.write(
            "Y方向切割线总长度:    " +
            '{:.4f}'.format(
                round(
                    globalconfig.Y_LENGTH /
                    globalconfig.Y_OUTLINE_RATIO *
                    globalconfig.Y_ARRAY_NUM,
                    4)) +
            "mm\n")
        # info.write("说明:通孔的图层为"+str(hole_list)+"\n")

        info.write("\n\n菲林设计人:" + globalconfig.AUTHOR_NAME + "\n")
        info.write(
            "菲林设计时间:" +
            time.strftime(
                '%Y-%m-%d %X',
                time.localtime(
                    time.time())) +
            "\n")
        info.write("说明:需要制作菲林的图层为")
        for feilin in self.feilin_list:
            info.write(feilin + " ")
        # info.write("\n阵列方式:请将以上图层图案向上阵列"+str(globalconfig.Y_ARRAY_NUM)+"行，行偏移为"+'{:.4f}'.format(round(globalconfig.Y_LENGTH/globalconfig.Y_OUTLINE_RATIO,4))+"mm\n")
        info.write("\n阵列方式:请将以上图层图案\n")
        for line in range(0, globalconfig.BLOCK_Y_NUM):
            info.write("从下至上数，位于第" +
                       str(line +
                           1) +
                       "行outline框中的图案向上阵列" +
                       str(globalconfig.eachblock_y_list[line]) +
                       "行，行偏移为" +
                       '{:.4f}'.format(round(globalconfig.Y_LENGTH /
                                             globalconfig.Y_OUTLINE_RATIO, 4)) +
                       "mm\n")
        if self.blocknum > 1:
            info.write("有部分的图层图案未分布在每一行，故阵列后这些图层的图案不会布满菲林图案区域，此外正常设计，请注意\n")
        info.close()


def buildcutlineset():
    """build cutline polyline set
    """
    cutlineset = []

    crosspointlist = [[-globalconfig.RING_OFFSET,
                       -globalconfig.RING_OFFSET],
                      [-globalconfig.RING_OFFSET,
                       globalconfig.RING_OFFSET + globalconfig.RING_DISTANCE],
                      [globalconfig.RING_OFFSET + globalconfig.RING_DISTANCE,
                       globalconfig.RING_OFFSET + globalconfig.RING_DISTANCE]]

    for crosspoint in crosspointlist:
        cutlineset.append([[crosspoint[0] +
                            globalconfig.LENGTH_OF_CROSS /
                            sqrt(2) /
                            2, crosspoint[1] +
                            globalconfig.LENGTH_OF_CROSS /
                            sqrt(2) /
                            2], [crosspoint[0] -
                                 globalconfig.LENGTH_OF_CROSS /
                                 sqrt(2) /
                                 2, crosspoint[1] -
                                 globalconfig.LENGTH_OF_CROSS /
                                 sqrt(2) /
                                 2]])
        cutlineset.append([[crosspoint[0] +
                            globalconfig.LENGTH_OF_CROSS /
                            sqrt(2) /
                            2, crosspoint[1] -
                            globalconfig.LENGTH_OF_CROSS /
                            sqrt(2) /
                            2], [crosspoint[0] -
                                 globalconfig.LENGTH_OF_CROSS /
                                 sqrt(2) /
                                 2, crosspoint[1] +
                                 globalconfig.LENGTH_OF_CROSS /
                                 sqrt(2) /
                                 2]])

    cutlineset.append([[globalconfig.RING_OFFSET +
                        globalconfig.RING_DISTANCE +
                        globalconfig.LENGTH_OF_CROSS /
                        2, -
                        globalconfig.RING_OFFSET], [globalconfig.RING_OFFSET +
                                                    globalconfig.RING_DISTANCE -
                                                    globalconfig.LENGTH_OF_CROSS /
                                                    2, -
                                                    globalconfig.RING_OFFSET]])
    cutlineset.append([[globalconfig.RING_OFFSET +
                        globalconfig.RING_DISTANCE, -
                        globalconfig.RING_OFFSET +
                        globalconfig.LENGTH_OF_CROSS /
                        2], [globalconfig.RING_OFFSET +
                             globalconfig.RING_DISTANCE, -
                             globalconfig.RING_OFFSET -
                             globalconfig.LENGTH_OF_CROSS /
                             2]])

    # cutlineset=[[[-3.2697,-3.2697],[-4.3304,-4.3304]],[[-3.2697,-4.3304],[-4.3304,-3.2697]]]
    # cutlineset.extend([[[-3.2697,176.0104],[-4.3304,174.9497]],[[-3.2697,174.9497],[-4.3304,176.0104]]])
    # cutlineset.extend([[[176.0104,176.0104],[174.9497,174.9497]],[[176.0104,174.9497],[174.9497,176.0104]]])
    # cutlineset.extend([[[175.4800,-3.05],[175.4800,-4.55]],[[174.7300,-3.8],[176.2300,-3.8]]])

    for cutline in cutlineset:
        for pos in cutline:
            pos[0] = pos[0] + globalconfig.CUTLINE_X_OFFSET
            pos[1] = pos[1] + globalconfig.CUTLINE_Y_OFFSET

    for row in range(0, globalconfig.X_ARRAY_NUM + 1):
        if not globalconfig.IS_CUTLINE_SHIFTIN:
            cutlineset.append([[globalconfig.X_BLANK +
                                row *
                                (globalconfig.X_LENGTH /
                                 globalconfig.X_OUTLINE_RATIO) +
                                globalconfig.CUTLINE_X_OFFSET, 0.0 +
                                globalconfig.CUTLINE_Y_OFFSET], [globalconfig.X_BLANK +
                                                                 row *
                                                                 (globalconfig.X_LENGTH /
                                                                  globalconfig.X_OUTLINE_RATIO) +
                                                                 globalconfig.CUTLINE_X_OFFSET, -
                                                                 globalconfig.CUTLINE_LENGTH +
                                                                 globalconfig.CUTLINE_Y_OFFSET]])
            cutlineset.append([[globalconfig.X_BLANK +
                                row *
                                (globalconfig.X_LENGTH /
                                 globalconfig.X_OUTLINE_RATIO) +
                                globalconfig.CUTLINE_X_OFFSET, globalconfig.RING_DISTANCE +
                                globalconfig.CUTLINE_Y_OFFSET], [globalconfig.X_BLANK +
                                                                 row *
                                                                 (globalconfig.X_LENGTH /
                                                                  globalconfig.X_OUTLINE_RATIO) +
                                                                 globalconfig.CUTLINE_X_OFFSET, globalconfig.CUTLINE_LENGTH +
                                                                 globalconfig.RING_DISTANCE +
                                                                 globalconfig.CUTLINE_Y_OFFSET]])
        else:
            cutlineset.append([[globalconfig.X_BLANK +
                                row *
                                (globalconfig.X_LENGTH /
                                 globalconfig.X_OUTLINE_RATIO) +
                                globalconfig.CUTLINE_X_OFFSET, 0.0 +
                                globalconfig.CUTLINE_Y_OFFSET], [globalconfig.X_BLANK +
                                                                 row *
                                                                 (globalconfig.X_LENGTH /
                                                                  globalconfig.X_OUTLINE_RATIO) +
                                                                 globalconfig.CUTLINE_X_OFFSET, globalconfig.CUTLINE_LENGTH +
                                                                 globalconfig.CUTLINE_Y_OFFSET]])
            cutlineset.append([[globalconfig.X_BLANK +
                                row *
                                (globalconfig.X_LENGTH /
                                 globalconfig.X_OUTLINE_RATIO) +
                                globalconfig.CUTLINE_X_OFFSET, globalconfig.RING_DISTANCE +
                                globalconfig.CUTLINE_Y_OFFSET], [globalconfig.X_BLANK +
                                                                 row *
                                                                 (globalconfig.X_LENGTH /
                                                                  globalconfig.X_OUTLINE_RATIO) +
                                                                 globalconfig.CUTLINE_X_OFFSET, -
                                                                 globalconfig.CUTLINE_LENGTH +
                                                                 globalconfig.RING_DISTANCE +
                                                                 globalconfig.CUTLINE_Y_OFFSET]])
    for line in range(0, globalconfig.Y_ARRAY_NUM + 1):
        if not globalconfig.IS_CUTLINE_SHIFTIN:
            cutlineset.append([[0.0 + globalconfig.CUTLINE_X_OFFSET,
                                globalconfig.Y_BLANK + line * (globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO) + globalconfig.CUTLINE_Y_OFFSET],
                               [-globalconfig.CUTLINE_LENGTH + globalconfig.CUTLINE_X_OFFSET,
                                globalconfig.Y_BLANK + line * (globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO) + globalconfig.CUTLINE_Y_OFFSET]])
            cutlineset.append([[globalconfig.RING_DISTANCE +
                                globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                                line *
                                (globalconfig.Y_LENGTH /
                                 globalconfig.Y_OUTLINE_RATIO) +
                                globalconfig.CUTLINE_Y_OFFSET], [globalconfig.CUTLINE_LENGTH +
                                                                 globalconfig.RING_DISTANCE +
                                                                 globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                                                                 line *
                                                                 (globalconfig.Y_LENGTH /
                                                                  globalconfig.Y_OUTLINE_RATIO) +
                                                                 globalconfig.CUTLINE_Y_OFFSET]])
        else:
            cutlineset.append([[0.0 +
                                globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                                line *
                                (globalconfig.Y_LENGTH /
                                 globalconfig.Y_OUTLINE_RATIO) +
                                globalconfig.CUTLINE_Y_OFFSET], [globalconfig.CUTLINE_LENGTH +
                                                                 globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                                                                 line *
                                                                 (globalconfig.Y_LENGTH /
                                                                  globalconfig.Y_OUTLINE_RATIO) +
                                                                 globalconfig.CUTLINE_Y_OFFSET]])
            cutlineset.append([[globalconfig.RING_DISTANCE + globalconfig.CUTLINE_X_OFFSET,
                                globalconfig.Y_BLANK + line * (globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO) + globalconfig.CUTLINE_Y_OFFSET],
                               [-globalconfig.CUTLINE_LENGTH + globalconfig.RING_DISTANCE + globalconfig.CUTLINE_X_OFFSET,
                                globalconfig.Y_BLANK + line * (globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO) + globalconfig.CUTLINE_Y_OFFSET]])
    return cutlineset


def buildflashlist():
    """build flash set
    """
    flashlist = []
    crosspointlist = [[-globalconfig.RING_OFFSET,
                       -globalconfig.RING_OFFSET],
                      [-globalconfig.RING_OFFSET,
                       globalconfig.RING_OFFSET + globalconfig.RING_DISTANCE],
                      [globalconfig.RING_OFFSET + globalconfig.RING_DISTANCE,
                       globalconfig.RING_OFFSET + globalconfig.RING_DISTANCE]]

    for crosspoint in crosspointlist:
        flashlist.append([crosspoint[0] +
                          globalconfig.LENGTH_OF_CROSS /
                          sqrt(2) /
                          2, crosspoint[1] +
                          globalconfig.LENGTH_OF_CROSS /
                          sqrt(2) /
                          2])
        flashlist.append([crosspoint[0] -
                          globalconfig.LENGTH_OF_CROSS /
                          sqrt(2) /
                          2, crosspoint[1] -
                          globalconfig.LENGTH_OF_CROSS /
                          sqrt(2) /
                          2])
        flashlist.append([crosspoint[0] +
                          globalconfig.LENGTH_OF_CROSS /
                          sqrt(2) /
                          2, crosspoint[1] -
                          globalconfig.LENGTH_OF_CROSS /
                          sqrt(2) /
                          2])
        flashlist.append([crosspoint[0] -
                          globalconfig.LENGTH_OF_CROSS /
                          sqrt(2) /
                          2, crosspoint[1] +
                          globalconfig.LENGTH_OF_CROSS /
                          sqrt(2) /
                          2])

    flashlist.append([globalconfig.RING_OFFSET +
                      globalconfig.RING_DISTANCE +
                      globalconfig.LENGTH_OF_CROSS /
                      2, -
                      globalconfig.RING_OFFSET])
    flashlist.append([globalconfig.RING_OFFSET +
                      globalconfig.RING_DISTANCE -
                      globalconfig.LENGTH_OF_CROSS /
                      2, -
                      globalconfig.RING_OFFSET])
    flashlist.append([globalconfig.RING_OFFSET +
                      globalconfig.RING_DISTANCE, -
                      globalconfig.RING_OFFSET +
                      globalconfig.LENGTH_OF_CROSS /
                      2])
    flashlist.append([globalconfig.RING_OFFSET +
                      globalconfig.RING_DISTANCE, -
                      globalconfig.RING_OFFSET -
                      globalconfig.LENGTH_OF_CROSS /
                      2])
#     flashlist=[[-3.2697,-3.2697],[-4.3304,-4.3304],[-3.2697,-4.3304],[-4.3304,-3.2697]]
#     flashlist.extend([[-3.2697,176.0104],[-4.3304,174.9497],[-3.2697,174.9497],[-4.3304,176.0104]])
#     flashlist.extend([[176.0104,176.0104],[174.9497,174.9497],[176.0104,174.9497],[174.9497,176.0104]])
#     flashlist.extend([[175.4800,-3.05],[175.4800,-4.55],[174.7300,-3.8],[176.2300,-3.8]])
#
    for flash in flashlist:
        flash[0] = flash[0] + globalconfig.CUTLINE_X_OFFSET
        flash[1] = flash[1] + globalconfig.CUTLINE_Y_OFFSET

    for row in range(0, globalconfig.X_ARRAY_NUM + 1):
        flashlist.append([globalconfig.X_BLANK +
                          row *
                          (globalconfig.X_LENGTH /
                           globalconfig.X_OUTLINE_RATIO) +
                          globalconfig.CUTLINE_X_OFFSET, 0.0 +
                          globalconfig.CUTLINE_Y_OFFSET])
        flashlist.append([globalconfig.X_BLANK +
                          row *
                          (globalconfig.X_LENGTH /
                           globalconfig.X_OUTLINE_RATIO) +
                          globalconfig.CUTLINE_X_OFFSET, globalconfig.RING_DISTANCE +
                          globalconfig.CUTLINE_Y_OFFSET])
        if not globalconfig.IS_CUTLINE_SHIFTIN:
            flashlist.append([globalconfig.X_BLANK +
                              row *
                              (globalconfig.X_LENGTH /
                               globalconfig.X_OUTLINE_RATIO) +
                              globalconfig.CUTLINE_X_OFFSET, -
                              globalconfig.CUTLINE_LENGTH +
                              globalconfig.CUTLINE_Y_OFFSET])
            flashlist.append([globalconfig.X_BLANK +
                              row *
                              (globalconfig.X_LENGTH /
                               globalconfig.X_OUTLINE_RATIO) +
                              globalconfig.CUTLINE_X_OFFSET, globalconfig.CUTLINE_LENGTH +
                              globalconfig.RING_DISTANCE +
                              globalconfig.CUTLINE_Y_OFFSET])
        else:
            flashlist.append([globalconfig.X_BLANK +
                              row *
                              (globalconfig.X_LENGTH /
                               globalconfig.X_OUTLINE_RATIO) +
                              globalconfig.CUTLINE_X_OFFSET, globalconfig.CUTLINE_LENGTH +
                              globalconfig.CUTLINE_Y_OFFSET])
            flashlist.append([globalconfig.X_BLANK +
                              row *
                              (globalconfig.X_LENGTH /
                               globalconfig.X_OUTLINE_RATIO) +
                              globalconfig.CUTLINE_X_OFFSET, -
                              globalconfig.CUTLINE_LENGTH +
                              globalconfig.RING_DISTANCE +
                              globalconfig.CUTLINE_Y_OFFSET])

    for line in range(0, globalconfig.Y_ARRAY_NUM + 1):
        flashlist.append([0.0 +
                          globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                          line *
                          (globalconfig.Y_LENGTH /
                           globalconfig.Y_OUTLINE_RATIO) +
                          globalconfig.CUTLINE_Y_OFFSET])
        flashlist.append([globalconfig.RING_DISTANCE +
                          globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                          line *
                          (globalconfig.Y_LENGTH /
                           globalconfig.Y_OUTLINE_RATIO) +
                          globalconfig.CUTLINE_Y_OFFSET])
        if not globalconfig.IS_CUTLINE_SHIFTIN:
            flashlist.append([-globalconfig.CUTLINE_LENGTH + globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                              line * (globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO) + globalconfig.CUTLINE_Y_OFFSET])
            flashlist.append([globalconfig.CUTLINE_LENGTH +
                              globalconfig.RING_DISTANCE +
                              globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                              line *
                              (globalconfig.Y_LENGTH /
                               globalconfig.Y_OUTLINE_RATIO) +
                              globalconfig.CUTLINE_Y_OFFSET])
        else:
            flashlist.append([globalconfig.CUTLINE_LENGTH +
                              globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                              line *
                              (globalconfig.Y_LENGTH /
                               globalconfig.Y_OUTLINE_RATIO) +
                              globalconfig.CUTLINE_Y_OFFSET])
            flashlist.append([-globalconfig.CUTLINE_LENGTH + globalconfig.RING_DISTANCE + globalconfig.CUTLINE_X_OFFSET,
                              globalconfig.Y_BLANK + line * (globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO) + globalconfig.CUTLINE_Y_OFFSET])

    return flashlist


def buildringlist():
    """Build positioning ring list.

    '5H' keeps the original five rings (including the FIFTH_RING_OFFSET one);
    '4H' omits that entry.
    """
    ringlist = [[[-globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                  0.0 + globalconfig.CUTLINE_Y_OFFSET],
                 [globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                  0.0 + globalconfig.CUTLINE_Y_OFFSET]],
                [[-globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                  globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET],
                 [globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                  globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET]],
                [[-globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                  globalconfig.FIFTH_RING_OFFSET + globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET],
                 [globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                    globalconfig.FIFTH_RING_OFFSET + globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET]],
                [[globalconfig.RING_DISTANCE - globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                  0.0 + globalconfig.CUTLINE_Y_OFFSET],
                 [globalconfig.RING_DISTANCE + globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                    0.0 + globalconfig.CUTLINE_Y_OFFSET]],
                [[globalconfig.RING_DISTANCE - globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                  globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET],
                 [globalconfig.RING_DISTANCE + globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                  globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET]]]
    if POSITION_RING_MODE == '4H':
        ringlist.pop(2)  # 去掉带 FIFTH_RING_OFFSET 的第五个环
    return ringlist


def buildringholelist():
    """Build positioning ring hole positions (4H omits the fifth-ring entry)."""
    ringholelist = [[globalconfig.CUTLINE_X_OFFSET,
                     globalconfig.CUTLINE_Y_OFFSET],
                    [globalconfig.CUTLINE_X_OFFSET,
                     globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET],
                    [globalconfig.CUTLINE_X_OFFSET,
                     globalconfig.FIFTH_RING_OFFSET + globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET],
                    [globalconfig.RING_DISTANCE + globalconfig.CUTLINE_X_OFFSET,
                     globalconfig.CUTLINE_Y_OFFSET],
                    [globalconfig.RING_DISTANCE + globalconfig.CUTLINE_X_OFFSET,
                     globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET],
                    ]
    if POSITION_RING_MODE == '4H':
        ringholelist.pop(2)  # 去掉带 FIFTH_RING_OFFSET 的第五个定位孔
    return ringholelist


def buildmarkpointlist(eachrationumlist, blockcount):
    """build mark point list
    """

    markpointlistdict = {}

    markpointlist = []
    rationumaccumulationlist = []
    rationumaccumulationlist.append(0)
    for i in range(1, globalconfig.RATIO_NUM):  # 计算放缩率数量累加列表
        rationumaccumulationlist.append(
            rationumaccumulationlist[i - 1] + eachrationumlist[i - 1])

    block_x_count = blockcount % globalconfig.BLOCK_X_NUM
    block_y_count = blockcount // globalconfig.BLOCK_X_NUM

    block_x_offset = globalconfig.block_x_accumulationlist[block_x_count] * \
        globalconfig.X_LENGTH / globalconfig.X_OUTLINE_RATIO
    block_y_offset = globalconfig.block_y_accumulationlist[block_y_count] * \
        globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO

    for i in range(len(eachrationumlist)):
        markpointlist = []
        for row in range(0, eachrationumlist[i]):
            markpointlist.append([globalconfig.X_BLANK +
                                  globalconfig.CUTLINE_X_OFFSET +
                                  (globalconfig.X_LENGTH /
                                   globalconfig.X_OUTLINE_RATIO) *
                                  (rationumaccumulationlist[i] +
                                   row) +
                                  globalconfig.MARK_X_OFFSET +
                                  block_x_offset, globalconfig.Y_BLANK +
                                  globalconfig.CUTLINE_Y_OFFSET +
                                  globalconfig.MARK_Y_OFFSET +
                                  block_y_offset])

        if globalconfig.BLOCK_X_NUM == 1 and globalconfig.BLOCK_Y_NUM == 1:
            mark = globalconfig.MARKNOTE + globalconfig.markratiolist[i]
        elif globalconfig.BLOCK_X_NUM == 1 or globalconfig.BLOCK_Y_NUM == 1:

            if globalconfig.BLOCK_Y_NUM == 1:
                if globalconfig.RATIO_NUM == 1:
                    mark = globalconfig.MARKNOTE + \
                        globalconfig.blockmark_x_list[block_x_count]
                else:
                    mark = globalconfig.MARKNOTE + \
                        globalconfig.blockmark_x_list[block_x_count] + globalconfig.markratiolist[i]
            if globalconfig.BLOCK_X_NUM == 1:
                if globalconfig.RATIO_NUM == 1:
                    mark = globalconfig.MARKNOTE + \
                        globalconfig.blockmark_y_list[block_y_count]
                else:
                    mark = globalconfig.MARKNOTE + \
                        globalconfig.blockmark_y_list[block_y_count] + globalconfig.markratiolist[i]
        else:
            if globalconfig.RATIO_NUM == 1:
                mark = globalconfig.MARKNOTE + \
                    globalconfig.blockmark_x_list[block_x_count] + globalconfig.blockmark_y_list[block_y_count]
            else:
                mark = globalconfig.MARKNOTE + \
                    globalconfig.blockmark_x_list[block_x_count] + globalconfig.blockmark_y_list[block_y_count] + globalconfig.markratiolist[i]
        markpointlistdict[mark] = markpointlist
    return markpointlistdict


def buildfilelist(workdir=None):
    """Scan a directory for numbered sub-folders containing DXF files.

    Args:
        workdir: Directory to scan. Defaults to the directory of this script.

    Returns:
        Dictionary mapping each numbered folder (int) to the list of DXF
        file paths found inside it.
    """
    dirdict = {}
    if workdir is None:
        workdir = _app_dir()
    workdir = os.path.abspath(workdir)

    for item in os.listdir(workdir):
        filepath = os.path.join(workdir, item)
        if os.path.isdir(filepath) and item.isdigit():
            readfilelist = []
            for onefile in os.listdir(filepath):
                filepath2 = os.path.join(filepath, onefile)
                if os.path.splitext(onefile)[
                        1] == '.dxf':  # 查找目录下的dxf文件，加入到readfilelist文件列表中
                    readfilelist.append(filepath2)
            # dirlist是字典，key是文件夹的名称，value是文件夹中dxf文件列表
            dirdict[int(item)] = readfilelist
    # feilin=file('feilin(ph).dxf','w')
    # #新建一个文件，名字先占位用，后续改成由配置文件中读入名称。

    return dirdict


def holepolylinedictarraycopy(holepolylinedict):
    """input a hole polyline dataset dict and array them by line
    """
    holepolylinearraydict = {}
    for e in holepolylinedict:  # 对通孔图层多段线字典进行遍历，将里面的多段线向上阵列
        holepolylinedataset = []
        for row in range(0, globalconfig.Y_ARRAY_NUM):
            holepolylinedataset.extend(
                datasetjustcopy(
                    holepolylinedict[e],
                    1,
                    1,
                    0,
                    globalconfig.Y_LENGTH /
                    globalconfig.Y_OUTLINE_RATIO *
                    row))
        holepolylinearraydict[e] = holepolylinedataset
    return holepolylinearraydict


# l-多段线列表  x_ratio-x方向放缩率 y_ratio-y方向放缩率 x_offset-x方向偏移 y_offset-y方向偏移
# layername-图层名称 arraycount-数数位置计数，判断是否在边缘？
def polylinedatasetarraycopy(
        l,
        x_ratio,
        y_ratio,
        x_offset,
        y_offset,
        layername,
        arraycount,
        arraylength,
        blockcount):
    """copy a polyline dataset and enlarged by a certain ratio
    """
    if layername in globalconfig.JUSTCOPYLIST and layername != "Outline":  # 根据图层名称判断是按中心放缩率直接放大后复制还是按多种放缩率放大后做边上的点的延伸或者不延伸的操作
        if arraycount == 0:
            dataset = datasetratiocopy_xl_extend(
                l,
                globalconfig.X_OUTLINE_RATIO,
                globalconfig.Y_OUTLINE_RATIO,
                x_offset,
                y_offset)
        elif arraycount == arraylength - 1:  # 判断是最右边的图案
            dataset = datasetratiocopy_xr_extend(
                l,
                globalconfig.X_OUTLINE_RATIO,
                globalconfig.Y_OUTLINE_RATIO,
                x_offset,
                y_offset)
        else:  # 判断是中间的图案
            dataset = datasetratiocopy_notextend(
                l,
                globalconfig.X_OUTLINE_RATIO,
                globalconfig.Y_OUTLINE_RATIO,
                x_offset,
                y_offset)
    elif layername == "Outline":
        dataset = datasetjustcopy(
            l,
            globalconfig.X_OUTLINE_RATIO,
            globalconfig.Y_OUTLINE_RATIO,
            x_offset,
            y_offset)
    elif layername in globalconfig.EXTENDCOPYLIST[blockcount]:
        dataset = datasetratiocopy_extend(
            l, x_ratio, y_ratio, x_offset, y_offset)
    else:
        if arraycount == 0:  # 判断是最左边的图案
            dataset = datasetratiocopy_xl_extend(
                l, x_ratio, y_ratio, x_offset, y_offset)
        elif arraycount == arraylength - 1:  # 判断是最右边的图案
            dataset = datasetratiocopy_xr_extend(
                l, x_ratio, y_ratio, x_offset, y_offset)
        else:  # 判断是中间的图案
            dataset = datasetratiocopy_notextend(
                l, x_ratio, y_ratio, x_offset, y_offset)
    return dataset


# l-多段线列表  ratio-放缩比例，基点是原点 x_offset y_offset-移动的偏移
def datasetjustcopy(l, x_ratio, y_ratio, x_offset, y_offset):
    """just enlarged by center ratio
    """
    dataset = []
    for polyline in l:
        newpolyline = []
        for pos in polyline:
            newpolyline.append(
                [pos[0] / x_ratio + x_offset, pos[1] / y_ratio + y_offset])
        dataset.append(newpolyline)
    return dataset


def datasetratiocopy_xl_extend(l, x_ratio, y_ratio, x_offset, y_offset):  # 只延伸上下两边以及左边的点
    """just enlarged a dataset by certain ratio with vertex on outline extended
    """
    dataset = []
    for polyline in l:
        newpolyline = []
        for pos in polyline:
            pos_x = pos[0]
            pos_y = pos[1]
            if abs((abs(pos_x) - globalconfig.X_LENGTH / 2)) < 0.01:
                if pos_x < 0:  # judge if the pos is on the origin outline,if on outline,will be moved to the new enlarged outline and plus an extene length
                    pos_x = pos[0] / globalconfig.X_OUTLINE_RATIO + \
                        (abs(pos_x) / pos_x * globalconfig.X_EXTENDED_LENGTH) + x_offset
                else:
                    pos_x = pos[0] / globalconfig.X_OUTLINE_RATIO + x_offset
            else:
                pos_x = pos[0] / x_ratio + x_offset
            if abs((abs(pos_y) - globalconfig.Y_LENGTH / 2)) < 0.01:
                pos_y = pos[1] / globalconfig.Y_OUTLINE_RATIO + \
                    (abs(pos_y) / pos_y * globalconfig.Y_EXTENDED_LENGTH) + y_offset
            else:
                pos_y = pos[1] / y_ratio + y_offset
            newpolyline.append([pos_x, pos_y])
        dataset.append(newpolyline)
    return dataset


def datasetratiocopy_xr_extend(l, x_ratio, y_ratio, x_offset, y_offset):  # 只延伸上下两边以及右边的点
    """just enlarged a dataset by certain ratio with vertex on outline extended
    """
    dataset = []
    for polyline in l:
        newpolyline = []
        for pos in polyline:
            pos_x = pos[0]
            pos_y = pos[1]
            if abs((abs(pos_x) - globalconfig.X_LENGTH / 2)) < 0.01:
                if pos_x > 0:  # judge if the pos is on the origin outline,if on outline,will be moved to the new enlarged outline and plus an extene length
                    pos_x = pos[0] / globalconfig.X_OUTLINE_RATIO + \
                        (abs(pos_x) / pos_x * globalconfig.X_EXTENDED_LENGTH) + x_offset
                else:
                    pos_x = pos[0] / globalconfig.X_OUTLINE_RATIO + x_offset
            else:
                pos_x = pos[0] / x_ratio + x_offset
            if abs((abs(pos_y) - globalconfig.Y_LENGTH / 2)) < 0.01:
                pos_y = pos[1] / globalconfig.Y_OUTLINE_RATIO + \
                    (abs(pos_y) / pos_y * globalconfig.Y_EXTENDED_LENGTH) + y_offset
            else:
                pos_y = pos[1] / y_ratio + y_offset
            newpolyline.append([pos_x, pos_y])
        dataset.append(newpolyline)
    return dataset


def datasetratiocopy_extend(l, x_ratio, y_ratio, x_offset, y_offset):  # 全部四边上的点都延伸
    """just enlarged a dataset by certain ratio with vertex on outline extended
    """
    dataset = []
    for polyline in l:
        newpolyline = []
        for pos in polyline:
            pos_x = pos[0]
            pos_y = pos[1]
            # judge if the pos is on the origin outline,if on outline,will be
            # moved to the new enlarged outline and plus an extene length
            if abs((abs(pos_x) - globalconfig.X_LENGTH / 2)) < 0.01:
                pos_x = pos[0] / globalconfig.X_OUTLINE_RATIO + \
                    (abs(pos_x) / pos_x * globalconfig.X_EXTENDED_LENGTH) + x_offset
            else:
                pos_x = pos[0] / x_ratio + x_offset
            if abs((abs(pos_y) - globalconfig.Y_LENGTH / 2)) < 0.01:
                pos_y = pos[1] / globalconfig.Y_OUTLINE_RATIO + \
                    (abs(pos_y) / pos_y * globalconfig.Y_EXTENDED_LENGTH) + y_offset
            else:
                pos_y = pos[1] / y_ratio + y_offset
            newpolyline.append([pos_x, pos_y])
        dataset.append(newpolyline)
    return dataset


# 虽然说是不延伸，但是上下两边上的点Y方向还是会延伸的。
def datasetratiocopy_notextend(l, x_ratio, y_ratio, x_offset, y_offset):
    """just enlarged a dataset by certain ratio with vertex on outline not extended
    """
    dataset = []
    for polyline in l:
        newpolyline = []
        for pos in polyline:
            pos_x = pos[0]
            pos_y = pos[1]
            # judge if the pos is on the origin outline,if on outline,will be
            # moved to the new enlarged outline and plus an extene length
            if abs((abs(pos_x) - globalconfig.X_LENGTH / 2)) < 0.01:
                pos_x = pos[0] / globalconfig.X_OUTLINE_RATIO + x_offset
            else:
                pos_x = pos[0] / x_ratio + x_offset
            if abs((abs(pos_y) - globalconfig.Y_LENGTH / 2)) < 0.01:
                pos_y = pos[1] / globalconfig.Y_OUTLINE_RATIO + y_offset + (
                    abs(pos_y) / pos_y * globalconfig.Y_EXTENDED_LENGTH)  # 虽然说是不延伸，但是上下两边上的点Y方向还是会延伸的。
            else:
                pos_y = pos[1] / y_ratio + y_offset
            newpolyline.append([pos_x, pos_y])
        dataset.append(newpolyline)

    return dataset


# 1) Private (only for developpers)
_HEADER_POINTS = ['insbase', 'extmin', 'extmax']
# ---helper functions


def _point(x, index=0):
    """Convert tuple to a dxf point"""
    return '\n'.join(['%s\n%s' % ((i + 1) * 10 + index, x[i])
                      for i in range(len(x))])


def _points(p):
    """Convert a list of tuples to dxf points"""
    return [_point(p[i], i)for i in range(len(p))]

# ---base classes


class _Call:
    """Makes a callable class."""

    def copy(self):
        """Returns a copy."""
        return copy.deepcopy(self)

    def __call__(self, **attrs):
        """Returns a copy with modified attributes."""
        copied = self.copy()
        for attr in attrs:
            setattr(copied, attr, attrs[attr])
        return copied


class _Entity(_Call):
    """Base class for _common group codes for entities."""

    def __init__(self, color=None, extrusion=None, layer='0',
                 lineType=None, lineTypeScale=None, lineWeight=None,
                 thickness=None, parent=None):
        """None values will be omitted."""
        self.color = color
        self.extrusion = extrusion
        self.layer = layer
        self.lineType = lineType
        self.lineTypeScale = lineTypeScale
        self.lineWeight = lineWeight
        self.thickness = thickness
        self.parent = parent

    def _common(self):
        """Return common group codes as a string."""
        if self.parent:
            parent = self.parent
        else:
            parent = self
        result = '8\n%s' % parent.layer
        if parent.color is not None:
            result += '\n62\n%s' % parent.color
        if parent.extrusion is not None:
            result += '\n%s' % _point(parent.extrusion, 200)
        if parent.lineType is not None:
            result += '\n6\n%s' % parent.lineType
        if parent.lineWeight is not None:
            result += '\n370\n%s' % parent.lineWeight
        if parent.lineTypeScale is not None:
            result += '\n48\n%s' % parent.lineTypeScale
        if parent.thickness is not None:
            result += '\n39\n%s' % parent.thickness
        return result


class _Entities:
    """Base class to deal with composed objects."""

    def __dxf__(self):
        return []

    def __str__(self):
        return '\n'.join([str(x) for x in self.__dxf__()])


class _Collection(_Call):
    """Base class to expose entities methods to main object."""

    def __init__(self, entities=[]):
        self.entities = copy.copy(entities)
        # link entities methods to drawing
        for attr in dir(self.entities):
            if attr[0] != '_':
                attrObject = getattr(self.entities, attr)
                if callable(attrObject):
                    setattr(self, attr, attrObject)


# 2) Constants
# ---color values
BYBLOCK = 0
BYLAYER = 256

# ---block-type flags (bit coded values, may be combined):
ANONYMOUS = 1  # This is an anonymous block generated by hatching, associative dimensioning, other internal operations, or an application
# This block has non-constant attribute definitions (this bit is not set
# if the block has any attribute definitions that are constant, or has no
# attribute definitions at all)
NON_CONSTANT_ATTRIBUTES = 2
XREF = 4  # This block is an external reference (xref)
XREF_OVERLAY = 8  # This block is an xref overlay
EXTERNAL = 16  # This block is externally dependent
# This is a resolved external reference, or dependent of an external
# reference (ignored on input)
RESOLVED = 32
# This definition is a referenced external reference (ignored on input)
REFERENCED = 64

# ---mtext flags
# attachment point
TOP_LEFT = 1
TOP_CENTER = 2
TOP_RIGHT = 3
MIDDLE_LEFT = 4
MIDDLE_CENTER = 5
MIDDLE_RIGHT = 6
BOTTOM_LEFT = 7
BOTTOM_CENTER = 8
BOTTOM_RIGHT = 9
# drawing direction
LEFT_RIGHT = 1
TOP_BOTTOM = 3
BY_STYLE = 5  # the flow direction is inherited from the associated text style
# line spacing style (optional):
AT_LEAST = 1  # taller characters will override
EXACT = 2  # taller characters will not override

# ---polyline flags
# This is a closed polyline (or a polygon mesh closed in the M direction)
CLOSED = 1
CURVE_FIT = 2      # Curve-fit vertices have been added
SPLINE_FIT = 4      # Spline-fit vertices have been added
POLYLINE_3D = 8      # This is a 3D polyline
POLYGON_MESH = 16     # This is a 3D polygon mesh
CLOSED_N = 32     # The polygon mesh is closed in the N direction
POLYFACE_MESH = 64     # The polyline is a polyface mesh
# The linetype pattern is generated continuously around the vertices of
# this polyline
CONTINOUS_LINETYPE_PATTERN = 128

# ---text flags
# horizontal
LEFT = 0
CENTER = 1
RIGHT = 2
ALIGNED = 3  # if vertical alignment = 0
MIDDLE = 4  # if vertical alignment = 0
FIT = 5  # if vertical alignment = 0
# vertical
BASELINE = 0
BOTTOM = 1
MIDDLE = 2
TOP = 3

# 3) Classes
# ---entitities


class Arc(_Entity):
    """Arc, angles in degrees."""

    def __init__(self, center=(0, 0, 0), radius=1,
                 startAngle=0.0, endAngle=90, **common):
        """Angles in degrees."""
        _Entity.__init__(self, **common)
        self.center = center
        self.radius = radius
        self.startAngle = startAngle
        self.endAngle = endAngle

    def __str__(self):
        return '0\nARC\n%s\n%s\n40\n%s\n50\n%s\n51\n%s' %\
               (self._common(), _point(self.center),
                self.radius, self.startAngle, self.endAngle)


class Circle(_Entity):
    """Circle"""

    def __init__(self, center=(0, 0, 0), radius=1, **common):
        _Entity.__init__(self, **common)
        self.center = center
        self.radius = radius

    def __str__(self):
        return '0\nCIRCLE\n%s\n%s\n40\n%s' %\
               (self._common(), _point(self.center), self.radius)


class Face(_Entity):
    """3dface"""

    def __init__(self, points, **common):
        _Entity.__init__(self, **common)
        self.points = points

    def __str__(self):
        return '\n'.join(['0\n3DFACE', self._common()] +
                         _points(self.points)
                         )


class Insert(_Entity):
    """Block instance."""

    def __init__(self, name, point=(0, 0, 0),
                 xscale=None, yscale=None, zscale=None,
                 cols=None, colspacing=None, rows=None, rowspacing=None,
                 rotation=None,
                 **common):
        _Entity.__init__(self, **common)
        self.name = name
        self.point = point
        self.xscale = xscale
        self.yscale = yscale
        self.zscale = zscale
        self.cols = cols
        self.colspacing = colspacing
        self.rows = rows
        self.rowspacing = rowspacing
        self.rotation = rotation

    def __str__(self):
        result = '0\nINSERT\n2\n%s\n%s\n%s' %\
            (self.name, self._common(), _point(self.point))
        if self.xscale is not None:
            result += '\n41\n%s' % self.xscale
        if self.yscale is not None:
            result += '\n42\n%s' % self.yscale
        if self.zscale is not None:
            result += '\n43\n%s' % self.zscale
        if self.rotation:
            result += '\n50\n%s' % self.rotation
        if self.cols is not None:
            result += '\n70\n%s' % self.cols
        if self.colspacing is not None:
            result += '\n44\n%s' % self.colspacing
        if self.rows is not None:
            result += '\n71\n%s' % self.rows
        if self.rowspacing is not None:
            result += '\n45\n%s' % self.rowspacing
        return result


class Line(_Entity):
    """Line"""

    def __init__(self, points, **common):
        _Entity.__init__(self, **common)
        self.points = points

    def __str__(self):
        return '\n'.join(['0\nLINE', self._common()] +
                         _points(self.points))


class LwPolyLine(_Entity):
    """This is a LWPOLYLINE. I have no idea how it differs from a normal PolyLine"""

    def __init__(self, points, flag=0, width=None, **common):
        _Entity.__init__(self, **common)
        self.points = points
        self.flag = flag
        self.width = width

    def __str__(self):
        result = '0\nLWPOLYLINE\n%s\n70\n%s' %\
            (self._common(), self.flag)
        result += '\n90\n%s' % len(self.points)
        for point in self.points:
            result += '\n%s' % _point(point)
        if self.width:
            result += '\n40\n%s\n41\n%s' % (self.width, self.width)
        return result


class PolyPad(_Entity):
    # TODO: Finish polyline (now implemented as a series of lines)
    def __init__(self, points, layer='0', flag=0, width=None, **common):
        _Entity.__init__(self, **common)
        self.points = points
        self.flag = flag
        self.width = width
        self.layer = layer

    def __str__(self):
        result = '0\nPOLYLINE\n%s\n66\n%s\n70\n%s\n40\n%s\n41\n%s' %\
            (self._common(), self.flag, self.flag, self.width, self.width)
        for point in self.points:
            result += '\n0\nVERTEX\n8\n%s\n%s' % (self.layer, _point(point))
            if self.width:
                result += '\n42\n1.0'
        result += '\n0\nSEQEND'
        return result


class PolyLine(_Entity):
    # TODO: Finish polyline (now implemented as a series of lines)
    def __init__(self, points, layer='0', flag=0, width=None, **common):
        _Entity.__init__(self, **common)
        self.points = points
        self.flag = flag
        self.width = width
        self.layer = layer

    def __str__(self):
        result = '0\nPOLYLINE\n%s\n66\n%s\n70\n%s' %\
            (self._common(), self.flag, self.flag)
        for point in self.points:
            result += '\n0\nVERTEX\n8\n%s\n%s' % (self.layer, _point(point))
            if self.width:
                result += '\n40\n%s\n41\n%s' % (self.width, self.width)
        result += '\n0\nSEQEND'
        return result


class Point(_Entity):
    """Colored solid fill."""

    def __init__(self, points=None, **common):
        _Entity.__init__(self, **common)
        self.points = points


class SinglePoint(_Entity):
    """Colored solid fill."""

    def __init__(self, points, layer='0', **common):
        _Entity.__init__(self, **common)
        self.points = points
        self.layer = layer

    def __str__(self):
        result = ''
        for point in [self.points]:
            result += '0\nPOINT\n8\n%s\n%s' % (self.layer, _point(point))
        return result


class Solid(_Entity):
    """Colored solid fill."""

    def __init__(self, points=None, **common):
        _Entity.__init__(self, **common)
        self.points = points

    def __str__(self):
        return '\n'.join(['0\nSOLID', self._common()] +
                         _points(self.points[:2] +
                                 [self.points[3], self.points[2]]))


class Text(_Entity):
    """Single text line."""

    def __init__(
            self,
            text='',
            point=(
                0,
                0,
                0),
            alignment=None,
            flag=None,
            height=1,
            justifyhor=None,
            justifyver=None,
            rotation=None,
            obliqueAngle=None,
            style=None,
            xscale=None,
            **common):
        _Entity.__init__(self, **common)
        self.text = text
        self.point = point
        self.alignment = alignment
        self.flag = flag
        self.height = height
        self.justifyhor = justifyhor
        self.justifyver = justifyver
        self.rotation = rotation
        self.obliqueAngle = obliqueAngle
        self.style = style
        self.xscale = xscale

    def __str__(self):
        result = '0\nTEXT\n%s\n%s\n40\n%s\n1\n%s' %\
            (self._common(), _point(self.point), self.height, self.text)
        if self.rotation:
            result += '\n50\n%s' % self.rotation
        if self.xscale:
            result += '\n41\n%s' % self.xscale
        if self.obliqueAngle:
            result += '\n51\n%s' % self.obliqueAngle
        if self.style:
            result += '\n7\n%s' % self.style
        if self.flag:
            result += '\n71\n%s' % self.flag
        if self.justifyhor:
            result += '\n72\n%s' % self.justifyhor
        if self.alignment:
            result += '\n%s' % _point(self.alignment, 1)
        if self.justifyver:
            result += '\n73\n%s' % self.justifyver
        return result


class Mtext(Text):
    """Surrogate for mtext, generates some Text instances."""

    def __init__(
            self,
            text='',
            point=(
                0,
                0,
                0),
            width=250,
            spacingFactor=1.5,
            down=0,
            spacingWidth=None,
            **options):
        Text.__init__(self, text=text, point=point, **options)
        if down:
            spacingFactor *= -1
        self.spacingFactor = spacingFactor
        self.spacingWidth = spacingWidth
        self.width = width
        self.down = down

    def __str__(self):
        texts = self.text.replace('\r\n', '\n').split('\n')
        if not self.down:
            texts.reverse()
        result = ''
        x = y = 0
        if self.spacingWidth:
            spacingWidth = self.spacingWidth
        else:
            spacingWidth = self.height * self.spacingFactor
        for text in texts:
            while text:
                result += '\n%s' % Text(text[:self.width],
                                        point=(self.point[0] + x * spacingWidth,
                                               self.point[1] + y * spacingWidth,
                                               self.point[2]),
                                        alignment=self.alignment,
                                        flag=self.flag,
                                        height=self.height,
                                        justifyhor=self.justifyhor,
                                        justifyver=self.justifyver,
                                        rotation=self.rotation,
                                        obliqueAngle=self.obliqueAngle,
                                        style=self.style,
                                        xscale=self.xscale,
                                        parent=self)
                text = text[self.width:]
                if self.rotation:
                    x += 1
                else:
                    y += 1
        return result[1:]

# class _Mtext(_Entity):
##    """Mtext not functioning for minimal dxf."""
# def __init__(self,text='',point=(0,0,0),attachment=1,
# charWidth=None,charHeight=1,direction=1,height=100,rotation=0,
# spacingStyle=None,spacingFactor=None,style=None,width=100,
# xdirection=None,**common):
# _Entity.__init__(self,**common)
# self.text=text
# self.point=point
# self.attachment=attachment
# self.charWidth=charWidth
# self.charHeight=charHeight
# self.direction=direction
# self.height=height
# self.rotation=rotation
# self.spacingStyle=spacingStyle
# self.spacingFactor=spacingFactor
# self.style=style
# self.width=width
# self.xdirection=xdirection
# def __str__(self):
# input=self.text
# text=''
# while len(input)>250:
# text+='\n3\n%s'%input[:250]
# input=input[250:]
# text+='\n1\n%s'%input
# result= '0\nMTEXT\n%s\n%s\n40\n%s\n41\n%s\n71\n%s\n72\n%s%s\n43\n%s\n50\n%s'%\
# (self._common(),_point(self.point),self.charHeight,self.width,
# self.attachment,self.direction,text,
# self.height,
# self.rotation)
##        if self.style:result+='\n7\n%s'%self.style
##        if self.xdirection:result+='\n%s'%_point(self.xdirection,1)
##        if self.charWidth:result+='\n42\n%s'%self.charWidth
##        if self.spacingStyle:result+='\n73\n%s'%self.spacingStyle
##        if self.spacingFactor:result+='\n44\n%s'%self.spacingFactor
# return result

# ---tables


class Block(_Collection):
    """Use list methods to add entities, eg append."""

    def __init__(self, name, layer='0', flag=0, base=(0, 0, 0), entities=[]):
        self.entities = copy.copy(entities)
        _Collection.__init__(self, entities)
        self.layer = layer
        self.name = name
        self.flag = 0
        self.base = base

    def __str__(self):
        e = '\n'.join([str(x)for x in self.entities])
        return '0\nBLOCK\n8\n%s\n2\n%s\n70\n%s\n%s\n3\n%s\n%s\n0\nENDBLK' % (
            self.layer, self.name, self.flag, _point(self.base), self.name, e)


class Layer(_Call):
    """Layer"""

    def __init__(self, name='0', color=255, lineType='continuous', flag=0):
        self.name = name
        self.color = color
        self.lineType = lineType
        self.flag = flag

    def __str__(self):
        return '0\nLAYER\n2\n%s\n70\n%s\n62\n%s\n6\n%s' %\
               (self.name, self.flag, self.color, self.lineType)


class LineType(_Call):
    """Custom linetype"""

    def __init__(
            self,
            name='continuous',
            description='Solid line',
            elements=[],
            flag=64):
        # TODO: Implement lineType elements
        self.name = name
        self.description = description
        self.elements = copy.copy(elements)
        self.flag = flag

    def __str__(self):
        return '0\nLTYPE\n2\n%s\n70\n%s\n3\n%s\n72\n65\n73\n%s\n40\n0.0' % (
            self.name.upper(), self.flag, self.description, len(self.elements))


class Style(_Call):
    """Text style"""

    def __init__(
            self,
            name='standard',
            flag=0,
            height=0,
            widthFactor=1,
            obliqueAngle=0,
            mirror=0,
            lastHeight=1,
            font='arial.ttf',
            bigFont=''):
        self.name = name
        self.flag = flag
        self.height = height
        self.widthFactor = widthFactor
        self.obliqueAngle = obliqueAngle
        self.mirror = mirror
        self.lastHeight = lastHeight
        self.font = font
        self.bigFont = bigFont

    def __str__(self):
        return '0\nSTYLE\n2\n%s\n70\n%s\n40\n%s\n41\n%s\n50\n%s\n71\n%s\n42\n%s\n3\n%s\n4\n%s' %\
               (self.name.upper(), self.flag, self.flag, self.widthFactor,
                self.obliqueAngle, self.mirror, self.lastHeight,
                self.font.upper(), self.bigFont.upper())


class View(_Call):
    def __init__(self, name, flag=0, width=1, height=1, center=(0.5, 0.5),
                 direction=(0, 0, 1), target=(0, 0, 0), lens=50,
                 frontClipping=0, backClipping=0, twist=0, mode=0):
        self.name = name
        self.flag = flag
        self.width = width
        self.height = height
        self.center = center
        self.direction = direction
        self.target = target
        self.lens = lens
        self.frontClipping = frontClipping
        self.backClipping = backClipping
        self.twist = twist
        self.mode = mode

    def __str__(self):
        return '0\nVIEW\n2\n%s\n70\n%s\n40\n%s\n%s\n41\n%s\n%s\n%s\n42\n%s\n43\n%s\n44\n%s\n50\n%s\n71\n%s' %\
               (self.name, self.flag, self.height, _point(self.center), self.width,
                _point(self.direction, 1), _point(self.target, 2), self.lens,
                self.frontClipping, self.backClipping, self.twist, self.mode)


def ViewByWindow(name, leftBottom=(0, 0), rightTop=(1, 1), **options):
    width = abs(rightTop[0] - leftBottom[0])
    height = abs(rightTop[1] - leftBottom[1])
    center = ((rightTop[0] + leftBottom[0]) * 0.5,
              (rightTop[1] + leftBottom[1]) * 0.5)
    return View(
        name=name,
        width=width,
        height=height,
        center=center,
        **options)

# ---drawing


class Drawing(_Collection):
    """Dxf drawing. Use append or any other list methods to add objects."""

    def __init__(self, insbase=(0.0, 0.0, 0.0), extmin=(0.0, 0.0), extmax=(0.0, 0.0),
                 layers=[Layer()], linetypes=[LineType()], styles=[Style()], blocks=[],
                 views=[], entities=None, fileName='test.dxf'):
        # TODO: replace list with None,arial
        if not entities:
            entities = []
        _Collection.__init__(self, entities)
        self.insbase = insbase
        self.extmin = extmin
        self.extmax = extmax
        self.layers = copy.copy(layers)
        self.linetypes = copy.copy(linetypes)
        self.styles = copy.copy(styles)
        self.views = copy.copy(views)
        self.blocks = copy.copy(blocks)
        self.fileName = fileName
        # private
        self.acadver = '9\n$ACADVER\n1\nAC1006'

    def _name(self, x):
        """Helper function for self._point"""
        return '9\n$%s' % x.upper()

    def _point(self, name, x):
        """Point setting from drawing like extmin,extmax,..."""
        return '%s\n%s' % (self._name(name), _point(x))

    def _section(self, name, x):
        """Sections like tables,blocks,entities,..."""
        if x:
            xstr = '\n' + '\n'.join(x)
        else:
            xstr = ''
        return '0\nSECTION\n2\n%s%s\n0\nENDSEC' % (name.upper(), xstr)

    def _table(self, name, x):
        """Tables like ltype,layer,style,..."""
        if x:
            xstr = '\n' + '\n'.join(x)
        else:
            xstr = ''
        return '0\nTABLE\n2\n%s\n70\n%s%s\n0\nENDTAB' % (
            name.upper(), len(x), xstr)

    def __str__(self):
        """Returns drawing as dxf string."""
        header = [self.acadver] + \
            [self._point(attr, getattr(self, attr)) for attr in _HEADER_POINTS]
        header = self._section('header', header)

        tables = [self._table('ltype', [str(x) for x in self.linetypes]),
                  self._table('layer', [str(x) for x in self.layers]),
                  self._table('style', [str(x) for x in self.styles]),
                  self._table('view', [str(x) for x in self.views]),
                  ]
        tables = self._section('tables', tables)

        blocks = self._section('blocks', [str(x) for x in self.blocks])

        entities = self._section('entities', [str(x) for x in self.entities])

        all = '\n'.join([header, tables, blocks, entities, '0\nEOF\n'])
        return all

    def saveas(self, fileName):
        self.fileName = fileName
        self.save()

    def _update_extents(self):
        """按全部实体计算图形范围并写入 $EXTMIN / $EXTMAX。

        缺少有效范围时 CAD 打开不会自动缩放（需 Z+A）；
        写入范围后打开即可显示全部图案。
        """
        xs = []
        ys = []

        def add(x, y):
            try:
                xs.append(float(x))
                ys.append(float(y))
            except (TypeError, ValueError):
                pass

        def add_pts(pts):
            if not pts:
                return
            if isinstance(pts[0], (list, tuple)):
                for p in pts:
                    if p is not None and len(p) >= 2:
                        add(p[0], p[1])
            elif len(pts) >= 2:
                add(pts[0], pts[1])

        def scan_entity(entity):
            pts = getattr(entity, 'points', None)
            if pts:
                add_pts(pts)
                return
            center = getattr(entity, 'center', None)
            if center is not None:
                radius = float(getattr(entity, 'radius', 0) or 0)
                add(center[0] - radius, center[1] - radius)
                add(center[0] + radius, center[1] + radius)
                return
            point = getattr(entity, 'point', None)
            if point is not None and len(point) >= 2:
                add(point[0], point[1])
                height = float(getattr(entity, 'height', 0) or 0)
                if height > 0:
                    add(point[0], point[1] + height)
                    text = str(getattr(entity, 'text', '') or '')
                    rotation = float(getattr(entity, 'rotation', 0) or 0)
                    approx_width = height * len(text) * 0.55
                    if rotation % 180 == 90:
                        add(point[0], point[1] + approx_width)
                    else:
                        add(point[0] + approx_width, point[1] + height)
                return

        for entity in self.entities:
            scan_entity(entity)
        # 块内实体也要纳入范围（LDI 的单行块图案等）
        for block in self.blocks:
            for entity in getattr(block, 'entities', []) or []:
                scan_entity(entity)
        if xs and ys:
            span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
            pad = span * 0.02
            self.extmin = (min(xs) - pad, min(ys) - pad)
            self.extmax = (max(xs) + pad, max(ys) + pad)

    def save(self):
        self._update_extents()
        test = open(self.fileName, 'w')
        test.write(str(self))
        test.close()


# ---extras
class Rectangle(_Entity):
    """Rectangle, creates lines."""

    def __init__(
            self,
            point=(
                0,
                0,
                0),
            width=1,
            height=1,
            solid=None,
            line=1,
            **common):
        _Entity.__init__(self, **common)
        self.point = point
        self.width = width
        self.height = height
        self.solid = solid
        self.line = line

    def __str__(self):
        result = ''
        points = [
            self.point,
            (self.point[0] +
             self.width,
             self.point[1],
             self.point[2]),
            (self.point[0] +
             self.width,
             self.point[1] +
             self.height,
             self.point[2]),
            (self.point[0],
             self.point[1] +
             self.height,
             self.point[2]),
            self.point]
        if self.solid:
            result += '\n%s' % Solid(points=points[:-1], parent=self.solid)
        if self.line:
            for i in range(4):
                result += '\n%s' %\
                    Line(points=[points[i], points[i + 1]], parent=self)
        return result[1:]


class LineList(_Entity):
    """Like polyline, but built of individual lines."""

    def __init__(self, points=[], closed=0, **common):
        _Entity.__init__(self, **common)
        self.closed = closed
        self.points = copy.copy(points)

    def __str__(self):
        if self.closed:
            points = self.points + [self.points[0]]
        else:
            points = self.points
        result = ''
        for i in range(len(points) - 1):
            result += '\n%s' %\
                Line(points=[points[i], points[i + 1]], parent=self)
        return result[1:]


# ---test


def _shengxiong_mode1(drawing, hole_items, holelayer):
    """模式1：每孔画 holelayer 圆（半径=原图孔径×1.1/3）与 PET 圆（0.005）。

    孔径取孔在原图中的实际孔径（即 原图孔径×1.1×2/3 的直径）；
    缺少原图孔径时退回按该孔当前孔径计算。
    """
    for item in hole_items:
        center = [item[0], item[1]]
        design_diam = item[3] if len(item) > 3 else item[2]
        drawing.append(
            Circle(
                center=center,
                radius=design_diam * 1.1 / 3,
                layer=holelayer))
        drawing.append(
            Circle(
                center=center,
                radius=0.005,
                layer='PET'))


def _shengxiong_mode2(drawing, hole_items, holelayer):
    """模式2：分档逻辑按每个孔自身孔径处理。"""
    for item in hole_items:
        centerpos = [item[0], item[1]]
        diam = item[2]
        if diam <= 0.0425:
            drawing.append(
                SinglePoint(
                    points=centerpos,
                    layer=holelayer))
        elif diam <= 0.0595:
            drawing.append(
                Circle(
                    center=centerpos,
                    radius=0.0175,
                    layer=holelayer))
            drawing.append(
                SinglePoint(
                    points=centerpos,
                    layer='PET'))
        elif diam <= 0.0765:
            drawing.append(
                Circle(
                    center=centerpos,
                    radius=0.0275,
                    layer=holelayer))
            drawing.append(
                SinglePoint(
                    points=centerpos,
                    layer='PET'))
        elif diam <= 0.0935:
            drawing.append(
                Circle(
                    center=centerpos,
                    radius=0.0375,
                    layer=holelayer))
            drawing.append(
                SinglePoint(
                    points=centerpos,
                    layer='PET'))
        elif diam <= 0.102:
            drawing.append(
                Circle(
                    center=centerpos,
                    radius=0.0475,
                    layer=holelayer))
            drawing.append(
                SinglePoint(
                    points=centerpos,
                    layer='PET'))
        elif diam <= 0.119:
            drawing.append(
                Circle(
                    center=centerpos,
                    radius=0.055,
                    layer=holelayer))
            drawing.append(
                SinglePoint(
                    points=centerpos,
                    layer='PET'))
        elif diam <= 0.1445:
            drawing.append(
                Circle(
                    center=centerpos,
                    radius=0.065,
                    layer=holelayer))
            drawing.append(
                SinglePoint(
                    points=centerpos,
                    layer='PET'))
        else:
            drawing.append(
                Circle(
                    center=centerpos,
                    radius=diam / 1.7 - 0.01,
                    layer=holelayer))
            drawing.append(
                SinglePoint(
                    points=centerpos,
                    layer='PET'))


def generate_shengxiong_film(block, holelayer, centerposlist, output_dir=None):
    """生成并保存单个通孔层的盛雄开孔 DXF 文件（按 SHENGXIONG_MODE）。"""
    drawing = Drawing()
    drawing.blocks.append(block)
    if SHENGXIONG_MODE == 1:
        _shengxiong_mode1(drawing, centerposlist, holelayer)
    else:
        _shengxiong_mode2(drawing, centerposlist, holelayer)
    for ring in buildringholelist():
        drawing.append(
            Circle(
                center=ring,
                radius=globalconfig.RING_HOLE_DIAMETER / 2,
                layer=POSITION_RING_MODE))
    filename = (
        globalconfig.NAME_OF_FEILIN +
        '-' +
        holelayer +
        '.dxf')
    if output_dir:
        filename = os.path.join(output_dir, filename)
    drawing.saveas(filename)


def build_ldi_frame():
    """Build the 200x200 square frame centered on the LDI origin."""
    half = 100.0
    return [
        [-half, half, 0],
        [half, half, 0],
        [half, -half, 0],
        [-half, -half, 0],
    ]


def _ldi_center():
    """LDI 坐标原点对应的整版排列外框中心（原始坐标）。"""
    return (globalconfig.CUTLINE_X_OFFSET + globalconfig.RING_DISTANCE / 2,
            globalconfig.CUTLINE_Y_OFFSET + globalconfig.RING_DISTANCE / 2)


def _ldi_shift_point(point):
    """把原始坐标平移到“整版外框中心 = (0,0)”的 LDI 坐标系。"""
    cx, cy = _ldi_center()
    return [point[0] - cx, point[1] - cy]


def _ldi_shift_polyline(polyline):
    return [_ldi_shift_point(point) for point in polyline]


def _ldi_new_drawing(block):
    """Create an LDI Drawing with the shared cutline-endpoint block."""
    drawing = Drawing()
    drawing.blocks.append(block)
    drawing.styles.append(Style())
    drawing.views.append(View('Normal'))
    return drawing


def _ldi_row_step():
    """Y offset between adjacent arrayed rows."""
    return globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO


def _ldi_block_rows(block_y_count):
    """Additional row copies needed to fill this block's Y span."""
    return max(0, globalconfig.eachblock_y_list[block_y_count] - 1)


def _array_full_centers(centers, block_y_count):
    """Return centers plus upward row copies to fill the block's Y span."""
    step = _ldi_row_step()
    rows = _ldi_block_rows(block_y_count)
    full = list(centers)
    for row in range(1, rows + 1):
        offset = step * row
        full.extend(
            [[center[0], center[1] + offset] for center in centers])
    return full


def _array_full_items(items, block_y_count):
    """Return [(x, y, 孔径[, 原图孔径])] plus upward row copies."""
    step = _ldi_row_step()
    rows = _ldi_block_rows(block_y_count)
    full = list(items)
    for row in range(1, rows + 1):
        offset = step * row
        full.extend([[item[0], item[1] + offset] + list(item[2:])
                     for item in items])
    return full


def _ldi_row_block_name(drawing, layer, blockcount):
    """生成 LDI 单行块的占位名（同名冲突自动加序号）。"""
    def clean(text):
        return re.sub(r'[^0-9A-Za-z_\-\u4e00-\u9fff]+', '_', text)
    base = 'LDI_%s_%s_B%d' % (
        clean(globalconfig.NAME_OF_FEILIN), clean(layer), blockcount + 1)
    existing = {getattr(b, 'name', '') for b in drawing.blocks}
    name = base
    suffix = 1
    while name in existing:
        suffix += 1
        name = '%s_%d' % (base, suffix)
    return name


def _ldi_add_row_block(drawing, layer, row_entities, block_y_count,
                       blockcount):
    """把一个“单行”定义成块，并按行阵列插入该块。"""
    if not row_entities:
        return
    name = _ldi_row_block_name(drawing, layer, blockcount)
    drawing.blocks.append(
        Block(name=name, layer=layer, base=(0, 0, 0),
              entities=list(row_entities)))
    rows = max(1, globalconfig.eachblock_y_list[block_y_count])
    step = _ldi_row_step()
    for row in range(rows):
        drawing.append(
            Insert(layer=layer, name=name, point=(0, step * row, 0)))


def _append_ldi_pattern(drawing, layer, polylines, block_y_count,
                        blockcount):
    """把该层单行图案定义成块并按行阵列插入。"""
    entities = [
        PolyLine(points=_ldi_shift_polyline(polyline), layer=layer, flag=1)
        for polyline in polylines]
    _ldi_add_row_block(
        drawing, layer, entities, block_y_count, blockcount)


def _append_ldi_pads(drawing, layer, centers, block_y_count, blockcount):
    """把该层单行点网圆定义成块并按行阵列插入。"""
    radius = _pad_layer_diameter(layer) / 2
    entities = [
        Circle(center=_ldi_shift_point(list(center)),
               radius=radius, layer=layer)
        for center in centers]
    _ldi_add_row_block(
        drawing, layer, entities, block_y_count, blockcount)


def _finalize_ldi_layer(drawing, layer, ldi_dir):
    """Add rings/cutlines/crosses/NAME text/frame and save one LDI layer file."""
    for ring in buildringlist():
        drawing.append(
            PolyPad(
                points=_ldi_shift_polyline(ring),
                layer=layer,
                flag=1,
                width=globalconfig.RING_WIDTH))
    # 纯点网（P 开头）不需要切割线与十字架
    if not _is_pure_pointnet(layer):
        for cutline in buildcutlineset():
            drawing.append(
                PolyLine(
                    points=_ldi_shift_polyline(cutline),
                    layer=layer,
                    flag=1,
                    width=globalconfig.CUTLINE_WIDTH))
        for flash in buildflashlist():
            drawing.append(
                Insert(
                    layer=layer,
                    name='cutlineendpoint',
                    point=_ldi_shift_point(flash)))
    if layer.capitalize()[0] == 'P' or layer.capitalize()[0] == 'H':
        title_height_offset = 5.5
    else:
        title_height_offset = 8.5
    drawing.append(
        Text(
            layer=layer,
            text=globalconfig.NAME_OF_FEILIN + '-' + layer,
            point=_ldi_shift_point((
                globalconfig.RING_DISTANCE / 2 -
                len(globalconfig.NAME_OF_FEILIN) * 1.5 / 2 +
                globalconfig.CUTLINE_X_OFFSET,
                title_height_offset +
                globalconfig.RING_DISTANCE +
                globalconfig.CUTLINE_Y_OFFSET)),
            height=1.5))
    drawing.append(
        PolyLine(
            points=build_ldi_frame(),
            layer=layer,
            flag=1,
            width=1))
    drawing.layers.append(Layer(name='0', color=7))
    drawing.layers.append(Layer(name=layer, color=7))
    drawing.saveas(
        os.path.join(
            ldi_dir,
            globalconfig.NAME_OF_FEILIN + '-' + layer + '.dxf'))


def _load_design_rules(config_path):
    """读取 [设计规则] 段：默认值与按图层覆盖，空/“-”沿用默认值。"""
    parser = configparser.ConfigParser()
    with open(config_path, 'r', encoding='utf-8-sig') as f:
        parser.read_file(f)
    rules = {
        'enabled': True,
        'spacing': DEFAULT_MIN_SPACING,
        'clearance': DEFAULT_MIN_CLEARANCE,
        'layers': {},
    }
    if not parser.has_section(DESIGN_RULE_SECTION):
        return rules
    rules['enabled'] = parser.getboolean(
        DESIGN_RULE_SECTION, '是否启用', fallback=True)
    rules['spacing'] = parser.getfloat(
        DESIGN_RULE_SECTION, '默认最小间距', fallback=DEFAULT_MIN_SPACING)
    rules['clearance'] = parser.getfloat(
        DESIGN_RULE_SECTION, '默认最小留边量', fallback=DEFAULT_MIN_CLEARANCE)
    text = parser.get(DESIGN_RULE_SECTION, '图层规则', fallback='') or ''
    for group in text.split(';'):
        group = group.strip()
        if not group:
            continue
        parts = [p.strip() for p in group.split('|')]
        name = parts[0]
        if not name:
            continue
        spacing = None
        clearance = None
        if len(parts) > 1 and parts[1] not in ('', '-'):
            spacing = float(parts[1])
        if len(parts) > 2 and parts[2] not in ('', '-'):
            clearance = float(parts[2])
        rules['layers'][name] = (spacing, clearance)
    return rules


def _design_rule_for(layer, rules):
    spacing, clearance = rules['layers'].get(
        layer, (None, None))
    return (rules['spacing'] if spacing is None else spacing,
            rules['clearance'] if clearance is None else clearance)


def _pattern_shapes(polylines):
    """把图层多段线转换为 shapely 几何（闭合→面，未闭合→线）。"""
    def clean(polyline):
        pts = []
        for pos in polyline:
            pt = (float(pos[0]), float(pos[1]))
            if not pts or pt != pts[-1]:
                pts.append(pt)
        return pts

    shapes = []
    for polyline in polylines:
        pts = clean(polyline)
        if len(pts) < 2:
            continue
        closed = len(pts) >= 4 and math.hypot(
            pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) <= 1e-6
        if closed:
            polygon = Polygon(pts)
            if not polygon.is_valid:
                polygon = make_valid(polygon)
            if polygon.is_empty or polygon.area <= 1e-12:
                continue
            shapes.append(polygon)
        else:
            shapes.append(LineString(pts))
    return shapes


def _build_pattern_groups(polylines):
    """合并嵌套轮廓：被包含的轮廓视为同一图案的内部孔/内环。"""
    shapes = _pattern_shapes(polylines)
    polygons = []
    others = []
    for shape in shapes:
        if shape.geom_type in ('Polygon', 'MultiPolygon') and shape.area > 0:
            polygons.append(shape)
        else:
            others.append(shape)
    order = sorted(range(len(polygons)), key=lambda i: -polygons[i].area)
    assigned = [False] * len(polygons)
    groups = []
    for i in order:
        if assigned[i]:
            continue
        assigned[i] = True
        members = [polygons[i]]
        for j in order:
            if assigned[j]:
                continue
            if polygons[i].covers(polygons[j]):
                assigned[j] = True
                members.append(polygons[j])
        groups.append(unary_union(members))
    groups.extend(others)
    return groups


def _min_spacing(groups):
    """同层不同图案组之间的最小边到边距离与最近点对。"""
    if len(groups) < 2:
        return None, None
    tree = STRtree(groups)
    best = None
    best_pair = None
    for index, geometry in enumerate(groups):
        result = tree.query_nearest(
            geometry, return_distance=True, exclusive=True,
            all_matches=False)
        if result is None:
            continue
        indices, distances = result
        if len(indices) == 0:
            continue
        distance = float(distances[0])
        if best is None or distance < best:
            best = distance
            best_pair = (index, int(indices[0]))
    if best_pair is None:
        return None, None
    point_a, point_b = nearest_points(
        groups[best_pair[0]], groups[best_pair[1]])
    return best, ((point_a.x, point_a.y), (point_b.x, point_b.y))


def _min_clearance(groups, frame):
    """图案组到设计外框内边的最小距离（无外框返回 None）。"""
    if not groups or not frame or len(frame) < 4:
        return None, None
    frame_pts = [(float(p[0]), float(p[1])) for p in frame]
    frame_poly = Polygon(frame_pts)
    if not frame_poly.is_valid:
        frame_poly = make_valid(frame_poly)
    if frame_poly.is_empty:
        return None, None
    boundary = frame_poly.boundary
    best = None
    best_point = None
    for geometry in groups:
        distance = geometry.distance(boundary)
        if best is None or distance < best:
            best = distance
            point_a, _point_b = nearest_points(geometry, boundary)
            best_point = (point_a.x, point_a.y)
    return best, best_point


def check_design_rules(workdir=None, config_path=None, report_path=None):
    """检查各图案层的最小间距与最小留边是否满足 [设计规则]。

    返回报告文件路径；缺少 shapely 或输入目录时返回 None。
    """
    if shapely is None:
        print('设计规则检查需要 shapely 库，请先安装：pip install shapely')
        return None
    global globalconfig
    if workdir is None:
        workdir = _app_dir()
    workdir = os.path.abspath(workdir)
    if config_path is None:
        config_path = os.path.join(workdir, 'config.ini')
    globalconfig = Globalconfig(config_path)
    rules = _load_design_rules(config_path)
    dirdict = buildfilelist(workdir)
    if not dirdict:
        print('工作目录中没有数字文件夹，无法检查设计规则。')
        return None
    sources, source_error = load_pattern_sources(workdir, dirdict)
    if source_error:
        print(source_error)
        return None
    if report_path is None:
        report_path = os.path.join(workdir, '设计规则检查报告.txt')

    lines = [
        '设计规则检查报告',
        '检查时间: ' + time.strftime(
            '%Y-%m-%d %H:%M:%S', time.localtime(time.time())),
        '工作目录: ' + workdir,
        '默认规则: 最小间距 %.4fmm，最小留边量 %.4fmm' % (
            rules['spacing'], rules['clearance']),
        '',
    ]
    if not rules['enabled']:
        lines.append('（设计规则检查未启用）')
    checked = 0
    for blockcount, blockname in enumerate(sorted(dirdict)):
        lines.append('[区块%s]' % blockname)
        feature = Feilin_dxfpolyline(len(dirdict))
        source = sources.get(blockname)
        if source is not None:
            # 编辑用总图来源：直接取已按外框中心归零的分层数据
            layer_items = [
                (layer, polylines,
                 (source.get('frames') or {}).get(layer))
                for layer, polylines in sorted(
                    source.get('layers', {}).items())
                if layer[:1].upper() not in ('V', 'H', 'P')]
        else:
            layer_items = []
            for path in sorted(dirdict[blockname]):
                layer = os.path.splitext(os.path.basename(path))[0]
                if layer[:1].upper() in ('V', 'H', 'P'):
                    continue
                with open(path, 'r') as f:
                    dataset, circles = feature._parse_dxf_entities(f)
                frame = feature._strip_layer_frame(dataset, circles)
                feature._center_layer_on_frame(dataset, circles, frame)
                layer_items.append((layer, dataset, frame))
        for layer, dataset, frame in layer_items:
            groups = _build_pattern_groups(dataset)
            spacing, spacing_points = _min_spacing(groups)
            clearance, clearance_point = _min_clearance(groups, frame)
            rule_spacing, rule_clearance = _design_rule_for(layer, rules)
            checked += 1

            def verdict(value, rule):
                if value is None:
                    return '未检查'
                return '满足' if value >= rule - 1e-6 else '超限'

            lines.append(
                '图层 %s：最小间距 %s（规则 %.4fmm，%s）；'
                '最小留边 %s（规则 %.4fmm，%s）' % (
                    layer,
                    '未检查' if spacing is None else '%.4fmm' % spacing,
                    rule_spacing, verdict(spacing, rule_spacing),
                    '未检查' if clearance is None else '%.4fmm' % clearance,
                    rule_clearance, verdict(clearance, rule_clearance)))
            if spacing_points is not None:
                lines.append(
                    '    最近间距点：(%(ax).4f, %(ay).4f) - '
                    '(%(bx).4f, %(by).4f)' % {
                        'ax': spacing_points[0][0],
                        'ay': spacing_points[0][1],
                        'bx': spacing_points[1][0],
                        'by': spacing_points[1][1]})
            if clearance_point is not None:
                lines.append('    最窄留边点：(%.4f, %.4f)' % clearance_point)
        lines.append('')
    lines.append('共检查图案层 %d 个。' % checked)
    with open(report_path, 'w', encoding='utf-8-sig') as f:
        f.write('\n'.join(lines))
    print('\n'.join(lines))
    print('报告已保存: ' + report_path)
    return report_path


def main(workdir=None, config_path=None, overview_layout=None):
    """Generate film design files for the given working directory.

    Args:
        workdir: Directory containing numbered DXF sub-folders. All output
            files are written here. Defaults to the directory of this script.
        config_path: Path to config.ini. Defaults to config.ini in workdir.
        overview_layout: 可选；总图专用排图参数。
            dict: {'order': [图层名...], 'pairs': {图层: 通孔层或None}}。

    Returns:
        0 on success or when the input check fails, or None on error paths.
    """
    global globalconfig
    if workdir is None:
        workdir = _app_dir()
    workdir = os.path.abspath(workdir)
    if config_path is None:
        config_path = os.path.join(workdir, 'config.ini')
    globalconfig = Globalconfig(config_path)

    old_cwd = os.getcwd()
    os.chdir(workdir)
    try:
        return _run_film_generation(workdir, overview_layout)
    finally:
        if getattr(globalconfig, '_swap_backup', None):
            globalconfig.restore_film_axes()
        os.chdir(old_cwd)


def _split_overview_layout(overview_layout):
    """把 overview_layout 拆成 (图层顺序, 配对覆盖)；空值返回 (None, None)。"""
    if not overview_layout:
        return None, None
    if isinstance(overview_layout, dict):
        return overview_layout.get('order'), overview_layout.get('pairs')
    return overview_layout


def _overview_rows(overview_layout):
    """取成型参数表逐行 (图层, 通孔层或None)；无则返回 None。"""
    if overview_layout and isinstance(overview_layout, dict):
        return overview_layout.get('rows')
    return None


def _merge_effective_pairs(blockcount, pair_override):
    """把表格配对合并进当前区块的生效配对（表格优先，None=移除配对）。"""
    if not pair_override:
        return
    effective = dict(globalconfig.layerholepairdictlist_actual[blockcount])
    for layer, hole in pair_override.items():
        if hole:
            effective[layer] = hole
        else:
            effective.pop(layer, None)
    globalconfig.layerholepairdictlist_actual[blockcount] = effective


def _hole_layer_sort_key(hole_layer):
    match = re.search(r'\d+', str(hole_layer or ''))
    return int(match.group()) if match else 0


def _compute_pad_map(blockcount, overview_layout, hole_layers=None):
    """计算生效“通孔→点网层”映射，并返回自动生成的 P 网映射。

    表格/配置中已有的 H/P 映射优先；开启“通孔层是否增加点网”时，
    对没有映射的通孔层自动生成 Vn→Pn。
    """
    rows = _overview_rows(overview_layout)
    _order, pair_override = _split_overview_layout(overview_layout)
    if not rows and pair_override:
        rows = [(layer, hole) for layer, hole in pair_override.items()]
    effective = dict(globalconfig.holepadpairdictlist[blockcount] or {})
    for item in rows or []:
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            layer, hole = item[0], item[1]
            if _is_pad_layer(layer) and hole:
                effective[hole] = layer
    auto_added = {}
    if getattr(globalconfig, 'ADD_POINTNET', True) and hole_layers:
        for hole in sorted(hole_layers, key=_hole_layer_sort_key):
            if hole in effective:
                continue
            pointnet = _auto_pointnet_name(hole)
            if not pointnet:
                continue
            effective[hole] = pointnet
            auto_added[hole] = pointnet
    return effective, auto_added


def _merge_effective_pad_pairs(blockcount, overview_layout, hole_layers=None):
    """把生效“通孔与pad配对”写入配置对象，返回自动生成的 P 网映射。"""
    effective, auto_added = _compute_pad_map(
        blockcount, overview_layout, hole_layers)
    globalconfig.holepadpairdictlist[blockcount] = effective
    return auto_added


def _append_filled_ring(drawing, polyline, layer, sectors=16):
    """以三角扇 SOLID 填充一个闭合圆环（供总图通孔层使用）。"""
    points = list(polyline)
    if len(points) > 1 and points[0] == points[-1]:
        points = points[:-1]
    if len(points) < 12:
        return
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    radius = sum(
        math.hypot(p[0] - cx, p[1] - cy) for p in points) / len(points)
    center = [cx, cy]
    for index in range(sectors):
        a0 = 2 * math.pi * index / sectors
        a1 = 2 * math.pi * (index + 1) / sectors
        p0 = [cx + radius * math.cos(a0), cy + radius * math.sin(a0)]
        p1 = [cx + radius * math.cos(a1), cy + radius * math.sin(a1)]
        drawing.append(
            Solid(points=[p0, p1, center, center], layer=layer))


def _build_block_overview(feilin_dxfpolyline, blockname, blockcount,
                          readfilelist, output_path, layer_order=None,
                          pair_override=None, layout_rows=None,
                          extra_rows=None, source=None):
    """生成并保存单个区块的“图层-通孔对应关系”总图 DXF。"""
    layerholedxf = Drawing()
    (layerholepairlist, notepoints,
     extra_notes) = feilin_dxfpolyline.createlayerholepair(
         blockname, blockcount, readfilelist,
         layer_order=layer_order, pair_override=pair_override,
         layout_rows=layout_rows, extra_rows=extra_rows, source=source)

    layercolordict = {}
    for layername in layerholepairlist:
        t = random.randint(10, 17)
        layercolordict[layername] = random.randrange(10 + t, 240 + t, 10)
    layercolordict['Outline'] = 1
    layercolordict['Mark'] = 5

    for layer_name in layerholepairlist:
        layerholedxf.layers.append(
            Layer(name=layer_name, color=layercolordict[layer_name]))
        for polyline in layerholepairlist[layer_name]:
            if layer_name[:1].lower() == 'v':
                # 通孔层圆填充实心色块，便于观察
                _append_filled_ring(layerholedxf, polyline, layer_name)
            layerholedxf.append(
                PolyLine(points=polyline, layer=layer_name, flag=1))

    for note, note_point in notepoints:
        layerholedxf.append(
            Text(
                layer='0',
                text=note,
                point=note_point,
                height=0.25 * globalconfig.Y_LENGTH,
                rotation=0))
    for note_text, note_point in extra_notes:
        layerholedxf.append(
            Text(
                layer='0',
                text=note_text,
                point=note_point,
                height=0.25 * globalconfig.Y_LENGTH,
                rotation=0))
    layerholedxf.saveas(output_path)


# 编辑用总图：原图复制并按“下排图案层 + 上排配对通孔层”双行槽位排布，
# 供在 CAD 中直接修改（读回时按各层设计外框中心定位）
EDIT_OVERVIEW_DIR_NAME = '编辑总图'

# 编辑用总图图层配色：沿用预览总图的色系（非标准色、区分度高）。
# 24 个色系各取深浅两档，共 48 色，按槽位顺序依次分配；顺序固定，
# 重复生成时同一图层颜色保持一致。
EDIT_OVERVIEW_PALETTE = tuple(
    [12 + 10 * family for family in range(24)] +
    [17 + 10 * family for family in range(24)])
# 标注文字所在图层的颜色（与预览总图一致的中性色）
EDIT_OVERVIEW_NOTE_COLOR = 7


def _edit_overview_path(workdir, blockname):
    """编辑用总图路径：编辑总图/<菲林名称>编辑总图<N>.dxf。"""
    return os.path.join(
        workdir, EDIT_OVERVIEW_DIR_NAME,
        globalconfig.NAME_OF_FEILIN + '编辑总图' + str(blockname) + '.dxf')


def _edit_overview_slots(blockcount, readfilelist, overview_layout=None):
    """计算编辑用总图的槽位列表（顺序与预览总图一致）。

    返回 [{'layer': 下排图案层, 'hole': 上排通孔层或 None,
    'draw_hole': 是否在本槽位绘制通孔层几何}]。
    每个输入图层只出现一次：共用通孔层只在其第一个配对槽位上方绘制几何，
    其余配对槽位只标注通孔层名。未参与配对/表格的剩余图层追加在最后。
    """
    layer_names = [
        os.path.splitext(os.path.basename(path))[0]
        for path in readfilelist]
    available = set(layer_names)
    layer_order, pair_override = _split_overview_layout(overview_layout)
    rows = _overview_rows(overview_layout)

    def hole_of(layer):
        if pair_override is not None:
            return pair_override.get(layer)
        return globalconfig.layerholepairdictlist_actual[
            blockcount].get(layer)

    if rows:
        candidates = [(item[0], item[1] if len(item) > 1 else None)
                      for item in rows
                      if isinstance(item, (tuple, list)) and item]
    elif layer_order:
        candidates = [(name, hole_of(name)) for name in layer_order]
    else:
        candidates = [(name, hole_of(name)) for name in layer_names]

    ordered = []
    seen = set()
    for layer, hole in candidates:
        if layer in seen or layer not in available or _is_pad_layer(layer):
            continue
        seen.add(layer)
        ordered.append((layer, hole))
    # 共用通孔层只在其第一个配对槽位上方绘制几何（其余槽位只标注层名）
    hole_owner = {}
    for layer, hole in ordered:
        if hole in available and hole not in hole_owner:
            hole_owner[hole] = layer
    slots = []
    for layer, hole in ordered:
        if layer in hole_owner:
            # 该图层已作为别的槽位的上排通孔层绘制，不再单独占槽位
            continue
        slots.append({'layer': layer,
                      'hole': hole if hole in available else None,
                      'draw_hole': hole_owner.get(hole) == layer})
    # 未参与上述顺序的剩余输入图层：追加在最右侧槽位（下排）；
    # 已在上排绘制的通孔层不再单独占槽位
    drawn_layers = {slot['layer'] for slot in slots}
    drawn_layers.update(
        slot['hole'] for slot in slots if slot['draw_hole'])
    for layer in layer_names:
        if layer in drawn_layers:
            continue
        drawn_layers.add(layer)
        slots.append({'layer': layer, 'hole': None, 'draw_hole': False})
    return slots


def load_pattern_sources(workdir, dirdict):
    """按“图案来源”配置准备生成输入。

    返回 (sourcedict, error)：sourcedict 为 {区块号: 解析结果}，只有来源为
    “编辑总图”时非空；error 非空表示缺少/无法解析编辑用总图，应中止。
    """
    if getattr(globalconfig, 'PATTERN_SOURCE', '原图') != '编辑总图':
        return {}, None
    feature = Feilin_dxfpolyline(len(dirdict) or 1)
    sources = {}
    for blockname in sorted(dirdict):
        path = _edit_overview_path(workdir, blockname)
        if not os.path.isfile(path):
            return None, (
                '未找到编辑用总图：%s\n'
                '请先点击“生成编辑用总图”，'
                '或把“图案来源”切回“原图”。' % path)
        try:
            source = feature.extract_layers_from_edit_dxf(path)
        except EditOverviewError as exc:
            return None, str(exc)
        except Exception as exc:  # noqa: BLE001 - 需要给出中文提示并中止
            return None, '编辑用总图解析失败：%s\n%s' % (path, exc)
        if not source.get('layers'):
            return None, '编辑用总图中没有可用图层：%s' % path
        # 按输入文件夹的文件顺序还原图层顺序，保证“原图/编辑总图”
        # 两种来源生成的图层顺序一致（编辑总图本身按槽位顺序存放实体）
        file_order = [
            os.path.splitext(os.path.basename(item))[0]
            for item in dirdict.get(blockname, [])]
        sources[blockname] = _reorder_source_layers(source, file_order)
    return sources, None


def _reorder_source_layers(source, order):
    """按给定顺序重排编辑用总图的图层字典（未列出的图层排在最后）。"""
    layers = source.get('layers', {})
    circles = source.get('circles', {})
    frames = source.get('frames', {})
    ordered = {}
    for name in order:
        if name in layers:
            ordered[name] = layers[name]
    for name, value in layers.items():
        ordered.setdefault(name, value)
    return {
        'layers': ordered,
        'circles': {name: circles.get(name, []) for name in ordered},
        'frames': {name: frames.get(name) for name in ordered},
    }


def generate_edit_overview(workdir=None, config_path=None,
                           overview_layout=None):
    """生成各区块“编辑用总图”（原图复制 + 预览同款双行槽位排布）。

    每个槽位下排是该图案层，上排是配对通孔层（共用通孔层只在其第一个
    配对槽位上方绘制几何，其余槽位只标注通孔层名）；不把通孔圆复制到
    下排图案框内。只复制原始输入图层，不做旋转/缩放/PAD 等生成处理；
    多段线仍写 POLYLINE，圆仍写 CIRCLE，并保留各层原始设计外框。
    返回生成文件的绝对路径列表；输入检查未通过时返回空列表。
    """
    global globalconfig
    if workdir is None:
        workdir = _app_dir()
    workdir = os.path.abspath(workdir)
    if config_path is None:
        config_path = os.path.join(workdir, 'config.ini')
    globalconfig = Globalconfig(config_path)

    old_cwd = os.getcwd()
    os.chdir(workdir)
    try:
        dirdict = buildfilelist(workdir)
        blocknum = len(dirdict)
        if blocknum != globalconfig.BLOCK_Y_NUM * globalconfig.BLOCK_X_NUM:
            print('dict no. is not equal to config.ini setting!!!')
            return []
        out_dir = os.path.join(workdir, EDIT_OVERVIEW_DIR_NAME)
        os.makedirs(out_dir, exist_ok=True)
        feature = Feilin_dxfpolyline(blocknum)
        if _overview_rows(overview_layout):
            print('编辑用总图排布: 按成型参数表顺序与配对')
        else:
            print('编辑用总图排布: 按配置文件配对与文件顺序')

        # 与预览总图一致的版式常量（编辑总图不旋转，用原始设计尺寸）
        orig_x = getattr(globalconfig, 'ORIGINAL_X_LENGTH',
                         globalconfig.X_LENGTH)
        orig_y = getattr(globalconfig, 'ORIGINAL_Y_LENGTH',
                         globalconfig.Y_LENGTH)
        note_height = 0.25 * orig_y
        row_gap = OVERVIEW_GAP + note_height
        upper_y = orig_y + row_gap
        slot_pitch = orig_x + OVERVIEW_GAP
        note_y = -orig_y / 2 - 1.3 * note_height
        upper_note_y = orig_y / 2 + (row_gap - note_height) / 2

        outputs = []
        for blockcount, blockname in enumerate(sorted(dirdict)):
            readfilelist = dirdict[blockname]
            paths_by_layer = {
                os.path.splitext(os.path.basename(path))[0]: path
                for path in readfilelist}
            slots = _edit_overview_slots(
                blockcount, readfilelist, overview_layout)
            drawing = Drawing()
            drawing.layers = []
            layer_color = {}
            cache = {}

            def geometry_of(name):
                """解析并缓存某图层的原始几何与外框中心（只读）。"""
                if name in cache:
                    return cache[name]
                dataset, circles, _layer_of = feature._parse_dxf_entities_raw(
                    _read_dxf_text(paths_by_layer[name]))
                frame = feature._find_layer_frame(
                    dataset, size=(orig_x, orig_y))
                if frame is not None:
                    xs = [p[0] for p in frame]
                    ys = [p[1] for p in frame]
                    anchor = ((min(xs) + max(xs)) / 2,
                              (min(ys) + max(ys)) / 2)
                else:
                    pts = [p for poly in dataset for p in poly]
                    pts += [c['center'] for c in circles]
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    anchor = ((min(xs) + max(xs)) / 2,
                              (min(ys) + max(ys)) / 2)
                    print('警告：图层 %s 未找到设计外框'
                          '（应为 %.4f×%.4fmm 的闭合矩形），'
                          '暂按其几何中心对齐槽位；'
                          '该层读回时会报错，请补上设计外框。'
                          % (name, orig_x, orig_y))
                cache[name] = (dataset, circles, anchor)
                return cache[name]

            def color_of(name):
                """图层颜色：按加入顺序从调色板取值（同一图层固定）。"""
                return layer_color.get(name)

            def add_layer(name, color=None):
                if name in layer_color:
                    return
                if color is None:
                    color = EDIT_OVERVIEW_PALETTE[
                        len(layer_color) % len(EDIT_OVERVIEW_PALETTE)]
                layer_color[name] = color
                drawing.layers.append(Layer(name=name, color=color))

            def place(name, slot_x, slot_y):
                """把整层平移一次到槽位中心（外框与图案不会错位）。"""
                dataset, circles, anchor = geometry_of(name)
                dx = slot_x - anchor[0]
                dy = slot_y - anchor[1]
                add_layer(name)
                circle_by_index = {
                    circle['ring_index']: circle for circle in circles}
                for index, polyline in enumerate(dataset):
                    circle = circle_by_index.get(index)
                    if circle is not None:
                        drawing.append(
                            Circle(center=[circle['center'][0] + dx,
                                           circle['center'][1] + dy],
                                   radius=circle['radius'],
                                   layer=name))
                        continue
                    drawing.append(
                        PolyLine(points=[[p[0] + dx, p[1] + dy]
                                         for p in polyline],
                                 layer=name, flag=1))

            def add_note(text, x, y, color=None):
                drawing.append(
                    Text(layer='0', text=text, point=(x, y),
                         height=note_height, rotation=0, color=color))

            for index, slot in enumerate(slots):
                slot_x = slot_pitch * index
                place(slot['layer'], slot_x, 0.0)
                add_note(slot['layer'],
                         slot_x - len(slot['layer']) * note_height * 0.275,
                         note_y, color_of(slot['layer']))
                hole = slot['hole']
                if not hole:
                    continue
                if slot['draw_hole']:
                    place(hole, slot_x, upper_y)
                add_note(hole,
                         slot_x - len(hole) * note_height * 0.275,
                         upper_note_y, color_of(hole))
            add_layer('0', EDIT_OVERVIEW_NOTE_COLOR)

            output_path = _edit_overview_path(workdir, blockname)
            drawing.saveas(output_path)
            outputs.append(output_path)
        return outputs
    finally:
        os.chdir(old_cwd)


def generate_overview(workdir=None, config_path=None, overview_layout=None):
    """只生成各区块总图 DXF（供 GUI“输出总图”预览使用）。

    返回生成文件的绝对路径列表；输入检查未通过时返回空列表。
    """
    global globalconfig
    if workdir is None:
        workdir = _app_dir()
    workdir = os.path.abspath(workdir)
    if config_path is None:
        config_path = os.path.join(workdir, 'config.ini')
    globalconfig = Globalconfig(config_path)

    old_cwd = os.getcwd()
    os.chdir(workdir)
    try:
        dirdict = buildfilelist(workdir)
        blocknum = len(dirdict)
        if blocknum != globalconfig.BLOCK_Y_NUM * globalconfig.BLOCK_X_NUM:
            print('dict no. is not equal to config.ini setting!!!')
            return []
        sources, error = load_pattern_sources(workdir, dirdict)
        if error:
            print(error)
            return []
        film_dir = os.path.join(workdir, '菲林')
        os.makedirs(film_dir, exist_ok=True)
        if globalconfig.ROTATE_90:
            globalconfig.swap_film_axes()
        layer_order, pair_override = _split_overview_layout(overview_layout)
        layout_rows = _overview_rows(overview_layout)
        blockseqlist = list(dirdict.keys())
        if len(blockseqlist) > 1:
            blockseqlist.sort()
        outputs = []
        for blockcount, blockname in enumerate(blockseqlist):
            feilin_dxfpolyline = Feilin_dxfpolyline(blocknum)
            output_path = os.path.join(
                film_dir,
                globalconfig.NAME_OF_FEILIN + '总图' +
                str(blockname) + '.dxf')
            source = sources.get(blockname)
            hole_layers = _hole_layers_from_files(dirdict[blockname], source)
            _effective, auto_added = _compute_pad_map(
                blockcount, overview_layout, hole_layers)
            auto_rows = [
                (auto_added[hole], hole)
                for hole in sorted(auto_added, key=_hole_layer_sort_key)]
            _build_block_overview(
                feilin_dxfpolyline, blockname, blockcount,
                dirdict[blockname], output_path,
                layer_order=layer_order, pair_override=pair_override,
                layout_rows=layout_rows, extra_rows=auto_rows,
                source=source)
            outputs.append(output_path)
        return outputs
    finally:
        if getattr(globalconfig, '_swap_backup', None):
            globalconfig.restore_film_axes()
        os.chdir(old_cwd)


def _run_film_generation(workdir, overview_layout=None):
    """Run the generation pipeline in the given working directory."""
    # Blocks
    # hole_list=[]
    # feilin_list=[]
    b = Block('cutlineendpoint')
    b.append(PolyPad(points=[(-0.02, 0, 0), (0.02, 0, 0)], flag=1, width=0.04))

    # Drawing
    feilin = Drawing()
    # tables
    feilin.blocks.append(b)  # table blocks
    feilin.styles.append(Style())  # table styles
    feilin.views.append(View('Normal'))  # table view
    # feilin.views.append(ViewByWindow('Window',leftBottom=(1,0),rightTop=(2,1)))
    # #idem

    # 绘制菲林内部图案
    dirdict = buildfilelist(workdir)
    blocknum = len(dirdict)

    # 一个初略的输入检查,若目录中的菲林目录数量与配置中给定的拼网行列数量对不上，则不运行程序，提示后直接退出
    if blocknum != globalconfig.BLOCK_Y_NUM * globalconfig.BLOCK_X_NUM:
        print("dict no. is not equal to config.ini setting!!!")
        return 0
    sources, source_error = load_pattern_sources(workdir, dirdict)
    if source_error:
        print(source_error)
        return 0
    layer_order, pair_override = _split_overview_layout(overview_layout)
    layout_rows = _overview_rows(overview_layout)

    # 输出目录：菲林 / 开孔模式 / LDI
    film_dir = os.path.join(workdir, '菲林')
    hole_mode_dir = os.path.join(workdir, '开孔模式')
    os.makedirs(film_dir, exist_ok=True)
    os.makedirs(hole_mode_dir, exist_ok=True)

    ldi_enabled = bool(globalconfig.LDI_ENABLED)
    ldi_dir = os.path.join(workdir, 'LDI')
    ldi_drawings = {}
    if ldi_enabled:
        os.makedirs(ldi_dir, exist_ok=True)

    if globalconfig.ROTATE_90:
        # 旋转 90°：X/Y 设计参数整体互换，使阵列与切割线网格方向一致
        globalconfig.swap_film_axes()

    # 盛雄开孔：按区块收集各通孔层一行带的中心点（用于满阵列）
    sx_band_centers = {}

    # 检查MARK大小
    # if globalconfig.MARK_HEIGHT<0.70:
       # print("MARK height is less than 0.70,plz adjust mark height!!!")
       # return 0

    blockseqlist = list(dirdict.keys())

    if len(blockseqlist) > 1:
        blockseqlist.sort()

    feilinhole = Feilinhole()

    feilin_dxfpolyline = Feilin_dxfpolyline(blocknum)

    for blockcount, blockname in enumerate(
            blockseqlist):  # blockcount-第几个区块？ blockname-区块名称，就是目录名
        # 导入成型参数表时，表格配对全流程生效（表格优先，None=无配对）
        _merge_effective_pairs(blockcount, pair_override)
        source = sources.get(blockname)
        hole_layers = _hole_layers_from_files(dirdict[blockname], source)
        auto_added = _merge_effective_pad_pairs(
            blockcount, overview_layout, hole_layers)
        auto_rows = [
            (auto_added[hole], hole)
            for hole in sorted(auto_added, key=_hole_layer_sort_key)]
        eachrationumlist, holepolylinedict, feilinpolylinedict = feilin_dxfpolyline.createnewblock(
            blockname, blockcount, dirdict[blockname], source=source)
        # 收集该区块的通孔层中心点（一行带）
        block_y_count = blockcount // globalconfig.BLOCK_X_NUM
        for holelayer in holepolylinedict:
            band_items = feilin_dxfpolyline._hole_items(
                holepolylinedict[holelayer])
            design_diams = _design_diams_for(
                feilin_dxfpolyline, holelayer, len(band_items))
            if design_diams is not None:
                # 同时带上原图孔径，供盛雄开孔模式按原图孔径计算孔径
                band_items = [
                    [x, y, diam, design]
                    for (x, y, diam), design in zip(band_items, design_diams)]
            sx_band_centers.setdefault(holelayer, []).append((
                band_items,
                block_y_count))
        for feilinlayer in feilinpolylinedict:  # 遍历字典
            for polyline in feilinpolylinedict[feilinlayer]:  # 遍历字典值，即多段线列表
                feilin.append(
                    PolyLine(
                        points=polyline,
                        layer=feilinlayer,
                        flag=1))

        # LDI：按金属层收集“带”并向上阵列满
        if ldi_enabled:
            for feilinlayer in feilinpolylinedict:
                if feilinlayer == 'Outline':
                    continue
                if feilinlayer not in ldi_drawings:
                    ldi_drawings[feilinlayer] = _ldi_new_drawing(b)
                _append_ldi_pattern(
                    ldi_drawings[feilinlayer],
                    feilinlayer,
                    feilinpolylinedict[feilinlayer],
                    block_y_count,
                    blockcount)

        if globalconfig.DRAWHOLE:
            for holelayer in holepolylinedict:
                for polyline in holepolylinedict[holelayer]:
                    feilin.append(
                        PolyLine(
                            points=polyline,
                            layer=holelayer,
                            flag=1))

        if globalconfig.DRAWPAD:
            block_pad_centers = {}
            for holelayer in globalconfig.holepadpairdictlist[blockcount]:
                if holelayer in list(holepolylinedict.keys()):
                    if globalconfig.holepadpairdictlist[blockcount][holelayer] not in feilin_dxfpolyline.feilin_list:
                        feilin_dxfpolyline.feilin_list.append(
                            globalconfig.holepadpairdictlist[blockcount][holelayer])
                    # PAD 只画原始通孔，排除后加的假引孔圆环
                    hole_rings = holepolylinedict[holelayer]
                    design_diams = _design_diams_for(
                        feilin_dxfpolyline, holelayer, len(hole_rings))
                    extra = feilin_dxfpolyline._hole_extra_count.get(
                        holelayer, 0)
                    if extra:
                        num_cols = sum(eachrationumlist)
                        chunk = len(hole_rings) // num_cols
                        keep = chunk - extra
                        keep_index = [
                            i for i in range(len(hole_rings))
                            if (i % chunk) < keep]
                        hole_rings = [hole_rings[i] for i in keep_index]
                        if design_diams is not None:
                            design_diams = [
                                design_diams[i] for i in keep_index]
                    # 人工小孔径假引孔也不生成点网 PAD（按原图孔径判定）
                    hole_rings = _filter_fake_rings(hole_rings, design_diams)
                    pad_centers = feilinhole.calculateholecenterposlist(
                        hole_rings)
                    for centerpos in pad_centers:
                        pad_layer_name = \
                            globalconfig.holepadpairdictlist[blockcount][
                                holelayer]
                        feilin.append(
                            Circle(
                                center=centerpos,
                                radius=_pad_layer_diameter(
                                    pad_layer_name) / 2,
                                layer=pad_layer_name))
                    if ldi_enabled:
                        pad_layer = globalconfig.holepadpairdictlist[blockcount][holelayer]
                        block_pad_centers.setdefault(pad_layer, []).extend(
                            pad_centers)
            # LDI：PAD 层同样向上阵列满
            if ldi_enabled:
                block_y_count = blockcount // globalconfig.BLOCK_X_NUM
                for pad_layer, pad_centers in block_pad_centers.items():
                    if pad_layer not in ldi_drawings:
                        ldi_drawings[pad_layer] = _ldi_new_drawing(b)
                    _append_ldi_pads(
                        ldi_drawings[pad_layer],
                        pad_layer,
                        pad_centers,
                        block_y_count,
                        blockcount)

        # 绘制菲林MARK
        markpointlistdict = buildmarkpointlist(eachrationumlist, blockcount)
        if globalconfig.DRAWMARKNOTE:
            for mark in markpointlistdict:
                for markpoint in markpointlistdict[mark]:
                    feilin.append(
                        Text(
                            layer='Mark',
                            text=mark,
                            point=markpoint,
                            height=globalconfig.MARK_HEIGHT,
                            rotation=globalconfig.MARK_ROTATION_ANGLE))
        # 统计通孔坐标
        feilinhole.add_block_holes(holepolylinedict, blockcount)

        # 绘制图层通孔对应的多段线（总图）
        _build_block_overview(
            feilin_dxfpolyline,
            blockname,
            blockcount,
            dirdict[blockname],
            os.path.join(
                film_dir,
                globalconfig.NAME_OF_FEILIN +
                '总图' + str(blockname) + '.dxf'),
            layer_order=layer_order,
            pair_override=pair_override,
            layout_rows=layout_rows,
            extra_rows=auto_rows,
            source=source)


    # 给菲林图层上色
    layercolordict = {}
    for layername in feilin_dxfpolyline.feilin_list:
        t = random.randint(10, 17)
        layercolordict[layername] = random.randrange(10 + t, 240 + t, 10)

    layercolordict["Outline"] = 1
    layercolordict["Mark"] = 5
    # layercolordict["Cutline"]=2

    for e in layercolordict:
        feilin.layers.append(Layer(name=e, color=layercolordict[e]))

#    for holelayer in holepolylinedict:
#        if holelayer in globalconfig.LONGHOLELIST:
#            longholedxf=Drawing()
#            longholedxf.blocks.append(b)
#            for centerpos in feilinhole.calculaterlongholecenterposlist(holelayer):
#                longholedxf.append(Circle(center=centerpos,radius=globalconfig.LONGHOLEDIAMETER/2,layer=holelayer))
#            for ring in buildringlist():
#                longholedxf.append(PolyPad(points=ring,layer=holelayer,flag=1,width=globalconfig.RING_WIDTH))
#            #for cutline in buildcutlineset():
#                #longholedxf.append(PolyLine(points=cutline,layer=holelayer,flag=1,width=globalconfig.CUTLINE_WIDTH))
#            #for flash in buildflashlist():
#                #longholedxf.append(Insert(layer=holelayer,name='cutlineendpoint',point=flash))
#            longholedxf.saveas(holelayer+u'(长通孔)'+'.dxf')

    # 绘制长通孔层
    if globalconfig.DRAWLONGHOLE:
        longholedxf = Drawing()
        longholedxf.blocks.append(b)
        for holelayer in holepolylinedict:
            if holelayer in globalconfig.LONGHOLELIST:
                for centerpos in feilinhole.calculaterlongholecenterposlist(
                        holelayer):
                    longholedxf.append(
                        Circle(
                            center=centerpos,
                            radius=globalconfig.LONGHOLEDIAMETER / 2,
                            layer=holelayer))
                for ring in buildringlist():
                    longholedxf.append(
                        PolyPad(
                            points=ring,
                            layer=holelayer,
                            flag=1,
                            width=globalconfig.RING_WIDTH))
                # for cutline in buildcutlineset():
                    # longholedxf.append(PolyLine(points=cutline,layer=holelayer,flag=1,width=globalconfig.CUTLINE_WIDTH))
                # for flash in buildflashlist():
                    # longholedxf.append(Insert(layer=holelayer,name='cutlineendpoint',point=flash))
        longholedxf.saveas(
            os.path.join(
                film_dir,
                globalconfig.NAME_OF_FEILIN + '(长通孔)' + '.dxf'))

    # 绘制盛雄开孔机用的菲林
    for holelayer in sx_band_centers:
        hole_items = []
        for band_items, block_y_count in sx_band_centers[holelayer]:
            if globalconfig.SHENGXIONG_ARRAY_FULL:
                hole_items.extend(
                    _array_full_items(band_items, block_y_count))
            else:
                hole_items.extend(band_items)
        generate_shengxiong_film(
            b,
            holelayer,
            hole_items,
            hole_mode_dir)

    # 绘制切割线,菲林名称,定位圆环,十字架
    for feilin_layer in feilin_dxfpolyline.feilin_list:
        for ring in buildringlist():
            feilin.append(
                PolyPad(
                    points=ring,
                    layer=feilin_layer,
                    flag=1,
                    width=globalconfig.RING_WIDTH))
        # 纯点网（P 开头）不需要切割线与十字架
        if not _is_pure_pointnet(feilin_layer):
            for cutline in buildcutlineset():
                feilin.append(
                    PolyLine(
                        points=cutline,
                        layer=feilin_layer,
                        flag=1,
                        width=globalconfig.CUTLINE_WIDTH))
            for flash in buildflashlist():
                feilin.append(
                    Insert(
                        layer=feilin_layer,
                        name='cutlineendpoint',
                        point=flash))
        if feilin_layer.capitalize()[0] == 'P' or feilin_layer.capitalize()[
                0] == 'H':
            Title_height_offset = 5.5
        else:
            Title_height_offset = 8.5
        feilin.append(
            Text(
                layer=feilin_layer,
                text=globalconfig.NAME_OF_FEILIN +
                '-' +
                feilin_layer,
                point=(
                    globalconfig.RING_DISTANCE /
                    2 -
                    len(
                        globalconfig.NAME_OF_FEILIN) *
                    1.5 /
                    2 +
                    globalconfig.CUTLINE_X_OFFSET,
                    Title_height_offset +
                    globalconfig.RING_DISTANCE +
                    globalconfig.CUTLINE_Y_OFFSET),
                height=1.5))
        feilin.append(
            Text(
                layer=feilin_layer,
                text='Date:' +
                time.strftime(
                    '%Y-%m-%d',
                    time.localtime(
                        time.time())) +
                '    设计者:' +
                globalconfig.AUTHOR_NAME,
                point=(
                    globalconfig.RING_DISTANCE /
                    2 -
                    25.0 +
                    globalconfig.CUTLINE_X_OFFSET,
                    globalconfig.CUTLINE_Y_OFFSET +
                    globalconfig.RING_DISTANCE /
                    2 -
                    122 -
                    1.5),
                height=1.5))
    feilinnote = "说明:需要制作菲林的图层为"
    for f in feilin_dxfpolyline.feilin_list:
        feilinnote = feilinnote + f + '  '
    # info.write("\n阵列方式:请将以上图层图案向上阵列"+str(globalconfig.Y_ARRAY_NUM)+"行，行偏移为"+'{:.4f}'.format(round(globalconfig.Y_LENGTH/globalconfig.Y_OUTLINE_RATIO,4))+"mm\n")
    feilinnote = feilinnote + "\n阵列方式:请将以上图层图案\n"
    for line in range(0, globalconfig.BLOCK_Y_NUM):
        feilinnote = feilinnote + "从下至上数，位于第" + str(
            line + 1) + "行outline框中的图案向上阵列" + str(
            globalconfig.eachblock_y_list[line]) + "行，行偏移为" + '{:.4f}'.format(
            round(
                globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO,
                4)) + "mm\n"
        if feilin_dxfpolyline.blocknum > 1:
            feilinnote = feilinnote + "有部分的图层图案未分布在每一行，故阵列后这些图层的图案不会布满菲林图案区域，此外正常设计，请注意\n"
    feilin.append(
        Mtext(
            layer='0',
            text=feilinnote,
            point=(
                globalconfig.RING_DISTANCE *
                1.5 +
                globalconfig.CUTLINE_X_OFFSET,
                globalconfig.CUTLINE_Y_OFFSET +
                globalconfig.RING_DISTANCE /
                2,
                0),
            height=1.5))

    # 输出 LDI 分图层文件
    if ldi_enabled:
        for ldi_layer in ldi_drawings:
            _finalize_ldi_layer(
                ldi_drawings[ldi_layer], ldi_layer, ldi_dir)

    # 绘制所有菲林图案
    feilin.saveas(
        os.path.join(
            film_dir,
            globalconfig.NAME_OF_FEILIN + '(总菲林)' + '.dxf'))
    # 输出菲林信息文件
    feilin_dxfpolyline.outputfeilininfo(film_dir)
    # 输出菲林通孔坐标文件
    feilinhole.outputholepos(film_dir)
    # 输出长通孔坐标文件
    if globalconfig.DRAWLONGHOLE:
        feilinhole.outputlongholepos(film_dir)


if __name__ == '__main__':
    main()
