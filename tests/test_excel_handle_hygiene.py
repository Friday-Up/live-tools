import ast
from pathlib import Path
import unittest


LIVE_ROOT = Path(__file__).resolve().parents[1]


class ExcelHandleHygieneTest(unittest.TestCase):
    def test_production_workbooks_are_closed(self):
        offenders = []
        for path in sorted(LIVE_ROOT.glob("live-*/**/*.py")):
            if "tests" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                workbook_names = _workbook_assignment_names(node)
                if not workbook_names:
                    continue
                closed_names = _closed_names(node)
                missing = sorted(workbook_names - closed_names)
                if missing:
                    offenders.append(f"{path.relative_to(LIVE_ROOT)}:{node.lineno} missing close for {', '.join(missing)}")

        self.assertEqual(offenders, [])


def _workbook_assignment_names(function_node):
    names = set()
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Assign):
            continue
        if not _is_workbook_factory_call(node.value):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def _is_workbook_factory_call(node):
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in {"load_workbook", "Workbook"}
    if isinstance(func, ast.Attribute):
        return func.attr in {"load_workbook", "Workbook"}
    return False


def _closed_names(function_node):
    names = set()
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "close":
            continue
        if isinstance(func.value, ast.Name):
            names.add(func.value.id)
    return names


if __name__ == "__main__":
    unittest.main()
