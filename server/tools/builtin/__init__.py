"""tools/builtin — 内置工具集合.

每个子模块定义一个工具并在导入时自动 register()。
新增工具时在这里加一行 import，register_all() 会触发它。
"""

# 导入即注册（register_all 也会 import 本模块）
from tools.builtin import weather  # noqa: F401
from tools.builtin import image_gen  # noqa: F401
