"""tool-calling 能力包：α/β 双轨制工具调用。

核心模块：
- registry  从 YAML 注册声明 + Python entry point 加载工具
- dispatcher  从对话文本（"/tool name {json}"）中识别并触发调用
- router  REST 端点
"""
__version__ = "1.0.0"
