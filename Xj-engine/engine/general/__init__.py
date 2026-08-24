"""engine.general — ETLEngine general 族行为实现层（U2）。

规则抽离铁律：本包零业务规则字面量——白名单/阈值/路径/开关/保护标记
一律由调用方从 contract_rules/*.yaml 读入后通过函数参数注入；
本包只承载行为实现（parser 提取、魔数字节表、存储原语、BM25 构建）。
零历史平台代码 import。
"""
