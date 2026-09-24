# coding:utf-8
"""drawfeilin3d（3D 模型 → 每层图案 DXF）自检脚本。

不依赖 pytest，直接运行：

    python tests/test_slice3d.py

覆盖：层栈解析、截面分类、DXF 写出与回读、端到端生成。
"""

import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import trimesh  # noqa: E402

import drawfeilin as core  # noqa: E402
import drawfeilin3d as slice3d  # noqa: E402


REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESIGN_SIZE = (4.8, 4.2)
LAYER_THICKNESS = 0.1
VIA_RADIUS = 0.05          # 直径 0.1mm，落在默认通孔区间 [0.05, 1.0]


def build_synthetic_model(path, layers=3):
    """造一个“生带整版 + 每层金属图案 + 上下贯通通孔圆柱”的测试模型。"""
    height = LAYER_THICKNESS * layers
    meshes = []

    # 生带整版：截面尺寸等于设计外框 -> 应被当作外框过滤
    plate = trimesh.creation.box(
        extents=[DESIGN_SIZE[0], DESIGN_SIZE[1], height])
    plate.apply_translation([0.0, 0.0, height / 2.0])
    meshes.append(plate)

    # 每层金属图案：2.0 x 0.6 x 0.08 的薄片
    for index in range(layers):
        z_center = LAYER_THICKNESS * (index + 0.5)
        pattern = trimesh.creation.box(extents=[2.0, 0.6, 0.08])
        pattern.apply_translation([0.0, 0.0, z_center])
        meshes.append(pattern)

    # 两个贯通通孔圆柱（直径 0.1mm）
    for x in (-1.5, 1.5):
        via = trimesh.creation.cylinder(radius=VIA_RADIUS, height=height)
        via.apply_translation([x, 0.0, height / 2.0])
        meshes.append(via)

    model = trimesh.util.concatenate(meshes)
    model.export(path)
    return path


def build_form_layout(layers=3, start=1):
    """构造与 GUI 解析结果同构的 form_layout（含新增 stack 字段）。"""
    stack = []
    order = ['MARK', '基板']
    pairs = {'MARK': None, '基板': None}
    for index in range(layers):
        number = start + index
        name = 'L%d' % number
        hole = 'V%d' % number
        stack.append({
            'name': 'MARK', 'hole': '', 'z': None,
            'thickness_mm': None, '膜厚': 50, '层类型': ''})
        stack.append({
            'name': name, 'hole': hole, 'z': None,
            'thickness_mm': LAYER_THICKNESS, '膜厚': 40, '层类型': ''})
        order.append(name)
        pairs[name] = hole
    order.append('基板')
    stack.insert(1, {
        'name': '基板', 'hole': '', 'z': None,
        'thickness_mm': None, '膜厚': 50, '层类型': ''})
    rows = [(name, pairs.get(name)) for name in order]
    return {'order': order, 'pairs': pairs, 'rows': rows,
            'count': len(order), 'stack': stack}


def build_two_plate_model(path):
    """两个不同 Z、不同尺寸的图案薄片 + 整版生带（用于验证同名层合并）。"""
    meshes = []
    plate = trimesh.creation.box(extents=[DESIGN_SIZE[0], DESIGN_SIZE[1], 0.2])
    plate.apply_translation([0.0, 0.0, 0.1])
    meshes.append(plate)
    for index, z_center in enumerate((0.05, 0.15)):
        pattern = trimesh.creation.box(
            extents=[2.0 - index * 0.5, 0.6, 0.04])
        pattern.apply_translation([0.0, 0.0, z_center])
        meshes.append(pattern)
    model = trimesh.util.concatenate(meshes)
    model.export(path)
    return path


def make_workdir(layers=3):
    """建临时工作目录：拷贝仓库 config.ini 并把“图案来源”切到原图。"""
    workdir = tempfile.mkdtemp(prefix='drawfeilin3d_')
    source = os.path.join(REPO_DIR, 'config.ini')
    with open(source, 'r', encoding='utf-8-sig') as handle:
        text = handle.read()
    text = re.sub(r'图案来源\s*=\s*.*', '图案来源 = 原图', text)
    text = re.sub(r'是否输出ldi\s*=\s*.*', '是否输出ldi = Yes', text)
    text = re.sub(r'是否绘制通孔层\s*=\s*.*', '是否绘制通孔层 = No', text)
    with open(os.path.join(workdir, 'config.ini'), 'w',
              encoding='utf-8-sig') as handle:
        handle.write(text)
    return workdir


def test_options_defaults():
    options = slice3d.read_slice_options(None)
    assert options['模型单位'] == 'mm'
    assert options['层序方向'] == '自上而下'
    assert options['通孔直径下限'] == 0.05
    assert options['通孔直径上限'] == 1.0
    assert options['覆盖前备份'] is True
    assert options['切片Z基准'] is None

    overridden = slice3d.read_slice_options(None, {
        '层序方向': '自下而上', '切片Z基准': '0.02', '覆盖前备份': 'No'})
    assert overridden['层序方向'] == '自下而上'
    assert overridden['切片Z基准'] == 0.02
    assert overridden['覆盖前备份'] is False

    try:
        slice3d.read_slice_options(None, {'模型单位': '尺'})
    except slice3d.Slice3DError as exc:
        assert '模型单位' in str(exc)
    else:  # pragma: no cover - 不应发生
        raise AssertionError('非法单位应报错')


def test_parse_layer_stack_top_down():
    options = slice3d.read_slice_options(None)
    layout = build_form_layout(layers=3)
    stack, warnings = slice3d.parse_layer_stack(
        layout, options, (0.0, 0.3))
    assert [item['name'] for item in stack] == ['L1', 'L2', 'L3']
    assert [item['hole'] for item in stack] == ['V1', 'V2', 'V3']
    # 自上而下：表格第一行在最上方，Z 依次向下推进
    assert abs(stack[0]['z'] - 0.25) < 1e-9
    assert abs(stack[1]['z'] - 0.15) < 1e-9
    assert abs(stack[2]['z'] - 0.05) < 1e-9
    assert any('跳过' in text for text in warnings)


def test_parse_layer_stack_bottom_up_and_errors():
    options = slice3d.read_slice_options(None, {'层序方向': '自下而上'})
    layout = build_form_layout(layers=3)
    stack, _warnings = slice3d.parse_layer_stack(layout, options, (0.0, 0.3))
    assert abs(stack[0]['z'] - 0.05) < 1e-9
    assert abs(stack[2]['z'] - 0.25) < 1e-9

    # 层厚累计与模型高度不符 -> 中止
    layout = build_form_layout(layers=3)
    for item in layout['stack']:
        if item['name'].startswith('L'):
            item['thickness_mm'] = 0.5
    try:
        slice3d.parse_layer_stack(layout, options, (0.0, 0.3))
    except slice3d.Slice3DError as exc:
        assert '偏差过大' in str(exc)

    # 既无 Z 也无层厚 -> 中止
    layout = build_form_layout(layers=2)
    for item in layout['stack']:
        if item['name'].startswith('L'):
            item['thickness_mm'] = None
            item['膜厚'] = None
    try:
        slice3d.parse_layer_stack(layout, options, (0.0, 0.2))
    except slice3d.Slice3DError as exc:
        assert '层厚' in str(exc)


def test_circle_classification():
    options = slice3d.read_slice_options(None)
    circle = trimesh.creation.cylinder(radius=VIA_RADIUS, height=0.1)
    section = circle.section(plane_origin=[0, 0, 0],
                             plane_normal=[0, 0, 1])
    polygons = slice3d._section_polygons(circle, 0.0)
    assert polygons, '圆柱截面应有轮廓'
    via = slice3d.circle_from_polygon(polygons[0], options)
    assert via is not None, '直径 0.1mm 的圆应识别为通孔'
    assert abs(via[2] - VIA_RADIUS) < 0.002
    assert section is not None

    # 尺寸超出通孔区间 -> 不识别为通孔
    big = trimesh.creation.cylinder(radius=1.5, height=0.1)
    big_polygon = slice3d._section_polygons(big, 0.0)[0]
    assert slice3d.circle_from_polygon(big_polygon, options) is None

    # 长方形轮廓 -> 不识别为通孔
    box = trimesh.creation.box(extents=[0.2, 0.2, 0.1])
    rectangle = slice3d._section_polygons(box, 0.0)[0]
    assert slice3d.circle_from_polygon(rectangle, options) is None
    assert slice3d._is_frame_like(rectangle, (0.2, 0.2))


def test_step_input_reports_clear_error():
    try:
        slice3d.load_model('demo.step', 'mm')
    except slice3d.Slice3DError as exc:
        assert 'STEP' in str(exc)
    else:  # pragma: no cover - 不应发生
        raise AssertionError('STEP 输入应给出明确提示')


def test_slice_and_read_back():
    tmp = tempfile.mkdtemp(prefix='drawfeilin3d_slice_')
    try:
        model = build_synthetic_model(os.path.join(tmp, 'model.stl'))
        layout = build_form_layout(layers=3)
        options = slice3d.read_slice_options(None)
        stack, _warnings = slice3d.parse_layer_stack(layout, options, (0.0, 0.3))
        report = slice3d.slice_model_to_layers(
            model, stack, DESIGN_SIZE, options,
            os.path.join(tmp, 'out'), log=lambda text: None)

        names = sorted(os.path.basename(path)
                       for path in report['files'])
        assert names == ['L1.dxf', 'L2.dxf', 'L3.dxf',
                         'V1.dxf', 'V2.dxf', 'V3.dxf'], names

        core.globalconfig = core.Globalconfig(
            os.path.join(REPO_DIR, 'config.ini'))
        feature = core.Feilin_dxfpolyline(1)
        for number in (1, 2, 3):
            pattern = os.path.join(tmp, 'out', 'L%d.dxf' % number)
            dataset, circles = feature._parse_dxf_entities(open(pattern))
            assert len(dataset) == 2, (pattern, len(dataset))
            assert circles == []

            hole = os.path.join(tmp, 'out', 'V%d.dxf' % number)
            _dataset, hole_circles = feature._parse_dxf_entities(open(hole))
            assert len(hole_circles) == 2, (hole, len(hole_circles))
            radii = sorted(round(item['radius'], 4) for item in hole_circles)
            assert radii == [round(VIA_RADIUS, 4)] * 2, radii
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_duplicate_layer_names_merge():
    """同一图层名出现在多个 Z（同一张网印在多层）时按名称合并轮廓。"""
    tmp = tempfile.mkdtemp(prefix='drawfeilin3d_merge_')
    try:
        model = build_two_plate_model(os.path.join(tmp, 'model.stl'))
        options = slice3d.read_slice_options(None)
        stack = [
            {'name': 'L1', 'hole': None, 'z': 0.05,
             'thickness': None, 'source': None},
            {'name': 'L1', 'hole': None, 'z': 0.15,
             'thickness': None, 'source': None},
        ]
        report = slice3d.slice_model_to_layers(
            model, stack, DESIGN_SIZE, options,
            os.path.join(tmp, 'out'), log=lambda text: None)
        assert [os.path.basename(path) for path in report['files']] == ['L1.dxf']

        core.globalconfig = core.Globalconfig(
            os.path.join(REPO_DIR, 'config.ini'))
        feature = core.Feilin_dxfpolyline(1)
        dataset, _circles = feature._parse_dxf_entities(
            open(os.path.join(tmp, 'out', 'L1.dxf')))
        assert len(dataset) == 3, len(dataset)  # 外框 + 两处图案
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_shipped_form_table_parses():
    """真实成型参数表（老版表格）仍能解析，并带上 3D 切片用的 stack 字段。"""
    import drawfeilin_gui as gui
    table = os.path.join(REPO_DIR, '成型参数信息填写表.xlsx')
    if not os.path.isfile(table):
        return
    layout = gui.App._parse_form_table(table)
    assert layout['count'] == len(layout['order'])
    assert len(layout['stack']) == len(layout['order'])
    assert layout['stack'][0]['name'] == layout['order'][0]
    assert {'name', 'hole', 'z', 'thickness_mm', '膜厚', '层类型'} <= \
        set(layout['stack'][0])
    names = {item['name'] for item in layout['stack']}
    assert 'L1' in names and 'V' not in names


def test_end_to_end_generation():
    workdir = make_workdir()
    try:
        model = build_synthetic_model(os.path.join(workdir, 'model.stl'))
        layout = build_form_layout(layers=3)
        report = slice3d.slice_block_to_workdir(
            model_path=model, workdir=workdir, block=1,
            form_layout=layout, config_path=os.path.join(workdir, 'config.ini'),
            log=lambda text: None)
        assert report['backup'] is None, '首次切片不应产生备份'
        for name in ('L1', 'L2', 'L3', 'V1', 'V2', 'V3'):
            assert os.path.isfile(os.path.join(workdir, '1', name + '.dxf'))

        result = core.main(workdir,
                           os.path.join(workdir, 'config.ini'))
        assert result is None or result == 0
        film_dir = os.path.join(workdir, '菲林')
        ldi_dir = os.path.join(workdir, 'LDI')
        assert os.path.isdir(film_dir) and os.listdir(film_dir)
        assert os.path.isdir(ldi_dir) and os.listdir(ldi_dir)

        # 再次切片：原区块目录应被备份
        second = slice3d.slice_block_to_workdir(
            model_path=model, workdir=workdir, block=1,
            form_layout=layout, config_path=os.path.join(workdir, 'config.ini'),
            log=lambda text: None)
        assert second['backup'] and os.path.isdir(second['backup'])
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main():
    tests = [
        test_options_defaults,
        test_parse_layer_stack_top_down,
        test_parse_layer_stack_bottom_up_and_errors,
        test_circle_classification,
        test_step_input_reports_clear_error,
        test_slice_and_read_back,
        test_duplicate_layer_names_merge,
        test_shipped_form_table_parses,
        test_end_to_end_generation,
    ]
    failures = []
    for test in tests:
        try:
            test()
            print('PASS %s' % test.__name__)
        except Exception as exc:  # noqa: BLE001 - 自检脚本需汇总所有失败
            failures.append((test.__name__, exc))
            print('FAIL %s: %s' % (test.__name__, exc))
    print('-' * 60)
    if failures:
        print('失败 %d / %d' % (len(failures), len(tests)))
        return 1
    print('全部通过（%d 项）' % len(tests))
    return 0


if __name__ == '__main__':
    sys.exit(main())
