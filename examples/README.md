# 两支团队的合成试用

示例均为合成。青榆和石桥是两个虚构审定团队。先在独立对话中为其中一个团队生成画像。再换一个对话读取已导出的 Skill，试写 [同一份新材料](new-brief.md)。

| 审定团队 | 过程稿与审定稿 | 另一份独立审定稿 |
| --- | --- | --- |
| 青榆 | [第一案初稿](team-qingyu/01-draft.md) · [第一案审定稿](team-qingyu/01-final.md) | [第二案审定稿](team-qingyu/02-final.md) |
| 石桥 | [第一案初稿](team-shiqiao/01-draft.md) · [第一案审定稿](team-shiqiao/01-final.md) | [第二案审定稿](team-shiqiao/02-final.md) |

两组稿件均为二审答辩理由节选。初稿与审定稿行文不同，样本中载明的事实和请求由本轮材料限定。只用同一行的材料归纳该团队写法。

已有两份可直接试用的样例画像。要跳到试写，在仓库根目录执行以下命令。

```bash
python3 scripts/export_voice.py examples/profiles/qingyu.json generated
python3 scripts/export_voice.py examples/profiles/shiqiao.json generated
```

分别打开新的对话。第一份指定 `generated/qingyu-legal-voice/SKILL.md`，第二份指定 `generated/shiqiao-legal-voice/SKILL.md`。两次均只提供 [这份新材料](new-brief.md)，要求起草文书节选。

两次试写均只读取了各自导出的 Skill 和新材料。[青榆试写](qingyu-output.md)把一审认定放在首段，随后说明合同与材料。[石桥试写](shiqiao-output.md)先分析上诉所据材料和证明缺口，再用一审认定收束。两稿保留同一句一审认定、同一页码和原请求。两份画像的规则均限定在样本支持的二审答辩状。真实团队可用更多独立样本验证共通的写法及其他文体。

对照时先看每稿的起笔、材料顺序、证明范围和收束。再核对是否保留针对此次争点的条件、引文、主体和请求。少量样本可以演示流程，实际可复用的程度仍以团队审阅为准。
