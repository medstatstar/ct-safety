# Report Template / 报告模板

> **🌐 Output language / 输出语言 (configurable, opt-in / 可配置、按需):**
> Output language follows the user's stated preference and is **not mandated**.
> - Default recommendation: bilingual `English / 中文` (both shown side by side), since this skill is published bilingually.
> - Single-language output (English-only or Chinese-only) is fully supported — just set the user's requested language.
> - In regulated clinical workflows where output language must be tightly controlled, use the user's single requested language only.
> / 输出语言**遵循使用者指定偏好，不做强制**。默认推荐双语 `English / 中文`（并列展示），因为本技能以双语发布；也完全支持单语输出（仅英文或仅中文），只需按使用者要求的语言即可；在输出语言须严格管控的受监管临床试验场景中，仅使用使用者指定的单一语言。
>
> **English / 中文:** By default, end every analysis with this structure + results; include the standalone R code block ONLY when the user explicitly asks for it. / 默认每次分析以该结构 + 结果收尾；仅当使用者明确要求时，才附上完整可运行的 R 代码块。

---

## Structure / 报告结构

### 1. Title / 标题
```
## 📊 Sample Size / Power Report | 样本量/效能计算报告
```

### 2. Trial Design / 检验设计
```
- **Design Type | 设计类型**: [Parallel/Crossover/Group Sequential/Adaptive]
- **Primary Endpoint | 主要终点**: [Continuous/Binary/Time-to-Event]
- **Hypothesis | 假设检验**: [Superiority/Non-inferiority/Equivalence]
- **Direction | 检验方向**: [One-sided/Two-sided]
```

### 3. Input Parameters / 输入参数
```
- **Significance (α) | 显著性水平**: [value, one/two-sided]
- **Power (1-β) | 期望效能**: [value]
- **Effect Size | 效应量**: [Cohen's d / HR / OR / rate diff]
- **Allocation | 分配比**: [1:1 / 2:1 / ...]
- **Dropout Rate | 脱落率**: [X%] → adjustment factor 1/(1-X%)
```

### 4. Results / 计算结果
```
- **Per-group N | 每组样本量**: [N1, N2]
- **Total N | 总样本量**: [N]
- **Adjusted for Dropout | 考虑脱落**: [N_adjusted]
- **[Adaptive/GS] Interim Analyses | 期中分析次数**: [K]
- **[Survival] Events Needed | 所需事件数**: [D]
```

### 5. Interpretation / 结果解释
```
[Plain-language explanation of what the sample size means]
[用通俗语言解释结果]
```

### 6. Assumptions / 前提假设
```
[Normality, equal variance, independence, etc.]
```

### 7. Methodological Limits / 方法学限制
```
[Python fallback: simplified formula vs R exact]
[R exact: approximation conditions]
```

### 8. Sensitivity / 敏感性建议
```
[If effect size decreases by 20%, how does N change?]
```

---

## ⚠️ On Request: Reproducible R Code / 按需提供：可复现的 R 代码

> **EN/CN:** Include this block ONLY when the user explicitly asks for the reproducible R code; it is hidden by default.

```markdown
---

## 📋 Reproducible R Code | 可复现的 R 代码

> Copy to R Studio or save as `.R` and run with `Rscript` to reproduce.

```r
# ============================================================
# Sample Size Calculation — Standalone R Script
# 样本量计算 - 可独立运行的 R 脚本
# Generated | 生成时间: [YYYY-MM-DD]
# Path | 计算路径: [R exact / Python fallback + R equiv]
# ============================================================

# ---- 0. Setup (uncomment first run) | 环境准备 ----
# install.packages(c("TrialSize", "pwr", "rpact", "gsDesign"))

# ---- 1. Load packages | 加载包 ----
library(TrialSize)
library(pwr)
# library(rpact)     # Enable for Adaptive/GS
# library(gsDesign)  # Enable for Group Sequential

# ---- 2. Parameters | 参数设置 ----
alpha <- [value]
power <- [value]
effect_size <- [value]

# ---- 3. Calculate | 计算 ----
[core function calls with hardcoded values]

# ---- 4. Output | 输出 ----
cat("\n===== Result | 计算结果 =====\n")

# ---- 5. Dropout adjustment | 脱落调整 ----
dropout_rate <- [value]
n_adj <- ceiling(n / (1 - dropout_rate))
cat(sprintf("Adjusted for %.0f%% dropout: %d\n", dropout_rate*100, n_adj))
```

**Run | 运行方式**:
- R Studio: paste into script window
- CLI | 命令行: `Rscript clin_calc.R`
```

---

## R Code Generation Rules / R 代码生成规则

| Rule 规则 | Description 说明 |
|:---------|:----------------|
| **Complete 完整** | install.packages / library / calc / output |
| **Hardcoded 硬编码** | Actual values, no placeholders |
| **Runnable 可复现** | Copy-paste executable in R |
| **Multi-method 多方法** | Key scenarios: ≥2 packages |
| **Dropout 脱落** | Include clinical utility code |
