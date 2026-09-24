# coding:utf-8
"""3D 模型 → 每层图案 DXF（LTCC 分层切片前端）。

把整体 3D 实体（STL/OBJ/PLY 等网格格式）按成型参数表定义的层栈逐层取
截面，把截面轮廓按“图案层 / 通孔层”分类后，写成 drawfeilin 可直接读取的
分层 DXF：每个图层一个文件，文件名即图层名。

输出契约（与 drawfeilin 现有输入模型一致）：

    * 图案层（L/C/G/H/P 开头）写闭合 POLYLINE（其顶点为 VERTEX）；
    * 通孔层（V 开头）写 CIRCLE，圆心/半径取自截面圆；
    * 每层都写“产品设计尺寸”的设计外框，并以外框中心为坐标原点；
    * 不施加瓷体收缩率、不旋转、不镜像——这些仍由 drawfeilin 生成阶段
      按 config.ini 处理。

坐标口径：模型按 `模型单位` 换算成 mm，XY 平移使模型包围盒中心落在原点；
Z 方向按 `层序方向` 与 `切片Z基准` 从成型参数表的层栈推进。
"""

import datetime
import math
import os
import re
import shutil
import tempfile

import configparser

try:
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union
except Exception:  # pragma: no cover - 运行环境缺依赖时给出提示
    LineString = None
    polygonize = None
    unary_union = None

try:
    import numpy as np
except Exception:  # pragma: no cover - 运行环境缺依赖时给出提示
    np = None

try:
    import trimesh
except Exception:  # pragma: no cover - 运行环境缺依赖时给出提示
    trimesh = None

import drawfeilin as core


# ============================================================================
# 常量
# ============================================================================

# 图案层前缀（与 drawfeilin 的 P/H 点网规则保持一致）
PATTERN_PREFIXES = ('L', 'C', 'G', 'H', 'P')
# 通孔层前缀
HOLE_PREFIX = 'V'
# 成型参数表中不参与切片的行（基板、MARK 等）
SKIP_LAYER_NAMES = ('基板', 'MARK', 'MARK2', '外形', 'OUTLINE')
# 层类型列的“跳过”写法
SKIP_KIND_VALUES = ('跳过', '不切片', 'skip')

# [3D切片] 段默认值，与 config.ini 模板一致
DEFAULT_SLICE_CONFIG = {
    '模型单位': 'mm',
    '切片采样容差': '0.01',
    '通孔直径下限': '0.05',
    '通孔直径上限': '1.0',
    '近圆判定长宽比': '1.2',
    '圆度下限': '0.85',
    '层序方向': '自上而下',
    '切片Z基准': '',
    '覆盖前备份': 'Yes',
}

# 单位 -> mm 换算
UNIT_TO_MM = {
    'mm': 1.0, '毫米': 1.0,
    'cm': 10.0, '厘米': 10.0,
    'm': 1000.0, '米': 1000.0,
    'inch': 25.4, 'in': 25.4, '英寸': 25.4,
    'mil': 0.0254,
    'um': 0.001, 'μm': 0.001, '微米': 0.001,
}

# 支持/暂不支持的 3D 文件后缀
MESH_EXTENSIONS = ('.stl', '.obj', '.ply', '.off', '.glb', '.gltf', '.3mf')
STEP_EXTENSIONS = ('.step', '.stp', '.iges', '.igs')

# 层厚累计与模型 Z 高度的允许偏差（取较大者）：0.05mm 或 5%
THICKNESS_RATIO_TOL = 0.05
THICKNESS_ABS_TOL = 0.05

# 轮廓过滤：小于该尺寸的碎片不计入图案
MIN_CONTOUR_SIZE = 0.005


class Slice3DError(ValueError):
    """切片过程中的可预期错误（需要中文提示并中止）。"""


# ============================================================================
# 配置与工具
# ============================================================================

def _match_config_key(key):
    """把 configparser 小写化后的键名匹配回默认表里的原名。"""
    lowered = str(key).strip().lower()
    for name in DEFAULT_SLICE_CONFIG:
        if name.lower() == lowered:
            return name
    return None


def read_slice_options(config_path=None, overrides=None):
    """读取 [3D切片] 配置段，返回带类型转换的选项字典。

    overrides 为界面上的临时覆盖值（同名键优先）。
    """
    raw = dict(DEFAULT_SLICE_CONFIG)
    if config_path and os.path.isfile(config_path):
        parser = configparser.ConfigParser()
        parser.optionxform = str
        try:
            parser.read(config_path, encoding='utf-8-sig')
        except (OSError, configparser.Error):
            parser = None
        if parser is not None and parser.has_section('3D切片'):
            for key, value in parser.items('3D切片'):
                name = _match_config_key(key)
                if name and str(value).strip() != '':
                    raw[name] = str(value).strip()
    for key, value in (overrides or {}).items():
        name = _match_config_key(key) or key
        if value is not None and str(value).strip() != '':
            raw[name] = str(value).strip()

    def _as_float(name, minimum=None):
        try:
            number = float(raw[name])
        except (TypeError, ValueError):
            raise Slice3DError('[3D切片] %s 必须是数字：%s' % (name, raw[name]))
        if minimum is not None and number < minimum:
            raise Slice3DError('[3D切片] %s 不能小于 %s。' % (name, minimum))
        return number

    unit = str(raw['模型单位']).strip().lower()
    if unit not in UNIT_TO_MM:
        raise Slice3DError(
            '[3D切片] 模型单位无法识别：%s（可用 mm、cm、m、inch、mil、um）'
            % raw['模型单位'])
    direction = str(raw['层序方向']).strip()
    if direction not in ('自上而下', '自下而上'):
        raise Slice3DError(
            '[3D切片] 层序方向只能是“自上而下”或“自下而上”：%s' % direction)

    options = {
        '模型单位': unit,
        '单位换算': UNIT_TO_MM[unit],
        '切片采样容差': _as_float('切片采样容差', 0.0),
        '通孔直径下限': _as_float('通孔直径下限', 0.0),
        '通孔直径上限': _as_float('通孔直径上限', 0.0),
        '近圆判定长宽比': _as_float('近圆判定长宽比', 1.0),
        '圆度下限': _as_float('圆度下限', 0.0),
        '层序方向': direction,
        '切片Z基准': str(raw['切片Z基准']).strip(),
        '覆盖前备份': str(raw['覆盖前备份']).strip().lower() not in
        ('no', 'false', '0', '否'),
    }
    if options['通孔直径上限'] < options['通孔直径下限']:
        raise Slice3DError('[3D切片] 通孔直径上限不能小于下限。')
    if options['切片Z基准'] != '':
        try:
            options['切片Z基准'] = float(options['切片Z基准'])
        except ValueError:
            raise Slice3DError(
                '[3D切片] 切片Z基准必须是数字或留空：%s'
                % options['切片Z基准'])
    else:
        options['切片Z基准'] = None
    return options


def design_size_from_config(config_path):
    """从 config.ini 读取产品设计尺寸 (x, y)，单位 mm。"""
    if not config_path or not os.path.isfile(config_path):
        raise Slice3DError('未找到 config.ini：%s' % config_path)
    parser = configparser.ConfigParser()
    parser.optionxform = str
    parser.read(config_path, encoding='utf-8-sig')
    try:
        return (parser.getfloat('DEFAULT', '产品设计x方向长度'),
                parser.getfloat('DEFAULT', '产品设计y方向长度'))
    except (configparser.Error, ValueError) as exc:
        raise Slice3DError(
            'config.ini 中“产品设计x方向长度/产品设计y方向长度”读取失败：%s'
            % exc)


def _is_pattern_layer(name):
    """图案层：L/C/G/H/P 开头且不是纯字母占位。"""
    text = str(name or '').strip()
    if not text:
        return False
    upper = text.upper()
    if upper in SKIP_LAYER_NAMES:
        return False
    return upper[:1] in PATTERN_PREFIXES


def _is_hole_layer(name):
    """通孔层：V + 数字。"""
    return bool(re.match(r'^[Vv]\d+$', str(name or '').strip()))


def _layer_color(index):
    """按槽位顺序分配颜色（避开 7 号白与背景色）。"""
    palette = [1, 3, 5, 4, 6, 2, 30, 40, 50, 90, 140, 190]
    return palette[index % len(palette)]


# ============================================================================
# 模型载入
# ============================================================================

def load_model(model_path, unit='mm'):
    """载入 3D 模型并统一到 mm，返回 trimesh.Trimesh。

    STEP/IGES 目前只保留适配器入口：需要 OCP/CadQuery，本次不实现。
    """
    if trimesh is None:
        raise Slice3DError(
            '缺少 trimesh 依赖，无法读取 3D 模型。\n'
            '请先安装：pip install trimesh')

    extension = os.path.splitext(str(model_path or ''))[1].lower()
    if extension in STEP_EXTENSIONS:
        raise Slice3DError(
            '暂不支持 STEP/IGES 输入：%s\n'
            '本次实现只支持网格格式（%s）。\n'
            '请先在 CAD 中另存为 STL，或在后续版本接入 OCP/CadQuery。'
            % (os.path.basename(str(model_path)), '、'.join(MESH_EXTENSIONS)))
    if not model_path or not os.path.isfile(model_path):
        raise Slice3DError('未找到 3D 模型文件：%s' % model_path)

    scale = UNIT_TO_MM.get(str(unit or 'mm').strip().lower())
    if scale is None:
        raise Slice3DError('无法识别的模型单位：%s' % unit)

    try:
        loaded = trimesh.load(model_path, force=None)
    except Exception as exc:  # noqa: BLE001 - 需要中文提示
        raise Slice3DError('读取 3D 模型失败：%s\n%s' % (model_path, exc))

    if isinstance(loaded, trimesh.Scene):
        if not loaded.geometry:
            raise Slice3DError('3D 模型中没有可用的几何体：%s' % model_path)
        # dump(concatenate=True) 会把各节点变换应用到网格后合并
        mesh = loaded.dump(concatenate=True)
    else:
        mesh = loaded
    if mesh is None or len(getattr(mesh, 'faces', [])) == 0:
        raise Slice3DError('3D 模型中没有可用三角面片：%s' % model_path)

    mesh = mesh.copy()
    if abs(scale - 1.0) > 1e-12:
        mesh.apply_scale(scale)
    return mesh


def model_bounds(mesh):
    """返回模型包围盒 (xmin, ymin, zmin, xmax, ymax, zmax)，单位 mm。"""
    bounds = mesh.bounds
    return (float(bounds[0][0]), float(bounds[0][1]), float(bounds[0][2]),
            float(bounds[1][0]), float(bounds[1][1]), float(bounds[1][2]))


def _z_range_from_bounds(bounds):
    """把各种 bounds 输入统一成 (zmin, zmax)。"""
    if bounds is None:
        raise Slice3DError('缺少模型包围盒，无法确定切片 Z 范围。')
    values = list(bounds)
    if len(values) == 2 and not hasattr(values[0], '__len__'):
        return (float(values[0]), float(values[1]))
    flat = []
    for value in values:
        if hasattr(value, '__len__'):
            flat.extend(float(item) for item in value)
        else:
            flat.append(float(value))
    if len(flat) < 6:
        raise Slice3DError('模型包围盒格式无法识别：%r' % (bounds,))
    return (min(flat[2], flat[5]), max(flat[2], flat[5]))


# ============================================================================
# 层栈解析
# ============================================================================

def _stack_items(form_layout):
    """把成型参数表解析结果统一成 [{name, hole, ...}, ...]（保持表格顺序）。"""
    if not form_layout:
        return []
    stack = form_layout.get('stack')
    if stack:
        return [dict(item) for item in stack]
    items = []
    for row in form_layout.get('rows') or []:
        if isinstance(row, (list, tuple)):
            name = row[0] if row else None
            hole = row[1] if len(row) > 1 else None
        else:
            name, hole = row, None
        items.append({'name': name, 'hole': hole})
    if not items:
        for name, hole in (form_layout.get('pairs') or {}).items():
            items.append({'name': name, 'hole': hole})
    return items


def _item_thickness(item):
    """取该行层厚（mm）与来源说明；无可用值时返回 (None, None)。"""
    thickness = item.get('thickness_mm')
    if thickness not in (None, ''):
        return float(thickness), '厚度(mm)'
    fired = item.get('烧结后厚度')
    if fired not in (None, ''):
        return float(fired), '烧结后厚度'
    film = item.get('膜厚')
    if film not in (None, ''):
        # 膜厚列沿用行业习惯的 µm 量纲
        return float(film) / 1000.0, '膜厚(µm)'
    return None, None


def _item_z(item):
    """取该行显式给定的切片 Z（mm）；无则返回 None。"""
    value = item.get('z')
    if value in (None, ''):
        return None
    return float(value)


def parse_layer_stack(form_layout, options, model_bounds=None):
    """把成型参数表 + 切片选项整理成逐层切片计划。

    model_bounds 接受 (zmin, zmax) 或 trimesh 的 (2, 3) 包围盒。

    返回 (stack, warnings)：
        stack: [{'name', 'hole', 'z', 'thickness', 'source'}, ...]
        warnings: 需要提示给用户的说明文字列表
    """
    items = _stack_items(form_layout)
    if not items:
        raise Slice3DError(
            '没有可用的层栈。请先“导入成型参数表…”，'
            '表格需包含“层数名称”列。')

    warnings = []
    entries = []
    skipped = []
    for index, item in enumerate(items):
        name = str(item.get('name') or '').strip()
        hole = str(item.get('hole') or '').strip()
        kind = str(item.get('kind') or '').strip().lower()
        if kind in SKIP_KIND_VALUES:
            skipped.append(name or ('第%d行' % (index + 1)))
            continue
        if not _is_pattern_layer(name):
            skipped.append(name or ('第%d行' % (index + 1)))
            continue
        if hole and not _is_hole_layer(hole):
            # 形如“0”“4H”的通孔模式列不构成通孔层
            hole = ''
        entries.append({
            'name': name,
            'hole': hole or None,
            'z': _item_z(item),
            'thickness': None,
            'source': None,
            '_item': item,
        })
    if not entries:
        raise Slice3DError(
            '成型参数表中没有可切片的图案层行'
            '（层名需以 L/C/G/H/P 开头）。已跳过：%s'
            % ('、'.join(skipped) or '无'))

    # 显式 Z 优先；缺 Z 的行按层厚沿“层序方向”累加
    missing_thickness = []
    for entry in entries:
        if entry['z'] is not None:
            continue
        thickness, source = _item_thickness(entry['_item'])
        entry['thickness'] = thickness
        entry['source'] = source
        if thickness is None or thickness <= 0:
            missing_thickness.append(entry['name'])
    if missing_thickness:
        raise Slice3DError(
            '以下图层既没有“切片Z(mm)”，也没有可用的层厚'
            '（厚度(mm) / 烧结后厚度 / 膜厚）：%s\n'
            '请补齐成型参数表后再切片。'
            % '、'.join(missing_thickness))

    zmin, zmax = _z_range_from_bounds(model_bounds) if model_bounds is not None \
        else (None, None)
    top_down = options['层序方向'] == '自上而下'
    base = options.get('切片Z基准')
    if base is None:
        base = zmax if top_down else zmin
        if base is None:
            raise Slice3DError(
                '缺少模型包围盒，请在 [3D切片] 中填写“切片Z基准”。')
    cursor = float(base)
    total = 0.0
    for entry in entries:
        if entry['z'] is not None:
            continue
        thickness = entry['thickness']
        if top_down:
            entry['z'] = cursor - thickness / 2.0
            cursor -= thickness
        else:
            entry['z'] = cursor + thickness / 2.0
            cursor += thickness
        total += thickness

    fallback_sources = sorted({
        entry['source'] for entry in entries
        if entry['source'] and entry['source'] != '厚度(mm)'})
    if fallback_sources:
        warnings.append(
            '以下行的层厚取自回退列（%s），建议在成型参数表中补“厚度(mm)”'
            '或用“切片Z(mm)”直接给定每层 Z。'
            % '、'.join(fallback_sources))

    if zmin is not None and total > 0:
        height = zmax - zmin
        tolerance = max(THICKNESS_ABS_TOL, height * THICKNESS_RATIO_TOL)
        if abs(total - height) > tolerance:
            raise Slice3DError(
                '层厚累计 %.4fmm 与模型 Z 高度 %.4fmm 偏差过大'
                '（容差 %.4fmm）。\n'
                '请检查成型参数表的层厚列，或直接填写每层“切片Z(mm)”。'
                % (total, height, tolerance))

    if zmin is not None:
        outside = ['%s(Z=%.4f)' % (entry['name'], entry['z'])
                   for entry in entries
                   if entry['z'] < zmin - 1e-6 or entry['z'] > zmax + 1e-6]
        if outside:
            raise Slice3DError(
                '以下图层的切片 Z 超出模型 Z 范围 [%.4f, %.4f]：%s\n'
                '请检查“层序方向 / 切片Z基准 / 层厚”。'
                % (zmin, zmax, '、'.join(outside)))

    if skipped:
        warnings.append('已跳过不参与切片的行：%s' % '、'.join(skipped))

    for entry in entries:
        entry.pop('_item', None)
    return entries, warnings


# ============================================================================
# 截面与轮廓分类
# ============================================================================

def _section_polygons(mesh, z):
    """取 Z 处截面，返回 shapely Polygon 列表（未简化，便于识别通孔）。"""
    if LineString is None:
        raise Slice3DError(
            '缺少 shapely 依赖，无法处理截面轮廓。\n'
            '请先安装：pip install shapely')
    try:
        section = mesh.section(
            plane_origin=[0.0, 0.0, float(z)],
            plane_normal=[0.0, 0.0, 1.0])
    except Exception as exc:  # noqa: BLE001 - 需要中文提示
        raise Slice3DError('Z=%.4f 处求截面失败：%s' % (z, exc))
    if section is None:
        return []

    lines = []
    for entity in section.entities:
        try:
            points = section.vertices[entity.points][:, :2]
        except Exception:
            continue
        if len(points) < 2:
            continue
        lines.append(LineString(points))
    if not lines:
        return []

    polygons = []
    merged = unary_union(lines)
    for candidate in polygonize(merged):
        if candidate is None or candidate.is_empty:
            continue
        if not candidate.is_valid:
            candidate = candidate.buffer(0)
        if candidate.is_empty:
            continue
        items = candidate.geoms if candidate.geom_type == 'MultiPolygon' \
            else [candidate]
        for item in items:
            if item.geom_type != 'Polygon' or item.is_empty:
                continue
            minx, miny, maxx, maxy = item.bounds
            if (maxx - minx) < MIN_CONTOUR_SIZE and \
                    (maxy - miny) < MIN_CONTOUR_SIZE:
                continue
            polygons.append(item)
    return polygons


def _is_frame_like(polygon, design_size, tolerance=0.05):
    """轮廓包围盒是否等于设计外框尺寸（则该轮廓按外框处理，不再当图案）。"""
    minx, miny, maxx, maxy = polygon.bounds
    width = maxx - minx
    height = maxy - miny
    return (abs(width - design_size[0]) <= tolerance
            and abs(height - design_size[1]) <= tolerance) or \
        (abs(width - design_size[1]) <= tolerance
         and abs(height - design_size[0]) <= tolerance)


def _fit_circle(points):
    """最小二乘拟合圆（Kasa），返回 (cx, cy, r)；点数不足返回 None。

    正多边形（CAD 圆转 STL 的常见结果）顶点共圆，拟合结果即名义半径，
    比用外接矩形推算更可靠。
    """
    if np is None or len(points) < 3:
        return None
    xs = np.array([p[0] for p in points], dtype=float)
    ys = np.array([p[1] for p in points], dtype=float)
    matrix = np.column_stack([2.0 * xs, 2.0 * ys, np.ones(len(xs))])
    rhs = xs ** 2 + ys ** 2
    try:
        solution, *_rest = np.linalg.lstsq(matrix, rhs, rcond=None)
    except Exception:
        return None
    cx, cy, constant = (float(value) for value in solution)
    squared = constant + cx * cx + cy * cy
    if squared <= 0:
        return None
    return (cx, cy, math.sqrt(squared))


def circle_from_polygon(polygon, options):
    """把近似圆的截面轮廓识别成通孔，返回 (cx, cy, r)；不是通孔返回 None。"""
    if polygon is None or polygon.is_empty:
        return None
    if polygon.area <= 0 or polygon.length <= 0:
        return None

    # 外形比例先过滤掉细长轮廓
    minx, miny, maxx, maxy = polygon.bounds
    width = maxx - minx
    height = maxy - miny
    short_side = min(width, height)
    if short_side <= 0 or max(width, height) / short_side > \
            options['近圆判定长宽比']:
        return None

    # 圆度：矩形约 0.785，正六边形约 0.907，圆接近 1
    roundness = 4.0 * math.pi * polygon.area / (polygon.length ** 2)
    if roundness < options['圆度下限']:
        return None

    points = list(polygon.exterior.coords)
    if len(points) > 1 and points[0] == points[-1]:
        points = points[:-1]
    fitted = _fit_circle(points)
    if fitted is None:
        center = polygon.centroid
        diameter = 2.0 * math.sqrt(polygon.area / math.pi)
        return (float(center.x), float(center.y), float(diameter / 2.0))
    cx, cy, _radius = fitted
    # 三角化网格在层中面切出的轮廓半径会略小于名义值（弦中点偏内），
    # 取到拟合圆心的最大距离还原设计孔径。
    radius = max(math.hypot(px - cx, py - cy) for px, py in points)
    diameter = 2.0 * radius
    if diameter < options['通孔直径下限'] - 1e-9 or \
            diameter > options['通孔直径上限'] + 1e-9:
        return None
    return (float(cx), float(cy), float(radius))


def _polygon_loops(polygon, tolerance=0.0):
    """把截面多边形转成闭合点列（外环 + 内环）。

    简化只作用于图案轮廓：通孔已在分类阶段被识别为 CIRCLE，
    不会因为小块面被容差吃掉。
    """
    simplified = polygon
    if tolerance and tolerance > 0:
        try:
            candidate = polygon.simplify(
                tolerance, preserve_topology=True)
            if not candidate.is_empty and candidate.geom_type == 'Polygon':
                simplified = candidate
        except Exception:
            simplified = polygon
    loops = []
    for ring in [simplified.exterior] + list(simplified.interiors):
        points = [[float(x), float(y)] for x, y in ring.coords]
        if len(points) < 4:
            continue
        if points[0] != points[-1]:
            points.append(list(points[0]))
        loops.append(points)
    return loops


def _frame_points(design_size):
    """设计外框（闭合矩形，中心在原点）。"""
    half_x = design_size[0] / 2.0
    half_y = design_size[1] / 2.0
    return [[-half_x, half_y], [half_x, half_y],
            [half_x, -half_y], [-half_x, -half_y], [-half_x, half_y]]


# ============================================================================
# DXF 输出
# ============================================================================

def write_layer_dxf(name, loops, circles, frame, out_path, color=7):
    """写出一个图层 DXF（外框 + 闭合多段线 + CIRCLE）。"""
    drawing = core.Drawing()
    drawing.layers.append(core.Layer(name='0', color=7))
    drawing.layers.append(core.Layer(name=name, color=color))
    if frame:
        drawing.append(core.PolyLine(
            points=[(x, y, 0) for x, y in frame], layer=name, flag=1))
    for loop in loops:
        drawing.append(core.PolyLine(
            points=[(x, y, 0) for x, y in loop], layer=name, flag=1))
    for (cx, cy, radius) in circles:
        drawing.append(core.Circle(
            center=(cx, cy, 0), radius=radius, layer=name))
    drawing.saveas(out_path)
    return out_path


# ============================================================================
# 切片主流程
# ============================================================================

def slice_model_to_layers(model_path, stack, design_size, options, out_dir,
                          log=print):
    """按层栈逐层切片并把结果写成 DXF，返回报告字典。"""
    os.makedirs(out_dir, exist_ok=True)
    mesh = load_model(model_path, options['模型单位'])
    bounds = model_bounds(mesh)
    center_x = (bounds[0] + bounds[3]) / 2.0
    center_y = (bounds[1] + bounds[4]) / 2.0
    log('模型: %s' % os.path.basename(model_path))
    log('模型 Z 范围: %.4f ~ %.4f mm（层数 %d）'
        % (bounds[2], bounds[5], len(stack)))
    log('模型 XY 包围盒中心: (%.4f, %.4f) -> 平移到原点'
        % (center_x, center_y))

    pattern_data = {}
    hole_data = {}
    warnings = []
    layer_index = 0
    order = []
    for entry in stack:
        name = entry['name']
        hole = entry.get('hole')
        z = float(entry['z'])
        polygons = _section_polygons(mesh, z)
        loops = []
        vias = []
        skipped_frame = 0
        for polygon in polygons:
            if _is_frame_like(polygon, design_size):
                skipped_frame += 1
                continue
            circle = circle_from_polygon(polygon, options)
            if circle is not None and hole:
                vias.append(circle)
                continue
            loops.extend(_polygon_loops(
                polygon, options['切片采样容差']))

        # 统一平移到“模型包围盒中心 = 原点”
        loops = [[[x - center_x, y - center_y] for x, y in loop]
                 for loop in loops]
        vias = [(cx - center_x, cy - center_y, radius)
                for (cx, cy, radius) in vias]

        # 同名图层在成型参数表中可能出现在多个 Z（同一张网印在多层），
        # 这里按图层名合并轮廓，最终一个图层只输出一个 DXF。
        bucket = pattern_data.setdefault(name, {
            'loops': [],
            'circles': [],
            'color': _layer_color(layer_index),
            'entries': [],
        })
        bucket['loops'].extend(loops)
        bucket['entries'].append((z, len(loops), len(vias)))
        layer_index += 1
        if name not in order:
            order.append(name)
        if hole:
            hole_bucket = hole_data.setdefault(
                hole, {'circles': [], 'seen': set(),
                       'color': _layer_color(layer_index)})
            for (cx, cy, radius) in vias:
                key = (round(cx, 4), round(cy, 4), round(radius, 4))
                if key in hole_bucket['seen']:
                    continue
                hole_bucket['seen'].add(key)
                hole_bucket['circles'].append((cx, cy, radius))
            if hole not in order:
                order.append(hole)
        log('%-6s Z=%8.4fmm  轮廓 %-4d 通孔 %-4d%s'
            % (name, z, len(loops), len(vias),
               '（外框轮廓 %d 个已按外框处理）' % skipped_frame
               if skipped_frame else ''))
        if not loops and not vias:
            warnings.append('%s (Z=%.4f) 截面为空，只输出设计外框。'
                            % (name, z))

    frame = _frame_points(design_size)
    files = []
    for name in order:
        data = pattern_data.get(name)
        if data is None:
            data = hole_data[name]
            files.append(write_layer_dxf(
                name=name, loops=[], circles=data['circles'],
                frame=frame,
                out_path=os.path.join(out_dir, name + '.dxf'),
                color=data['color']))
            continue
        if len(data['entries']) > 1:
            log('%-6s 合并 %d 处截面，共轮廓 %d 条'
                % (name, len(data['entries']), len(data['loops'])))
        files.append(write_layer_dxf(
            name=name, loops=data['loops'], circles=data['circles'],
            frame=frame,
            out_path=os.path.join(out_dir, name + '.dxf'),
            color=data['color']))

    report = {
        'model': model_path,
        'files': files,
        'pattern_layers': [name for name in order if name in pattern_data],
        'hole_layers': sorted(hole_data),
        'warnings': warnings,
        'bounds': bounds,
    }
    return report


def _backup_block_dir(block_dir):
    """把区块目录整体移动到 _backup 目录，返回备份路径。"""
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    base = '%s_backup_%s' % (os.path.basename(block_dir.rstrip('\\/')), stamp)
    parent = os.path.dirname(os.path.abspath(block_dir))
    target = os.path.join(parent, base)
    suffix = 1
    while os.path.exists(target):
        suffix += 1
        target = os.path.join(parent, '%s_%d' % (base, suffix))
    shutil.move(block_dir, target)
    return target


def slice_block_to_workdir(model_path, workdir, block, form_layout,
                           config_path=None, options=None, log=print):
    """把 3D 模型切片成区块目录下的分层 DXF（覆盖前自动备份）。

    返回报告字典；失败抛出 Slice3DError。
    """
    if not os.path.isdir(workdir):
        raise Slice3DError('工作目录不存在：%s' % workdir)
    if config_path is None:
        config_path = os.path.join(workdir, 'config.ini')
    resolved = read_slice_options(config_path, options)
    design_size = design_size_from_config(config_path)
    block_dir = os.path.join(workdir, str(block).strip())
    if not str(block).strip().isdigit():
        raise Slice3DError('区块号必须是数字：%s' % block)

    mesh = load_model(model_path, resolved['模型单位'])
    bounds = model_bounds(mesh)
    stack, warnings = parse_layer_stack(form_layout, resolved, bounds)

    staging = tempfile.mkdtemp(prefix='_3d切片_', dir=workdir)
    backup = None
    try:
        report = slice_model_to_layers(
            model_path=model_path, stack=stack, design_size=design_size,
            options=resolved, out_dir=staging, log=log)
        if resolved['覆盖前备份'] and os.path.isdir(block_dir):
            backup = _backup_block_dir(block_dir)
            log('已备份原区块目录: %s' % backup)
        os.makedirs(block_dir, exist_ok=True)
        for item in sorted(os.listdir(staging)):
            shutil.move(os.path.join(staging, item),
                        os.path.join(block_dir, item))
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    report['backup'] = backup
    report['block_dir'] = block_dir
    report['warnings'] = warnings + report['warnings']
    return report
