# 临床试验安全信号专家（ct-safety）

[🇨🇳 中文](#) ｜ [🇺🇸 English](./README.md)

<div align="center">
  <img src="assets/icon.svg" width="240" height="240" alt="ct-safety 图标"/>
</div>

> 一个默认安全的药物警戒技能：对 **FDA FAERS** 公开不良事件数据筛查药物-事件安全信号（PRR / ROR / IC / EBGM，含 95% 置信区间），并可选叠加中国官方药物警戒通报作佐证。仅读取公开数据——**零保密输入（A 档，`network=public-retrieval`）**。自 v0.9.9 起，所有检索采用**薄本地端**架构：本地仅做计算（disproportionality / 信号评分），所有出站检索统一经 Coze 端点 `ct-search.coze.site` 外发。

## 适用人群

`ct-*` 临床试验技能家族专用于解决临床试验全生命周期的各类需求，主要面向三类人群：

- **各制药企业的临床试验从业者** —— 申办方、CRO，以及医学 / 统计 / 注册等角色；
- **在医疗机构中设计、管理临床试验项目，或参与临床试验研究实务的医护人员**；
- **希望系统学习临床试验知识的医学专业学生**。

## 耗时与检索量提示

> ⚠️ **耗时与下载量上限**。自 v0.9.9 起，所有检索经 Coze 统一端点 `ct-search.coze.site` 外发（薄本地端架构）。耗时取决于 Coze 端处理 + 网络。以下为 **2026-09-08 实测**（上海 / 约 200 Mbps，Coze 端点）：
>
> | 负载 | 命令形态 | 实测 wall-clock | 产出 |
> |---|---|---|---|
> | **概览**（count-facet，默认路径） | `ct_safety.py --drug candesartan --run`（不给 `--event`） | **约 10–30 秒** | 匹配报告数，top-10 反应 |
> | **信号检测** | `ct_safety.py --drug candesartan --event NAUSEA --run` | **约 15–45 秒** | 2×2 表 + PRR/ROR/IC/EBGM |
> | **叠加中国 PV 佐证** | `ct_safety.py --drug osimertinib --event PNEUMONITIS --with-cn-pv --drug-cn 奥希替尼 --event-cn 肺炎 --run` | **约 20–60 秒** | FAERS 信号 + 中国通报 |
>
> **单次运行上限（与实现参数一致）**：
> - `fetch_reports.py --max <n>` → 硬上限 **10,000**（`HARD_CAP`）；超出自动 clamp 并打印 `[WARN]`。
> - `ct_safety.py --case-level <n>` → **单页**抓取，硬上限 **100**；超出自动截断并打印 `[WARN]`。且**必须配合 `--event`** 使用（否则被忽略）。批量下载请改用 `fetch_reports.py --max`。
> - openFDA 配额（仅本机直连的 `query_total` / `fetch_case_reports`）：匿名 240 次/分、1,000 次/天按 IP；免费 key 240 次/分、120,000 次/天按 key。单次请求超时 120 秒。
>
> **触顶 / 超时行为**：超出上限**不报错**——自动截断到上限、打印 `[WARN] ... clamped/truncated` 并返回部分结果。Coze 端配额耗尽返回结构化错误，需加 `--api-key` 或降低请求频率。单页超时重试 3 次后报错。
>
> **如何避免长时间等待**：先用概览摸清基数再决定是否下载个案；用 `--date-from` / `--date-to` 缩小时间窗；`--max` 由小到大逐步加（500 → 2000 → …）。

## 如何在对话里使用

直接用自然语言告诉助手你想做什么即可。下面是可直接复制的真实示例——示例只给标签与示意，真实计算遵循下方「安全」一节的两段式安全流程。

### 示例 1 · 某药的高发不良事件

**你这样说：**
> 帮我校查一下 candesartan 在 FAERS 里报告最多的不良事件。

**助手会这样回（示意）：**
> 我会从 FAERS 公开数据库汇总 candesartan 报告最多的反应，含计数、严重性、器官系统归类——作为提出具体信号问题前的安全性基线。

**如何触发真实计算：**
> 概览会自动执行。说「跳过预览，直接跑」技能即抓取 FAERS 各分面并打印汇总；未给 `--event` 时不会报错——自动降级为高频不良事件报告。

### 示例 2 · 某个具体药物-事件信号

**你这样说：**
> candesartan 会不会增加血管性水肿风险？

**助手会这样回（示意）：**
> 我会基于 FAERS 构建药物-事件 2×2 表，报告 PRR / ROR / IC / EBGM 及 95% 置信区间与信号判定，并对 Top-N 事件做 Benjamini-Hochberg FDR 校正。

**如何触发真实计算：**
> 概览（总数 + Top-N）先自动跑出，然后停下等你确认。要跑详细信号检测，回复「确认，跑详情」即可——或直接说「跳过预览，直接跑」立即执行。

### 示例 3 · 用中国官方药物警戒通报佐证

**你这样说：**
> 有没有奥希替尼肺炎的中国官方安全通报？

**助手会这样回（示意）：**
> 我会检索**国家药品不良反应监测中心**（cdr-adr.org.cn）公开栏目，用药物+事件关键词匹配官方通报，作为 FAERS 量化信号的**定性佐证**。这些仅属叙事性通报、非个案计数，因此绝不进入 disproportionality 计算。

**如何触发真实计算：**
> 中文关键词检索是详情步骤的一部分。确认详情步骤（或「跳过预览，直接跑」），并传中文词以提高召回：如 药名 奥希替尼 / 事件 肺炎。

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
> 选一个菜单项（或先选「详细解释差异」）。选定配置后同样走两段式：先轻量概览，详细检索等你确认才执行（或「跳过预览，直接跑」立即跑）。

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
> 分支理清意图后，同样的两段式适用：概览自动跑，详情等你确认（或「跳过预览，直接跑」立即执行）。

### 示例 6 · 带证据分级的综合信号评分

**你这样说：**
> 给我一个奥希替尼肺炎的安全信号评分，带证据分级——把 FDA 标签和中国 PV 也拉上。

**助手会这样回（示意）：**
> 我会跑完整的三角验证：FAERS disproportionality（PRR/ROR/IC/EBGM）+ FDA 标签的 labeled-vs-unlabeled 判定 + 中国官方药物警戒通报，最终合成安全信号评分（0–100）与 T1–T4 证据分级。

**如何触发真实计算：**
> 这是最完整的路径——确认详情步骤（或「跳过预览，直接跑」），技能即查询全部三个源，对信号打分并定级。评分与分级写入 HTML/XLSX 报告。

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
| 已发表安全性文献佐证 | 关联调用 **`ct-literature --safety`** 取 CSM / 安全性文献子集 | 「拉一下奥希替尼肺炎的已发表综述，佐证这个信号」 |

### 用已发表文献佐证（关联调用 `ct-literature --safety`）

当某个 FAERS 信号需要**定性**的已发表证据支撑（综述、药物警戒论文）时，调用 **`ct-literature --safety`**。它会把 CSM 定性子集作为独立的**「安全性相关」**页返回，可用于给信号做背景说明与佐证。

> **边界（重要）。** `ct-literature --safety` 仅作**已发表文献语境**，绝不可进入 FAERS 的 2×2 不成比例分析表（否则会扭曲计数）。用它来佐证、解释信号，而非作为定量来源。结构化信号统计请留在 `ct-safety` 内部（FAERS + label + 中国 PV）。

## 常见问题 FAQ

**只给一个药名、不给事件能算吗？**
能。只给 `--drug`（或只说药名）不再报错——自动降级为高频不良事件报告（无 2×2 表）。要算具体信号，请补一个事件（MedDRA 首选术语，如 `ANGIOEDEMA`）。

**PRR 和 ROR 有什么区别？**
二者都基于药物-事件 2×2 表的 disproportionality。ROR（报告比值比）以比值比形式呈现，下限 95% CI > 1 即判信号；PRR（比例报告比）在 PRR ≥ 2 **且** χ² ≥ 4 时判信号；IC（信息成分，UMC/VigiBase）下限 CI > 0 判信号；EBGM（FDA MGPS 贝叶斯收缩）EB05 ≥ 2 判信号。技能同时报告四种，并对多事件做 Benjamini-Hochberg FDR 校正。

**怎么才能真跑出信号表，而不是只看代码？**
默认只给概览（总数 + Top-N）并停下。确认详情步骤，或说「跳过预览，直接跑」——技能即执行 FAERS 检索与 disproportionality 分析，返回 JSON / Markdown（及可选 PNG 图）。

**中文环境输出是中文吗？**
是。技能跟随你的输入语言：`zh-*` 区域下提示与报告切中文，其余切英文。代码注释与文档仅英文。

**openFDA key 怎么配？**
默认**无需 key** 即可运行（主路径经 Coze 统一端点）。仅本机直连的 `query_total` / `fetch_case_reports` 走 openFDA（匿名 240 次/分、1,000 次/天，按 IP）。仅高吞吐场景才需免费 key，到 https://open.fda.gov/api/register/ 邮箱即注册（无信用卡）。用以下三种自配置方式之一提供：
- 环境变量：`export OPENFDA_API_KEY=YOUR_KEY`（推荐，每个脚本自动读取）；
- 技能根目录 `.env` 文件：`OPENFDA_API_KEY=YOUR_KEY`（已 git-ignore，不会随包发布）；
- 命令行：`--api-key YOUR_KEY`。

切勿在聊天里发送 key，也别把它写进任何会随技能发布的文件——key 仅本地存储，且仅经 HTTPS 发往官方 openFDA API。

**Q: 发现结果有误怎么办？怎么上报？**
A: 本技能遵循 ct-base §20.3 错误报告流程。若您怀疑结果有误（或引擎报错），直接说 **"上报问题" / "report a bug" / "提交错误报告"**。技能在检测到疑似缺陷时（如引擎报错、重试仍失败）也会**主动询问**是否上报——**每会话最多 1 次**，您可随时拒绝。无论哪种方式，助手都会：
1. **生成一份脱敏报告**（11 键白名单：skill / skill_version / test / error_type / error_code / engine_status / description / locale / query_origin / session_hash / attempts——**不含您的原始输入值或个人数据**，仅 `description` 字段由您把关披露，如所用算法/函数、错误消息原文）；
2. **展示报告全文供您检视**——可补充问题描述或更正任何内容后再确认；
3. **经您明确确认后发送**——本会话有 coze 调用则发往统一端点 `https://ct-bugreport.coze.site/run`；纯本地则保存脱敏报告 + 提示邮件联系作者（数据不出域）；
4. **收到回执**——包括您此前从同一来源提交的报告是否已被修复（含修复说明）或仍在处理中。

整个过程您完全可控：报告在**发送前**先展示给您，未经您明确说「发送」绝不传输任何内容。

## 安全（安全预览）

**两段式流程，默认安全。** 第一步（概览：总数 + Top-N）自动执行。第二步（详细检索 / 信号检测）**仅在你显式确认后**才执行——或当你说「跳过预览，直接跑」时。在确认前不会触发任何大批量下载，随口一问也不会跑重计算。

**出站披露。** 自 v0.9.9 起，技能采用**薄本地端**架构：本地仅做计算（disproportionality / 信号评分 / labeled 判定），所有出站检索统一经 Coze 端点 `ct-search.coze.site` 外发。技能仅读取公开源：
- **FDA FAERS**（必需，量化）—— 经 Coze `faers` 节点检索；
- **FDA Label**（使用 `--with-fda-label` 时的可选第三源）—— 经 Coze `fda_label` 节点检索；
- **国家药品不良反应监测中心** `cdr-adr.org.cn`（使用 `--with-cn-pv` 时的可选源，仅定性佐证）—— 经 Coze `nmpa_pv` 节点检索。

**零保密数据或信息输入**（A 档：普通数据输入 + 对外检索，`network=public-retrieval`）。NMPA 主站被 WAF 拦截（HTTP 412），已刻意排除。你的 openFDA key（若用于本机直连的 `query_total` / `fetch_case_reports`）**仅本地存储**，且**仅经 HTTPS 发往官方 openFDA API**。

信号检测仅供筛查，非因果结论；监管提交（DSUR / PBRER / 标签变更）须另行按 GCP / ICH E2 评估。

## 进阶参考

开发者 CLI、参数、数据源边界与错误处理放在此处（按使用者视角布局，从首屏下移）。

### 数据源

| 源 | 访问方式 | 状态 |
|---|---|---|
| FDA FAERS（openFDA `drug/event.json`） | 薄本地端 → Coze 统一端点 `ct-search.coze.site`（`faers` 节点）；`query_total` / `fetch_case_reports` 仍本机直连 | 必需（A 档，量化） |
| FDA Label（openFDA `drug/label.json`） | 薄本地端 → Coze 端点（`fda_label` 节点）；`check_event` 本地判定 | 可选 `--with-fda-label`（标签内/外风险） |
| 国家不良反应监测中心（cdr-adr.org.cn） | 薄本地端 → Coze 端点（`nmpa_pv` 节点）；本地保留关键词扩展 + 证据分级 + 缓存 | 可选 `--with-cn-pv`（仅定性佐证） |

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
| `URLError` / timeout | 无网络 / 代理 | 确认网络可达；配置代理 |
| Coze 端点错误 | Coze 端配额耗尽 / token 无效 / 端点未 allow-list | 检查 Coze 部署状态及 `config.json` `auto_approve_endpoints` |
| HTTP 429 / 限流 | 超 openFDA 限额（仅本机直连 `query_total` / `fetch_case_reports`） | 加 `--api-key`；或降频 |
| 只给 `--drug` 未给 `--event` | 意图是看高发反应而非 2×2 信号 | 自动降级为 Top-N 报告；加 `--event <PT>` 算信号 |
| 字段名不匹配 | 药名字段错 | 默认 `patient.drug.medicinalproduct`；用 `--field patient.drug.openfda.substance_name` 标准化 |
| CN-PV 0 命中 | 关键词过窄 | 传 `--drug-cn` + `--event-cn`；调大 `--cn-max` |
| 多词事件持续 404 | 该三词 PT 未被索引（本机直连路径） | 换标准 MedDRA PT |
| `--max > 10000` | 突破免费配额上限 | 自动 clamp 到 `HARD_CAP=10000`；注意选择偏倚（API 返回顺序，非随机） |

### 比较研究设计模式（多药 / 单 SOC）

当用户要求*对比*（「compare X vs Y」「同类头对头」「active-comparator disproportionality」「可发表的比较 PV 论文」），切换到比较轨道：(1) 数据准备 → (2) 选研究风格 + Lite/Standard/Advanced/Publication+ 工作负载 → (3) 选指标、对照逻辑、稳健性路线 → (4) 给每个结果打证据分级。硬规则：绝不在未准备原始计数上跑 disproportionality；始终先展示四种配置再推荐一种；每个实质结果带分级标签（`[Tier 1]` 信号 / `[Tier 2]` 比较 / `[Tier 3]` 稳健性）；Tier-4 主张（发生率、因果、获益-风险、处方）无外部数据禁止。

### 回归测试

```bash
python tests/run_tests.py            # 离线（mock 网络）
python tests/run_tests.py --live     # 额外跑 tests/test_live.py（真实 openFDA）
CT_SAFETY_LIVE=1 python tests/run_tests.py
```

**版本**：v0.9.9 | **许可证**：MIT | **作者**：medstatstar, phoe-zip

如有功能改进建议、Bug 报告或其他反馈，欢迎直接联系作者：medstatstar@gmail.com（张文彤 / Wintone Zhang）。

---

## 保密声明

> CT 全系列技能由 20+ 个技能构成，按「输入是否涉密」分为 **A、B 两档**（network / egress / publish 为独立正交属性，详见 ct-base §11），完整覆盖新药临床试验（Clinical Trial）全流程的各方面需求。
>
> - **A 档（输入非涉密）**：输入为普通数据，可完全本地运行（`network=off`）或对外公开检索（`network=public-retrieval`，如 ct-registry / ct-advisor 等）；不涉及任何保密信息。A 档技能均在 GitHub 公开发布。
> - **B 档（输入涉密）**：输入含药企需严格保密的临床试验数据 / 方案 / CRF（如 ct-analysis、ct-sdtm、ct-protocol、ct-eligibility 等）；B 档**既能本地处理**（`egress=none`，数据不出域）**也能对外公开检索**（`network=public-retrieval`，如 ct-protocol 调 ct-registry / ct-literature 抓取公开试验设计与文献作参考——仅公开查询词出域）；或需审批出站（`egress=approval-req`，如 ct-eligibility）。但**均不对外公开发布**；涉密输入绝不随包 / 出站；若有定制 / 本地部署需求，欢迎与作者联系。
>
> 📧 联系方式：medstatstar@gmail.com，张文彤（Wintone Zhang）
