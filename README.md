# Csmith 驱动的新兴语言编译器差分测试

本项目将 Csmith 生成的 C 程序翻译为目标语言程序，并比较两端运行后的校验和，用于发现翻译语义差异和潜在的目标语言编译器问题。目前包含较完整的仓颉代码生成流程、基础 Carbon 代码生成流程，以及人工数据对驱动的大模型辅助规则扩展路线。

## 项目结构

- `sanitizer/`：提取 Csmith 核心程序和校验和变量。
- `translator/frontend/`：Clang AST 解析及 C 到中间表示转换。
- `translator/ir/`：中间表示节点、类型系统和语义归一化。
- `translator/backend/`：仓颉、Carbon 代码生成器及生成规则。
- `translator/difftest/`：批量生成、翻译、编译、运行和结果汇总。
- `translator/manual_pairs/`：人工数据对学习与验证工具。
- `translator/autofix/`：基于 LLM 的候选规则生成和自动修复实验。
- `dataset/manual_pairs/`：用于规则学习和回归验证的小规模人工数据对。
- `Csmith/`：渐进式 Csmith 概率配置。

大规模测试产物不纳入 Git 仓库，默认写入 `dataset/difftest/`。

## 环境要求

- Python 3.11 及以上版本
- Csmith 2.4.0
- C 编译器，例如 GCC 或 Clang
- 仓颉工具链 `cjc`，运行仓颉差分测试时需要
- Carbon 工具链，验证 Carbon 输出时需要

安装 Python 依赖：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

若 Python 包未能自动定位 libclang，可设置：

```bash
export LIBCLANG_FILE=/absolute/path/to/libclang
export CSMITH_INCLUDE=/absolute/path/to/csmith/include
```

## 基本使用

将预处理后的核心 C 程序翻译为仓颉：

```bash
python -m translator.frontend.clang_frontend input.c --autofix-iters 0 --out output.cj
```

翻译为 Carbon：

```bash
python -m translator.frontend.clang_frontend_carbon input.c --out output.carbon
```

运行仓颉差分测试：

```bash
python -m translator.difftest.batch \
  --seed-from 1 \
  --seed-to 100 \
  --flags-sh Csmith/profile_v0/flags_v0.sh \
  --prob-txt Csmith/profile_v0/prob_v0.txt \
  --out-dir dataset/difftest/seed_1_100
```

运行 Carbon 批量翻译：

```bash
python -m translator.difftest.batch_carbon \
  --seed-from 1 \
  --seed-to 100 \
  --out-dir dataset/difftest/carbon_1_100
```

## 大模型辅助规则生成

复制 `.env.example` 为 `.env.local`，填写兼容 Responses API 的服务地址、密钥和模型名称。密钥文件已被 Git 忽略。

```bash
python -m translator.manual_pairs.learn \
  --backend b \
  --root dataset/manual_pairs \
  --rule expr:Binary
```

模型生成的规则仍需通过人工数据对和差分测试验证。

## 当前限制

项目针对受限 Csmith-C 子集，不支持完整 C 语言。当前主要限制包括复杂指针别名、指针算术、任意内存布局、结构体、联合体、位域、浮点和 `goto` 等。
