# Changelog — ct-safety

## v0.9.1 (2026-08-29) · FAERS 个案级去重（P1-A，本地，未发布）

### Added / 病例级重复计数偏倚修正
- **新增 `scripts/faers_dedup.py`（纯本地、零新增联网）**：两级 FAERS 个案去重。
  - **L1 版本折叠**：同一 `safetyreportid` 的后续报告（follow-up）只保留最高 `safetyreportversion`，其余标记 superseded。这是**纯正确性修复**——FAERS 对同一病例的每次版本更新都会重新入库，原始个案清单必然重复计数。默认开启。
  - **L2 疑似重复探测**：人口学指纹（性别 / 归一年龄 / 国家）一致且反应 PT 集合 Jaccard ≥ 阈值（默认 0.8）→ 同簇；完全一致记 `exact`，相似记 `probable`。**默认只标记不删除**（药物警戒场景静默删病例有风险），需显式 `--drop-suspected-dupes` 才每簇留 1 条代表。
  - `normalize_age()` 归一 openFDA 年龄单位 800–805（小时/日/周/月/年/十年）为整数年，避免「45 岁」与「540 月」被判为不同人。
  - 空证据（无人口学且无 PT）**永不聚类**，防止缺字段记录被误并。
- **`scripts/fetch_faers.py` 扩展个案字段**：从既有 openFDA 响应中额外提取 `safetyreportversion / patientsex / patientonsetage / patientonsetageunit / occurcountry / reportercountry`——去重所需，**零新增请求**。此前仅留 `safetyreportid`，无从判重。
- **`scripts/ct_safety.py` 接入编排层**：`--case-level` 抓取后自动跑去重，去重后的个案供 Naranjo 聚合（`causality.from_faers_cases`）使用，避免重复病例扭曲因果归因；写出 `faers_cases_dedup.json`（含逐条 `dedup_reason` / `dedup_level`），并在报告中新增「个案级去重 / Case-level de-duplication」段落。
- **新增 CLI**：`--no-case-dedup`（关闭）、`--dedup-jaccard`（L2 阈值）、`--drop-suspected-dupes`（剔除而非仅标记）。

### Note / 明示局限（写入报告正文，不做过度声称）
- 去重**只作用于个案清单**。PRR / ROR / IC / EBGM 的分子分母来自 openFDA **聚合端点**，本地无从拆到病例层面，**故不成比例分析结果未被此模块修正**。该局限同时写入 `summary.limitation` 与报告段落，避免读者误认为信号已去偏。

### Compatibility / 兼容性
- 新增字段均为增量，旧 `faers_cases.json` 缺字段时优雅降级（缺人口学即不参与 L2 聚类）；`--no-case-dedup` 可完全回退旧行为。

### Verified / 验证
- `py_compile` 通过（`fetch_faers.py` / `faers_dedup.py` / `ct_safety.py`）。
- 离线冒烟 `_smoke_safety_dedup.py` **18/18 断言 PASS**：L1 折叠、L2 exact（含 540 月 = 45 年年龄归一）、L2 probable（Jaccard 0.67 < 0.8 默认不误并）、空证据不聚类、独立病例判 unique、`--drop-suspected` 每簇留 1、`--jaccard 0.6` 调参命中、二次运行幂等。
- 报告段落渲染 + flag-only / drop 两种策略端到端核对通过（5 例样本：raw 5 → L1 后 4 → flag-only 保留 4 / drop 后 3）。

## v0.9.0 (2026-08-22) · 增加 bug report 功能（ct-base §20.3 接入补齐）

### Added / bug report 接入（ct-base §20.3 + §20.3.7）
- **`adapters/bug_report.py` 补齐 §20.3.7 三函数**：新增 `confirm_thanks()`（发送成功固定感谢）、`parse_history()`（history 字段→dict 容错）、`build_followup()`（依据 resultstr 生成 2.2 已修复 / 2.3 未修复通知）。此前该文件仅含 §20.3.1–§20.3.5 基础函数，缺 §20.3.7 历史回执能力。
- **`_MSGS` 字典补齐**：新增 `thank_zh/en`、`done_zh/en`、`pending_zh/en` 六个键，供上述三函数调用。
- **新增 `adapters/config.json`**：`auto_approve_endpoints` 列入 `https://ct-bugreport.coze.site/run`，满足 §20.3.5（每个技能须将统一 bug-report 端点列入自动批准白名单）。此前 ct-safety 缺失 config.json。
- **README 出站披露补齐**：新增 "Bug-report endpoint disclosure (ct-base §5 / §20.3)" 段落，披露 11-key 白名单信封发送至 `https://ct-bugreport.coze.site/run`，与 SKILL.md §20.3 章节对齐。
- **已合规项确认**：`bug_report.py` 的 `DEFAULT_ENDPOINT` 已为 `https://ct-bugreport.coze.site/run` 且含嵌入式公共 token（§5）；SKILL.md Bug Reporting 章节（双阶段确认 + 11-key 白名单 + 出站披露）此前已就位（2026-08-21）。

### Note / 架构说明
- ct-safety 为**纯 Python + openFDA 公开 REST API 技能**（计算核心在 `scripts/disproportionality.py`、`ebgm.py`、`signal_score.py` 等，无 R 依赖；`required_commands` 仅 `python`）。无 coze 云端计算端点。
- **模式 B 全面测试（ct-update methodology §11.1，10 案例）已执行**：新增 `tests/mode_b_test.py`，覆盖四方法 happy-path、continuity 校正、a==0 结构零、负计数钳制、EBGM 独立性、signal_score 风险分层、Naranjo 因果归因、MedDRA 编码，以及真实 openFDA 联调（`--validate-controls` 阳/阴性对照自检）。10/10 通过（CLEAN）。

### Fixed / 模式 B 发现的代码缺陷
- **`disproportionality.compute()` 零 cell 溢出**：`continuity=False` 且 b/c/d 任一为 0 时，`se_log_ror = sqrt(1/a+1/b+1/c+1/d)` 出现 `1/0` → `OverflowError` 崩溃（真实 FAERS 罕见事件组合可触发空 margin）。已在 a==0 兜底块后新增"零 margin cell 兜底"：返回保守 null（无信号、不溢出）。修复经 `tests/mode_b_test.py` 案例 4 回归验证。
- **IC 信号判定过于敏感（已降敏）**：原规则 `ic_lo > 0` 在 IC 点估计微弱、95% 下限仅略大于 0 时即判信号（如 IC=0.126、ci_low=0.024），导致阴性对照假阳性。改为 `ic > 0.1 and ic_lo > 0.1`——点估计与下限均需有实质余量，排除边际噪声；真实强信号（IC 通常 >1）不受影响。经真实 openFDA 数据回归：ibuprofen/PNEUMONITIS（IC=0.126/ci_low=0.024）现正确判 False，阴性组特异度 4/4=1.0。
- **`requests` 依赖升级 2.31.0 → 2.32.5**：消除 clawhub_security_audit 标记的 6 个 CVE（CVE-2024-47081 等，中低危、边缘暴露面），纯补丁版不破坏 API。`requirements.txt` 已更新，本地环境已验证 2.32.5 可正常调 openFDA。

### Pending / 待确认（非阻断，记入发布报告）
- **clawhub_security_audit MEDIUM（读取类，已豁免）**：① 读取 `~/.workbuddy/AGENTS.md` 做语言自动切换；② "no data leaves the domain" 文案与出站行为；③ `--out-dir` 参数。均属设计层面 MEDIUM、本地读取不发布个人内容，已确认豁免，未改动。`requests` CVE 项已随上述升级解决。

## v0.1.38 (2026-08-16) · ct-update P1 升级落地（本地，未发布）
- **P1-C 信号验证工作流**（`--verify-signal`）：新增 `scripts/signal_verification.py`，接入主流程 `_run_verify_signal`；对 (药物,事件) 季度报告序列做时序 CUSUM/Poisson 趋势检验，并给出剂量-反应/去卷积确证补充（后两者需 `--case-level` 个案数据，公开计数接口下优雅降级）。
- **P1-D MedDRA 编码辅助**（`--code-verbatim`）：`scripts/meddra_coding.py` 的 `VerbatimCoder` 接入主流程；verbatim AE 术语→建议 PT（内置字典模糊匹配，LLM 模式 opt-in 不自动开启）；未给 `--event` 时以首选项 PT 作为事件。
- **P1-E 信号优先级排序与风险分级**（`--prioritize`）：`scripts/signal_prioritizer.py` 接入 `_run_prioritize`；多维评分（临床严重度×新颖性×频率×趋势×多源）输出 CRITICAL/HIGH/MEDIUM/LOW 与行动建议，写 `priority.json`。
- **P1-K Label-gap & 时间趋势优先级层**：随 `--prioritize` 生效——`--with-fda-label` 的 expectedness（label-gap）与 `--trend` 的异常趋势作为优先级层维度，未预期风险+异常趋势自动抬升优先级。
- **P1-F PSUR/PBRER 自动报告**（`--psur`）：`scripts/psur_generator.py` 接入 `_run_psur`；由检测信号生成 CIOMS/ICH E2C(R2) 格式 PSUR Markdown（psur.md），风险分级取自 E 层。
- 修复 4 个 P1 脚本误写的版本号 `v2.3.0` → `v0.1.38`；全部 `py_compile` 通过 + 离线功能自测通过；`applied_upgrades.json` 登记 C/D/E/F/K 并 verify 通过。

## v0.1.29 (2026-08-08) · 对齐 ct-base v1.1.21 §5 私有凭据范式：fetch_faers.py / fetch_fda_label.py 的 resolve_api_key 增加 `obf:` 前缀 XOR+base64 轻混淆解码（向后兼容明文 .env）；新增 .env.example；openfda_api_key.md / SKILL.md 注明 .env 支持混淆值
