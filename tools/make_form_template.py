# coding:utf-8
"""生成/更新“成型参数信息填写表”模板（幂等，可重复执行）。

用法：

    python tools/make_form_template.py

在原有 7 列（层数名称/膜厚/通孔模式/烧结后厚度/层数/备注/丝网编号）之后
追加 3D 切片用的三列：`厚度(mm)`、`切片Z(mm)`、`层类型`，并新增“填写说明”
工作表逐列说明口径。列名是程序识别模板的唯一依据，改列名会让解析失效。
"""

import os
import sys

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill


REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(REPO_DIR, '成型参数信息填写表.xlsx')

# 表头顺序；前三列（层数名称/通孔模式）是程序定位表头的依据
HEADER = (
    '层数名称', '膜厚', '通孔模式', '烧结后厚度', '层数', '备注', '丝网编号',
    '厚度(mm)', '切片Z(mm)', '层类型',
)

# 需要用户填写的列（沿用原表的黄色底纹）
INPUT_COLUMNS = (
    '层数名称', '膜厚', '通孔模式', '烧结后厚度', '层数', '备注', '丝网编号',
    '厚度(mm)', '切片Z(mm)', '层类型',
)

NUMBER_COLUMNS = ('厚度(mm)', '切片Z(mm)')
WIDTHS = {
    '层数名称': 10, '膜厚': 8, '通孔模式': 11, '烧结后厚度': 12,
    '层数': 8, '备注': 16, '丝网编号': 22,
    '厚度(mm)': 12, '切片Z(mm)': 12, '层类型': 10,
}

INPUT_FILL = PatternFill('solid', fgColor='FFFFFF00')

# 每列口径说明：(列名, 是否必填, 说明)
COLUMN_HELP = (
    ('层数名称', '必填',
     '图层名，= 工作目录数字文件夹内该层 DXF 的文件名。图案层用 L/C/G/H/P '
     '开头（L1、C3、H2、G1…）；基板、MARK 等非图层行不参与生成与切片。'),
    ('膜厚', '选填',
     '印刷膜厚（µm），沿用原表格口径；仅作参考，不参与 3D 切片的 Z 计算。'),
    ('通孔模式', '必填',
     '该行图案层对应的通孔层名（如 V2）。填 4H、5H、0 或留空表示该行无通孔层。'),
    ('烧结后厚度', '选填',
     '烧结后的实际层厚（mm）；“厚度(mm)”留空时作为回退值参与 Z 累加。'),
    ('层数', '选填', '该行重复次数/工艺备注，不影响生成与切片。'),
    ('备注', '选填', '自由填写。'),
    ('丝网编号', '选填', '该行使用的丝网/生带编号。'),
    ('厚度(mm)', '3D 切片二选一',
     '该图层厚度（mm）。程序按“层序方向”从“切片Z基准”起逐层累加，取每层'
     '中面 Z 切片；各层厚度之和与 3D 模型 Z 高度偏差须在 5% 以内，否则中止。'),
    ('切片Z(mm)', '3D 切片二选一',
     '该图层中面在 3D 模型中的 Z 坐标（mm）。填了本列即优先使用，不再累加'
     '层厚，适合层厚不均或与模型高度对不上的情况。'),
    ('层类型', '选填',
     '填“跳过”表示该行不参与 3D 切片；留空则按层名前缀自动判定。'),
)

EXAMPLE_ROWS = (
    ('填法一：只填厚度（自上而下、切片Z基准留空）', '', '', ''),
    ('层数名称', '通孔模式', '厚度(mm)', '切片Z(mm)'),
    ('L1', 'V1', 0.1, None),
    ('L2', 'V2', 0.1, None),
    ('L3', 'V3', 0.1, None),
    ('→ 模型 Z 高度 0.3mm，三层中面 Z 依次为 0.25 / 0.15 / 0.05mm', '', '', ''),
    ('', '', '', ''),
    ('填法二：直接给每层中面 Z（与模型高度无关，最准）', '', '', ''),
    ('层数名称', '通孔模式', '厚度(mm)', '切片Z(mm)'),
    ('L1', 'V1', None, 0.25),
    ('L2', 'V2', None, 0.15),
    ('L3', 'V3', None, 0.05),
)

NOTES = (
    '程序在任意工作表中查找第一行含“层数名称 + 通孔模式”的表头（兼容旧表头'
    '“丝网号 + 通孔模式说明”），表头需出现在前 5 行内；列顺序不限。',
    '导入方式：GUI 主界面点“导入成型参数表…”，选择本文件；导入结果仅对本次'
    '会话生效，不写入 config.ini。',
    '同一图层名可以出现在多行（同一张网印在多层）：生成时按名称合并，3D 切片'
    '也会把这些 Z 处的轮廓合并成一个图层 DXF。',
    '3D 切片相关阈值与开关在 config.ini 的 [3D切片] 段：模型单位、切片采样'
    '容差、通孔直径下限/上限、近圆判定长宽比、圆度下限、层序方向、切片Z基准、'
    '覆盖前备份。',
)


def _header_columns(sheet):
    """返回 {列名: 列号}（读取表头行）。"""
    result = {}
    for col in range(1, sheet.max_column + 1):
        value = sheet.cell(row=1, column=col).value
        if value is None:
            continue
        name = str(value).strip()
        if name and name not in result:
            result[name] = col
    return result


def update_template(path):
    """在模板文件中补齐新增列与“填写说明”工作表。"""
    workbook = openpyxl.load_workbook(path)
    sheet = workbook.worksheets[0]
    columns = _header_columns(sheet)

    # 紧跟在最后一个表头列之后追加，避免原表中残留的空单元格撑出空列
    next_col = max(columns.values()) + 1
    for name in HEADER:
        if name in columns:
            continue
        col = next_col
        next_col += 1
        cell = sheet.cell(row=1, column=col, value=name)
        cell.font = Font(bold=True)
        sheet.cell(row=2, column=col)
        sheet.column_dimensions[cell.column_letter].width = WIDTHS.get(name, 12)
        columns[name] = col

    # 清掉表头范围之外的残留单元格（含格式），防止出现空列
    last_col = max(columns.values())
    for col in range(last_col + 1, sheet.max_column + 1):
        for row in range(1, sheet.max_row + 1):
            cell = sheet.cell(row=row, column=col)
            cell.value = None
            cell.fill = PatternFill()

    # 统一表头与数据区格式（原表数据行为黄色底纹）
    for name in HEADER:
        col = columns[name]
        sheet.cell(row=1, column=col).font = Font(bold=True)
        sheet.column_dimensions[
            sheet.cell(row=1, column=col).column_letter].width = \
            WIDTHS.get(name, 12)
        for row in range(2, sheet.max_row + 1):
            cell = sheet.cell(row=row, column=col)
            if name in INPUT_COLUMNS:
                cell.fill = INPUT_FILL
            if name in NUMBER_COLUMNS:
                cell.number_format = '0.###'
    sheet.freeze_panes = 'A2'

    build_help_sheet(workbook)
    workbook.save(path)
    return path


def build_help_sheet(workbook):
    """重建“填写说明”工作表。"""
    if '填写说明' in workbook.sheetnames:
        del workbook['填写说明']
    sheet = workbook.create_sheet('填写说明')
    sheet.column_dimensions['A'].width = 14
    sheet.column_dimensions['B'].width = 16
    sheet.column_dimensions['C'].width = 96

    title = sheet.cell(row=1, column=1, value='成型参数信息填写表 · 填写说明')
    title.font = Font(bold=True, size=12)
    sheet.cell(row=2, column=1,
               value='工作表“模版”为数据表，本页仅作说明，程序不会读取。')

    header_row = 4
    for col, text in enumerate(('列名', '是否必填', '说明'), start=1):
        cell = sheet.cell(row=header_row, column=col, value=text)
        cell.font = Font(bold=True)

    row = header_row + 1
    for name, required, text in COLUMN_HELP:
        sheet.cell(row=row, column=1, value=name)
        sheet.cell(row=row, column=2, value=required)
        cell = sheet.cell(row=row, column=3, value=text)
        cell.alignment = Alignment(wrap_text=True, vertical='top')
        row += 1

    row += 1
    cell = sheet.cell(row=row, column=1, value='3D 切片填法示例')
    cell.font = Font(bold=True)
    row += 1
    for values in EXAMPLE_ROWS:
        for col, value in enumerate(values, start=1):
            if value is not None and value != '':
                sheet.cell(row=row, column=col, value=value)
        row += 1

    row += 1
    cell = sheet.cell(row=row, column=1, value='其它说明')
    cell.font = Font(bold=True)
    row += 1
    for text in NOTES:
        cell = sheet.cell(row=row, column=1, value='• ' + text)
        cell.alignment = Alignment(wrap_text=True, vertical='top')
        sheet.merge_cells(start_row=row, start_column=1,
                          end_row=row, end_column=3)
        row += 1
    return sheet


def main():
    if not os.path.isfile(TEMPLATE_PATH):
        print('未找到模板文件：%s' % TEMPLATE_PATH)
        return 1
    update_template(TEMPLATE_PATH)
    print('已更新模板：%s' % TEMPLATE_PATH)
    return 0


if __name__ == '__main__':
    sys.exit(main())
