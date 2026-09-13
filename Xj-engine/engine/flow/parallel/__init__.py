"""LangGraph 内部动态拓扑并行支持包。"""

# 分支状态常量
BRANCH_PENDING = "pending"
BRANCH_RUNNING = "running"
BRANCH_SUCCESS = "success"
BRANCH_FAILED = "failed"
BRANCH_CANCEL = "cancel"

# 流程内部临时状态（仅用于 Dispatcher / Aggregator 路由）
STATUS_WAIT_AGGREGATE = "WAIT_BRANCH_AGGREGATE"
STATUS_SCAN_NEXT_BATCH = "SCAN_NEXT_BATCH"
STATUS_EXIT_PARALLEL_ZONE = "EXIT_PARALLEL_ZONE"
