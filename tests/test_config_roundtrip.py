# coding:utf-8
"""配置读写往返自检：保存配置不应重排节顺序或改写键名大小写。

不依赖 pytest，直接运行：

    python tests/test_config_roundtrip.py
"""

import difflib
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import drawfeilin_gui as gui  # noqa: E402


REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_repo_config_roundtrip_is_identical():
    """仓库自带 config.ini 读入再写回应完全一致（无节顺序/键名 churn）。"""
    source = os.path.join(REPO_DIR, 'config.ini')
    if not os.path.isfile(source):
        return
    tmp = tempfile.mkdtemp(prefix='drawfeilin_cfg_')
    try:
        target = os.path.join(tmp, 'config.ini')
        shutil.copy(source, target)
        with open(source, 'r', encoding='utf-8-sig') as handle:
            before = handle.read()

        data = gui.read_ini(target)
        gui.write_ini(target, data)

        with open(target, 'r', encoding='utf-8-sig') as handle:
            after = handle.read()
        diff = list(difflib.unified_diff(
            before.splitlines(), after.splitlines(),
            'before', 'after', lineterm=''))
        assert diff == [], '保存配置产生了差异：\n' + '\n'.join(diff[:20])

        # 节顺序与磁盘一致
        expected = [name for name in gui._existing_section_order(source)]
        assert list(data.keys()) == expected, (list(data.keys()), expected)
        assert os.path.isfile(target + '.bak'), '应生成 .bak 备份'
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_key_case_is_preserved():
    """含 ASCII 的键名（MARK旋转角度）与新增列键名不能被小写化。"""
    tmp = tempfile.mkdtemp(prefix='drawfeilin_cfg_')
    try:
        target = os.path.join(tmp, 'config.ini')
        with open(target, 'w', encoding='utf-8-sig') as handle:
            handle.write(
                '[DEFAULT]\n'
                'MARK旋转角度 = 90\n'
                '图案来源 = 原图\n'
                '\n'
                '[3D切片]\n'
                '切片Z基准 = 1.5\n'
                '覆盖前备份 = Yes\n')

        data = gui.read_ini(target)
        assert 'MARK旋转角度' in data['DEFAULT']
        assert 'mark旋转角度' not in data['DEFAULT']
        assert list(data['3D切片']) == ['切片Z基准', '覆盖前备份']

        gui.write_ini(target, data)
        text = open(target, 'r', encoding='utf-8-sig').read()
        assert 'MARK旋转角度 = 90' in text
        assert 'mark旋转角度' not in text
        assert '切片Z基准 = 1.5' in text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_new_section_appended_and_order_kept():
    """已有节保持原顺序，新增节追加在末尾。"""
    tmp = tempfile.mkdtemp(prefix='drawfeilin_cfg_')
    try:
        target = os.path.join(tmp, 'config.ini')
        with open(target, 'w', encoding='utf-8-sig') as handle:
            handle.write(
                '[DEFAULT]\n图案来源 = 原图\n'
                '\n[EXTRA]\n拼网列分割数 = 1\n'
                '\n[LONGTHROUGHHOLE]\n长通孔孔径 = 0.3\n')

        data = gui.read_ini(target)
        data['3D切片'] = {'模型单位': 'mm'}
        gui.write_ini(target, data)

        assert gui._existing_section_order(target) == [
            'DEFAULT', 'EXTRA', 'LONGTHROUGHHOLE', '3D切片']
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    tests = [
        test_repo_config_roundtrip_is_identical,
        test_key_case_is_preserved,
        test_new_section_appended_and_order_kept,
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
