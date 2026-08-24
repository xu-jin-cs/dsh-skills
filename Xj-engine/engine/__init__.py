"""ETLEngine — 通用文档 ETL 引擎（2026-08-16）。

参考 AgentEngine（ET 契约引擎）架构：内核固定时序 + 契约化 payload + 出参 code 语义。
调用方只调 kernel.etl_engine(payload)，规则全部来自 payload。
"""
