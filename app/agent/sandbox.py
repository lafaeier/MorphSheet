import ast
import threading
from io import StringIO
import pandas as pd
import numpy as np

FORBIDDEN_IMPORTS = {
    'os', 'subprocess', 'shutil', 'sys', 'importlib', 'ctypes',
    'socket', 'http', 'urllib', 'requests', 'pathlib', 'glob',
    'pickle', 'marshal', 'code', 'codeop', 'io', 'fileinput',
    'signal', 'multiprocessing', 'threading', 'concurrent',
}

FORBIDDEN_CALLS = {
    '__import__', 'exec', 'eval', 'compile', 'open', 'input',
    'globals', 'locals', 'vars', 'dir', 'getattr', 'setattr',
    'breakpoint', '__builtins__', 'exit', 'quit',
}

FORBIDDEN_ATTRS = {
    '__class__', '__bases__', '__mro__', '__subclasses__',
    '__globals__', '__code__', '__closure__', '__dict__',
}


def scan_code(code: str) -> list[str]:
    """AST 静态扫描，返回发现的安全问题列表。"""
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"SyntaxError: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split('.')[0]
                if root in FORBIDDEN_IMPORTS:
                    issues.append(f"禁止导入模块: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split('.')[0]
                if root in FORBIDDEN_IMPORTS:
                    issues.append(f"禁止导入模块: {node.module}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                issues.append(f"禁止调用: {node.func.id}()")
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRS:
                issues.append(f"禁止访问属性: .{node.attr}")

    return issues


def execute(code: str, source_df: pd.DataFrame, timeout: int = 30) -> dict:
    """在受限环境中执行生成的 Pandas 代码。

    返回: {"success": bool, "dataframe": pd.DataFrame|None, "error": str|None}
    """
    safe_globals = {
        '__builtins__': {
            'True': True, 'False': False, 'None': None,
            'int': int, 'float': float, 'str': str, 'bool': bool,
            'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
            'len': len, 'range': range, 'enumerate': enumerate,
            'zip': zip, 'map': map, 'filter': filter,
            'sorted': sorted, 'reversed': reversed,
            'min': min, 'max': max, 'sum': sum, 'abs': abs,
            'round': round, 'pow': pow, 'divmod': divmod,
            'print': print, 'type': type,
            '__import__': __import__,  # AST 扫描已拦截危险模块
            'isinstance': isinstance, 'issubclass': issubclass,
            'Exception': Exception, 'ValueError': ValueError,
            'TypeError': TypeError, 'KeyError': KeyError,
            'AttributeError': AttributeError, 'IndexError': IndexError,
            'StopIteration': StopIteration,
            'complex': complex, 'bytes': bytes, 'bytearray': bytearray,
            'repr': repr, 'hash': hash, 'id': id,
            'format': format, 'slice': slice,
        },
        'pd': pd,
        'np': np,
        're': __import__('re'),
        'datetime': __import__('datetime'),
    }

    local_vars = {'df': source_df.copy()}

    result = {"success": False, "dataframe": None, "error": None}

    def target():
        try:
            exec(code, safe_globals, local_vars)
            if 'transform' not in local_vars:
                result["error"] = "代码中未定义 transform(df) 函数"
                return
            output = local_vars['transform'](local_vars['df'])
            if not isinstance(output, pd.DataFrame):
                result["error"] = f"transform() 返回值必须是 DataFrame，实际为 {type(output).__name__}"
                return
            result["success"] = True
            result["dataframe"] = output
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {str(e)}"

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        return {"success": False, "error": f"代码执行超时 ({timeout}s)"}

    return result
