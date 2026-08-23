

## 流水线自检 / Pipeline Self-Validation (对照验证)

阳性对照 Positive controls（预期有信号）与阴性对照 Negative controls（预期无信号）用于检验检测流水线是否系统性漏检/误报。连续性校正 continuity=True。

| 组别 Group | 药物 Drug | 事件 Event | 预期 Expected | 实测信号 Signal | 一致 Match |
|---|---|---|---|---|---|
| positive | cerivastatin | RABDOMYOLYSIS | 有信号 | — | — |
| positive | troglitazone | HEPATITIS | 有信号 | 是 | 是 |
| positive | rosiglitazone | MYOCARDIAL INFARCTION | 有信号 | 是 | 是 |
| positive | leflunomide | HEPATIC FAILURE | 有信号 | 否 | 否 |
| positive | fluoroquinolone | TENDON RUPTURE | 有信号 | 是 | 是 |
| negative | paracetamol | RABDOMYOLYSIS | 无信号 | — | — |
| negative | ibuprofen | PNEUMONITIS | 无信号 | 否 | 是 |
| negative | amoxicillin | MYOCARDIAL INFARCTION | 无信号 | 否 | 是 |
| negative | salbutamol | HEPATIC FAILURE | 无信号 | 否 | 是 |

- 阳性对照一致率 Positive agreement: 3/5 (60.0%)
- 阴性对照一致率 Negative agreement: 4/4 (100.0%)