# 人工 C/Cangjie 数据对

本目录用于保存导师要求的人工翻译数据对。每个 case 至少包含：

- `core.c`：Csmith 原始程序经过 sanitizer 后得到的核心 C 程序。
- `reference.cj`：人工翻译并确认语义的仓颉参考程序。
- `features.json`：该样本的 level、Csmith profile 来源和语法/语义特性标签。

推荐按复杂度分层组织：

```text
dataset/manual_pairs/
  level_0_basic/
  level_1_array/
  level_2_side_effect/
  level_3_pointer_alias/
```

该目录服务于数据对驱动的后端扩展流程：前端和 IR 已经固定，目标语言相关逻辑不预先一次性写完整代码生成器，而是让 LLM 根据人工 C/目标语言数据对生成某个 IR 节点的候选输出规则。生成的规则先作为候选规则保存或写入规则集，再用人工数据对和 checksum 差分测试验证。

验证当前 emitter 对人工数据对的支持情况：

```bash
conda run -n py313 python -m translator.manual_pairs.eval --root dataset/manual_pairs
```

验证数据对驱动规则生成路径，即只使用 `GeneratedCangjieEmitter` 与 `ruleset_autogen_b.py`：

```bash
conda run -n py313 python -m translator.manual_pairs.eval \
  --root dataset/manual_pairs \
  --frontend b
```

从 Csmith seed 生成一个待人工翻译的数据对目录：

```bash
conda run -n py313 python -m translator.manual_pairs.scaffold \
  --seed 101 \
  --level level_1_array \
  --csmith-profile profile_v1 \
  --flags-sh Csmith/profile_v1/flags_v1.sh \
  --prob-txt Csmith/profile_v0/prob_v0.txt \
  --feature array \
  --feature while
```

基于人工数据对让 LLM 生成某个 IR 节点的 emitter 候选规则：

```bash
conda run -n py313 python -m translator.manual_pairs.learn \
  --root dataset/manual_pairs \
  --target Cangjie \
  --backend b \
  --feature array_index \
  --rule expr:Index
```

如果当前网络或接口不稳定，也可以只导出 prompt，然后把 prompt 交给 Codex 插件或网页模型生成 JSON 候选规则：

```bash
conda run -n py313 python -m translator.manual_pairs.learn \
  --root dataset/manual_pairs \
  --target Cangjie \
  --backend b \
  --feature array_index \
  --rule expr:Index \
  --dump-prompt \
  --out-dir dataset/manual_pair_learn/prompts
```

确认候选规则后写入 `ruleset_autogen.py` 并重新验证人工数据对：

```bash
conda run -n py313 python -m translator.manual_pairs.learn \
  --root dataset/manual_pairs \
  --target Cangjie \
  --backend b \
  --feature array_index \
  --rule expr:Index \
  --apply \
  --replace \
  --eval
```

按 `learning_plan.json` 分阶段批量迭代生成 emitter 规则：

```bash
conda run -n py313 python -m translator.manual_pairs.iterate \
  --plan dataset/manual_pairs/learning_plan.json \
  --backend b \
  --dry-run
```

实际生成、写入并在每个阶段后验证：

```bash
conda run -n py313 python -m translator.manual_pairs.iterate \
  --plan dataset/manual_pairs/learning_plan.json \
  --backend b \
  --apply \
  --replace \
  --eval-each \
  --continue-on-error
```

只导出整个计划中各阶段的 prompt：

```bash
conda run -n py313 python -m translator.manual_pairs.iterate \
  --plan dataset/manual_pairs/learning_plan.json \
  --backend b \
  --dump-prompts
```

如需把人工参考程序作为 Codex/LLM 生成候选 emitter 规则时的上下文，可在运行 autofix 前设置：

```bash
export MANUAL_PAIR_ROOT=dataset/manual_pairs
export MANUAL_PAIR_FEATURES=array,index
export MANUAL_PAIR_MAX=3
```

数据对驱动规则生成路径也可以直接进入 Csmith checksum 差分测试闭环：

```bash
conda run -n py313 python -m translator.difftest.batch \
  --seed-from 1 \
  --seed-to 30 \
  --frontend b \
  --out-dir dataset/difftest_b_1_30 \
  --timeout 30 \
  --clean
```

当前数据对驱动路径的定位是“由人工数据对和生成规则逐步扩展的后端”。它已经复用 checksum runtime，并覆盖基础表达式、变量、赋值、条件、循环、数组写回、break/continue、函数调用和 C 风格 32 位整数 helper。复杂指针、结构体和更深层语义归因仍应继续通过新增人工 pair 与阶段化规则生成补齐。
