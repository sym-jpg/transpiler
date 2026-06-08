# 渐进式 Csmith Profile 规划

本项目保留 `profile_v0` 作为现有大规模实验输入配置。新增的 `profile_v1`、`profile_v2`、`profile_v3` 只提供复杂度逐步提升的生成入口，不改变原有批测默认配置。

建议使用方式：

```bash
python -m translator.difftest.batch \
  --seed-from 1 \
  --seed-to 100 \
  --flags-sh Csmith/profile_v1/flags_v1.sh \
  --prob-txt Csmith/profile_v0/prob_v0.txt \
  --out-dir dataset/difftest_v1
```

阶段含义：

- `profile_v0`：当前稳定受限子集，用于论文已有 1-1000 seed 结果。
- `profile_v1`：略提高 block 和表达式复杂度，用于数组、循环、条件组合。
- `profile_v2`：继续提高表达式复杂度，用于副作用、短路和多维数组写回压力测试。
- `profile_v3`：更深 block 和更多函数，用于后续扩展指针、结构体等复杂特性前的压力层。

如果需要真正打开结构体、指针、bitfield 等概率，应复制 `profile_v0/prob_v0.txt` 为对应阶段的 `prob_vN.txt` 后按 Csmith 概率项逐步放开，并同步补充 `dataset/manual_pairs/level_N_*` 人工参考样例。

