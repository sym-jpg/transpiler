# Csmith Profile v0（Carbon/仓颉共用输入分布）

本目录定义 Csmith 的 v0 受限配置，用于生成满足 `docs/subset_v0.md` 的最小可用 C 子集。

目录文件：
- `flags_v0.sh`：硬开关 + 复杂度上限（与 Csmith 版本相关，需要按 `csmith --help` 校准）
- `prob_v0.txt`：概率配置（从默认 dump 出来后修改，不在白名单的项设为 0）
- `README.md`（本文件）：说明与用法

---

## 使用方式

### 1) 生成默认概率配置（第一次需要）
不同 Csmith 版本参数名略有差异，请先运行：
- `csmith --help` 查找 dump 默认概率的选项
- 常见形式：`--dump-default-probabilities`

然后把输出保存为 `prob_default.txt`，并复制为 `prob_v0.txt`：

```bash
csmith --dump-default-probabilities > prob_default.txt
cp prob_default.txt prob_v0.txt