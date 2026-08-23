# 临床试验安全信号专家（ct-safety）

[🇨🇳 中文](#) ｜ [🇺🇸 English](./README.md)

<div align="center">
  <img src="assets/icon.svg" width="240" height="240" alt="ct-safety 图标"/>
</div>

> 一个默认安全的药物警戒技能：对 **FDA FAERS** 公开不良事件数据筛查药物-事件安全信号（PRR / ROR / IC / EBGM，含 95% 置信区间），并可选叠加中国官方药物警戒通报作佐证。仅读取公开数据——**零保密输入（B 档）**。

## 适用人群

`ct-*` 临床试验技能家族专用于解决临床试验全生命周期的各类需求，主要面向三类人群：

- **各制药企业的临床试验从业者** —— 申办方、CRO，以及医学 / 统计 / 注册等角色；
- **在医疗机构中设计、管理临床试验项目，或参与临床试验研究实务的医护人员**；
- **希望系统学习临床试验知识的医学专业学生**。

## 如何在对话里使用

直接用自然语言告诉助手你想做什么即可。下面是可直接复制的真实示例——示例只给标签与示意，真实计算遵循下方「安全」一节的两段式安全流程。

### 示例 1 · 某药的高发不良事件

**你这样说：**
> 帮我校查一下 candesartan 在 FAERS 里报告最多的不良事件。

**助手会这样回（示意）：**
> 我会从 FAERS 公开数据库汇总 candesartan 报告最多的反应，含计数、严重性、器官系统归类——作为提出具体信号问题前的安全性基线。

**如何触发真实计算：**
> 概览会自动执行。说「直接计算」技能即抓取 FAERS 各分面并打印汇总；未给 `--event` 时不会报错——自动降级为高频不良事件报告。

### 示例 2 · 某个具体药物-事件信号

**你这样说：**
> candesartan 会不会增加血管性水肿风险？

**助手会这样回（示意）：**
> 我会基于 FAERS 构建药物-事件 2×2 表，报告 PRR / ROR / IC / EBGM 及 95% 置信区间与信号判定，并对 Top-N 事件做 Benjamini-Hochberg FDR 校正。

**如何触发真实计算：**
> 概览（总数 + Top-N）先自动跑出，然后停下等你确认。要跑详细信号检测，回复「确认，跑详情」即可——或直接说「直接计算」跳过预览立即执行。

### 示例 3 · 用中国官方药物警戒通报佐证

**你这样说：**
> 有没有奥希替尼肺炎的中国官方安全通报？

**助手会这样回（示意）：**
> 我会检索**国家药品不良反应监测中心**（cdr-adr.org.cn）公开栏目，用药物+事件关键词匹配官方通报，作为 FAERS 量化信号的**定性佐证**。这些仅属叙事性通报、非个案计数，因此绝不进入 disproportionality 计算。

**如何触发真实计算：**
> 中文关键词检索是详情步骤的一部分。确认详情步骤（或「直接计算」），并传中文词以提高召回：如 药名 奥希替尼 / 事件 肺炎。

### 示例 4 · 复杂场景：多药对比（弹出菜单）

**你这样说：**
> 对比一下 osimertinib、gefitinib、erlotinib 在肺炎上的安全性。

**助手会这样回（示意）：**
> 这事涉及多项选择，我不替你拍板，先给一个路由菜单：
>
> - **单事件对比（肺炎）——校正 ROR（aROR）** · 焦点药 vs 合并参照池
> - **叠加 FDR / 时间趋势 / 对照验证** · 更严谨，查询更多
> - **叠加中国 PV + FDA 标签三角验证 + 安全信号评分（T1–T4）** · 三源证据
> - **还拿不准 → 详细解释差异** · 我先逐条讲清每个选项的取舍，你再决定

**如何触发真实计算：**
> 选一个菜单项（或先选「详细解释差异」）。选定配置后同样走两段式：先轻量概览，详细检索等你确认才执行（或「直接计算」立即跑）。

### 示例 5 · 模糊场景：不确定要比什么（grill-me 追问）

**你这样说：**
> 我想看看这个药的安全性，但不知道该跟什么比。

**助手会这样回（示意）：**
> 没关系——我逐分支帮你理清：
>
> 1. 你心里**有具体事件**吗（如肺炎），还是先想看**高发反应**？
> 2. 这是**单药**分析，还是想跟**同类的竞品头对头**比？
> 3. 需要**带证据分级（T1–T4）的中/美官方佐证**，还是先快速筛查？
>
> 回答后我会给出确切分析方案，而不是甩一整张菜单。

**如何触发真实计算：**
> 分支理清意图后，同样的两段式适用：概览自动跑，详情等你确认（或「直接计算」立即执行）。

### 示例 6 · 强制真跑

**你这样说：**
> 直接计算——现在就跑 candesartan 血管性水肿的信号检测。

**助手会这样回（示意）：**
> 收到。我跳过预览，立即执行详细 FAERS 检索与 disproportionality 分析，并返回 JSON / Markdown 报告。

**如何触发真实计算：**
> 「直接计算」是显式覆盖指令，会立即执行详情步骤。

## 你能做些什么 —— 场景索引

| 能力 | 方法 | 试试这样说 |
|---|---|---|
| 药物不良事件画像 | FAERS 计数（高发反应、严重性、人口学） | 「查 candesartan 在 FAERS 里报告最多的反应」 |
| 药物-事件信号检测 | PRR / ROR / IC / EBGM + 95% CI + 信号判定 | 「candesartan 会不会升高血管性水肿风险？」 |
| 多方法交叉判定 | ROR 下限 CI > 1 · PRR ≥ 2 且 χ² ≥ 4 · IC 下限 CI > 0 · EBGM EB05 ≥ 2 | 「这个信号在多个方法上稳健吗？」 |
| 中国官方 PV 佐证 | cdr-adr.org.cn 公开通报（仅定性） | 「有任何中国官方的奥希替尼肺炎通报吗？」 |
| 多事件 FDR 控制 | Benjamini-Hochberg q 值（Top-N 事件） | 「对所有高发事件做假发现率控制筛查」 |
| PT→SOC 器官归类 | MedDRA PT → 系统器官分类映射 | 「把这些信号按器官系统分组」 |
| 时间趋势异常 | `--trend` CUSUM / rolling-Z / changepoint | 「奥希替尼肺炎报告最近有突增吗？」 |
| 多药校正 ROR | aROR 经 `--compare-drugs`（焦点 vs 合并参照） | 「对比 osimertinib 与 gefitinib 的肺炎风险」 |
| 多源三角验证 + 评分 | `--with-fda-label` → 安全信号评分 0–100、T1–T4 | 「给我一个带证据分级的综合信号评分」 |
| 非 ASCII 药名 | `--drug 阿司匹林` 自动解析为 INN | 「查一下阿司匹林的不良反应」 |

## 常见问题 FAQ

**只给一个药名、不给事件能算吗？**
能。只给 `--drug`（或只说药名）不再报错——自动降级为高频不良事件报告（无 2×2 表）。要算具体信号，请补一个事件（MedDRA 首选术语，如 `ANGIOEDEMA`）。

**PRR 和 ROR 有什么区别？**
二者都基于药物-事件 2×2 表的 disproportionality。ROR（报告比值比）以比值比形式呈现，下限 95% CI > 1 即判信号；PRR（比例报告比）在 PRR ≥ 2 **且** χ² ≥ 4 时判信号；IC（信息成分，UMC/VigiBase）下限 CI > 0 判信号；EBGM（FDA MGPS 贝叶斯收缩）EB05 ≥ 2 判信号。技能同时报告四种，并对多事件做 Benjamini-Hochberg FDR 校正。

**怎么才能真跑出信号表，而不是只看代码？**
默认只给概览（总数 + Top-N）并停下。确认详情步骤，或说「直接计算」——技能即执行 FAERS 检索与 disproportionality 分析，返回 JSON / Markdown（及可选 PNG 图）。

**中文环境输出是中文吗？**
是。技能跟随你的输入语言：`zh-*` 区域下提示与报告切中文，其余切英文。代码注释与文档仅英文。

**openFDA key 怎么配？**
默认**无需 key** 即可运行（匿名 240 次/分、1,000 次/天，按 IP）。仅高吞吐场景才需免费 key，到 https://open.fda.gov/api/register/ 邮箱即注册（无信用卡）。用以下三种自配置方式之一提供：
- 环境变量：`export OPENFDA_API_KEY=YOUR_KEY`（推荐，每个脚本自动读取）；
- 技能根目录 `.env` 文件：`OPENFDA_API_KEY=YOUR_KEY`（已 git-ignore，不会随包发布）；
- 命令行：`--api-key YOUR_KEY`。

切勿在聊天里发送 key，也别把它写进任何会随技能发布的文件——key 仅本地存储，且仅经 HTTPS 发往官方 openFDA API。

## 安全（安全预览）

**两段式流程，默认安全。** 第一步（概览：总数 + Top-N）自动执行。第二步（详细检索 / 信号检测）**仅在你显式确认后**才执行——或当你说「直接计算」时。在确认前不会触发任何大批量下载，随口一问也不会跑重计算。

**出站披露。** 技能仅读取公开源：
- **FDA FAERS** 经 openFDA `https://api.fda.gov/drug/event.json`（必需，量化）；
- **FDA Label** 经 openFDA `drug/label.json`（使用 `--with-fda-label` 时的可选第三源）；
- **国家药品不良反应监测中心** `cdr-adr.org.cn` 公开栏目（使用 `--with-cn-pv` 时的可选源，仅定性佐证——叙事通报、无个案计数，绝不进入 disproportionality）。

**零保密数据或信息输入**（B 档：普通数据输入 + 对外检索）。NMPA 主站被 WAF 拦截（HTTP 412），已刻意排除。你的 openFDA key（若使用）**仅本地存储**，且**仅经 HTTPS 发往官方 openFDA API**。

信号检测仅供筛查，非因果结论；监管提交（DSUR / PBRER / 标签变更）须另行按 GCP / ICH E2 评估。

## 进阶参考

开发者 CLI、参数、数据源边界与错误处理放在此处（按使用者视角布局，从首屏下移）。

### 数据源

| 源 | 访问方式 | 状态 |
|---|---|---|
| FDA FAERS（openFDA `drug/event.json`） | 官方公开 REST API，直连，低频无需 key | 必需（B 档，量化） |
| FDA Label（openFDA `drug/label.json`） | 同 openFDA，无需 key；`adverse_reactions` / `warnings` | 可选 `--with-fda-label`（标签内/外风险） |
| 国家不良反应监测中心（cdr-adr.org.cn） | 公开栏目抓取（药物警戒快讯 / 数据报告 / 通知通告 / 器械·化妆品警戒快讯）；无 WAF、无需 key | 可选 `--with-cn-pv`（仅定性佐证） |

### 环境要求

- Python 3.10+（推荐 Anaconda `C:\Tools\anaconda3\python.exe`）。
- 必需：`requests`。可选：`matplotlib`（PNG 图）。网络：只读 FAERS 公开 API。

### CLI 工作流

```bash
# Step 1 — 概览（自动执行，总数+Top-N，然后停下等你确认）
python scripts/overview.py --drug "candesartan" --top 10 \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# Step 2 — 汇总 Excel（默认 present 流程；count 分面、秒级、全量匹配基数）
python scripts/fetch_reports.py --drug "candesartan" \
    --date-from 20200101 --date-to 20261231 --out-xlsx faers_summary.xlsx

# Step 3 — 详情下载（仅当你明确要个案时；硬上限 10000）
python scripts/fetch_reports.py --drug "candesartan" --max 10000 \
    --date-from 20200101 --date-to 20261231 --run \
    --out faers_reports_raw.json --out-csv faers_reports.csv --out-xlsx faers_reports.xlsx

# 药物-事件信号检测（2x2 -> PRR/ROR/IC/EBGM）；确认后才跑
python scripts/ct_safety.py --drug "candesartan" --event "ANGIOEDEMA" \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# 中国 PV 定性佐证（可选）
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --with-cn-pv --drug-cn "奥希替尼" --event-cn "肺炎" --run --out-dir ./out

# 连续性校正（默认开启；--no-continuity 复现 v0.1.8）
python scripts/ct_safety.py --drug "candesartan" --event "ANGIOEDEMA" \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out
# 流水线自检（阳性/阴性对照，无需 --drug/--event）
python scripts/ct_safety.py --validate-controls --out-dir ./out
# 时间趋势异常（需 --event）
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --trend --date-from 20200101 --date-to 20261231 --run --out-dir ./out
# 多药校正 ROR（首药=焦点，其余=参照池；需 --event）
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --compare-drugs osimertinib gefitinib erlotinib \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out
# 多源三角验证 + 安全信号评分（0-100）+ T1-T4（默认 FAERS×CN-PV；加 --with-fda-label 启用第三源）
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --with-cn-pv --drug-cn "奥希替尼" --event-cn "肺炎" --with-fda-label \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# 独立 CN-PV 检索（无需 FAERS）
python scripts/fetch_cn_pv.py --drug "奥希替尼" --event-cn "肝损伤" --run --out cn_pv.json
```

### FAERS 字段边界（实测）

- **可检索 / 可 count**：`patient.drug.medicinalproduct`、`patient.reaction.reactionmeddrapt`（Top-N 用 `.exact`）、`receivedate`、`serious*` 布尔、`patient.patientsex`（1=男 / 2=女 / 0=未知）。
- **API 不可分面（仅存于个案体内）**：`patient.patientage`、`primarysource.reportertype`、`primarysourcecountry`（用 `.exact`）。需下载个案（`--run`）才能在本地统计年龄 / 国家 / 报告者类型。
- 多词 MedDRA PT：部分三词短语（`RENAL FAILURE ACUTE`）持续 404——改用标准 PT `ACUTE KIDNEY INJURY`；两词 PT（如 `HEPATIC FAILURE`）通常可用。`total()` 自动「404 → `.exact`」降级。

### 错误处理

| 错误 | 原因 | 修复 |
|---|---|---|
| `URLError` / timeout | 无网络 / 代理 | 确认 `api.fda.gov` 可达；配置代理 |
| HTTP 429 / 限流 | 超 openFDA 限额（按请求次数，非按条数）：匿名 240/分、1,000/天按 IP；免费 key 240/分、120,000/天按 key | 加 `--api-key`；或降频 |
| 只给 `--drug` 未给 `--event` | 意图是看高发反应而非 2×2 信号 | 自动降级为 Top-N 报告；加 `--event <PT>` 算信号 |
| 字段名不匹配 | 药名字段错 | 默认 `patient.drug.medicinalproduct`；用 `--field patient.drug.openfda.substance_name` 标准化 |
| CN-PV HTTP 412 / WAF | nmpa.gov.cn 被拦截 | 预期内——仅抓 cdr-adr.org.cn；NMPA 已排除 |
| CN-PV 0 命中 | 关键词过窄 | 传 `--drug-cn` + `--event-cn`；调大 `--cn-max` |
| 多词事件持续 404 | 该三词 PT 未被索引 | 换标准 MedDRA PT |
| `--max > 10000` | 突破免费配额上限 | 自动 clamp 到 `HARD_CAP=10000`；注意选择偏倚（API 返回顺序，非随机） |

### 比较研究设计模式（多药 / 单 SOC）

当用户要求*对比*（「compare X vs Y」「同类头对头」「active-comparator disproportionality」「可发表的比较 PV 论文」），切换到比较轨道：(1) 数据准备 → (2) 选研究风格 + Lite/Standard/Advanced/Publication+ 工作负载 → (3) 选指标、对照逻辑、稳健性路线 → (4) 给每个结果打证据分级。硬规则：绝不在未准备原始计数上跑 disproportionality；始终先展示四种配置再推荐一种；每个实质结果带分级标签（`[Tier 1]` 信号 / `[Tier 2]` 比较 / `[Tier 3]` 稳健性）；Tier-4 主张（发生率、因果、获益-风险、处方）无外部数据禁止。

### 回归测试

```bash
python tests/run_tests.py            # 离线（mock 网络）
python tests/run_tests.py --live     # 额外跑 tests/test_live.py（真实 openFDA）
CT_SAFETY_LIVE=1 python tests/run_tests.py
```

**版本**：v0.1.28 | **许可证**：MIT | **作者**：medstatstar, phoe-zip

如有功能改进建议、Bug 报告或其他反馈，欢迎直接联系作者：medstatstar@gmail.com（张文彤 / Wintone Zhang）。

---

## 保密声明

> CT 全系列技能由 20+ 个技能构成，按「保密信息出域风险 + 是否对外检索」分为 A、B 两档，完整覆盖新药临床试验（Clinical Trial）全流程的各方面需求。
>
> - **A 档（非涉密·公开）**：输入为普通数据，可完全本地运行（`network=off`）或对外公开检索（`network=public-retrieval`，如 ct-registry / ct-advisor 等）；不涉及任何保密信息。A 档技能均在 GitHub 公开发布。
> - **B 档（涉密·内部）**：涉及药企需严格保密的临床试验数据、内部资讯等敏感内容（如 ct-analysis、ct-sdtm、ct-eligibility 等）；B 档在本地处理（`egress=none`，数据不出域）或需审批出站（`egress=approval-req`，如 ct-eligibility）。B 档技能仅限企业内部使用，目前不对外公开发布。
>
> 若您对这些涉密技能确有实际需求，欢迎与作者联系，定制并安装相关技能。
>
> 📧 联系方式：medstatstar@gmail.com，张文彤（Wintone Zhang）
