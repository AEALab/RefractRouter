# 真人复核阅读版

本页按题目集中材料，保留随机复核编号。阅读后在 JSON 复核包填写，或按编号提供判断与理由。
模型、路线和自动分数已隐藏；节点命名与风格仍可能透露生成方式。空白项须由真人填写。

## 题目 1

<details><summary>查看原始题目与材料</summary>
<pre>这是独立编写的虚构封闭场景「培训分班容量分析」，不代表真实机构或法律规则。只用以下材料，不联网或执行工具。
E1：每条记录给出申请人数和已完成前置课程人数，仅已完成课程者有资格安排。E2：先按组汇总有资格人数，再与甲70、乙90、丙110、丁130的组席位比较。E3：各组时段相互冲突，剩余席位不能跨组相抵；不能用总申请人数冒充有资格需求。E4：只建议补充席位或调整时段，没有授权替任何人报名。
来源 test_seating-L001：第1项，乙组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L002：第2项，丙组，申请 7 人，其中完成前置课程 6 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L003：第3项，丁组，申请 8 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L004：第4项，甲组，申请 9 人，其中完成前置课程 8 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L005：第5项，乙组，申请 10 人，其中完成前置课程 2 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L006：第6项，丙组，申请 11 人，其中完成前置课程 6 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L007：第7项，丁组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L008：第8项，甲组，申请 13 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L009：第9项，乙组，申请 14 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L010：第10项，丙组，申请 15 人，其中完成前置课程 6 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L011：第11项，丁组，申请 16 人，其中完成前置课程 9 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L012：第12项，甲组，申请 17 人，其中完成前置课程 12 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L013：第13项，乙组，申请 5 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L014：第14项，丙组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L015：第15项，丁组，申请 7 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L016：第16项，甲组，申请 8 人，其中完成前置课程 4 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L017：第17项，乙组，申请 9 人，其中完成前置课程 9 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L018：第18项，丙组，申请 10 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L019：第19项，丁组，申请 11 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L020：第20项，甲组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L021：第21项，乙组，申请 13 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L022：第22项，丙组，申请 14 人，其中完成前置课程 4 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L023：第23项，丁组，申请 15 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L024：第24项，甲组，申请 16 人，其中完成前置课程 15 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L025：第25项，乙组，申请 17 人，其中完成前置课程 13 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L026：第26项，丙组，申请 5 人，其中完成前置课程 2 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L027：第27项，丁组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L028：第28项，甲组，申请 7 人，其中完成前置课程 4 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L029：第29项，乙组，申请 8 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L030：第30项，丙组，申请 9 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L031：第31项，丁组，申请 10 人，其中完成前置课程 8 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L032：第32项，甲组，申请 11 人，其中完成前置课程 8 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L033：第33项，乙组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L034：第34项，丙组，申请 13 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L035：第35项，丁组，申请 14 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L036：第36项，甲组，申请 15 人，其中完成前置课程 12 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L037：第37项，乙组，申请 16 人，其中完成前置课程 4 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L038：第38项，丙组，申请 17 人，其中完成前置课程 14 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L039：第39项，丁组，申请 5 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L040：第40项，甲组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L041：第41项，乙组，申请 7 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L042：第42项，丙组，申请 8 人，其中完成前置课程 6 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L043：第43项，丁组，申请 9 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L044：第44项，甲组，申请 10 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L045：第45项，乙组，申请 11 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L046：第46项，丙组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L047：第47项，丁组，申请 13 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L048：第48项，甲组，申请 14 人，其中完成前置课程 6 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L049：第49项，乙组，申请 15 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L050：第50项，丙组，申请 16 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L051：第51项，丁组，申请 17 人，其中完成前置课程 15 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L052：第52项，甲组，申请 5 人，其中完成前置课程 4 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L053：第53项，乙组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L054：第54项，丙组，申请 7 人，其中完成前置课程 2 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L055：第55项，丁组，申请 8 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L056：第56项，甲组，申请 9 人，其中完成前置课程 2 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L057：第57项，乙组，申请 10 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L058：第58项，丙组，申请 11 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L059：第59项，丁组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L060：第60项，甲组，申请 13 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L061：第61项，乙组，申请 14 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L062：第62项，丙组，申请 15 人，其中完成前置课程 2 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L063：第63项，丁组，申请 16 人，其中完成前置课程 16 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L064：第64项，甲组，申请 17 人，其中完成前置课程 16 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L065：第65项，乙组，申请 5 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L066：第66项，丙组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L067：第67项，丁组，申请 7 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L068：第68项，甲组，申请 8 人，其中完成前置课程 8 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L069：第69项，乙组，申请 9 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L070：第70项，丙组，申请 10 人，其中完成前置课程 6 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L071：第71项，丁组，申请 11 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L072：第72项，甲组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L073：第73项，乙组，申请 13 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L074：第74项，丙组，申请 14 人，其中完成前置课程 8 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L075：第75项，丁组，申请 15 人，其中完成前置课程 13 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L076：第76项，甲组，申请 16 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L077：第77项，乙组，申请 17 人，其中完成前置课程 17 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L078：第78项，丙组，申请 5 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L079：第79项，丁组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L080：第80项，甲组，申请 7 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L081：第81项，乙组，申请 8 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L082：第82项，丙组，申请 9 人，其中完成前置课程 4 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L083：第83项，丁组，申请 10 人，其中完成前置课程 9 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L084：第84项，甲组，申请 11 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L085：第85项，乙组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L086：第86项，丙组，申请 13 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L087：第87项，丁组，申请 14 人，其中完成前置课程 9 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L088：第88项，甲组，申请 15 人，其中完成前置课程 8 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L089：第89项，乙组，申请 16 人，其中完成前置课程 11 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L090：第90项，丙组，申请 17 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L091：第91项，丁组，申请 5 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L092：第92项，甲组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L093：第93项，乙组，申请 7 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L094：第94项，丙组，申请 8 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L095：第95项，丁组，申请 9 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L096：第96项，甲组，申请 10 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L097：第97项，乙组，申请 11 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L098：第98项，丙组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L099：第99项，丁组，申请 13 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。
来源 test_seating-L100：第100项，甲组，申请 14 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。
交付要求：按组计算申请、有资格、无资格人数与席位缺口，形成两阶段分班建议；保留不能跨组调剂和未授权代报名的约束。</pre>
</details>

**原始验收：** 完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。；遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。

<details><summary>查看冻结参考（长材料已独立重算）</summary>
<pre>{&quot;丁&quot;: {&quot;记录数&quot;: 25, &quot;第一列总和&quot;: 269, &quot;第二列总和&quot;: 151, &quot;申请&quot;: 269, &quot;有资格&quot;: 151, &quot;无资格&quot;: 118, &quot;席位&quot;: 130, &quot;缺口&quot;: 21}, &quot;丙&quot;: {&quot;记录数&quot;: 25, &quot;第一列总和&quot;: 270, &quot;第二列总和&quot;: 112, &quot;申请&quot;: 270, &quot;有资格&quot;: 112, &quot;无资格&quot;: 158, &quot;席位&quot;: 110, &quot;缺口&quot;: 2}, &quot;乙&quot;: {&quot;记录数&quot;: 25, &quot;第一列总和&quot;: 271, &quot;第二列总和&quot;: 144, &quot;申请&quot;: 271, &quot;有资格&quot;: 144, &quot;无资格&quot;: 127, &quot;席位&quot;: 90, &quot;缺口&quot;: 54}, &quot;甲&quot;: {&quot;记录数&quot;: 25, &quot;第一列总和&quot;: 281, &quot;第二列总和&quot;: 143, &quot;申请&quot;: 281, &quot;有资格&quot;: 143, &quot;无资格&quot;: 138, &quot;席位&quot;: 70, &quot;缺口&quot;: 73}}</pre>
</details>

### P001

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| cost | synthesis | 无 | 汇总全部原始事实，完成所需计算并列出来源；只交付本节点分析，不虚构信息。 |
| risk | verification | cost | 核验约束、信息缺口及可能的误判；如有上游结果必须据其完成判断，保留关键来源和限制。 |
| answer | generation | cost,risk | 完整完成原始任务，逐条核对所有交付要求。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;计算结果是后续判断的必要输入。&quot;,
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;cost&quot;,
        &quot;node_type&quot;: &quot;synthesis&quot;,
        &quot;parents&quot;: [],
        &quot;prompt_template&quot;: &quot;汇总全部原始事实，完成所需计算并列出来源；只交付本节点分析，不虚构信息。&quot;,
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;汇总全部原始事实，完成所需计算并列出来源；只交付本节点分析，不虚构信息。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;result&quot;: &quot;分析结果&quot;,
              &quot;evidence&quot;: &quot;原始材料来源标识与证据；没有证据时明确说明&quot;,
              &quot;assumptions&quot;: &quot;假设、不确定性与信息缺口；没有时明确说明&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;high&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;保留证据与假设，不虚构数据&quot;,
            &quot;覆盖本节点职责并明确限制&quot;
          ],
          &quot;covers&quot;: [
            0
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;risk&quot;,
        &quot;node_type&quot;: &quot;verification&quot;,
        &quot;parents&quot;: [
          &quot;cost&quot;
        ],
        &quot;prompt_template&quot;: &quot;核验约束、信息缺口及可能的误判；如有上游结果必须据其完成判断，保留关键来源和限制。&quot;,
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;核验约束、信息缺口及可能的误判；如有上游结果必须据其完成判断，保留关键来源和限制。&quot;,
          &quot;inputs&quot;: {
            &quot;cost&quot;: {
              &quot;fields&quot;: [
                &quot;result&quot;,
                &quot;evidence&quot;,
                &quot;assumptions&quot;
              ],
              &quot;reason&quot;: &quot;消费 cost 的分析、证据与假设，检查一致性后形成判断&quot;
            }
          },
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;result&quot;: &quot;分析结果&quot;,
              &quot;evidence&quot;: &quot;原始材料来源标识与证据；没有证据时明确说明&quot;,
              &quot;assumptions&quot;: &quot;假设、不确定性与信息缺口；没有时明确说明&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;high&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;保留证据与假设，不虚构数据&quot;,
            &quot;覆盖本节点职责并明确限制&quot;
          ],
          &quot;covers&quot;: [
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;parents&quot;: [
          &quot;cost&quot;,
          &quot;risk&quot;
        ],
        &quot;prompt_template&quot;: &quot;完整完成原始任务，逐条核对所有交付要求。&quot;,
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;完整完成原始任务，逐条核对所有交付要求。&quot;,
          &quot;inputs&quot;: {
            &quot;cost&quot;: {
              &quot;fields&quot;: [
                &quot;result&quot;,
                &quot;evidence&quot;,
                &quot;assumptions&quot;
              ],
              &quot;reason&quot;: &quot;消费 cost 的分析、证据与假设，检查一致性后形成判断&quot;
            },
            &quot;risk&quot;: {
              &quot;fields&quot;: [
                &quot;result&quot;,
                &quot;evidence&quot;,
                &quot;assumptions&quot;
              ],
              &quot;reason&quot;: &quot;消费 risk 的分析、证据与假设，检查一致性后形成判断&quot;
            }
          },
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终建议与可追溯依据&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;high&quot;,
            &quot;input_budget_tokens&quot;: 65536,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;保留证据与假设，不虚构数据&quot;,
            &quot;覆盖本节点职责并明确限制&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ]
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: null,
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P004

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| extract_group_summary | extraction | 无 | 按组准确汇总申请人数、有资格人数和无资格人数，并保留来源编号。 |
| answer | generation | extract_group_summary | 生成完整的两阶段分班建议正文，按组呈现统计、席位比较、建议和约束。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;extract_group_summary&quot;,
        &quot;node_type&quot;: &quot;extraction&quot;,
        &quot;prompt_template&quot;: &quot;根据以下材料，按甲、乙、丙、丁四组分别汇总：申请人数、已完成前置课程人数（即有资格人数）、无资格人数。逐条核对来源编号，不得用总申请人数冒充有资格需求。输出 JSON，字段为 group_summary，内容要求：在字符串中按「甲组：申请X人，有资格Y人，无资格Z人；乙组：申请X人，有资格Y人，无资格Z人；丙组：申请X人，有资格Y人，无资格Z人；丁组：申请X人，有资格Y人，无资格Z人」格式给出，并附每组涉及来源编号列表。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;按组准确汇总申请人数、有资格人数和无资格人数，并保留来源编号。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;group_summary&quot;: &quot;按甲、乙、丙、丁四组分别列出申请人数、有资格人数、无资格人数，并附每组来源编号列表&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;medium&quot;,
            &quot;input_budget_tokens&quot;: 65536,
            &quot;expected_output_tokens&quot;: 2000
          },
          &quot;checks&quot;: [
            &quot;四组申请人数、有资格人数、无资格人数均与材料一致&quot;,
            &quot;每组来源编号完整且无遗漏&quot;,
            &quot;未将无资格人数计入有资格需求&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;根据上游按组汇总结果，完成「培训分班容量分析」最终交付。要求：1）按组分别呈现申请人数、有资格人数、无资格人数；2）将各组有资格人数与甲70、乙90、丙110、丁130的组席位比较，计算各组席位缺口或剩余；3）形成两阶段分班建议：第一阶段按有资格人数安排，第二阶段针对缺口提出补充席位或调整时段建议；4）明确保留约束：各组时段相互冲突，剩余席位不能跨组相抵；不能用总申请人数冒充有资格需求；只建议补充席位或调整时段，没有授权替任何人报名；5）保留来源编号，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。直接输出正文，不封装为 JSON。&quot;,
        &quot;parents&quot;: [
          &quot;extract_group_summary&quot;
        ],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;生成完整的两阶段分班建议正文，按组呈现统计、席位比较、建议和约束。&quot;,
          &quot;inputs&quot;: {
            &quot;extract_group_summary&quot;: {
              &quot;fields&quot;: [
                &quot;group_summary&quot;
              ],
              &quot;reason&quot;: &quot;最终正文需要基于按组汇总的申请、有资格、无资格人数和来源编号进行席位比较与建议。&quot;
            }
          },
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终交付正文，包含按组统计、席位缺口、两阶段分班建议、约束说明和来源编号&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;medium&quot;,
            &quot;input_budget_tokens&quot;: 65536,
            &quot;expected_output_tokens&quot;: 3000
          },
          &quot;checks&quot;: [
            &quot;按组分别呈现申请、有资格、无资格人数和席位缺口&quot;,
            &quot;两阶段分班建议完整且符合材料约束&quot;,
            &quot;保留来源编号，区分事实、建议和未知事项&quot;,
            &quot;明确不能跨组调剂和未授权代报名约束&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务为封闭材料下的确定性统计与建议生成：需先按组汇总资格人数，再与席位比较并形成两阶段建议。材料较长且计算量大，拆分为按组并行提取汇总与最终综合生成两个阶段，可降低单节点计算遗漏风险，并在最终节点统一核对冲突、保留来源编号和约束。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 1061
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P010

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| stats | generation | 无 | 按组汇总100条记录的申请、有资格、无资格人数，并计算各组席位缺口，保留来源编号与计算依据。 |
| answer | generation | stats | 基于统计结果撰写最终交付正文，按组呈现统计与席位缺口，并形成两阶段分班建议，同时保留材料约束。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;stats&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;根据原始任务中的100条来源记录（test_seating-L001 至 test_seating-L100），严格按材料规则完成统计：\n1. 对每条记录，仅将「已完成前置课程人数」计为有资格人数；申请人数与已完成前置课程人数之差为无资格人数。\n2. 按甲、乙、丙、丁四组分别汇总：申请总人数、有资格总人数、无资格总人数。\n3. 将各组有资格总人数与席位比较：甲70、乙90、丙110、丁130。席位缺口=有资格总人数-席位；正数表示缺席位，负数或零表示席位有余。\n4. 不得跨组相抵，不得用申请总人数冒充有资格需求。\n5. 保留每条记录来源编号与关键数字的对应关系，便于核对。\n输出 JSON，字段要求：\n- group_summary：按组给出申请总人数、有资格总人数、无资格总人数、席位、席位缺口的汇总说明，需包含每组来源编号范围及关键计数依据。\n- calculation_notes：说明统计口径、是否发现异常或需要核对的记录、以及未在材料中说明的未知事项。\n- evidence：列出用于核对的关键来源编号及对应数字，确保可追溯。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;按组汇总100条记录的申请、有资格、无资格人数，并计算各组席位缺口，保留来源编号与计算依据。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;group_summary&quot;: &quot;按甲、乙、丙、丁四组分别说明申请总人数、有资格总人数、无资格总人数、席位及席位缺口的汇总结果与依据。&quot;,
              &quot;calculation_notes&quot;: &quot;说明统计口径、异常或需核对记录、材料未说明的未知事项。&quot;,
              &quot;evidence&quot;: &quot;列出用于核对的关键来源编号及对应数字。&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;medium&quot;,
            &quot;input_budget_tokens&quot;: 65536,
            &quot;expected_output_tokens&quot;: 3000
          },
          &quot;checks&quot;: [
            &quot;各组申请总人数、有资格总人数、无资格总人数与材料逐条记录一致。&quot;,
            &quot;席位缺口按有资格总人数与对应席位计算，未跨组相抵。&quot;,
            &quot;保留来源编号，未虚构材料外的数据或原因。&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;基于原始任务和统计节点提供的 group_summary、calculation_notes、evidence，撰写最终交付正文。要求：\n1. 按甲、乙、丙、丁四组分别呈现：申请总人数、有资格总人数、无资格总人数、席位、席位缺口。\n2. 形成两阶段分班建议：第一阶段先筛资格再分配，仅已完成前置课程者有资格安排；第二阶段在资格筛选后按组比较席位，只建议补充席位或调整时段。\n3. 明确保留约束：各组时段相互冲突，剩余席位不能跨组相抵；不能用总申请人数冒充有资格需求；没有授权替任何人报名。\n4. 区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。\n5. 保留来源编号，确保事实和计算与材料一致。\n直接输出正文，不封装为 JSON。&quot;,
        &quot;parents&quot;: [
          &quot;stats&quot;
        ],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;基于统计结果撰写最终交付正文，按组呈现统计与席位缺口，并形成两阶段分班建议，同时保留材料约束。&quot;,
          &quot;inputs&quot;: {
            &quot;stats&quot;: {
              &quot;fields&quot;: [
                &quot;group_summary&quot;,
                &quot;calculation_notes&quot;,
                &quot;evidence&quot;
              ],
              &quot;reason&quot;: &quot;最终正文需要消费按组汇总结果、计算口径与来源证据，才能准确呈现统计、缺口和建议，并保持可追溯性。&quot;
            }
          },
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终交付正文，按组呈现申请、有资格、无资格人数与席位缺口，并给出两阶段分班建议及约束说明。&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;medium&quot;,
            &quot;input_budget_tokens&quot;: 65536,
            &quot;expected_output_tokens&quot;: 4000
          },
          &quot;checks&quot;: [
            &quot;正文按甲、乙、丙、丁四组分别呈现申请、有资格、无资格人数与席位缺口。&quot;,
            &quot;两阶段分班建议完整，先筛资格再分配，并只建议补充席位或调整时段。&quot;,
            &quot;明确保留不能跨组调剂和未授权代报名的约束。&quot;,
            &quot;区分已知事实、建议和未知事项，保留来源编号，不虚构数据或已执行操作。&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务为封闭材料下的确定性统计与建议生成：需先按组汇总100条记录，再与席位比较并形成两阶段建议。汇总与比较强耦合且数据量中等，拆成两个节点即可：第一个节点完成按组统计与席位缺口计算，第二个节点基于统计结果撰写最终交付正文。拆分净收益是让统计节点专注核对数据、最终节点专注呈现约束与建议，避免单节点同时承担大量计数和成文导致遗漏；并行机会有限，串行依赖清晰，交接开销小。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 1396
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P011

没有结构合法的计划；仍需记录缺失 / 失败及其理由。

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: null,
  &quot;raw_plan_if_unparsed&quot;: &quot;{\n  \&quot;schema_version\&quot;: \&quot;text-task-plan-v2\&quot;,\n  \&quot;decomposition_reason\&quot;: \&quot;任务为封闭场景下的确定性统计与建议生成：需先按组汇总100条记录的有资格/无资格人数，再与固定席位比较并形成两阶段建议。汇总与比较强耦合且数据量中等，拆分为一个汇总节点和一个最终生成节点即可保证计算一致性和约束保留；进一步拆分不会带来质量收益，反而增加交接与核对开销。\&quot;,\n  \&quot;nodes\&quot;: [\n    {\n      \&quot;node_id\&quot;: \&quot;summary\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是文本任务执行器。仅使用以下材料，不联网、不执行工具、不虚构。材料为虚构封闭场景「培训分班容量分析」，不代表真实机构或法律规则。\\n\\n规则：\\nE1：每条记录给出申请人数和已完成前置课程人数，仅已完成课程者有资格安排。\\nE2：先按组汇总有资格人数，再与甲70、乙90、丙110、丁130的组席位比较。\\nE3：各组时段相互冲突，剩余席位不能跨组相抵；不能用总申请人数冒充有资格需求。\\nE4：只建议补充席位或调整时段，没有授权替任何人报名。\\n\\n材料：\\n来源 test_seating-L001：第1项，乙组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L002：第2项，丙组，申请 7 人，其中完成前置课程 6 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L003：第3项，丁组，申请 8 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L004：第4项，甲组，申请 9 人，其中完成前置课程 8 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L005：第5项，乙组，申请 10 人，其中完成前置课程 2 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L006：第6项，丙组，申请 11 人，其中完成前置课程 6 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L007：第7项，丁组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L008：第8项，甲组，申请 13 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L009：第9项，乙组，申请 14 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L010：第10项，丙组，申请 15 人，其中完成前置课程 6 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L011：第11项，丁组，申请 16 人，其中完成前置课程 9 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L012：第12项，甲组，申请 17 人，其中完成前置课程 12 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L013：第13项，乙组，申请 5 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L014：第14项，丙组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L015：第15项，丁组，申请 7 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L016：第16项，甲组，申请 8 人，其中完成前置课程 4 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L017：第17项，乙组，申请 9 人，其中完成前置课程 9 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L018：第18项，丙组，申请 10 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L019：第19项，丁组，申请 11 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L020：第20项，甲组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L021：第21项，乙组，申请 13 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L022：第22项，丙组，申请 14 人，其中完成前置课程 4 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L023：第23项，丁组，申请 15 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L024：第24项，甲组，申请 16 人，其中完成前置课程 15 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L025：第25项，乙组，申请 17 人，其中完成前置课程 13 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L026：第26项，丙组，申请 5 人，其中完成前置课程 2 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L027：第27项，丁组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L028：第28项，甲组，申请 7 人，其中完成前置课程 4 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L029：第29项，乙组，申请 8 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L030：第30项，丙组，申请 9 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L031：第31项，丁组，申请 10 人，其中完成前置课程 8 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L032：第32项，甲组，申请 11 人，其中完成前置课程 8 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L033：第33项，乙组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L034：第34项，丙组，申请 13 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L035：第35项，丁组，申请 14 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L036：第36项，甲组，申请 15 人，其中完成前置课程 12 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L037：第37项，乙组，申请 16 人，其中完成前置课程 4 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L038：第38项，丙组，申请 17 人，其中完成前置课程 14 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L039：第39项，丁组，申请 5 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L040：第40项，甲组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L041：第41项，乙组，申请 7 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L042：第42项，丙组，申请 8 人，其中完成前置课程 6 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L043：第43项，丁组，申请 9 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L044：第44项，甲组，申请 10 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L045：第45项，乙组，申请 11 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L046：第46项，丙组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L047：第47项，丁组，申请 13 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L048：第48项，甲组，申请 14 人，其中完成前置课程 6 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L049：第49项，乙组，申请 15 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L050：第50项，丙组，申请 16 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L051：第51项，丁组，申请 17 人，其中完成前置课程 15 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L052：第52项，甲组，申请 5 人，其中完成前置课程 4 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L053：第53项，乙组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L054：第54项，丙组，申请 7 人，其中完成前置课程 2 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L055：第55项，丁组，申请 8 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L056：第56项，甲组，申请 9 人，其中完成前置课程 2 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L057：第57项，乙组，申请 10 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L058：第58项，丙组，申请 11 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L059：第59项，丁组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L060：第60项，甲组，申请 13 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L061：第61项，乙组，申请 14 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L062：第62项，丙组，申请 15 人，其中完成前置课程 2 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L063：第63项，丁组，申请 16 人，其中完成前置课程 16 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L064：第64项，甲组，申请 17 人，其中完成前置课程 16 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L065：第65项，乙组，申请 5 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L066：第66项，丙组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L067：第67项，丁组，申请 7 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L068：第68项，甲组，申请 8 人，其中完成前置课程 8 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L069：第69项，乙组，申请 9 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L070：第70项，丙组，申请 10 人，其中完成前置课程 6 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L071：第71项，丁组，申请 11 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L072：第72项，甲组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L073：第73项，乙组，申请 13 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L074：第74项，丙组，申请 14 人，其中完成前置课程 8 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L075：第75项，丁组，申请 15 人，其中完成前置课程 13 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L076：第76项，甲组，申请 16 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L077：第77项，乙组，申请 17 人，其中完成前置课程 17 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L078：第78项，丙组，申请 5 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L079：第79项，丁组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L080：第80项，甲组，申请 7 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L081：第81项，乙组，申请 8 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L082：第82项，丙组，申请 9 人，其中完成前置课程 4 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L083：第83项，丁组，申请 10 人，其中完成前置课程 9 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L084：第84项，甲组，申请 11 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L085：第85项，乙组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L086：第86项，丙组，申请 13 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L087：第87项，丁组，申请 14 人，其中完成前置课程 9 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L088：第88项，甲组，申请 15 人，其中完成前置课程 8 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L089：第89项，乙组，申请 16 人，其中完成前置课程 11 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L090：第90项，丙组，申请 17 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L091：第91项，丁组，申请 5 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L092：第92项，甲组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L093：第93项，乙组，申请 7 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L094：第94项，丙组，申请 8 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L095：第95项，丁组，申请 9 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L096：第96项，甲组，申请 10 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L097：第97项，乙组，申请 11 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L098：第98项，丙组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L099：第99项，丁组，申请 13 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L100：第100项，甲组，申请 14 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n\\n请按甲、乙、丙、丁四组分别汇总：\\n1. 申请总人数；\\n2. 有资格人数（已完成前置课程人数之和）；\\n3. 无资格人数（申请总人数减有资格人数）；\\n4. 各组席位：甲70、乙90、丙110、丁130；\\n5. 席位缺口：有资格人数减席位；正数表示缺口，负数或零表示剩余席位。\\n\\n只输出 JSON 对象，不要输出 Markdown 代码围栏或额外说明。JSON 结构如下：\\n{\\n  \\\&quot;甲组\\\&quot;: \\\&quot;申请总人数=数值；有资格人数=数值；无资格人数=数值；席位=70；席位缺口=数值（正数表示缺口，负数表示剩余）\\\&quot;,\\n  \\\&quot;乙组\\\&quot;: \\\&quot;申请总人数=数值；有资格人数=数值；无资格人数=数值；席位=90；席位缺口=数值（正数表示缺口，负数表示剩余）\\\&quot;,\\n  \\\&quot;丙组\\\&quot;: \\\&quot;申请总人数=数值；有资格人数=数值；无资格人数=数值；席位=110；席位缺口=数值（正数表示缺口，负数表示剩余）\\\&quot;,\\n  \\\&quot;丁组\\\&quot;: \\\&quot;申请总人数=数值；有资格人数=数值；无资格人数=数值；席位=130；席位缺口=数值（正数表示缺口，负数表示剩余）\\\&quot;\\n}\&quot;,\n      \&quot;parents\&quot;: [],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;按甲、乙、丙、丁四组汇总申请总人数、有资格人数、无资格人数，并与固定席位比较得到席位缺口。\&quot;,\n        \&quot;inputs\&quot;: {},\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;json\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;甲组\&quot;: \&quot;包含甲组申请总人数、有资格人数、无资格人数、席位70和席位缺口的字符串\&quot;,\n            \&quot;乙组\&quot;: \&quot;包含乙组申请总人数、有资格人数、无资格人数、席位90和席位缺口的字符串\&quot;,\n            \&quot;丙组\&quot;: \&quot;包含丙组申请总人数、有资格人数、无资格人数、席位110和席位缺口的字符串\&quot;,\n            \&quot;丁组\&quot;: \&quot;包含丁组申请总人数、有资格人数、无资格人数、席位130和席位缺口的字符串\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;medium\&quot;,\n          \&quot;input_budget_tokens\&quot;: 65536,\n          \&quot;expected_output_tokens\&quot;: 1200\n        },\n        \&quot;checks\&quot;: [\n          \&quot;四组均给出申请总人数、有资格人数、无资格人数、席位和席位缺口\&quot;,\n          \&quot;有资格人数等于该组各记录已完成前置课程人数之和\&quot;,\n          \&quot;无资格人数等于申请总人数减有资格人数\&quot;,\n          \&quot;席位缺口等于有资格人数减对应组席位，且正负含义正确\&quot;,\n          \&quot;不跨组相抵，不将总申请人数当作有资格需求\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    },\n    {\n      \&quot;node_id\&quot;: \&quot;answer\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是文本任务执行器。仅使用以下材料和上游汇总结果，不联网、不执行工具、不虚构。材料为虚构封闭场景「培训分班容量分析」，不代表真实机构或法律规则。\\n\\n规则：\\nE1：每条记录给出申请人数和已完成前置课程人数，仅已完成课程者有资格安排。\\nE2：先按组汇总有资格人数，再与甲70、乙90、丙110、丁130的组席位比较。\\nE3：各组时段相互冲突，剩余席位不能跨组相抵；不能用总申请人数冒充有资格需求。\\nE4：只建议补充席位或调整时段，没有授权替任何人报名。\\n\\n材料：\\n来源 test_seating-L001：第1项，乙组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L002：第2项，丙组，申请 7 人，其中完成前置课程 6 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L003：第3项，丁组，申请 8 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L004：第4项，甲组，申请 9 人，其中完成前置课程 8 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L005：第5项，乙组，申请 10 人，其中完成前置课程 2 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L006：第6项，丙组，申请 11 人，其中完成前置课程 6 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L007：第7项，丁组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L008：第8项，甲组，申请 13 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L009：第9项，乙组，申请 14 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L010：第10项，丙组，申请 15 人，其中完成前置课程 6 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L011：第11项，丁组，申请 16 人，其中完成前置课程 9 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L012：第12项，甲组，申请 17 人，其中完成前置课程 12 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L013：第13项，乙组，申请 5 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L014：第14项，丙组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L015：第15项，丁组，申请 7 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L016：第16项，甲组，申请 8 人，其中完成前置课程 4 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L017：第17项，乙组，申请 9 人，其中完成前置课程 9 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L018：第18项，丙组，申请 10 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L019：第19项，丁组，申请 11 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L020：第20项，甲组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L021：第21项，乙组，申请 13 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L022：第22项，丙组，申请 14 人，其中完成前置课程 4 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L023：第23项，丁组，申请 15 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L024：第24项，甲组，申请 16 人，其中完成前置课程 15 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L025：第25项，乙组，申请 17 人，其中完成前置课程 13 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L026：第26项，丙组，申请 5 人，其中完成前置课程 2 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L027：第27项，丁组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L028：第28项，甲组，申请 7 人，其中完成前置课程 4 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L029：第29项，乙组，申请 8 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L030：第30项，丙组，申请 9 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L031：第31项，丁组，申请 10 人，其中完成前置课程 8 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L032：第32项，甲组，申请 11 人，其中完成前置课程 8 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L033：第33项，乙组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L034：第34项，丙组，申请 13 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L035：第35项，丁组，申请 14 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L036：第36项，甲组，申请 15 人，其中完成前置课程 12 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L037：第37项，乙组，申请 16 人，其中完成前置课程 4 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L038：第38项，丙组，申请 17 人，其中完成前置课程 14 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L039：第39项，丁组，申请 5 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L040：第40项，甲组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L041：第41项，乙组，申请 7 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L042：第42项，丙组，申请 8 人，其中完成前置课程 6 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L043：第43项，丁组，申请 9 人，其中完成前置课程 1 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L044：第44项，甲组，申请 10 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L045：第45项，乙组，申请 11 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L046：第46项，丙组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L047：第47项，丁组，申请 13 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L048：第48项，甲组，申请 14 人，其中完成前置课程 6 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L049：第49项，乙组，申请 15 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L050：第50项，丙组，申请 16 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L051：第51项，丁组，申请 17 人，其中完成前置课程 15 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L052：第52项，甲组，申请 5 人，其中完成前置课程 4 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L053：第53项，乙组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L054：第54项，丙组，申请 7 人，其中完成前置课程 2 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L055：第55项，丁组，申请 8 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L056：第56项，甲组，申请 9 人，其中完成前置课程 2 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L057：第57项，乙组，申请 10 人，其中完成前置课程 3 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L058：第58项，丙组，申请 11 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L059：第59项，丁组，申请 12 人，其中完成前置课程 10 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L060：第60项，甲组，申请 13 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L061：第61项，乙组，申请 14 人，其中完成前置课程 7 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L062：第62项，丙组，申请 15 人，其中完成前置课程 2 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L063：第63项，丁组，申请 16 人，其中完成前置课程 16 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L064：第64项，甲组，申请 17 人，其中完成前置课程 16 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L065：第65项，乙组，申请 5 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L066：第66项，丙组，申请 6 人，其中完成前置课程 0 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L067：第67项，丁组，申请 7 人，其中完成前置课程 5 人；没有其他资格证明，先筛资格再分配。\\n来源 test_seating-L068：第68项，甲组，申请 8 人，其中完成前置课程 8 人；没有其他资格证明，先&quot;,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;length&quot;,
    &quot;output_tokens&quot;: 8192
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P027

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| summarize | extraction | 无 | 按组汇总100条记录的申请、有资格、无资格人数并计算席位缺口，保留来源编号明细。 |
| answer | generation | summarize | 核对汇总结果并输出包含按组统计、两阶段分班建议和约束说明的最终正文。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;summarize&quot;,
        &quot;node_type&quot;: &quot;extraction&quot;,
        &quot;prompt_template&quot;: &quot;仅使用原始任务中提供的 test_seating-L001 至 test_seating-L100 共100条记录。按甲、乙、丙、丁四组分别统计：申请人数、已完成前置课程人数（即有资格人数）、无资格人数（申请人数减有资格人数）。再按材料给出的席位：甲70、乙90、丙110、丁130，计算每组席位缺口，缺口=有资格人数-席位；正数表示缺席位，负数或零表示席位有余。不得跨组相抵，不得用总申请人数冒充有资格需求。保留每条记录来源编号与组别、申请人数、完成前置课程人数的对应关系，确保可追溯。输出为 JSON，字段值均为非空字符串：group_summary 用分号分隔四组，每组写明「组名；申请人数；有资格人数；无资格人数；席位；席位缺口」；record_details 用分号分隔100条记录，每条写明「来源编号；组名；申请人数；完成前置课程人数」；assumptions 写明统计口径与未确认事项。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;按组汇总100条记录的申请、有资格、无资格人数并计算席位缺口，保留来源编号明细。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;group_summary&quot;: &quot;四组汇总结果，含组名、申请人数、有资格人数、无资格人数、席位、席位缺口&quot;,
              &quot;record_details&quot;: &quot;100条记录的来源编号、组名、申请人数、完成前置课程人数明细&quot;,
              &quot;assumptions&quot;: &quot;统计口径、已知约束与未确认事项&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 65536,
            &quot;expected_output_tokens&quot;: 4096
          },
          &quot;checks&quot;: [
            &quot;四组申请人数之和等于100条记录申请人数总和&quot;,
            &quot;每组有资格人数等于该组完成前置课程人数之和，无资格人数等于申请人数减有资格人数&quot;,
            &quot;席位缺口按有资格人数减对应组席位计算，未跨组相抵&quot;,
            &quot;record_details 覆盖全部100条来源编号且与原始材料一致&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;仅使用原始任务材料和 summarize 节点提供的统计结果。先核对四组申请、有资格、无资格人数与席位缺口是否与材料一致，检查有无遗漏或冲突。然后按交付要求输出最终正文，顺序为：一、按组统计结果，分别列出甲、乙、丙、丁四组的申请人数、有资格人数、无资格人数、席位及席位缺口，并保留来源编号依据；二、两阶段分班建议，第一阶段仅安排已完成前置课程的有资格人员，第二阶段针对席位缺口提出补充席位或调整时段的建议；三、约束说明，明确各组时段冲突、剩余席位不能跨组相抵、不能用总申请人数冒充有资格需求、未授权替任何人报名。区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。直接输出正文，不封装为 JSON。&quot;,
        &quot;parents&quot;: [
          &quot;summarize&quot;
        ],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;核对汇总结果并输出包含按组统计、两阶段分班建议和约束说明的最终正文。&quot;,
          &quot;inputs&quot;: {
            &quot;summarize&quot;: {
              &quot;fields&quot;: [
                &quot;group_summary&quot;,
                &quot;record_details&quot;,
                &quot;assumptions&quot;
              ],
              &quot;reason&quot;: &quot;最终正文需要消费按组统计、来源明细和统计口径，以核对一致性并保留来源编号。&quot;
            }
          },
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终交付正文，依次包含按组统计结果、两阶段分班建议、约束说明&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 65536,
            &quot;expected_output_tokens&quot;: 4096
          },
          &quot;checks&quot;: [
            &quot;正文完整包含按组统计、两阶段分班建议、约束说明三部分且顺序符合交付要求&quot;,
            &quot;四组统计数字与材料一致，并保留来源编号依据&quot;,
            &quot;明确区分已知事实、建议和未知事项，未虚构原因、数据或已执行操作&quot;,
            &quot;保留不能跨组调剂和未授权代报名的约束&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务为封闭材料下的确定性统计与建议生成：需先按组汇总100条记录，再与固定席位比较并形成两阶段建议。汇总与比较强耦合且数据量中等，拆分为一个汇总节点和一个最终生成节点即可；汇总节点产出结构化统计，最终节点核对并直接输出完整正文，避免多分支交接带来的重复读取与一致性风险。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 1254
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

## 题目 2

<details><summary>查看原始题目与材料</summary>
<pre>这是独立编写的虚构封闭场景「小型研究方案筛选」，不代表真实机构或法律规则。只用以下材料，不联网或执行工具。
G1：项目必须六周内完成、支出不超过40单位，并向所有参与者提供远程途径。G2：方案甲：五周、38单位、仅线下；方案乙：六周、40单位、提供远程；方案丙：四周、45单位、提供远程。G3：甲声称改成混合方式不用追加成本，但未提交排程或报价。

交付要求：同时检查三个硬条件，推荐当前有证据可行的方案；说明其他方案需要补什么证据或调整，不能把口头承诺当作既成事实。</pre>
</details>

**原始验收：** 完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。；遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。

<details><summary>查看冻结参考（长材料已独立重算）</summary>
<pre>只有乙同时满足；甲缺远程且修改未经证明；丙超5单位，不能因更快就忽略预算。</pre>
</details>

### P002

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| answer | generation | 无 | 依据给定材料检查三个硬条件，推荐当前有证据可行的方案，并说明其他方案需补充的证据或调整。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;这是独立编写的虚构封闭场景「小型研究方案筛选」，不代表真实机构或法律规则。只用以下材料，不联网或执行工具。\nG1：项目必须六周内完成、支出不超过40单位，并向所有参与者提供远程途径。G2：方案甲：五周、38单位、仅线下；方案乙：六周、40单位、提供远程；方案丙：四周、45单位、提供远程。G3：甲声称改成混合方式不用追加成本，但未提交排程或报价。\n\n交付要求：同时检查三个硬条件，推荐当前有证据可行的方案；说明其他方案需要补什么证据或调整，不能把口头承诺当作既成事实。\n\n请直接输出最终正文，依次包含以下部分：\n1. 三个硬条件检查：分别对方案甲、方案乙、方案丙逐项核对「六周内完成」「支出不超过40单位」「向所有参与者提供远程途径」，并保留来源编号（G1、G2、G3）。\n2. 当前有证据可行的方案推荐：基于材料中已明确的事实给出推荐，并说明依据。\n3. 其他方案需要补充的证据或调整：说明方案甲、方案丙分别需要补什么证据或做什么调整才可能满足条件；明确区分已知事实、建议和未知事项，不得把口头承诺当作既成事实。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;依据给定材料检查三个硬条件，推荐当前有证据可行的方案，并说明其他方案需补充的证据或调整。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终交付正文，依次包含三个硬条件检查、当前有证据可行的方案推荐、其他方案需要补充的证据或调整。&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 16384,
            &quot;expected_output_tokens&quot;: 1200
          },
          &quot;checks&quot;: [
            &quot;正文同时检查六周内完成、支出不超过40单位、提供远程途径三个硬条件，并覆盖方案甲、乙、丙。&quot;,
            &quot;推荐基于材料中已明确的事实，不把G3口头承诺当作既成事实。&quot;,
            &quot;说明方案甲和方案丙分别需要补充的证据或调整。&quot;,
            &quot;事实和计算与材料一致，并保留G1、G2、G3来源编号。&quot;,
            &quot;区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务规模小、材料短，三个硬条件检查与方案比较强耦合，拆分不会带来明显质量或时延收益，反而增加交接与汇总开销，因此采用单节点直接完成。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 758
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P007

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| answer | generation | 无 | 依据给定材料检查三个硬条件，推荐当前有证据可行的方案，并说明其他方案需补充的证据或调整，直接输出最终正文。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;这是独立编写的虚构封闭场景「小型研究方案筛选」，不代表真实机构或法律规则。只用以下材料，不联网或执行工具。\nG1：项目必须六周内完成、支出不超过40单位，并向所有参与者提供远程途径。G2：方案甲：五周、38单位、仅线下；方案乙：六周、40单位、提供远程；方案丙：四周、45单位、提供远程。G3：甲声称改成混合方式不用追加成本，但未提交排程或报价。\n\n交付要求：同时检查三个硬条件，推荐当前有证据可行的方案；说明其他方案需要补什么证据或调整，不能把口头承诺当作既成事实。\n\n请直接输出最终正文，按以下顺序组织：\n1. 三个硬条件检查：逐项列出「六周内完成」「支出不超过40单位」「向所有参与者提供远程途径」，并依据材料中的方案甲、乙、丙分别核对是否满足，保留来源编号（G1、G2、G3）。\n2. 当前有证据可行的方案推荐：基于材料中已提交的排程和报价等证据，说明推荐方案及理由；不得把口头承诺当作既成事实。\n3. 其他方案需要补充的证据或调整：分别说明未获推荐的方案需要补充什么证据或做出什么调整，才能满足三个硬条件；对材料未说明的事项保持未知或写成条件判断，不虚构原因、数据或已执行的操作。\n\n注意：事实和计算必须与材料一致；区分已知事实、建议和未知事项；引用材料时保留来源编号。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;依据给定材料检查三个硬条件，推荐当前有证据可行的方案，并说明其他方案需补充的证据或调整，直接输出最终正文。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;包含三个硬条件检查、当前有证据可行的方案推荐、其他方案需补充证据或调整的完整最终正文，按交付要求顺序呈现。&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 16384,
            &quot;expected_output_tokens&quot;: 1200
          },
          &quot;checks&quot;: [
            &quot;正文同时检查了六周内完成、支出不超过40单位、提供远程途径三个硬条件，并保留G1、G2、G3来源编号。&quot;,
            &quot;推荐结论仅依据材料中已提交的排程和报价等证据，未把甲的口头承诺当作既成事实。&quot;,
            &quot;分别说明了未获推荐方案需要补充的证据或调整，且未虚构材料未说明的原因、数据或已执行操作。&quot;,
            &quot;事实和计算与材料一致，区分了已知事实、建议和未知事项。&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务规模小、材料短，三个硬条件检查与方案比较强耦合，拆分不会带来明显并行收益，反而增加交接与汇总开销；单节点直接完成检查、比较和交付最合适。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 827
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P009

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| answer | generation | 无 | 依据给定材料检查三个硬条件、推荐当前有证据可行的方案，并说明其他方案需补充的证据或调整，直接输出最终正文。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;这是独立编写的虚构封闭场景「小型研究方案筛选」，不代表真实机构或法律规则。只用以下材料，不联网或执行工具。\nG1：项目必须六周内完成、支出不超过40单位，并向所有参与者提供远程途径。G2：方案甲：五周、38单位、仅线下；方案乙：六周、40单位、提供远程；方案丙：四周、45单位、提供远程。G3：甲声称改成混合方式不用追加成本，但未提交排程或报价。\n\n交付要求：同时检查三个硬条件，推荐当前有证据可行的方案；说明其他方案需要补什么证据或调整，不能把口头承诺当作既成事实。\n\n请直接输出最终正文，依次包含：\n1. 三个硬条件检查：分别对方案甲、乙、丙核对「六周内完成」「支出不超过40单位」「向所有参与者提供远程途径」，并保留来源编号（G1、G2、G3）。\n2. 当前有证据可行的方案推荐：基于材料中已有证据说明推荐方案及理由。\n3. 其他方案需要补什么证据或调整：分别说明甲、丙等未满足或证据不足的方案需要补充哪些证据或做出什么调整，明确区分已知事实、建议和未知事项，不能把口头承诺当作既成事实。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;依据给定材料检查三个硬条件、推荐当前有证据可行的方案，并说明其他方案需补充的证据或调整，直接输出最终正文。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;包含三个硬条件检查、当前有证据可行的方案推荐、其他方案需补充证据或调整的完整正文，保留来源编号，区分已知事实、建议和未知事项。&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 16384,
            &quot;expected_output_tokens&quot;: 1200
          },
          &quot;checks&quot;: [
            &quot;正文同时检查六周内完成、支出不超过40单位、向所有参与者提供远程途径三个硬条件，并覆盖方案甲、乙、丙。&quot;,
            &quot;推荐基于材料中已有证据的方案，并说明理由。&quot;,
            &quot;对其他方案说明需要补充的证据或调整，且不把口头承诺当作既成事实。&quot;,
            &quot;事实和计算与材料一致，保留来源编号G1、G2、G3。&quot;,
            &quot;区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务规模小、材料短，三个硬条件检查与方案比较强耦合，拆分不会带来明显质量或时延收益，反而增加交接与汇总开销，因此用单节点直接完成。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 770
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P015

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| answer | generation | 无 | 依据给定材料检查三个硬条件，推荐当前有证据可行的方案，并说明其他方案需补充的证据或调整。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;你是小型研究方案筛选分析员。仅使用以下材料，不联网、不执行工具，不虚构原因、数据或已执行的操作。材料：G1：项目必须六周内完成、支出不超过40单位，并向所有参与者提供远程途径。G2：方案甲：五周、38单位、仅线下；方案乙：六周、40单位、提供远程；方案丙：四周、45单位、提供远程。G3：甲声称改成混合方式不用追加成本，但未提交排程或报价。\n\n请按以下要求输出最终正文：\n1. 同时检查三个硬条件：六周内完成、支出不超过40单位、向所有参与者提供远程途径；逐项对照方案甲、乙、丙，保留来源编号（G1、G2、G3），明确哪些条件满足、哪些不满足、哪些未知。\n2. 推荐当前有证据可行的方案，并说明推荐依据；不得把口头承诺当作既成事实。\n3. 说明其他方案需要补充什么证据或调整才能满足全部硬条件；对方案甲的口头混合方式承诺，明确其尚未提交排程或报价，因此不能作为已满足远程途径或成本条件的证据。\n4. 区分已知事实、建议和未知事项；所有事实和计算与材料一致。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;依据给定材料检查三个硬条件，推荐当前有证据可行的方案，并说明其他方案需补充的证据或调整。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;包含三个硬条件逐项检查、当前有证据可行的方案推荐及依据、其他方案需补充证据或调整说明的最终正文，保留来源编号并区分已知事实、建议和未知事项。&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 16384,
            &quot;expected_output_tokens&quot;: 1200
          },
          &quot;checks&quot;: [
            &quot;逐项检查六周内完成、支出不超过40单位、提供远程途径三个条件，并覆盖方案甲、乙、丙。&quot;,
            &quot;推荐结论仅基于材料中有证据支持的事实，不把G3口头承诺当作既成事实。&quot;,
            &quot;说明方案甲、丙等未满足条件方案需补充的证据或调整。&quot;,
            &quot;保留G1、G2、G3来源编号，区分已知事实、建议和未知事项。&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务规模小、材料短，三个硬条件检查与方案比较强耦合，拆分不会带来明显质量或时延收益，反而增加交接与汇总开销，因此采用单节点直接完成检查、推荐与补证说明。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 757
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P028

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| answer | generation | 无 | 完整完成原始任务，逐条核对所有交付要求。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;短或强耦合交付不拆分。&quot;,
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;parents&quot;: [],
        &quot;prompt_template&quot;: &quot;完整完成原始任务，逐条核对所有交付要求。&quot;,
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;完整完成原始任务，逐条核对所有交付要求。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终建议与可追溯依据&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;medium&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;保留证据与假设，不虚构数据&quot;,
            &quot;覆盖本节点职责并明确限制&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ]
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: null,
  &quot;execution_trace&quot;: [
    {
      &quot;node_id&quot;: &quot;answer&quot;,
      &quot;output&quot;: &quot;**最终建议与可追溯依据**\n\n**一、三个硬条件核对（依据G1、G2）**\n\n| 方案 | 六周内完成 | 支出≤40单位 | 提供远程途径 | 是否满足全部硬条件 |\n|---|---|---|---|---|\n| 甲 | 是（五周） | 是（38单位） | 否（仅线下） | 否 |\n| 乙 | 是（六周） | 是（40单位） | 是 | **是** |\n| 丙 | 是（四周） | 否（45单位） | 是 | 否 |\n\n**二、推荐方案**\n\n推荐**方案乙**。依据G2，方案乙在六周内完成、支出40单位、提供远程途径，三项硬条件全部满足，是当前有证据支持可行的唯一方案。\n\n**三、其他方案所需补充证据或调整**\n\n- **方案甲**（依据G2、G3）：当前证据显示其仅线下，不满足远程条件。甲声称可改为混合方式且不追加成本，但该说法仅为口头承诺，未提交排程或报价，不能视为既成事实。若要使甲可行，需补充：①修改后的排程（含远程环节安排）；②不追加成本的正式报价或成本核算；③确认修改后仍能在六周内完成。在获得上述证据前，甲不满足全部硬条件。\n- **方案丙**（依据G2）：当前支出45单位，超出40单位上限，不满足支出条件。若要使丙可行，需调整方案以将支出降至40单位或以下，并提供更新后的预算证据；同时确认调整后仍能在六周内完成且保留远程途径。\n\n**四、假设与不确定性**\n\n- 本结论基于G2中给出的方案参数，假设各方案的时间、成本、远程属性均按材料原样理解。\n- 方案甲关于混合方式的说法（G3）属于未证实声明，本结论未将其纳入可行性判断。\n- 未对材料之外的任何方案或条件进行假设，也未执行任何工具或检索。&quot;
    }
  ],
  &quot;final_output&quot;: &quot;**最终建议与可追溯依据**\n\n**一、三个硬条件核对（依据G1、G2）**\n\n| 方案 | 六周内完成 | 支出≤40单位 | 提供远程途径 | 是否满足全部硬条件 |\n|---|---|---|---|---|\n| 甲 | 是（五周） | 是（38单位） | 否（仅线下） | 否 |\n| 乙 | 是（六周） | 是（40单位） | 是 | **是** |\n| 丙 | 是（四周） | 否（45单位） | 是 | 否 |\n\n**二、推荐方案**\n\n推荐**方案乙**。依据G2，方案乙在六周内完成、支出40单位、提供远程途径，三项硬条件全部满足，是当前有证据支持可行的唯一方案。\n\n**三、其他方案所需补充证据或调整**\n\n- **方案甲**（依据G2、G3）：当前证据显示其仅线下，不满足远程条件。甲声称可改为混合方式且不追加成本，但该说法仅为口头承诺，未提交排程或报价，不能视为既成事实。若要使甲可行，需补充：①修改后的排程（含远程环节安排）；②不追加成本的正式报价或成本核算；③确认修改后仍能在六周内完成。在获得上述证据前，甲不满足全部硬条件。\n- **方案丙**（依据G2）：当前支出45单位，超出40单位上限，不满足支出条件。若要使丙可行，需调整方案以将支出降至40单位或以下，并提供更新后的预算证据；同时确认调整后仍能在六周内完成且保留远程途径。\n\n**四、假设与不确定性**\n\n- 本结论基于G2中给出的方案参数，假设各方案的时间、成本、远程属性均按材料原样理解。\n- 方案甲关于混合方式的说法（G3）属于未证实声明，本结论未将其纳入可行性判断。\n- 未对材料之外的任何方案或条件进行假设，也未执行任何工具或检索。&quot;
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

## 题目 3

<details><summary>查看原始题目与材料</summary>
<pre>这是独立编写的虚构封闭场景「会议行动项整理」，不代表真实机构或法律规则。只用以下材料，不联网或执行工具。
M1：周一例会决定：设备组负责在周五前给出检查清单。M2：运营组只负责汇总现场反馈，完成日期尚未确定。M3：某成员建议周三试运行，但会议未表决，不能列成已批准决定。

交付要求：仅输出一张简短行动项表和一条待确认事项；区分决定与建议，不把未知期限补成周五。</pre>
</details>

**原始验收：** 完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。；遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。

<details><summary>查看冻结参考（长材料已独立重算）</summary>
<pre>设备组检查清单周五前；运营组现场反馈汇总期限待确认；周三试运行只是未表决建议。</pre>
</details>

### P003

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| answer | generation | 无 | 根据三条虚构会议材料生成一张简短行动项表和一条待确认事项，区分决定与建议，并保留来源编号。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;这是独立编写的虚构封闭场景「会议行动项整理」，不代表真实机构或法律规则。只用以下材料，不联网或执行工具。\nM1：周一例会决定：设备组负责在周五前给出检查清单。M2：运营组只负责汇总现场反馈，完成日期尚未确定。M3：某成员建议周三试运行，但会议未表决，不能列成已批准决定。\n\n交付要求：仅输出一张简短行动项表和一条待确认事项；区分决定与建议，不把未知期限补成周五。\n\n请直接输出最终正文，包含：\n1. 行动项表：列出行动项、责任方、期限、来源编号，并明确区分「决定」与「建议」；对未确定期限保持未知，不得补成周五。\n2. 待确认事项：仅一条，说明运营组汇总现场反馈的完成日期尚未确定，需要确认。\n\n约束：事实和计算与材料一致，保留来源编号；遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;根据三条虚构会议材料生成一张简短行动项表和一条待确认事项，区分决定与建议，并保留来源编号。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终交付的行动项表和待确认事项正文&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 16384,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;行动项表包含设备组检查清单、运营组汇总现场反馈、周三试运行建议三项内容&quot;,
            &quot;明确区分决定与建议，周三试运行未被列为已批准决定&quot;,
            &quot;运营组完成日期保持未知，未补成周五&quot;,
            &quot;保留 M1、M2、M3 来源编号&quot;,
            &quot;待确认事项仅一条，指向运营组完成日期未确定&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务规模小、材料短，仅需从三条材料中提取行动项并区分决定与建议，再生成简短表格和待确认事项。拆分不会带来质量或时延收益，反而增加交接开销，因此使用单节点完成。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 667
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P008

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| answer | generation | 无 | 根据三条虚构会议材料生成简短行动项表和一条待确认事项，区分决定与建议并保留来源编号。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;这是独立编写的虚构封闭场景「会议行动项整理」，不代表真实机构或法律规则。只用以下材料，不联网或执行工具。\nM1：周一例会决定：设备组负责在周五前给出检查清单。M2：运营组只负责汇总现场反馈，完成日期尚未确定。M3：某成员建议周三试运行，但会议未表决，不能列成已批准决定。\n\n交付要求：仅输出一张简短行动项表和一条待确认事项；区分决定与建议，不把未知期限补成周五。\n\n请直接输出最终正文，包含：\n1. 行动项表：区分「已批准决定」与「建议」，保留来源编号；设备组检查清单的期限按材料写周五前；运营组汇总现场反馈的完成日期写尚未确定；周三试运行列为建议且注明未表决。\n2. 待确认事项：仅一条，写明运营组汇总现场反馈的完成日期尚未确定，需待确认。\n不要补充材料未说明的原因、数据或已执行操作。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;根据三条虚构会议材料生成简短行动项表和一条待确认事项，区分决定与建议并保留来源编号。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终交付正文：行动项表加一条待确认事项&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 16384,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;行动项表区分已批准决定与建议，并保留 M1、M2、M3 来源编号&quot;,
            &quot;设备组检查清单期限写周五前，运营组汇总现场反馈期限写尚未确定&quot;,
            &quot;周三试运行列为建议并注明会议未表决&quot;,
            &quot;待确认事项仅一条，且不把未知期限补成周五&quot;,
            &quot;不虚构材料未说明的原因、数据或已执行操作&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务规模小、材料仅三条且交付物简短，拆分会引入交接与汇总开销而无质量或时延收益，故采用单节点直接生成。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 646
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P016

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| extract | extraction | 无 | 从材料中提取行动项、建议和未知事项，保留来源编号并区分事实状态 |
| answer | generation | extract | 生成一张简短行动项表和一条待确认事项，区分决定与建议并保留来源编号 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;extract&quot;,
        &quot;node_type&quot;: &quot;extraction&quot;,
        &quot;prompt_template&quot;: &quot;阅读以下虚构封闭场景材料，提取行动项相关信息。只依据材料，不联网、不执行工具、不补充外部知识。\n\n材料：\nM1：周一例会决定：设备组负责在周五前给出检查清单。M2：运营组只负责汇总现场反馈，完成日期尚未确定。M3：某成员建议周三试运行，但会议未表决，不能列成已批准决定。\n\n请输出结构化提取结果，保留来源编号，区分「已批准决定」「建议」「未知事项」。对每个行动项给出：负责方、事项内容、期限状态（明确期限/未确定/不适用）、来源编号。不要将建议写成决定，不要将未知期限补成周五。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;从材料中提取行动项、建议和未知事项，保留来源编号并区分事实状态&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;decisions&quot;: &quot;已批准决定的内容，逐项列出负责方、事项、期限状态和来源编号&quot;,
              &quot;suggestions&quot;: &quot;建议但未批准的内容，逐项列出建议内容、状态和来源编号&quot;,
              &quot;unknowns&quot;: &quot;材料中明确未确定或未说明的事项，逐项列出并保留来源编号&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 16384,
            &quot;expected_output_tokens&quot;: 800
          },
          &quot;checks&quot;: [
            &quot;已批准决定仅包含M1内容，且保留来源编号M1&quot;,
            &quot;M2的完成日期保持未确定，不写成周五或其他具体日期&quot;,
            &quot;M3被列为建议而非决定，并注明未表决&quot;,
            &quot;所有输出字段均为非空字符串&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;根据以下提取结果，输出最终交付内容。只依据提取结果和原始材料，不联网、不执行工具、不补充外部知识。\n\n原始材料：\nM1：周一例会决定：设备组负责在周五前给出检查清单。M2：运营组只负责汇总现场反馈，完成日期尚未确定。M3：某成员建议周三试运行，但会议未表决，不能列成已批准决定。\n\n提取结果：\n{extract}\n\n交付要求：仅输出一张简短行动项表和一条待确认事项；区分决定与建议，不把未知期限补成周五。表格需包含负责方、事项、期限状态和来源编号；待确认事项单独列出。直接输出正文，不要封装为JSON。&quot;,
        &quot;parents&quot;: [
          &quot;extract&quot;
        ],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;生成一张简短行动项表和一条待确认事项，区分决定与建议并保留来源编号&quot;,
          &quot;inputs&quot;: {
            &quot;extract&quot;: {
              &quot;fields&quot;: [
                &quot;decisions&quot;,
                &quot;suggestions&quot;,
                &quot;unknowns&quot;
              ],
              &quot;reason&quot;: &quot;需要消费提取出的决定、建议和未知事项，才能准确生成区分状态并保留来源编号的行动项表和待确认事项&quot;
            }
          },
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终交付的行动项表和待确认事项正文&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 65536,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;输出仅包含一张简短行动项表和一条待确认事项&quot;,
            &quot;行动项表区分已批准决定和建议，M3不列为已批准决定&quot;,
            &quot;M2的完成日期保持未确定，不写成周五或其他具体日期&quot;,
            &quot;保留来源编号M1、M2、M3&quot;,
            &quot;直接输出正文，不封装为JSON&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务为短小封闭场景，材料仅三条，需同时完成事实提取、决定与建议区分、未知期限保留及表格化交付。拆分为提取与生成两个节点可让生成节点获得结构化事实，降低漏项和混淆风险；但材料很短，进一步拆分收益不足。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 1112
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P017

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| answer | generation | 无 | 根据三条虚构会议材料生成简短行动项表和一条待确认事项，区分决定与建议并保留来源编号。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;这是独立编写的虚构封闭场景「会议行动项整理」，不代表真实机构或法律规则。只用以下材料，不联网或执行工具。\nM1：周一例会决定：设备组负责在周五前给出检查清单。M2：运营组只负责汇总现场反馈，完成日期尚未确定。M3：某成员建议周三试运行，但会议未表决，不能列成已批准决定。\n\n交付要求：仅输出一张简短行动项表和一条待确认事项；区分决定与建议，不把未知期限补成周五。\n\n请直接输出最终正文，包含：\n1. 行动项表：列出行动项、责任方、期限、来源编号，并明确区分「决定」与「建议」；对未确定期限写「待确认」或「未确定」，不得写成周五。\n2. 待确认事项：仅一条，说明运营组汇总现场反馈的完成日期尚未确定。\n\n约束：只使用上述材料，保留来源编号 M1、M2、M3；不虚构原因、数据或已执行的操作；不把建议写成已批准决定。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;根据三条虚构会议材料生成简短行动项表和一条待确认事项，区分决定与建议并保留来源编号。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终交付的行动项表和待确认事项正文&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 16384,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;行动项表包含设备组检查清单、运营组汇总现场反馈、周三试运行建议三项内容&quot;,
            &quot;明确区分决定与建议，周三试运行未写成已批准决定&quot;,
            &quot;运营组完成日期保持未确定，未补成周五&quot;,
            &quot;保留来源编号 M1、M2、M3&quot;,
            &quot;待确认事项仅一条且与材料一致&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务材料短小、约束明确，仅需从三条材料中提取行动项、区分决定与建议并保留来源编号。拆分不会带来质量或并行收益，反而增加交接与汇总开销，因此采用单节点直接生成。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 663
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P018

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| answer | generation | 无 | 完整完成原始任务，逐条核对所有交付要求。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;短或强耦合交付不拆分。&quot;,
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;parents&quot;: [],
        &quot;prompt_template&quot;: &quot;完整完成原始任务，逐条核对所有交付要求。&quot;,
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;完整完成原始任务，逐条核对所有交付要求。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终建议与可追溯依据&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;medium&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;保留证据与假设，不虚构数据&quot;,
            &quot;覆盖本节点职责并明确限制&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ]
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: null,
  &quot;execution_trace&quot;: [
    {
      &quot;node_id&quot;: &quot;answer&quot;,
      &quot;output&quot;: &quot;行动项表：\n- 设备组：周五前给出检查清单（来源：M1）\n- 运营组：汇总现场反馈，完成日期尚未确定（来源：M2）\n\n待确认事项：\n- 周三试运行仅为某成员建议，会议未表决，是否实施待确认（来源：M3）&quot;
    }
  ],
  &quot;final_output&quot;: &quot;行动项表：\n- 设备组：周五前给出检查清单（来源：M1）\n- 运营组：汇总现场反馈，完成日期尚未确定（来源：M2）\n\n待确认事项：\n- 周三试运行仅为某成员建议，会议未表决，是否实施待确认（来源：M3）&quot;
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

## 题目 4

<details><summary>查看原始题目与材料</summary>
<pre>这是独立编写的虚构封闭场景「会议通知压缩」，不代表真实机构或法律规则。只用以下材料，不联网或执行工具。
N1：原通知：材料核对完成后，协调员应在下周三上午十点前将六份议程草稿交给会务组；若材料仍有冲突，应先标明冲突来源，并在同一截止时间提交待确认版本。

交付要求：改写成一段更简洁的通知，保留角色、数量、截止时间与两个条件分支，不增加理由或分析章节。</pre>
</details>

**原始验收：** 用一段简洁通知保留原角色、数量、截止时间、接收方和全部条件分支，不添加分析章节。；遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。

<details><summary>查看冻结参考（长材料已独立重算）</summary>
<pre>必须保留协调员、六份、下周三上午十点前、会务组；核对完成提交草稿，有冲突标明来源并按时交待确认版本。</pre>
</details>

### P005

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| answer | generation | 无 | 将原通知改写为一段更简洁的通知，保留角色、数量、截止时间、接收方和两个条件分支，不添加分析章节。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;根据以下虚构封闭场景材料，改写通知。\n\n材料：\nN1：原通知：材料核对完成后，协调员应在下周三上午十点前将六份议程草稿交给会务组；若材料仍有冲突，应先标明冲突来源，并在同一截止时间提交待确认版本。\n\n交付要求：改写成一段更简洁的通知，保留角色、数量、截止时间与两个条件分支，不增加理由或分析章节。\n\n请直接输出改写后的一段通知正文，不要添加标题、说明或分析。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;将原通知改写为一段更简洁的通知，保留角色、数量、截止时间、接收方和两个条件分支，不添加分析章节。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;改写后的一段简洁通知正文&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 16384,
            &quot;expected_output_tokens&quot;: 300
          },
          &quot;checks&quot;: [
            &quot;输出为一段通知正文，无分析、理由或额外章节&quot;,
            &quot;保留协调员角色、六份议程草稿数量、下周三上午十点前截止时间、会务组接收方&quot;,
            &quot;保留正常提交与材料冲突时标明来源并提交待确认版本两个条件分支&quot;,
            &quot;未虚构原因、数据或已执行操作&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;用一段简洁通知保留原角色、数量、截止时间、接收方和全部条件分支，不添加分析章节。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务为单一短文本改写，材料仅一段通知，无并行分析或汇总需求；拆分会增加交接开销且不提升质量，故采用单节点直接生成。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 529
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P013

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| answer | generation | 无 | 将原通知改写为一段更简洁的通知，保留角色、数量、截止时间、接收方和两个条件分支，不添加分析章节。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;根据以下虚构封闭场景材料，改写通知。\n\n材料：\nN1：原通知：材料核对完成后，协调员应在下周三上午十点前将六份议程草稿交给会务组；若材料仍有冲突，应先标明冲突来源，并在同一截止时间提交待确认版本。\n\n交付要求：改写成一段更简洁的通知，保留角色、数量、截止时间与两个条件分支，不增加理由或分析章节。\n\n请直接输出改写后的一段通知正文，不要添加标题、说明或分析。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;将原通知改写为一段更简洁的通知，保留角色、数量、截止时间、接收方和两个条件分支，不添加分析章节。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;改写后的一段简洁通知正文&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 16384,
            &quot;expected_output_tokens&quot;: 300
          },
          &quot;checks&quot;: [
            &quot;输出为一段通知正文，无分析、理由或额外章节&quot;,
            &quot;保留协调员角色、六份议程草稿数量、下周三上午十点前截止时间、会务组接收方&quot;,
            &quot;保留两个条件分支：材料核对完成后的提交要求；材料仍有冲突时标明冲突来源并提交待确认版本&quot;,
            &quot;未虚构材料未说明的原因、数据或已执行操作&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;用一段简洁通知保留原角色、数量、截止时间、接收方和全部条件分支，不添加分析章节。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务为单一短文本改写，材料仅一段通知，无并行分析或汇总需求；拆分会增加交接开销且不提升质量，故使用单节点直接生成。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 539
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P021

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| answer | generation | 无 | 将给定通知改写为一段更简洁的通知，保留角色、数量、截止时间、接收方和两个条件分支，不添加理由或分析章节。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;这是独立编写的虚构封闭场景「会议通知压缩」，不代表真实机构或法律规则。只用以下材料，不联网或执行工具。\n\nN1：原通知：材料核对完成后，协调员应在下周三上午十点前将六份议程草稿交给会务组；若材料仍有冲突，应先标明冲突来源，并在同一截止时间提交待确认版本。\n\n交付要求：改写成一段更简洁的通知，保留角色、数量、截止时间与两个条件分支，不增加理由或分析章节。\n\n请直接输出改写后的一段通知正文，不要添加标题、说明、理由或分析章节。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;将给定通知改写为一段更简洁的通知，保留角色、数量、截止时间、接收方和两个条件分支，不添加理由或分析章节。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;改写后的一段简洁通知正文&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 16384,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;输出为一段通知正文，无标题、理由或分析章节&quot;,
            &quot;保留协调员角色、六份议程草稿数量、下周三上午十点前截止时间、会务组接收方&quot;,
            &quot;保留材料核对完成后提交的正常分支，以及材料仍有冲突时标明冲突来源并提交待确认版本的条件分支&quot;,
            &quot;未虚构材料中不存在的原因、数据或已执行操作&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;用一段简洁通知保留原角色、数量、截止时间、接收方和全部条件分支，不添加分析章节。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务为单一短文本改写，材料仅一段，需保留角色、数量、截止时间、接收方和两个条件分支。拆分不会带来质量或并行收益，反而增加交接与一致性风险，因此使用单节点直接生成。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 572
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P022

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| answer | generation | 无 | 将原通知改写为一段更简洁的通知，保留角色、数量、截止时间、接收方和两个条件分支，不添加理由或分析章节。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;这是独立编写的虚构封闭场景「会议通知压缩」，不代表真实机构或法律规则。只用以下材料，不联网或执行工具。\nN1：原通知：材料核对完成后，协调员应在下周三上午十点前将六份议程草稿交给会务组；若材料仍有冲突，应先标明冲突来源，并在同一截止时间提交待确认版本。\n\n交付要求：改写成一段更简洁的通知，保留角色、数量、截止时间与两个条件分支，不增加理由或分析章节。\n\n请直接输出改写后的一段通知正文，不要添加标题、说明或分析。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;将原通知改写为一段更简洁的通知，保留角色、数量、截止时间、接收方和两个条件分支，不添加理由或分析章节。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;改写后的一段简洁通知正文&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 16384,
            &quot;expected_output_tokens&quot;: 300
          },
          &quot;checks&quot;: [
            &quot;输出为一段通知正文，无分析章节或额外理由&quot;,
            &quot;保留协调员角色、六份议程草稿数量、下周三上午十点前截止时间、会务组接收方&quot;,
            &quot;保留材料核对完成后的正常提交分支和材料仍有冲突时的待确认版本分支&quot;,
            &quot;未虚构原因、数据或已执行的操作&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;用一段简洁通知保留原角色、数量、截止时间、接收方和全部条件分支，不添加分析章节。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务为单一短文本改写，材料仅一段通知，无并行分析或汇总需求；拆分会增加交接开销且不提升质量，故采用单节点。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 541
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P025

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| answer | generation | 无 | 完整完成原始任务，逐条核对所有交付要求。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;短或强耦合交付不拆分。&quot;,
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;parents&quot;: [],
        &quot;prompt_template&quot;: &quot;完整完成原始任务，逐条核对所有交付要求。&quot;,
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;完整完成原始任务，逐条核对所有交付要求。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终建议与可追溯依据&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;medium&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;保留证据与假设，不虚构数据&quot;,
            &quot;覆盖本节点职责并明确限制&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;用一段简洁通知保留原角色、数量、截止时间、接收方和全部条件分支，不添加分析章节。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ]
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: null,
  &quot;execution_trace&quot;: [
    {
      &quot;node_id&quot;: &quot;answer&quot;,
      &quot;output&quot;: &quot;协调员应在材料核对完成后，于下周三上午十点前将六份议程草稿交给会务组；若材料仍有冲突，则须标明冲突来源，并在同一截止时间提交待确认版本。&quot;
    }
  ],
  &quot;final_output&quot;: &quot;协调员应在材料核对完成后，于下周三上午十点前将六份议程草稿交给会务组；若材料仍有冲突，则须标明冲突来源，并在同一截止时间提交待确认版本。&quot;
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

## 题目 5

<details><summary>查看原始题目与材料</summary>
<pre>这是独立编写的虚构封闭场景「物资到货交接报告」，不代表真实机构或法律规则。只用以下材料，不联网或执行工具。
H1：每条记录给出应交数量、签收数量和一份来源编号；差额为应交减签收。H2：多签不等于可以抵消另一批次少签，正缺口须逐批计算后汇总。H3：核对报告必须保留每组的来源范围，列出总应交、总签收、净差及正缺口；没有损毁或责任证据。
来源 test_shipments-L001：第1批，乙组，应交 21 件，签收 20 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L002：第2批，丙组，应交 22 件，签收 22 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L003：第3批，丁组，应交 23 件，签收 24 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L004：第4批，甲组，应交 24 件，签收 26 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L005：第5批，乙组，应交 25 件，签收 28 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L006：第6批，丙组，应交 26 件，签收 30 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L007：第7批，丁组，应交 27 件，签收 32 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L008：第8批，甲组，应交 28 件，签收 34 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L009：第9批，乙组，应交 29 件，签收 36 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L010：第10批，丙组，应交 30 件，签收 19 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L011：第11批，丁组，应交 31 件，签收 21 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L012：第12批，甲组，应交 32 件，签收 23 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L013：第13批，乙组，应交 33 件，签收 25 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L014：第14批，丙组，应交 34 件，签收 27 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L015：第15批，丁组，应交 20 件，签收 29 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L016：第16批，甲组，应交 21 件，签收 31 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L017：第17批，乙组，应交 22 件，签收 33 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L018：第18批，丙组，应交 23 件，签收 35 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L019：第19批，丁组，应交 24 件，签收 18 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L020：第20批，甲组，应交 25 件，签收 20 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L021：第21批，乙组，应交 26 件，签收 22 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L022：第22批，丙组，应交 27 件，签收 24 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L023：第23批，丁组，应交 28 件，签收 26 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L024：第24批，甲组，应交 29 件，签收 28 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L025：第25批，乙组，应交 30 件，签收 30 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L026：第26批，丙组，应交 31 件，签收 32 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L027：第27批，丁组，应交 32 件，签收 34 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L028：第28批，甲组，应交 33 件，签收 36 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L029：第29批，乙组，应交 34 件，签收 19 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L030：第30批，丙组，应交 20 件，签收 21 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L031：第31批，丁组，应交 21 件，签收 23 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L032：第32批，甲组，应交 22 件，签收 25 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L033：第33批，乙组，应交 23 件，签收 27 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L034：第34批，丙组，应交 24 件，签收 29 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L035：第35批，丁组，应交 25 件，签收 31 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L036：第36批，甲组，应交 26 件，签收 33 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L037：第37批，乙组，应交 27 件，签收 35 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L038：第38批，丙组，应交 28 件，签收 18 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L039：第39批，丁组，应交 29 件，签收 20 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L040：第40批，甲组，应交 30 件，签收 22 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L041：第41批，乙组，应交 31 件，签收 24 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L042：第42批，丙组，应交 32 件，签收 26 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L043：第43批，丁组，应交 33 件，签收 28 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L044：第44批，甲组，应交 34 件，签收 30 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L045：第45批，乙组，应交 20 件，签收 32 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L046：第46批，丙组，应交 21 件，签收 34 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L047：第47批，丁组，应交 22 件，签收 36 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L048：第48批，甲组，应交 23 件，签收 19 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L049：第49批，乙组，应交 24 件，签收 21 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L050：第50批，丙组，应交 25 件，签收 23 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L051：第51批，丁组，应交 26 件，签收 25 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L052：第52批，甲组，应交 27 件，签收 27 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L053：第53批，乙组，应交 28 件，签收 29 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L054：第54批，丙组，应交 29 件，签收 31 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L055：第55批，丁组，应交 30 件，签收 33 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L056：第56批，甲组，应交 31 件，签收 35 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L057：第57批，乙组，应交 32 件，签收 18 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L058：第58批，丙组，应交 33 件，签收 20 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L059：第59批，丁组，应交 34 件，签收 22 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L060：第60批，甲组，应交 20 件，签收 24 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L061：第61批，乙组，应交 21 件，签收 26 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L062：第62批，丙组，应交 22 件，签收 28 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L063：第63批，丁组，应交 23 件，签收 30 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L064：第64批，甲组，应交 24 件，签收 32 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L065：第65批，乙组，应交 25 件，签收 34 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L066：第66批，丙组，应交 26 件，签收 36 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L067：第67批，丁组，应交 27 件，签收 19 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L068：第68批，甲组，应交 28 件，签收 21 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L069：第69批，乙组，应交 29 件，签收 23 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L070：第70批，丙组，应交 30 件，签收 25 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L071：第71批，丁组，应交 31 件，签收 27 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L072：第72批，甲组，应交 32 件，签收 29 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L073：第73批，乙组，应交 33 件，签收 31 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L074：第74批，丙组，应交 34 件，签收 33 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L075：第75批，丁组，应交 20 件，签收 35 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L076：第76批，甲组，应交 21 件，签收 18 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L077：第77批，乙组，应交 22 件，签收 20 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L078：第78批，丙组，应交 23 件，签收 22 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L079：第79批，丁组，应交 24 件，签收 24 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L080：第80批，甲组，应交 25 件，签收 26 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L081：第81批，乙组，应交 26 件，签收 28 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L082：第82批，丙组，应交 27 件，签收 30 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L083：第83批，丁组，应交 28 件，签收 32 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L084：第84批，甲组，应交 29 件，签收 34 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L085：第85批，乙组，应交 30 件，签收 36 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L086：第86批，丙组，应交 31 件，签收 19 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L087：第87批，丁组，应交 32 件，签收 21 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L088：第88批，甲组，应交 33 件，签收 23 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L089：第89批，乙组，应交 34 件，签收 25 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L090：第90批，丙组，应交 20 件，签收 27 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L091：第91批，丁组，应交 21 件，签收 29 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L092：第92批，甲组，应交 22 件，签收 31 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L093：第93批，乙组，应交 23 件，签收 33 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L094：第94批，丙组，应交 24 件，签收 35 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L095：第95批，丁组，应交 25 件，签收 18 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L096：第96批，甲组，应交 26 件，签收 20 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L097：第97批，乙组，应交 27 件，签收 22 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L098：第98批，丙组，应交 28 件，签收 24 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L099：第99批，丁组，应交 29 件，签收 26 件；每批单独核验，未记录损毁或责任结论。
来源 test_shipments-L100：第100批，甲组，应交 30 件，签收 28 件；每批单独核验，未记录损毁或责任结论。
交付要求：将分组事实、来源和异常限制完整交接到最终报告，区别净差与未满足数量，不因另一批多签就宣称全部交齐。</pre>
</details>

**原始验收：** 完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。；遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。

<details><summary>查看冻结参考（长材料已独立重算）</summary>
<pre>{&quot;丁&quot;: {&quot;记录数&quot;: 25, &quot;第一列总和&quot;: 665, &quot;第二列总和&quot;: 663, &quot;第一列减第二列&quot;: 2, &quot;正缺口&quot;: 78, &quot;第二列较大记录数&quot;: 12, &quot;第一列较大记录数&quot;: 12, &quot;正超额&quot;: 76}, &quot;丙&quot;: {&quot;记录数&quot;: 25, &quot;第一列总和&quot;: 670, &quot;第二列总和&quot;: 670, &quot;第一列减第二列&quot;: 0, &quot;正缺口&quot;: 75, &quot;第二列较大记录数&quot;: 12, &quot;第一列较大记录数&quot;: 12, &quot;正超额&quot;: 75}, &quot;乙&quot;: {&quot;记录数&quot;: 25, &quot;第一列总和&quot;: 675, &quot;第二列总和&quot;: 677, &quot;第一列减第二列&quot;: -2, &quot;正缺口&quot;: 76, &quot;第二列较大记录数&quot;: 12, &quot;第一列较大记录数&quot;: 12, &quot;正超额&quot;: 78}, &quot;甲&quot;: {&quot;记录数&quot;: 25, &quot;第一列总和&quot;: 675, &quot;第二列总和&quot;: 675, &quot;第一列减第二列&quot;: 0, &quot;正缺口&quot;: 62, &quot;第二列较大记录数&quot;: 12, &quot;第一列较大记录数&quot;: 12, &quot;正超额&quot;: 62}}</pre>
</details>

### P006

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| cost | synthesis | 无 | 汇总全部原始事实，完成所需计算并列出来源；只交付本节点分析，不虚构信息。 |
| risk | verification | 无 | 核验约束、信息缺口及可能的误判；如有上游结果必须据其完成判断，保留关键来源和限制。 |
| answer | generation | cost,risk | 完整完成原始任务，逐条核对所有交付要求。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;事实汇总与约束核验可以独立进行，再完整交付。&quot;,
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;cost&quot;,
        &quot;node_type&quot;: &quot;synthesis&quot;,
        &quot;parents&quot;: [],
        &quot;prompt_template&quot;: &quot;汇总全部原始事实，完成所需计算并列出来源；只交付本节点分析，不虚构信息。&quot;,
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;汇总全部原始事实，完成所需计算并列出来源；只交付本节点分析，不虚构信息。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;result&quot;: &quot;分析结果&quot;,
              &quot;evidence&quot;: &quot;原始材料来源标识与证据；没有证据时明确说明&quot;,
              &quot;assumptions&quot;: &quot;假设、不确定性与信息缺口；没有时明确说明&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;high&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;保留证据与假设，不虚构数据&quot;,
            &quot;覆盖本节点职责并明确限制&quot;
          ],
          &quot;covers&quot;: [
            0
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;risk&quot;,
        &quot;node_type&quot;: &quot;verification&quot;,
        &quot;parents&quot;: [],
        &quot;prompt_template&quot;: &quot;核验约束、信息缺口及可能的误判；如有上游结果必须据其完成判断，保留关键来源和限制。&quot;,
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;核验约束、信息缺口及可能的误判；如有上游结果必须据其完成判断，保留关键来源和限制。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;result&quot;: &quot;分析结果&quot;,
              &quot;evidence&quot;: &quot;原始材料来源标识与证据；没有证据时明确说明&quot;,
              &quot;assumptions&quot;: &quot;假设、不确定性与信息缺口；没有时明确说明&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;high&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;保留证据与假设，不虚构数据&quot;,
            &quot;覆盖本节点职责并明确限制&quot;
          ],
          &quot;covers&quot;: [
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;parents&quot;: [
          &quot;cost&quot;,
          &quot;risk&quot;
        ],
        &quot;prompt_template&quot;: &quot;完整完成原始任务，逐条核对所有交付要求。&quot;,
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;完整完成原始任务，逐条核对所有交付要求。&quot;,
          &quot;inputs&quot;: {
            &quot;cost&quot;: {
              &quot;fields&quot;: [
                &quot;result&quot;,
                &quot;evidence&quot;,
                &quot;assumptions&quot;
              ],
              &quot;reason&quot;: &quot;消费 cost 的分析、证据与假设，检查一致性后形成判断&quot;
            },
            &quot;risk&quot;: {
              &quot;fields&quot;: [
                &quot;result&quot;,
                &quot;evidence&quot;,
                &quot;assumptions&quot;
              ],
              &quot;reason&quot;: &quot;消费 risk 的分析、证据与假设，检查一致性后形成判断&quot;
            }
          },
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终建议与可追溯依据&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;high&quot;,
            &quot;input_budget_tokens&quot;: 65536,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;保留证据与假设，不虚构数据&quot;,
            &quot;覆盖本节点职责并明确限制&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ]
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: null,
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P029

没有结构合法的计划；仍需记录缺失 / 失败及其理由。

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: null,
  &quot;raw_plan_if_unparsed&quot;: &quot;{\n  \&quot;schema_version\&quot;: \&quot;text-task-plan-v2\&quot;,\n  \&quot;decomposition_reason\&quot;: \&quot;任务要求对100批物资逐批计算差额、按组汇总并区分净差与正缺口，同时保留来源编号和异常限制。计算量大且需要交叉核对，拆分为分组计算与最终汇总两个节点：分组计算节点并行处理四个组，最终汇总节点核对冲突、遗漏并生成完整报告。拆分净收益在于分组计算可并行且降低单节点计算负担，汇总节点负责一致性核对和最终交付。\&quot;,\n  \&quot;nodes\&quot;: [\n    {\n      \&quot;node_id\&quot;: \&quot;group_calc\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是物资到货交接核对员。请根据以下虚构封闭场景材料，对甲、乙、丙、丁四个组分别进行逐批核对。\\n\\n材料规则：\\n- 每条记录给出应交数量、签收数量和一份来源编号；差额为应交减签收。\\n- 多签不等于可以抵消另一批次少签，正缺口须逐批计算后汇总。\\n- 核对报告必须保留每组的来源范围，列出总应交、总签收、净差及正缺口；没有损毁或责任证据。\\n\\n请对每个组：\\n1. 列出该组所有批次的来源编号、应交数量、签收数量、差额（应交减签收）。\\n2. 计算该组总应交、总签收、净差（总应交减总签收）。\\n3. 计算该组正缺口：仅将差额为正（应交大于签收）的批次差额逐批相加；差额为负或零的批次不计入正缺口。\\n4. 保留该组的来源范围（即该组涉及的批次编号范围）。\\n\\n材料如下：\\n来源 test_shipments-L001：第1批，乙组，应交 21 件，签收 20 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L002：第2批，丙组，应交 22 件，签收 22 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L003：第3批，丁组，应交 23 件，签收 24 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L004：第4批，甲组，应交 24 件，签收 26 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L005：第5批，乙组，应交 25 件，签收 28 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L006：第6批，丙组，应交 26 件，签收 30 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L007：第7批，丁组，应交 27 件，签收 32 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L008：第8批，甲组，应交 28 件，签收 34 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L009：第9批，乙组，应交 29 件，签收 36 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L010：第10批，丙组，应交 30 件，签收 19 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L011：第11批，丁组，应交 31 件，签收 21 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L012：第12批，甲组，应交 32 件，签收 23 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L013：第13批，乙组，应交 33 件，签收 25 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L014：第14批，丙组，应交 34 件，签收 27 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L015：第15批，丁组，应交 20 件，签收 29 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L016：第16批，甲组，应交 21 件，签收 31 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L017：第17批，乙组，应交 22 件，签收 33 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L018：第18批，丙组，应交 23 件，签收 35 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L019：第19批，丁组，应交 24 件，签收 18 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L020：第20批，甲组，应交 25 件，签收 20 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L021：第21批，乙组，应交 26 件，签收 22 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L022：第22批，丙组，应交 27 件，签收 24 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L023：第23批，丁组，应交 28 件，签收 26 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L024：第24批，甲组，应交 29 件，签收 28 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L025：第25批，乙组，应交 30 件，签收 30 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L026：第26批，丙组，应交 31 件，签收 32 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L027：第27批，丁组，应交 32 件，签收 34 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L028：第28批，甲组，应交 33 件，签收 36 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L029：第29批，乙组，应交 34 件，签收 19 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L030：第30批，丙组，应交 20 件，签收 21 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L031：第31批，丁组，应交 21 件，签收 23 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L032：第32批，甲组，应交 22 件，签收 25 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L033：第33批，乙组，应交 23 件，签收 27 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L034：第34批，丙组，应交 24 件，签收 29 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L035：第35批，丁组，应交 25 件，签收 31 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L036：第36批，甲组，应交 26 件，签收 33 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L037：第37批，乙组，应交 27 件，签收 35 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L038：第38批，丙组，应交 28 件，签收 18 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L039：第39批，丁组，应交 29 件，签收 20 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L040：第40批，甲组，应交 30 件，签收 22 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L041：第41批，乙组，应交 31 件，签收 24 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L042：第42批，丙组，应交 32 件，签收 26 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L043：第43批，丁组，应交 33 件，签收 28 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L044：第44批，甲组，应交 34 件，签收 30 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L045：第45批，乙组，应交 20 件，签收 32 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L046：第46批，丙组，应交 21 件，签收 34 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L047：第47批，丁组，应交 22 件，签收 36 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L048：第48批，甲组，应交 23 件，签收 19 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L049：第49批，乙组，应交 24 件，签收 21 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L050：第50批，丙组，应交 25 件，签收 23 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L051：第51批，丁组，应交 26 件，签收 25 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L052：第52批，甲组，应交 27 件，签收 27 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L053：第53批，乙组，应交 28 件，签收 29 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L054：第54批，丙组，应交 29 件，签收 31 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L055：第55批，丁组，应交 30 件，签收 33 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L056：第56批，甲组，应交 31 件，签收 35 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L057：第57批，乙组，应交 32 件，签收 18 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L058：第58批，丙组，应交 33 件，签收 20 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L059：第59批，丁组，应交 34 件，签收 22 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L060：第60批，甲组，应交 20 件，签收 24 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L061：第61批，乙组，应交 21 件，签收 26 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L062：第62批，丙组，应交 22 件，签收 28 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L063：第63批，丁组，应交 23 件，签收 30 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L064：第64批，甲组，应交 24 件，签收 32 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L065：第65批，乙组，应交 25 件，签收 34 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L066：第66批，丙组，应交 26 件，签收 36 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L067：第67批，丁组，应交 27 件，签收 19 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L068：第68批，甲组，应交 28 件，签收 21 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L069：第69批，乙组，应交 29 件，签收 23 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L070：第70批，丙组，应交 30 件，签收 25 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L071：第71批，丁组，应交 31 件，签收 27 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L072：第72批，甲组，应交 32 件，签收 29 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L073：第73批，乙组，应交 33 件，签收 31 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L074：第74批，丙组，应交 34 件，签收 33 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L075：第75批，丁组，应交 20 件，签收 35 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L076：第76批，甲组，应交 21 件，签收 18 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L077：第77批，乙组，应交 22 件，签收 20 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L078：第78批，丙组，应交 23 件，签收 22 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L079：第79批，丁组，应交 24 件，签收 24 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L080：第80批，甲组，应交 25 件，签收 26 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L081：第81批，乙组，应交 26 件，签收 28 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L082：第82批，丙组，应交 27 件，签收 30 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L083：第83批，丁组，应交 28 件，签收 32 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L084：第84批，甲组，应交 29 件，签收 34 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L085：第85批，乙组，应交 30 件，签收 36 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L086：第86批，丙组，应交 31 件，签收 19 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L087：第87批，丁组，应交 32 件，签收 21 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L088：第88批，甲组，应交 33 件，签收 23 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L089：第89批，乙组，应交 34 件，签收 25 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L090：第90批，丙组，应交 20 件，签收 27 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L091：第91批，丁组，应交 21 件，签收 29 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L092：第92批，甲组，应交 22 件，签收 31 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L093：第93批，乙组，应交 23 件，签收 33 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L094：第94批，丙组，应交 24 件，签收 35 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L095：第95批，丁组，应交 25 件，签收 18 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L096：第96批，甲组，应交 26 件，签收 20 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L097：第97批，乙组，应交 27 件，签收 22 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L098：第98批，丙组，应交 28 件，签收 24 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L099：第99批，丁组，应交 29 件，签收 26 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L100：第100批，甲组，应交 30 件，签收 28 件；每批单独核验，未记录损毁或责任结论。\\n\\n请以 JSON 格式输出，包含以下字段：\\n- \\\&quot;group_results\\\&quot;：字符串，内容为四个组的核对结果。每个组包含：组名、来源范围、逐批明细（来源编号、应交、签收、差额）、总应交、总签收、净差、正缺口。\\n- \\\&quot;assumptions\\\&quot;：字符串，列出计算中采用的假设（如差额定义、正缺口定义、不跨批抵消等）。\\n- \\\&quot;uncertainties\\\&quot;：字符串，列出材料未说明或无法确定的事项（如损毁原因、责任归属等）。\&quot;,\n      \&quot;parents\&quot;: [],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;对甲、乙、丙、丁四个组分别进行逐批核对，计算每组总应交、总签收、净差和正缺口，并保留来源范围。\&quot;,\n        \&quot;inputs\&quot;: {},\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;json\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;group_results\&quot;: \&quot;四个组的核对结果，包含组名、来源范围、逐批明细、总应交、总签收、净差、正缺口\&quot;,\n            \&quot;assumptions\&quot;: \&quot;计算中采用的假设\&quot;,\n            \&quot;uncertainties\&quot;: \&quot;材料未说明或无法确定的事项\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;medium\&quot;,\n          \&quot;input_budget_tokens\&quot;: 65536,\n          \&quot;expected_output_tokens\&quot;: 4096\n        },\n        \&quot;checks\&quot;: [\n          \&quot;四个组均被覆盖，每组包含来源范围、逐批明细、总应交、总签收、净差、正缺口\&quot;,\n          \&quot;差额按应交减签收计算，正缺口仅累加差额为正的批次\&quot;,\n          \&quot;所有来源编号与材料一致，无虚构数据\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    },\n    {\n      \&quot;node_id\&quot;: \&quot;answer\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是物资到货交接报告撰写员。请根据分组核对结果，撰写完整的「物资到货交接报告」。\\n\\n报告必须满足以下要求：\\n1. 完整保留每个组的来源范围，列出总应交、总签收、净差及正缺口。\\n2. 区分净差与未满足数量（正缺口），不因另一批多签就宣称全部交齐。\\n3. 保留所有来源编号，事实和计算与材料一致。\\n4. 遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。\\n5. 材料未说明损毁或责任结论，报告中不得声称存在损毁或责任归属。\\n\\n分组核对结果如下：\\n&lt;group_results&gt;\\n{group_results}\\n&lt;/group_results&gt;\\n\\n计算假设：\\n&lt;assumptions&gt;\\n{assumptions}\\n&lt;/assumptions&gt;\\n\\n不确定事项：\\n&lt;uncertainties&gt;\\n{uncertainties}\\n&lt;/uncertainties&gt;\\n\\n请直接输出报告正文，不要封装为 JSON。报告应包含：\\n- 报告标题\\n- 核对说明（差额定义、正缺口定义、不跨批抵消原则）\\n- 分组核对结果（甲、乙、丙、丁四组，每组包含来源范围、逐批明细、总应交、总签收、净差、正缺口）\\n- 总体汇总（总应交、总签收、总净差、总正缺口）\\n- 异常与限制说明（区分已知事实与未知事项，不虚构损毁或责任结论）\&quot;,\n      \&quot;parents\&quot;: [\&quot;group_calc\&quot;],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;基于分组核对结果撰写完整的物资到货交接报告，保留来源范围、区分净差与正缺口、遵守材料约束。\&quot;,\n        \&quot;inputs\&quot;: {\n          \&quot;group_calc\&quot;: {\n            \&quot;fields\&quot;: [\&quot;group_results\&quot;, \&quot;assumptions\&quot;, \&quot;uncertainties\&quot;],\n            \&quot;reason\&quot;: \&quot;需要消费分组核对结果、计算假设和不确定事项，以生成完整报告并保持事实一致。\&quot;\n          }\n        },\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;text\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;text\&quot;: \&quot;完整的物资到货交接报告正文\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;medium\&quot;,\n          \&quot;input_budget_tokens\&quot;: 131072,\n          \&quot;expected_output_tokens\&quot;: 8192\n        },\n        \&quot;checks\&quot;: [\n          \&quot;报告包含四个组的来源范围、总应交、总签收、净差及正缺口\&quot;,\n          \&quot;报告区分净差与正缺口，不因多签抵消少签\&quot;,\n          \&quot;所有来源编号与材料一致，无虚构损毁或责任结论\&quot;,\n          \&quot;报告区分已知事实、建议和未知事项\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    }\n  ],\n  \&quot;final_node_id\&quot;: \&quot;answer\&quot;,\n  \&quot;acceptance_criteria\&quot;: [\n    \&quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。\&quot;,\n    \&quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。\&quot;\n  ]\n}&quot;,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 5952
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P033

没有结构合法的计划；仍需记录缺失 / 失败及其理由。

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: null,
  &quot;raw_plan_if_unparsed&quot;: &quot;{\n  \&quot;schema_version\&quot;: \&quot;text-task-plan-v2\&quot;,\n  \&quot;decomposition_reason\&quot;: \&quot;任务要求对100批物资逐批计算差额、按组汇总并区分净差与正缺口，同时保留来源编号和异常限制。计算量大且需要交叉核对，拆分为两个并行计算节点（按批次范围分段）和一个汇总节点，可在控制上下文开销的同时提高准确性；汇总节点负责核对两组结果、合并分组统计并生成最终报告。\&quot;,\n  \&quot;nodes\&quot;: [\n    {\n      \&quot;node_id\&quot;: \&quot;calc_1\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是物资到货交接核对助手。请仅依据以下材料，对第1批至第50批（来源 test_shipments-L001 至 test_shipments-L050）逐批计算：应交数量、签收数量、差额（应交减签收）、该批是否为正缺口（应交大于签收）。然后按组（甲组、乙组、丙组、丁组）汇总：每组涉及的批次来源编号范围、总应交、总签收、净差（总应交减总签收）、正缺口合计（仅将应交大于签收的批次差额相加，多签批次不得抵消少签批次）。材料未说明损毁或责任结论，不得虚构。输出 JSON，字段：batch_range（本段批次范围）、group_summary（按组汇总的字符串，包含每组来源范围、总应交、总签收、净差、正缺口）、positive_gap_total（本段正缺口合计）、notes（本段核对说明，注明未记录损毁或责任结论）。\&quot;,\n      \&quot;parents\&quot;: [],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;对第1至50批逐批计算差额并按组汇总净差与正缺口\&quot;,\n        \&quot;inputs\&quot;: {},\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;json\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;batch_range\&quot;: \&quot;本段批次范围说明\&quot;,\n            \&quot;group_summary\&quot;: \&quot;按组汇总的字符串，包含每组来源范围、总应交、总签收、净差、正缺口\&quot;,\n            \&quot;positive_gap_total\&quot;: \&quot;本段正缺口合计\&quot;,\n            \&quot;notes\&quot;: \&quot;本段核对说明，注明未记录损毁或责任结论\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;medium\&quot;,\n          \&quot;input_budget_tokens\&quot;: 65536,\n          \&quot;expected_output_tokens\&quot;: 3000\n        },\n        \&quot;checks\&quot;: [\n          \&quot;逐批计算应交、签收、差额及正缺口判断\&quot;,\n          \&quot;按组汇总总应交、总签收、净差和正缺口\&quot;,\n          \&quot;多签批次未抵消少签批次\&quot;,\n          \&quot;未虚构损毁或责任结论\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    },\n    {\n      \&quot;node_id\&quot;: \&quot;calc_2\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是物资到货交接核对助手。请仅依据以下材料，对第51批至第100批（来源 test_shipments-L051 至 test_shipments-L100）逐批计算：应交数量、签收数量、差额（应交减签收）、该批是否为正缺口（应交大于签收）。然后按组（甲组、乙组、丙组、丁组）汇总：每组涉及的批次来源编号范围、总应交、总签收、净差（总应交减总签收）、正缺口合计（仅将应交大于签收的批次差额相加，多签批次不得抵消少签批次）。材料未说明损毁或责任结论，不得虚构。输出 JSON，字段：batch_range（本段批次范围）、group_summary（按组汇总的字符串，包含每组来源范围、总应交、总签收、净差、正缺口）、positive_gap_total（本段正缺口合计）、notes（本段核对说明，注明未记录损毁或责任结论）。\&quot;,\n      \&quot;parents\&quot;: [],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;对第51至100批逐批计算差额并按组汇总净差与正缺口\&quot;,\n        \&quot;inputs\&quot;: {},\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;json\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;batch_range\&quot;: \&quot;本段批次范围说明\&quot;,\n            \&quot;group_summary\&quot;: \&quot;按组汇总的字符串，包含每组来源范围、总应交、总签收、净差、正缺口\&quot;,\n            \&quot;positive_gap_total\&quot;: \&quot;本段正缺口合计\&quot;,\n            \&quot;notes\&quot;: \&quot;本段核对说明，注明未记录损毁或责任结论\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;medium\&quot;,\n          \&quot;input_budget_tokens\&quot;: 65536,\n          \&quot;expected_output_tokens\&quot;: 3000\n        },\n        \&quot;checks\&quot;: [\n          \&quot;逐批计算应交、签收、差额及正缺口判断\&quot;,\n          \&quot;按组汇总总应交、总签收、净差和正缺口\&quot;,\n          \&quot;多签批次未抵消少签批次\&quot;,\n          \&quot;未虚构损毁或责任结论\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    },\n    {\n      \&quot;node_id\&quot;: \&quot;answer\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是物资到货交接报告撰写人。请仅依据原始材料和以下两段计算结果，生成最终「物资到货交接报告」。要求：1）完整保留每组的来源范围，列出每组总应交、总签收、净差及正缺口；2）明确区分净差与未满足数量（正缺口），不得因另一批多签就宣称全部交齐；3）保留来源编号；4）材料未记录损毁或责任结论，不得虚构原因、数据或已执行的操作；5）区分已知事实、建议和未知事项。报告正文直接输出，不封装为 JSON。\&quot;,\n      \&quot;parents\&quot;: [\&quot;calc_1\&quot;, \&quot;calc_2\&quot;],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;合并两段计算结果，生成完整物资到货交接报告，保留分组事实、来源和异常限制\&quot;,\n        \&quot;inputs\&quot;: {\n          \&quot;calc_1\&quot;: {\n            \&quot;fields\&quot;: [\&quot;batch_range\&quot;, \&quot;group_summary\&quot;, \&quot;positive_gap_total\&quot;, \&quot;notes\&quot;],\n            \&quot;reason\&quot;: \&quot;需要第1至50批的分组汇总和正缺口数据以合并全量统计\&quot;\n          },\n          \&quot;calc_2\&quot;: {\n            \&quot;fields\&quot;: [\&quot;batch_range\&quot;, \&quot;group_summary\&quot;, \&quot;positive_gap_total\&quot;, \&quot;notes\&quot;],\n            \&quot;reason\&quot;: \&quot;需要第51至100批的分组汇总和正缺口数据以合并全量统计\&quot;\n          }\n        },\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;text\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;text\&quot;: \&quot;最终物资到货交接报告正文，包含每组来源范围、总应交、总签收、净差、正缺口，并区分已知事实、建议和未知事项\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;medium\&quot;,\n          \&quot;input_budget_tokens\&quot;: 131072,\n          \&quot;expected_output_tokens\&quot;: 5000\n        },\n        \&quot;checks\&quot;: [\n          \&quot;报告包含每组来源范围、总应交、总签收、净差及正缺口\&quot;,\n          \&quot;明确区分净差与正缺口，多签批次未抵消少签批次\&quot;,\n          \&quot;保留来源编号\&quot;,\n          \&quot;未虚构损毁或责任结论\&quot;,\n          \&quot;区分已知事实、建议和未知事项\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    }\n  ],\n  \&quot;final_node_id\&quot;: \&quot;answer\&quot;,\n  \&quot;acceptance_criteria\&quot;: [\n    \&quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。\&quot;,\n    \&quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。\&quot;\n  ]\n}&quot;,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 1745
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P034

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| calc_1_50 | generation | 无 | 对第1至第50批物资记录逐批计算差额和正缺口，并按组汇总总应交、总签收、净差和正缺口。 |
| calc_51_100 | generation | 无 | 对第51至第100批物资记录逐批计算差额和正缺口，并按组汇总总应交、总签收、净差和正缺口。 |
| answer | generation | calc_1_50,calc_51_100 | 汇总第1至第100批物资到货交接核对结果，生成最终报告，保留分组来源范围、总应交、总签收、净差和正缺口，并区分净差与未满足数量。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;calc_1_50&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;你是虚构封闭场景「物资到货交接报告」的核对助手。只使用任务中提供的材料，不联网、不执行工具、不虚构信息。\n\n请处理来源 test_shipments-L001 至 test_shipments-L050 的50批记录。对每一批：\n1. 记录来源编号、批次号、组别、应交数量、签收数量。\n2. 计算差额 = 应交数量 - 签收数量。\n3. 若差额大于0，则该批存在正缺口，正缺口数量等于差额；若差额小于或等于0，则该批正缺口为0。\n4. 不将多签批次与少签批次相互抵消。\n\n然后按组（甲组、乙组、丙组、丁组）汇总：\n- 来源范围（列出该组包含的来源编号范围）\n- 总应交\n- 总签收\n- 净差 = 总应交 - 总签收\n- 正缺口 = 该组内所有批次正缺口之和\n\n输出 JSON，字段：\n- \&quot;records\&quot;: 字符串，逐批列出「来源编号|批次|组别|应交|签收|差额|正缺口」，每批一行。\n- \&quot;group_summary\&quot;: 字符串，按组列出「组别|来源范围|总应交|总签收|净差|正缺口」。\n- \&quot;assumptions\&quot;: 字符串，说明计算假设，例如多签不抵消少签、未记录损毁或责任结论。\n- \&quot;uncertainties\&quot;: 字符串，说明材料未提供的信息，例如损毁或责任原因未知。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;对第1至第50批物资记录逐批计算差额和正缺口，并按组汇总总应交、总签收、净差和正缺口。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;records&quot;: &quot;第1至第50批逐批记录，包含来源编号、批次、组别、应交、签收、差额、正缺口&quot;,
              &quot;group_summary&quot;: &quot;第1至第50批按组汇总的来源范围、总应交、总签收、净差、正缺口&quot;,
              &quot;assumptions&quot;: &quot;计算假设，如多签不抵消少签、未记录损毁或责任结论&quot;,
              &quot;uncertainties&quot;: &quot;材料未提供的信息，如损毁或责任原因未知&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;medium&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 4096
          },
          &quot;checks&quot;: [
            &quot;逐批列出第1至第50批的来源编号、组别、应交、签收、差额和正缺口&quot;,
            &quot;差额计算为应交减签收，正缺口仅对差额大于0的批次累计&quot;,
            &quot;按组汇总总应交、总签收、净差和正缺口，且不跨批抵消&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;calc_51_100&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;你是虚构封闭场景「物资到货交接报告」的核对助手。只使用任务中提供的材料，不联网、不执行工具、不虚构信息。\n\n请处理来源 test_shipments-L051 至 test_shipments-L100 的50批记录。对每一批：\n1. 记录来源编号、批次号、组别、应交数量、签收数量。\n2. 计算差额 = 应交数量 - 签收数量。\n3. 若差额大于0，则该批存在正缺口，正缺口数量等于差额；若差额小于或等于0，则该批正缺口为0。\n4. 不将多签批次与少签批次相互抵消。\n\n然后按组（甲组、乙组、丙组、丁组）汇总：\n- 来源范围（列出该组包含的来源编号范围）\n- 总应交\n- 总签收\n- 净差 = 总应交 - 总签收\n- 正缺口 = 该组内所有批次正缺口之和\n\n输出 JSON，字段：\n- \&quot;records\&quot;: 字符串，逐批列出「来源编号|批次|组别|应交|签收|差额|正缺口」，每批一行。\n- \&quot;group_summary\&quot;: 字符串，按组列出「组别|来源范围|总应交|总签收|净差|正缺口」。\n- \&quot;assumptions\&quot;: 字符串，说明计算假设，例如多签不抵消少签、未记录损毁或责任结论。\n- \&quot;uncertainties\&quot;: 字符串，说明材料未提供的信息，例如损毁或责任原因未知。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;对第51至第100批物资记录逐批计算差额和正缺口，并按组汇总总应交、总签收、净差和正缺口。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;records&quot;: &quot;第51至第100批逐批记录，包含来源编号、批次、组别、应交、签收、差额、正缺口&quot;,
              &quot;group_summary&quot;: &quot;第51至第100批按组汇总的来源范围、总应交、总签收、净差、正缺口&quot;,
              &quot;assumptions&quot;: &quot;计算假设，如多签不抵消少签、未记录损毁或责任结论&quot;,
              &quot;uncertainties&quot;: &quot;材料未提供的信息，如损毁或责任原因未知&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;medium&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 4096
          },
          &quot;checks&quot;: [
            &quot;逐批列出第51至第100批的来源编号、组别、应交、签收、差额和正缺口&quot;,
            &quot;差额计算为应交减签收，正缺口仅对差额大于0的批次累计&quot;,
            &quot;按组汇总总应交、总签收、净差和正缺口，且不跨批抵消&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;你是虚构封闭场景「物资到货交接报告」的最终报告撰写人。只使用任务材料和上游计算结果，不联网、不执行工具、不虚构信息。\n\n请根据以下上游结果撰写最终报告：\n- 第1至第50批计算结果：{{calc_1_50.records}}；分组汇总：{{calc_1_50.group_summary}}；假设：{{calc_1_50.assumptions}}；不确定事项：{{calc_1_50.uncertainties}}\n- 第51至第100批计算结果：{{calc_51_100.records}}；分组汇总：{{calc_51_100.group_summary}}；假设：{{calc_51_100.assumptions}}；不确定事项：{{calc_51_100.uncertainties}}\n\n报告必须：\n1. 保留每组的来源范围，列出总应交、总签收、净差及正缺口。\n2. 明确区分净差与未满足数量（正缺口），不得因另一批多签就宣称全部交齐。\n3. 将分组事实、来源和异常限制完整交接到最终报告。\n4. 不虚构损毁或责任证据；材料未记录损毁或责任结论时，明确说明未知。\n5. 最终报告直接输出正文，不封装为 JSON。\n\n报告结构建议：\n- 标题：物资到货交接报告\n- 说明：本报告基于虚构封闭场景材料，仅反映材料中的记录。\n- 分组核对结果：按甲组、乙组、丙组、丁组分别列出来源范围、总应交、总签收、净差、正缺口。\n- 逐批明细：列出100批的来源编号、批次、组别、应交、签收、差额、正缺口。\n- 异常与限制：说明多签不抵消少签、未记录损毁或责任结论、正缺口不等于净差等限制。\n- 结论：汇总总体情况，但不宣称全部交齐，除非材料支持。&quot;,
        &quot;parents&quot;: [
          &quot;calc_1_50&quot;,
          &quot;calc_51_100&quot;
        ],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;汇总第1至第100批物资到货交接核对结果，生成最终报告，保留分组来源范围、总应交、总签收、净差和正缺口，并区分净差与未满足数量。&quot;,
          &quot;inputs&quot;: {
            &quot;calc_1_50&quot;: {
              &quot;fields&quot;: [
                &quot;records&quot;,
                &quot;group_summary&quot;,
                &quot;assumptions&quot;,
                &quot;uncertainties&quot;
              ],
              &quot;reason&quot;: &quot;需要第1至第50批的逐批记录和分组汇总以合并到最终报告。&quot;
            },
            &quot;calc_51_100&quot;: {
              &quot;fields&quot;: [
                &quot;records&quot;,
                &quot;group_summary&quot;,
                &quot;assumptions&quot;,
                &quot;uncertainties&quot;
              ],
              &quot;reason&quot;: &quot;需要第51至第100批的逐批记录和分组汇总以合并到最终报告。&quot;
            }
          },
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终物资到货交接报告正文，包含分组核对结果、逐批明细、异常限制和结论&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;medium&quot;,
            &quot;input_budget_tokens&quot;: 65536,
            &quot;expected_output_tokens&quot;: 8192
          },
          &quot;checks&quot;: [
            &quot;报告包含甲组、乙组、丙组、丁组各自的来源范围、总应交、总签收、净差和正缺口&quot;,
            &quot;报告区分净差与正缺口，不因多签批次抵消少签批次而宣称全部交齐&quot;,
            &quot;报告保留100批的来源编号、批次、组别、应交、签收、差额和正缺口&quot;,
            &quot;报告不虚构损毁或责任原因，明确材料未记录相关结论&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务要求对100批物资逐批计算差额、按组汇总并区分净差与正缺口，同时保留来源编号和异常限制。计算量大且需要核对，拆分为两个并行提取/计算节点（按批次范围分段）和一个汇总生成节点，可在控制上下文开销的同时提高准确性；汇总节点负责核对两组结果、合并分组统计并生成最终报告。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 2556
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P035

没有结构合法的计划；仍需记录缺失 / 失败及其理由。

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: null,
  &quot;raw_plan_if_unparsed&quot;: &quot;{\n  \&quot;schema_version\&quot;: \&quot;text-task-plan-v2\&quot;,\n  \&quot;decomposition_reason\&quot;: \&quot;任务要求对100批物资逐批计算差额、按组汇总并区分净差与正缺口，同时保留来源编号和异常限制。计算量大且需要交叉核对，拆分为并行计算节点和最终汇总节点可提高准确性与可检查性；但汇总节点必须消费全部计算产物，存在较高上下文交接开销，因此仅拆为两个计算分支和一个最终汇总节点。\&quot;,\n  \&quot;nodes\&quot;: [\n    {\n      \&quot;node_id\&quot;: \&quot;calc_group_1\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是物资到货交接核对助手。仅使用以下材料，不联网、不执行工具、不虚构信息。\\n\\n材料规则：\\nH1：每条记录给出应交数量、签收数量和一份来源编号；差额为应交减签收。\\nH2：多签不等于可以抵消另一批次少签，正缺口须逐批计算后汇总。\\nH3：核对报告必须保留每组的来源范围，列出总应交、总签收、净差及正缺口；没有损毁或责任证据。\\n\\n请处理以下第1批至第50批记录：\\n来源 test_shipments-L001：第1批，乙组，应交 21 件，签收 20 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L002：第2批，丙组，应交 22 件，签收 22 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L003：第3批，丁组，应交 23 件，签收 24 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L004：第4批，甲组，应交 24 件，签收 26 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L005：第5批，乙组，应交 25 件，签收 28 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L006：第6批，丙组，应交 26 件，签收 30 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L007：第7批，丁组，应交 27 件，签收 32 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L008：第8批，甲组，应交 28 件，签收 34 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L009：第9批，乙组，应交 29 件，签收 36 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L010：第10批，丙组，应交 30 件，签收 19 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L011：第11批，丁组，应交 31 件，签收 21 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L012：第12批，甲组，应交 32 件，签收 23 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L013：第13批，乙组，应交 33 件，签收 25 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L014：第14批，丙组，应交 34 件，签收 27 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L015：第15批，丁组，应交 20 件，签收 29 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L016：第16批，甲组，应交 21 件，签收 31 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L017：第17批，乙组，应交 22 件，签收 33 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L018：第18批，丙组，应交 23 件，签收 35 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L019：第19批，丁组，应交 24 件，签收 18 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L020：第20批，甲组，应交 25 件，签收 20 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L021：第21批，乙组，应交 26 件，签收 22 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L022：第22批，丙组，应交 27 件，签收 24 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L023：第23批，丁组，应交 28 件，签收 26 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L024：第24批，甲组，应交 29 件，签收 28 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L025：第25批，乙组，应交 30 件，签收 30 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L026：第26批，丙组，应交 31 件，签收 32 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L027：第27批，丁组，应交 32 件，签收 34 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L028：第28批，甲组，应交 33 件，签收 36 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L029：第29批，乙组，应交 34 件，签收 19 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L030：第30批，丙组，应交 20 件，签收 21 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L031：第31批，丁组，应交 21 件，签收 23 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L032：第32批，甲组，应交 22 件，签收 25 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L033：第33批，乙组，应交 23 件，签收 27 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L034：第34批，丙组，应交 24 件，签收 29 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L035：第35批，丁组，应交 25 件，签收 31 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L036：第36批，甲组，应交 26 件，签收 33 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L037：第37批，乙组，应交 27 件，签收 35 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L038：第38批，丙组，应交 28 件，签收 18 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L039：第39批，丁组，应交 29 件，签收 20 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L040：第40批，甲组，应交 30 件，签收 22 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L041：第41批，乙组，应交 31 件，签收 24 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L042：第42批，丙组，应交 32 件，签收 26 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L043：第43批，丁组，应交 33 件，签收 28 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L044：第44批，甲组，应交 34 件，签收 30 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L045：第45批，乙组，应交 20 件，签收 32 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L046：第46批，丙组，应交 21 件，签收 34 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L047：第47批，丁组，应交 22 件，签收 36 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L048：第48批，甲组，应交 23 件，签收 19 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L049：第49批，乙组，应交 24 件，签收 21 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L050：第50批，丙组，应交 25 件，签收 23 件；每批单独核验，未记录损毁或责任结论。\\n\\n请按以下要求输出 JSON：\\n- 对每条记录计算差额=应交-签收；\\n- 按甲、乙、丙、丁四组分别汇总：总应交、总签收、净差、正缺口；\\n- 正缺口只累计差额大于0的批次，不得用多签批次抵消；\\n- 保留每组的来源编号范围；\\n- 不推断损毁或责任原因。\\n\\n输出字段：\\n- group_summary：字符串，按组列出总应交、总签收、净差、正缺口及来源编号范围；\\n- batch_details：字符串，逐批列出批次、组别、来源编号、应交、签收、差额；\\n- assumptions：字符串，列出计算假设；\\n- uncertainties：字符串，列出材料未说明或无法判断的事项。\&quot;,\n      \&quot;parents\&quot;: [],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;对第1批至第50批物资记录逐批计算差额，并按组汇总总应交、总签收、净差和正缺口，保留来源编号范围。\&quot;,\n        \&quot;inputs\&quot;: {},\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;json\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;group_summary\&quot;: \&quot;按甲、乙、丙、丁组列出总应交、总签收、净差、正缺口及来源编号范围的文本\&quot;,\n            \&quot;batch_details\&quot;: \&quot;逐批列出批次、组别、来源编号、应交、签收、差额的文本\&quot;,\n            \&quot;assumptions\&quot;: \&quot;计算假设说明\&quot;,\n            \&quot;uncertainties\&quot;: \&quot;材料未说明或无法判断的事项\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;medium\&quot;,\n          \&quot;input_budget_tokens\&quot;: 65536,\n          \&quot;expected_output_tokens\&quot;: 4096\n        },\n        \&quot;checks\&quot;: [\n          \&quot;覆盖第1批至第50批全部记录\&quot;,\n          \&quot;差额按应交减签收计算\&quot;,\n          \&quot;正缺口只累计差额大于0的批次\&quot;,\n          \&quot;保留每组来源编号范围\&quot;,\n          \&quot;不虚构损毁或责任原因\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    },\n    {\n      \&quot;node_id\&quot;: \&quot;calc_group_2\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是物资到货交接核对助手。仅使用以下材料，不联网、不执行工具、不虚构信息。\\n\\n材料规则：\\nH1：每条记录给出应交数量、签收数量和一份来源编号；差额为应交减签收。\\nH2：多签不等于可以抵消另一批次少签，正缺口须逐批计算后汇总。\\nH3：核对报告必须保留每组的来源范围，列出总应交、总签收、净差及正缺口；没有损毁或责任证据。\\n\\n请处理以下第51批至第100批记录：\\n来源 test_shipments-L051：第51批，丁组，应交 26 件，签收 25 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L052：第52批，甲组，应交 27 件，签收 27 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L053：第53批，乙组，应交 28 件，签收 29 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L054：第54批，丙组，应交 29 件，签收 31 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L055：第55批，丁组，应交 30 件，签收 33 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L056：第56批，甲组，应交 31 件，签收 35 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L057：第57批，乙组，应交 32 件，签收 18 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L058：第58批，丙组，应交 33 件，签收 20 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L059：第59批，丁组，应交 34 件，签收 22 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L060：第60批，甲组，应交 20 件，签收 24 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L061：第61批，乙组，应交 21 件，签收 26 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L062：第62批，丙组，应交 22 件，签收 28 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L063：第63批，丁组，应交 23 件，签收 30 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L064：第64批，甲组，应交 24 件，签收 32 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L065：第65批，乙组，应交 25 件，签收 34 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L066：第66批，丙组，应交 26 件，签收 36 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L067：第67批，丁组，应交 27 件，签收 19 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L068：第68批，甲组，应交 28 件，签收 21 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L069：第69批，乙组，应交 29 件，签收 23 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L070：第70批，丙组，应交 30 件，签收 25 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L071：第71批，丁组，应交 31 件，签收 27 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L072：第72批，甲组，应交 32 件，签收 29 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L073：第73批，乙组，应交 33 件，签收 31 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L074：第74批，丙组，应交 34 件，签收 33 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L075：第75批，丁组，应交 20 件，签收 35 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L076：第76批，甲组，应交 21 件，签收 18 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L077：第77批，乙组，应交 22 件，签收 20 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L078：第78批，丙组，应交 23 件，签收 22 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L079：第79批，丁组，应交 24 件，签收 24 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L080：第80批，甲组，应交 25 件，签收 26 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L081：第81批，乙组，应交 26 件，签收 28 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L082：第82批，丙组，应交 27 件，签收 30 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L083：第83批，丁组，应交 28 件，签收 32 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L084：第84批，甲组，应交 29 件，签收 34 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L085：第85批，乙组，应交 30 件，签收 36 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L086：第86批，丙组，应交 31 件，签收 19 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L087：第87批，丁组，应交 32 件，签收 21 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L088：第88批，甲组，应交 33 件，签收 23 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L089：第89批，乙组，应交 34 件，签收 25 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L090：第90批，丙组，应交 20 件，签收 27 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L091：第91批，丁组，应交 21 件，签收 29 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L092：第92批，甲组，应交 22 件，签收 31 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L093：第93批，乙组，应交 23 件，签收 33 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L094：第94批，丙组，应交 24 件，签收 35 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L095：第95批，丁组，应交 25 件，签收 18 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L096：第96批，甲组，应交 26 件，签收 20 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L097：第97批，乙组，应交 27 件，签收 22 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L098：第98批，丙组，应交 28 件，签收 24 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L099：第99批，丁组，应交 29 件，签收 26 件；每批单独核验，未记录损毁或责任结论。\\n来源 test_shipments-L100：第100批，甲组，应交 30 件，签收 28 件；每批单独核验，未记录损毁或责任结论。\\n\\n请按以下要求输出 JSON：\\n- 对每条记录计算差额=应交-签收；\\n- 按甲、乙、丙、丁四组分别汇总：总应交、总签收、净差、正缺口；\\n- 正缺口只累计差额大于0的批次，不得用多签批次抵消；\\n- 保留每组的来源编号范围；\\n- 不推断损毁或责任原因。\\n\\n输出字段：\\n- group_summary：字符串，按组列出总应交、总签收、净差、正缺口及来源编号范围；\\n- batch_details：字符串，逐批列出批次、组别、来源编号、应交、签收、差额；\\n- assumptions：字符串，列出计算假设；\\n- uncertainties：字符串，列出材料未说明或无法判断的事项。\&quot;,\n      \&quot;parents\&quot;: [],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;对第51批至第100批物资记录逐批计算差额，并按组汇总总应交、总签收、净差和正缺口，保留来源编号范围。\&quot;,\n        \&quot;inputs\&quot;: {},\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;json\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;group_summary\&quot;: \&quot;按甲、乙、丙、丁组列出总应交、总签收、净差、正缺口及来源编号范围的文本\&quot;,\n            \&quot;batch_details\&quot;: \&quot;逐批列出批次、组别、来源编号、应交、签收、差额的文本\&quot;,\n            \&quot;assumptions\&quot;: \&quot;计算假设说明\&quot;,\n            \&quot;uncertainties\&quot;: \&quot;材料未说明或无法判断的事项\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;medium\&quot;,\n          \&quot;input_budget_tokens\&quot;: 65536,\n          \&quot;expected_output_tokens\&quot;: 4096\n        },\n        \&quot;checks\&quot;: [\n          \&quot;覆盖第51批至第100批全部记录\&quot;,\n          \&quot;差额按应交减签收计算\&quot;,\n          \&quot;正缺口只累计差额大于0的批次\&quot;,\n          \&quot;保留每组来源编号范围\&quot;,\n          \&quot;不虚构损毁或责任原因\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    },\n    {\n      \&quot;node_id\&quot;: \&quot;answer\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是物资到货交接核对报告撰写人。仅使用原始材料和两个计算节点的结果，不联网、不执行工具、不虚构信息。\\n\\n原始材料规则：\\nH1：每条记录给出应交数量、签收数量和一份来源编号；差额为应交减签收。\\nH2：多签不等于可以抵消另一批次少签，正缺口须逐批计算后汇总。\\nH3：核对报告必须保留每组的来源范围，列出总应交、总签收、净差及正缺口；没有损毁或责任证据。\\n\\n交付要求：将分组事实、来源和异常限制完整交接到最终报告，区别净差与未满足数量，不因另一批多签就宣称全部交齐。\\n\\n第1批至第50批计算结果：\\n{calc_group_1}\\n\\n第51批至第100批计算结果：\\n{calc_group_2}\\n\\n请撰写最终「物资到货交接报告」正文，直接输出正文，不要封装为 JSON。报告必须：\\n1. 保留每组的来源编号范围；\\n2. 列出每组总应交、总签收、净差及正缺口；\\n3. 明确区分净差与正缺口，说明多签不能抵消少签；\\n4. 保留来源编号，不虚构损毁或责任原因；\\n5. 对材料未说明的事项保持未知或条件判断；\\n6. 覆盖全部100批记录，不得遗漏。\&quot;,\n      \&quot;parents\&quot;: [\&quot;calc_group_1\&quot;, \&quot;calc_group_2\&quot;],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;汇总两个计算节点的结果，撰写完整、可检查的物资到货交接报告，保留分组事实、来源编号、净差与正缺口，并遵守材料约束。\&quot;,\n        \&quot;inputs\&quot;: {\n          \&quot;calc_group_1\&quot;: {\n            \&quot;fields\&quot;: [\&quot;group_summary\&quot;, \&quot;batch_details\&quot;, \&quot;assumptions\&quot;, \&quot;uncertainties\&quot;],\n            \&quot;reason\&quot;: \&quot;需要第1批至第50批的分组汇总、逐批明细、假设和不确定事项，以合并为完整报告。\&quot;\n          },\n          \&quot;calc_group_2\&quot;: {\n            \&quot;fields\&quot;: [\&quot;group_summary\&quot;, \&quot;batch_details\&quot;, \&quot;assumptions\&quot;, \&quot;uncertainties\&quot;],\n            \&quot;reason\&quot;: \&quot;需要第51批至第100批的分组汇总、逐批明细、假设和不确定事项，以合并为完整报告。\&quot;\n          }\n        },\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;text\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;text\&quot;: \&quot;最终物资到货交接报告正文，包含每组来源范围、总应交、总签收、净差、正缺口及异常限制说明\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;high\&quot;,\n          \&quot;risk\&quot;: \&quot;medium\&quot;,\n          \&quot;input_budget_tokens\&quot;: 131072,\n          \&quot;expected_output_tokens\&quot;: 8192\n        },\n        \&quot;checks\&quot;: [\n          \&quot;报告覆盖全部100批记录\&quot;,\n          \&quot;每组均列出总应交、总签收、净差和正缺口\&quot;,\n          \&quot;明确区分净差与正缺口，并说明多签不能抵消少签\&quot;,\n          \&quot;保留来源编号和每组来源范围\&quot;,\n          \&quot;不虚构损毁或责任原因，未知事项保持未知或条件判断\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    }\n  ],\n  \&quot;final_node_id\&quot;: \&quot;answer\&quot;,\n  \&quot;acceptance_criteria\&quot;: [\n    \&quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。\&quot;,\n    \&quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。\&quot;\n  ]\n}&quot;,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 6644
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

## 题目 6

<details><summary>查看原始题目与材料</summary>
<pre>这是独立编写的虚构封闭场景「维护工单月报」，不代表真实机构或法律规则。只用以下材料，不联网或执行工具。
W1：每条工单给出计划分钟与实际分钟；正偏差为实际减计划，小于零表示提前。W2：最终报告必须同时包含各组总工时、全部工单的总偏差、超计划工单数及限制。W3：材料没有故障原因或人员绩效证据，不能因耗时推断责任；不能只复制一条分支摘要。
来源 test_workorders-L001：第1单，乙组，计划 31 分钟，实际 28 分钟；无人员评价或故障归因材料。
来源 test_workorders-L002：第2单，丙组，计划 32 分钟，实际 31 分钟；无人员评价或故障归因材料。
来源 test_workorders-L003：第3单，丁组，计划 33 分钟，实际 34 分钟；无人员评价或故障归因材料。
来源 test_workorders-L004：第4单，甲组，计划 34 分钟，实际 37 分钟；无人员评价或故障归因材料。
来源 test_workorders-L005：第5单，乙组，计划 35 分钟，实际 40 分钟；无人员评价或故障归因材料。
来源 test_workorders-L006：第6单，丙组，计划 36 分钟，实际 43 分钟；无人员评价或故障归因材料。
来源 test_workorders-L007：第7单，丁组，计划 37 分钟，实际 46 分钟；无人员评价或故障归因材料。
来源 test_workorders-L008：第8单，甲组，计划 38 分钟，实际 49 分钟；无人员评价或故障归因材料。
来源 test_workorders-L009：第9单，乙组，计划 39 分钟，实际 52 分钟；无人员评价或故障归因材料。
来源 test_workorders-L010：第10单，丙组，计划 40 分钟，实际 55 分钟；无人员评价或故障归因材料。
来源 test_workorders-L011：第11单，丁组，计划 41 分钟，实际 58 分钟；无人员评价或故障归因材料。
来源 test_workorders-L012：第12单，甲组，计划 42 分钟，实际 26 分钟；无人员评价或故障归因材料。
来源 test_workorders-L013：第13单，乙组，计划 43 分钟，实际 29 分钟；无人员评价或故障归因材料。
来源 test_workorders-L014：第14单，丙组，计划 44 分钟，实际 32 分钟；无人员评价或故障归因材料。
来源 test_workorders-L015：第15单，丁组，计划 45 分钟，实际 35 分钟；无人员评价或故障归因材料。
来源 test_workorders-L016：第16单，甲组，计划 46 分钟，实际 38 分钟；无人员评价或故障归因材料。
来源 test_workorders-L017：第17单，乙组，计划 47 分钟，实际 41 分钟；无人员评价或故障归因材料。
来源 test_workorders-L018：第18单，丙组，计划 48 分钟，实际 44 分钟；无人员评价或故障归因材料。
来源 test_workorders-L019：第19单，丁组，计划 49 分钟，实际 47 分钟；无人员评价或故障归因材料。
来源 test_workorders-L020：第20单，甲组，计划 30 分钟，实际 50 分钟；无人员评价或故障归因材料。
来源 test_workorders-L021：第21单，乙组，计划 31 分钟，实际 53 分钟；无人员评价或故障归因材料。
来源 test_workorders-L022：第22单，丙组，计划 32 分钟，实际 56 分钟；无人员评价或故障归因材料。
来源 test_workorders-L023：第23单，丁组，计划 33 分钟，实际 59 分钟；无人员评价或故障归因材料。
来源 test_workorders-L024：第24单，甲组，计划 34 分钟，实际 27 分钟；无人员评价或故障归因材料。
来源 test_workorders-L025：第25单，乙组，计划 35 分钟，实际 30 分钟；无人员评价或故障归因材料。
来源 test_workorders-L026：第26单，丙组，计划 36 分钟，实际 33 分钟；无人员评价或故障归因材料。
来源 test_workorders-L027：第27单，丁组，计划 37 分钟，实际 36 分钟；无人员评价或故障归因材料。
来源 test_workorders-L028：第28单，甲组，计划 38 分钟，实际 39 分钟；无人员评价或故障归因材料。
来源 test_workorders-L029：第29单，乙组，计划 39 分钟，实际 42 分钟；无人员评价或故障归因材料。
来源 test_workorders-L030：第30单，丙组，计划 40 分钟，实际 45 分钟；无人员评价或故障归因材料。
来源 test_workorders-L031：第31单，丁组，计划 41 分钟，实际 48 分钟；无人员评价或故障归因材料。
来源 test_workorders-L032：第32单，甲组，计划 42 分钟，实际 51 分钟；无人员评价或故障归因材料。
来源 test_workorders-L033：第33单，乙组，计划 43 分钟，实际 54 分钟；无人员评价或故障归因材料。
来源 test_workorders-L034：第34单，丙组，计划 44 分钟，实际 57 分钟；无人员评价或故障归因材料。
来源 test_workorders-L035：第35单，丁组，计划 45 分钟，实际 25 分钟；无人员评价或故障归因材料。
来源 test_workorders-L036：第36单，甲组，计划 46 分钟，实际 28 分钟；无人员评价或故障归因材料。
来源 test_workorders-L037：第37单，乙组，计划 47 分钟，实际 31 分钟；无人员评价或故障归因材料。
来源 test_workorders-L038：第38单，丙组，计划 48 分钟，实际 34 分钟；无人员评价或故障归因材料。
来源 test_workorders-L039：第39单，丁组，计划 49 分钟，实际 37 分钟；无人员评价或故障归因材料。
来源 test_workorders-L040：第40单，甲组，计划 30 分钟，实际 40 分钟；无人员评价或故障归因材料。
来源 test_workorders-L041：第41单，乙组，计划 31 分钟，实际 43 分钟；无人员评价或故障归因材料。
来源 test_workorders-L042：第42单，丙组，计划 32 分钟，实际 46 分钟；无人员评价或故障归因材料。
来源 test_workorders-L043：第43单，丁组，计划 33 分钟，实际 49 分钟；无人员评价或故障归因材料。
来源 test_workorders-L044：第44单，甲组，计划 34 分钟，实际 52 分钟；无人员评价或故障归因材料。
来源 test_workorders-L045：第45单，乙组，计划 35 分钟，实际 55 分钟；无人员评价或故障归因材料。
来源 test_workorders-L046：第46单，丙组，计划 36 分钟，实际 58 分钟；无人员评价或故障归因材料。
来源 test_workorders-L047：第47单，丁组，计划 37 分钟，实际 26 分钟；无人员评价或故障归因材料。
来源 test_workorders-L048：第48单，甲组，计划 38 分钟，实际 29 分钟；无人员评价或故障归因材料。
来源 test_workorders-L049：第49单，乙组，计划 39 分钟，实际 32 分钟；无人员评价或故障归因材料。
来源 test_workorders-L050：第50单，丙组，计划 40 分钟，实际 35 分钟；无人员评价或故障归因材料。
来源 test_workorders-L051：第51单，丁组，计划 41 分钟，实际 38 分钟；无人员评价或故障归因材料。
来源 test_workorders-L052：第52单，甲组，计划 42 分钟，实际 41 分钟；无人员评价或故障归因材料。
来源 test_workorders-L053：第53单，乙组，计划 43 分钟，实际 44 分钟；无人员评价或故障归因材料。
来源 test_workorders-L054：第54单，丙组，计划 44 分钟，实际 47 分钟；无人员评价或故障归因材料。
来源 test_workorders-L055：第55单，丁组，计划 45 分钟，实际 50 分钟；无人员评价或故障归因材料。
来源 test_workorders-L056：第56单，甲组，计划 46 分钟，实际 53 分钟；无人员评价或故障归因材料。
来源 test_workorders-L057：第57单，乙组，计划 47 分钟，实际 56 分钟；无人员评价或故障归因材料。
来源 test_workorders-L058：第58单，丙组，计划 48 分钟，实际 59 分钟；无人员评价或故障归因材料。
来源 test_workorders-L059：第59单，丁组，计划 49 分钟，实际 27 分钟；无人员评价或故障归因材料。
来源 test_workorders-L060：第60单，甲组，计划 30 分钟，实际 30 分钟；无人员评价或故障归因材料。
来源 test_workorders-L061：第61单，乙组，计划 31 分钟，实际 33 分钟；无人员评价或故障归因材料。
来源 test_workorders-L062：第62单，丙组，计划 32 分钟，实际 36 分钟；无人员评价或故障归因材料。
来源 test_workorders-L063：第63单，丁组，计划 33 分钟，实际 39 分钟；无人员评价或故障归因材料。
来源 test_workorders-L064：第64单，甲组，计划 34 分钟，实际 42 分钟；无人员评价或故障归因材料。
来源 test_workorders-L065：第65单，乙组，计划 35 分钟，实际 45 分钟；无人员评价或故障归因材料。
来源 test_workorders-L066：第66单，丙组，计划 36 分钟，实际 48 分钟；无人员评价或故障归因材料。
来源 test_workorders-L067：第67单，丁组，计划 37 分钟，实际 51 分钟；无人员评价或故障归因材料。
来源 test_workorders-L068：第68单，甲组，计划 38 分钟，实际 54 分钟；无人员评价或故障归因材料。
来源 test_workorders-L069：第69单，乙组，计划 39 分钟，实际 57 分钟；无人员评价或故障归因材料。
来源 test_workorders-L070：第70单，丙组，计划 40 分钟，实际 25 分钟；无人员评价或故障归因材料。
来源 test_workorders-L071：第71单，丁组，计划 41 分钟，实际 28 分钟；无人员评价或故障归因材料。
来源 test_workorders-L072：第72单，甲组，计划 42 分钟，实际 31 分钟；无人员评价或故障归因材料。
来源 test_workorders-L073：第73单，乙组，计划 43 分钟，实际 34 分钟；无人员评价或故障归因材料。
来源 test_workorders-L074：第74单，丙组，计划 44 分钟，实际 37 分钟；无人员评价或故障归因材料。
来源 test_workorders-L075：第75单，丁组，计划 45 分钟，实际 40 分钟；无人员评价或故障归因材料。
来源 test_workorders-L076：第76单，甲组，计划 46 分钟，实际 43 分钟；无人员评价或故障归因材料。
来源 test_workorders-L077：第77单，乙组，计划 47 分钟，实际 46 分钟；无人员评价或故障归因材料。
来源 test_workorders-L078：第78单，丙组，计划 48 分钟，实际 49 分钟；无人员评价或故障归因材料。
来源 test_workorders-L079：第79单，丁组，计划 49 分钟，实际 52 分钟；无人员评价或故障归因材料。
来源 test_workorders-L080：第80单，甲组，计划 30 分钟，实际 55 分钟；无人员评价或故障归因材料。
来源 test_workorders-L081：第81单，乙组，计划 31 分钟，实际 58 分钟；无人员评价或故障归因材料。
来源 test_workorders-L082：第82单，丙组，计划 32 分钟，实际 26 分钟；无人员评价或故障归因材料。
来源 test_workorders-L083：第83单，丁组，计划 33 分钟，实际 29 分钟；无人员评价或故障归因材料。
来源 test_workorders-L084：第84单，甲组，计划 34 分钟，实际 32 分钟；无人员评价或故障归因材料。
来源 test_workorders-L085：第85单，乙组，计划 35 分钟，实际 35 分钟；无人员评价或故障归因材料。
来源 test_workorders-L086：第86单，丙组，计划 36 分钟，实际 38 分钟；无人员评价或故障归因材料。
来源 test_workorders-L087：第87单，丁组，计划 37 分钟，实际 41 分钟；无人员评价或故障归因材料。
来源 test_workorders-L088：第88单，甲组，计划 38 分钟，实际 44 分钟；无人员评价或故障归因材料。
来源 test_workorders-L089：第89单，乙组，计划 39 分钟，实际 47 分钟；无人员评价或故障归因材料。
来源 test_workorders-L090：第90单，丙组，计划 40 分钟，实际 50 分钟；无人员评价或故障归因材料。
来源 test_workorders-L091：第91单，丁组，计划 41 分钟，实际 53 分钟；无人员评价或故障归因材料。
来源 test_workorders-L092：第92单，甲组，计划 42 分钟，实际 56 分钟；无人员评价或故障归因材料。
来源 test_workorders-L093：第93单，乙组，计划 43 分钟，实际 59 分钟；无人员评价或故障归因材料。
来源 test_workorders-L094：第94单，丙组，计划 44 分钟，实际 27 分钟；无人员评价或故障归因材料。
来源 test_workorders-L095：第95单，丁组，计划 45 分钟，实际 30 分钟；无人员评价或故障归因材料。
来源 test_workorders-L096：第96单，甲组，计划 46 分钟，实际 33 分钟；无人员评价或故障归因材料。
来源 test_workorders-L097：第97单，乙组，计划 47 分钟，实际 36 分钟；无人员评价或故障归因材料。
来源 test_workorders-L098：第98单，丙组，计划 48 分钟，实际 39 分钟；无人员评价或故障归因材料。
来源 test_workorders-L099：第99单，丁组，计划 49 分钟，实际 42 分钟；无人员评价或故障归因材料。
来源 test_workorders-L100：第100单，甲组，计划 30 分钟，实际 45 分钟；无人员评价或故障归因材料。
交付要求：综合全表形成完整月报，核对分组汇总与总计相等，分别报告净偏差及正超时量，不混淆两者。</pre>
</details>

**原始验收：** 完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。；遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。

<details><summary>查看冻结参考（长材料已独立重算）</summary>
<pre>{&quot;丁&quot;: {&quot;记录数&quot;: 25, &quot;第一列总和&quot;: 1025, &quot;第二列总和&quot;: 1020, &quot;第一列减第二列&quot;: 5, &quot;正缺口&quot;: 125, &quot;第二列较大记录数&quot;: 12, &quot;第一列较大记录数&quot;: 13, &quot;正超额&quot;: 120}, &quot;丙&quot;: {&quot;记录数&quot;: 25, &quot;第一列总和&quot;: 1000, &quot;第二列总和&quot;: 1050, &quot;第一列减第二列&quot;: -50, &quot;正缺口&quot;: 93, &quot;第二列较大记录数&quot;: 14, &quot;第一列较大记录数&quot;: 11, &quot;正超额&quot;: 143}, &quot;乙&quot;: {&quot;记录数&quot;: 25, &quot;第一列总和&quot;: 975, &quot;第二列总和&quot;: 1080, &quot;第一列减第二列&quot;: -105, &quot;正缺口&quot;: 72, &quot;第二列较大记录数&quot;: 15, &quot;第一列较大记录数&quot;: 9, &quot;正超额&quot;: 177}, &quot;甲&quot;: {&quot;记录数&quot;: 25, &quot;第一列总和&quot;: 950, &quot;第二列总和&quot;: 1025, &quot;第一列减第二列&quot;: -75, &quot;正缺口&quot;: 88, &quot;第二列较大记录数&quot;: 14, &quot;第一列较大记录数&quot;: 10, &quot;正超额&quot;: 163}}</pre>
</details>

### P012

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| group_a_stats | generation | 无 | 统计甲组和乙组工单的数量、计划总分钟、实际总分钟、总偏差、净偏差、正超时量、超计划工单数、提前工单数、持平工单数，并保留来源编号。 |
| group_b_stats | generation | 无 | 统计丙组和丁组工单的数量、计划总分钟、实际总分钟、总偏差、净偏差、正超时量、超计划工单数、提前工单数、持平工单数，并保留来源编号。 |
| answer | generation | group_a_stats,group_b_stats | 综合甲、乙、丙、丁四组统计结果，核对分组汇总与总计相等，形成包含各组总工时、全部工单总偏差、超计划工单数及限制、净偏差与正超时量分别报告的完整月报，并区分已知事实、建议和未知事项。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;group_a_stats&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;你是维护工单月报统计助手。请仅根据以下材料，统计甲组和乙组的工单数据。材料为虚构封闭场景，不代表真实机构或法律规则。\n\n材料：\nL001：第1单，乙组，计划31，实际28\nL004：第4单，甲组，计划34，实际37\nL005：第5单，乙组，计划35，实际40\nL008：第8单，甲组，计划38，实际49\nL009：第9单，乙组，计划39，实际52\nL012：第12单，甲组，计划42，实际26\nL013：第13单，乙组，计划43，实际29\nL016：第16单，甲组，计划46，实际38\nL017：第17单，乙组，计划47，实际41\nL020：第20单，甲组，计划30，实际50\nL021：第21单，乙组，计划31，实际53\nL024：第24单，甲组，计划34，实际27\nL025：第25单，乙组，计划35，实际30\nL028：第28单，甲组，计划38，实际39\nL029：第29单，乙组，计划39，实际42\nL032：第32单，甲组，计划42，实际51\nL033：第33单，乙组，计划43，实际54\nL036：第36单，甲组，计划46，实际28\nL037：第37单，乙组，计划47，实际31\nL040：第40单，甲组，计划30，实际40\nL041：第41单，乙组，计划31，实际43\nL044：第44单，甲组，计划34，实际52\nL045：第45单，乙组，计划35，实际55\nL048：第48单，甲组，计划38，实际29\nL049：第49单，乙组，计划39，实际32\nL052：第52单，甲组，计划42，实际41\nL053：第53单，乙组，计划43，实际44\nL056：第56单，甲组，计划46，实际53\nL057：第57单，乙组，计划47，实际56\nL060：第60单，甲组，计划30，实际30\nL061：第61单，乙组，计划31，实际33\nL064：第64单，甲组，计划34，实际42\nL065：第65单，乙组，计划35，实际45\nL068：第68单，甲组，计划38，实际54\nL069：第69单，乙组，计划39，实际57\nL072：第72单，甲组，计划42，实际31\nL073：第73单，乙组，计划43，实际34\nL076：第76单，甲组，计划46，实际43\nL077：第77单，乙组，计划47，实际46\nL080：第80单，甲组，计划30，实际55\nL081：第81单，乙组，计划31，实际58\nL084：第84单，甲组，计划34，实际32\nL085：第85单，乙组，计划35，实际35\nL088：第88单，甲组，计划38，实际44\nL089：第89单，乙组，计划39，实际47\nL092：第92单，甲组，计划42，实际56\nL093：第93单，乙组，计划43，实际59\nL096：第96单，甲组，计划46，实际33\nL097：第97单，乙组，计划47，实际36\nL100：第100单，甲组，计划30，实际45\n\n请分别计算甲组和乙组的以下指标，并保留来源编号：\n1. 工单数量\n2. 计划总分钟\n3. 实际总分钟\n4. 总偏差（实际减计划之和）\n5. 净偏差（实际减计划之和，可为负）\n6. 正超时量（仅正偏差之和，即实际大于计划的部分之和）\n7. 超计划工单数（实际大于计划的工单数量）\n8. 提前工单数（实际小于计划的工单数量）\n9. 持平工单数（实际等于计划的工单数量）\n\n注意：正偏差为实际减计划，小于零表示提前。材料没有故障原因或人员绩效证据，不能因耗时推断责任。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;统计甲组和乙组工单的数量、计划总分钟、实际总分钟、总偏差、净偏差、正超时量、超计划工单数、提前工单数、持平工单数，并保留来源编号。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;group_a_summary&quot;: &quot;甲组统计结果，包含工单数量、计划总分钟、实际总分钟、总偏差、净偏差、正超时量、超计划工单数、提前工单数、持平工单数及来源编号列表&quot;,
              &quot;group_b_summary&quot;: &quot;乙组统计结果，包含工单数量、计划总分钟、实际总分钟、总偏差、净偏差、正超时量、超计划工单数、提前工单数、持平工单数及来源编号列表&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;medium&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 2000
          },
          &quot;checks&quot;: [
            &quot;甲组和乙组统计结果分别包含工单数量、计划总分钟、实际总分钟、总偏差、净偏差、正超时量、超计划工单数、提前工单数、持平工单数&quot;,
            &quot;统计结果保留来源编号&quot;,
            &quot;正偏差为实际减计划，小于零表示提前；净偏差与正超时量不混淆&quot;,
            &quot;不虚构故障原因或人员绩效证据&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;group_b_stats&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;你是维护工单月报统计助手。请仅根据以下材料，统计丙组和丁组的工单数据。材料为虚构封闭场景，不代表真实机构或法律规则。\n\n材料：\nL002：第2单，丙组，计划32，实际31\nL003：第3单，丁组，计划33，实际34\nL006：第6单，丙组，计划36，实际43\nL007：第7单，丁组，计划37，实际46\nL010：第10单，丙组，计划40，实际55\nL011：第11单，丁组，计划41，实际58\nL014：第14单，丙组，计划44，实际32\nL015：第15单，丁组，计划45，实际35\nL018：第18单，丙组，计划48，实际44\nL019：第19单，丁组，计划49，实际47\nL022：第22单，丙组，计划32，实际56\nL023：第23单，丁组，计划33，实际59\nL026：第26单，丙组，计划36，实际33\nL027：第27单，丁组，计划37，实际36\nL030：第30单，丙组，计划40，实际45\nL031：第31单，丁组，计划41，实际48\nL034：第34单，丙组，计划44，实际57\nL035：第35单，丁组，计划45，实际25\nL038：第38单，丙组，计划48，实际34\nL039：第39单，丁组，计划49，实际37\nL042：第42单，丙组，计划32，实际46\nL043：第43单，丁组，计划33，实际49\nL046：第46单，丙组，计划36，实际58\nL047：第47单，丁组，计划37，实际26\nL050：第50单，丙组，计划40，实际35\nL051：第51单，丁组，计划41，实际38\nL054：第54单，丙组，计划44，实际47\nL055：第55单，丁组，计划45，实际50\nL058：第58单，丙组，计划48，实际59\nL059：第59单，丁组，计划49，实际27\nL062：第62单，丙组，计划32，实际36\nL063：第63单，丁组，计划33，实际39\nL066：第66单，丙组，计划36，实际48\nL067：第67单，丁组，计划37，实际51\nL070：第70单，丙组，计划40，实际25\nL071：第71单，丁组，计划41，实际28\nL074：第74单，丙组，计划44，实际37\nL075：第75单，丁组，计划45，实际40\nL078：第78单，丙组，计划48，实际49\nL079：第79单，丁组，计划49，实际52\nL082：第82单，丙组，计划32，实际26\nL083：第83单，丁组，计划33，实际29\nL086：第86单，丙组，计划36，实际38\nL087：第87单，丁组，计划37，实际41\nL090：第90单，丙组，计划40，实际50\nL091：第91单，丁组，计划41，实际53\nL094：第94单，丙组，计划44，实际27\nL095：第95单，丁组，计划45，实际30\nL098：第98单，丙组，计划48，实际39\nL099：第99单，丁组，计划49，实际42\n\n请分别计算丙组和丁组的以下指标，并保留来源编号：\n1. 工单数量\n2. 计划总分钟\n3. 实际总分钟\n4. 总偏差（实际减计划之和）\n5. 净偏差（实际减计划之和，可为负）\n6. 正超时量（仅正偏差之和，即实际大于计划的部分之和）\n7. 超计划工单数（实际大于计划的工单数量）\n8. 提前工单数（实际小于计划的工单数量）\n9. 持平工单数（实际等于计划的工单数量）\n\n注意：正偏差为实际减计划，小于零表示提前。材料没有故障原因或人员绩效证据，不能因耗时推断责任。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;统计丙组和丁组工单的数量、计划总分钟、实际总分钟、总偏差、净偏差、正超时量、超计划工单数、提前工单数、持平工单数，并保留来源编号。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;group_c_summary&quot;: &quot;丙组统计结果，包含工单数量、计划总分钟、实际总分钟、总偏差、净偏差、正超时量、超计划工单数、提前工单数、持平工单数及来源编号列表&quot;,
              &quot;group_d_summary&quot;: &quot;丁组统计结果，包含工单数量、计划总分钟、实际总分钟、总偏差、净偏差、正超时量、超计划工单数、提前工单数、持平工单数及来源编号列表&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;medium&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 2000
          },
          &quot;checks&quot;: [
            &quot;丙组和丁组统计结果分别包含工单数量、计划总分钟、实际总分钟、总偏差、净偏差、正超时量、超计划工单数、提前工单数、持平工单数&quot;,
            &quot;统计结果保留来源编号&quot;,
            &quot;正偏差为实际减计划，小于零表示提前；净偏差与正超时量不混淆&quot;,
            &quot;不虚构故障原因或人员绩效证据&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;你是维护工单月报撰写助手。请根据以下分组统计结果，综合全表形成完整月报。材料为虚构封闭场景，不代表真实机构或法律规则。\n\n分组统计结果：\n甲组：{group_a_summary}\n乙组：{group_b_summary}\n丙组：{group_c_summary}\n丁组：{group_d_summary}\n\n交付要求：\n1. 综合全表形成完整月报。\n2. 核对分组汇总与总计相等。\n3. 分别报告净偏差及正超时量，不混淆两者。\n4. 最终报告必须同时包含各组总工时、全部工单的总偏差、超计划工单数及限制。\n5. 材料没有故障原因或人员绩效证据，不能因耗时推断责任；不能只复制一条分支摘要。\n6. 保留来源编号。\n7. 区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。\n\n请在月报中依次呈现：\n一、各组总工时（甲、乙、丙、丁四组的计划总分钟与实际总分钟）\n二、全部工单的总偏差（实际减计划之和）\n三、超计划工单数及限制（说明超计划工单的判定标准为实际大于计划，并列出超计划工单数；同时说明材料限制：无故障原因或人员绩效证据，不能因耗时推断责任）\n四、净偏差与正超时量分别报告（净偏差为实际减计划之和，可为负；正超时量为仅正偏差之和，两者不混淆）\n五、核对说明（分组汇总与总计是否相等）\n六、已知事实、建议和未知事项的区分说明\n\n注意：最终报告直接输出正文，不封装为JSON。&quot;,
        &quot;parents&quot;: [
          &quot;group_a_stats&quot;,
          &quot;group_b_stats&quot;
        ],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;综合甲、乙、丙、丁四组统计结果，核对分组汇总与总计相等，形成包含各组总工时、全部工单总偏差、超计划工单数及限制、净偏差与正超时量分别报告的完整月报，并区分已知事实、建议和未知事项。&quot;,
          &quot;inputs&quot;: {
            &quot;group_a_stats&quot;: {
              &quot;fields&quot;: [
                &quot;group_a_summary&quot;,
                &quot;group_b_summary&quot;
              ],
              &quot;reason&quot;: &quot;需要甲组和乙组的统计结果以汇总各组总工时、总偏差、超计划工单数及净偏差与正超时量。&quot;
            },
            &quot;group_b_stats&quot;: {
              &quot;fields&quot;: [
                &quot;group_c_summary&quot;,
                &quot;group_d_summary&quot;
              ],
              &quot;reason&quot;: &quot;需要丙组和丁组的统计结果以汇总各组总工时、总偏差、超计划工单数及净偏差与正超时量。&quot;
            }
          },
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;完整月报正文，依次包含各组总工时、全部工单总偏差、超计划工单数及限制、净偏差与正超时量分别报告、核对说明、已知事实建议和未知事项区分说明&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;medium&quot;,
            &quot;input_budget_tokens&quot;: 65536,
            &quot;expected_output_tokens&quot;: 4000
          },
          &quot;checks&quot;: [
            &quot;月报包含各组总工时（甲、乙、丙、丁四组的计划总分钟与实际总分钟）&quot;,
            &quot;月报包含全部工单的总偏差&quot;,
            &quot;月报包含超计划工单数及限制说明&quot;,
            &quot;月报分别报告净偏差与正超时量，不混淆两者&quot;,
            &quot;月报核对分组汇总与总计相等&quot;,
            &quot;月报保留来源编号&quot;,
            &quot;月报区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务为100条工单的统计汇总与月报撰写。计算量大且需交叉核对，拆分为两个独立分组统计节点并行处理，再由汇总节点核对一致性并生成最终月报。拆分净收益在于并行降低时延、分组统计降低单节点计算错误风险；汇总节点需核对分组与总计相等、净偏差与正超时量不混淆，交接开销可控。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 3963
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P014

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| extract_group_a | extraction | 无 | 提取并统计甲组全部工单的计划、实际、偏差及超时指标。 |
| extract_group_b | extraction | 无 | 提取并统计乙组全部工单的计划、实际、偏差及超时指标。 |
| extract_group_c | extraction | 无 | 提取并统计丙组全部工单的计划、实际、偏差及超时指标。 |
| extract_group_d | extraction | 无 | 提取并统计丁组全部工单的计划、实际、偏差及超时指标。 |
| answer | generation | extract_group_a,extract_group_b,extract_group_c,extract_group_d | 汇总四个分组统计结果，核对一致性，生成包含各组总工时、全部工单总偏差、超计划工单数及限制、净偏差与正超时量分别报告的完整月报。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;extract_group_a&quot;,
        &quot;node_type&quot;: &quot;extraction&quot;,
        &quot;prompt_template&quot;: &quot;从原始任务材料中提取甲组全部工单（来源编号含 L004、L008、L012、L016、L020、L024、L028、L032、L036、L040、L044、L048、L052、L056、L060、L064、L068、L072、L076、L080、L084、L088、L092、L096、L100 等甲组条目）。对每条工单记录来源编号、计划分钟、实际分钟、偏差（实际减计划）。计算甲组：工单数、计划总分钟、实际总分钟、总偏差（实际总分钟减计划总分钟）、净偏差、正超时量（仅正偏差之和）、超计划工单数（偏差大于0的工单数）。不得推断故障原因或人员绩效。输出字段：group_name、order_count、planned_total、actual_total、total_deviation、positive_overrun_sum、overrun_count、detail_records。detail_records 用字符串逐条列出「来源编号|计划|实际|偏差」，以分号分隔。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;提取并统计甲组全部工单的计划、实际、偏差及超时指标。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;group_name&quot;: &quot;组名，固定为甲组&quot;,
              &quot;order_count&quot;: &quot;甲组工单数量&quot;,
              &quot;planned_total&quot;: &quot;甲组计划分钟总和&quot;,
              &quot;actual_total&quot;: &quot;甲组实际分钟总和&quot;,
              &quot;total_deviation&quot;: &quot;甲组总偏差，即实际总分钟减计划总分钟&quot;,
              &quot;positive_overrun_sum&quot;: &quot;甲组正超时量，即所有正偏差之和&quot;,
              &quot;overrun_count&quot;: &quot;甲组超计划工单数，即偏差大于0的工单数&quot;,
              &quot;detail_records&quot;: &quot;逐条列出甲组工单的来源编号、计划分钟、实际分钟、偏差，格式为「来源编号|计划|实际|偏差」，以分号分隔&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 2500
          },
          &quot;checks&quot;: [
            &quot;甲组工单数量与材料一致&quot;,
            &quot;计划总分钟、实际总分钟、总偏差、正超时量、超计划工单数计算正确&quot;,
            &quot;detail_records 保留来源编号且偏差计算正确&quot;,
            &quot;未虚构故障原因或人员绩效&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;extract_group_b&quot;,
        &quot;node_type&quot;: &quot;extraction&quot;,
        &quot;prompt_template&quot;: &quot;从原始任务材料中提取乙组全部工单（来源编号含 L001、L005、L009、L013、L017、L021、L025、L029、L033、L037、L041、L045、L049、L053、L057、L061、L065、L069、L073、L077、L081、L085、L089、L093、L097 等乙组条目）。对每条工单记录来源编号、计划分钟、实际分钟、偏差（实际减计划）。计算乙组：工单数、计划总分钟、实际总分钟、总偏差（实际总分钟减计划总分钟）、净偏差、正超时量（仅正偏差之和）、超计划工单数（偏差大于0的工单数）。不得推断故障原因或人员绩效。输出字段：group_name、order_count、planned_total、actual_total、total_deviation、positive_overrun_sum、overrun_count、detail_records。detail_records 用字符串逐条列出「来源编号|计划|实际|偏差」，以分号分隔。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;提取并统计乙组全部工单的计划、实际、偏差及超时指标。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;group_name&quot;: &quot;组名，固定为乙组&quot;,
              &quot;order_count&quot;: &quot;乙组工单数量&quot;,
              &quot;planned_total&quot;: &quot;乙组计划分钟总和&quot;,
              &quot;actual_total&quot;: &quot;乙组实际分钟总和&quot;,
              &quot;total_deviation&quot;: &quot;乙组总偏差，即实际总分钟减计划总分钟&quot;,
              &quot;positive_overrun_sum&quot;: &quot;乙组正超时量，即所有正偏差之和&quot;,
              &quot;overrun_count&quot;: &quot;乙组超计划工单数，即偏差大于0的工单数&quot;,
              &quot;detail_records&quot;: &quot;逐条列出乙组工单的来源编号、计划分钟、实际分钟、偏差，格式为「来源编号|计划|实际|偏差」，以分号分隔&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 2500
          },
          &quot;checks&quot;: [
            &quot;乙组工单数量与材料一致&quot;,
            &quot;计划总分钟、实际总分钟、总偏差、正超时量、超计划工单数计算正确&quot;,
            &quot;detail_records 保留来源编号且偏差计算正确&quot;,
            &quot;未虚构故障原因或人员绩效&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;extract_group_c&quot;,
        &quot;node_type&quot;: &quot;extraction&quot;,
        &quot;prompt_template&quot;: &quot;从原始任务材料中提取丙组全部工单（来源编号含 L002、L006、L010、L014、L018、L022、L026、L030、L034、L038、L042、L046、L050、L054、L058、L062、L066、L070、L074、L078、L082、L086、L090、L094、L098 等丙组条目）。对每条工单记录来源编号、计划分钟、实际分钟、偏差（实际减计划）。计算丙组：工单数、计划总分钟、实际总分钟、总偏差（实际总分钟减计划总分钟）、净偏差、正超时量（仅正偏差之和）、超计划工单数（偏差大于0的工单数）。不得推断故障原因或人员绩效。输出字段：group_name、order_count、planned_total、actual_total、total_deviation、positive_overrun_sum、overrun_count、detail_records。detail_records 用字符串逐条列出「来源编号|计划|实际|偏差」，以分号分隔。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;提取并统计丙组全部工单的计划、实际、偏差及超时指标。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;group_name&quot;: &quot;组名，固定为丙组&quot;,
              &quot;order_count&quot;: &quot;丙组工单数量&quot;,
              &quot;planned_total&quot;: &quot;丙组计划分钟总和&quot;,
              &quot;actual_total&quot;: &quot;丙组实际分钟总和&quot;,
              &quot;total_deviation&quot;: &quot;丙组总偏差，即实际总分钟减计划总分钟&quot;,
              &quot;positive_overrun_sum&quot;: &quot;丙组正超时量，即所有正偏差之和&quot;,
              &quot;overrun_count&quot;: &quot;丙组超计划工单数，即偏差大于0的工单数&quot;,
              &quot;detail_records&quot;: &quot;逐条列出丙组工单的来源编号、计划分钟、实际分钟、偏差，格式为「来源编号|计划|实际|偏差」，以分号分隔&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 2500
          },
          &quot;checks&quot;: [
            &quot;丙组工单数量与材料一致&quot;,
            &quot;计划总分钟、实际总分钟、总偏差、正超时量、超计划工单数计算正确&quot;,
            &quot;detail_records 保留来源编号且偏差计算正确&quot;,
            &quot;未虚构故障原因或人员绩效&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;extract_group_d&quot;,
        &quot;node_type&quot;: &quot;extraction&quot;,
        &quot;prompt_template&quot;: &quot;从原始任务材料中提取丁组全部工单（来源编号含 L003、L007、L011、L015、L019、L023、L027、L031、L035、L039、L043、L047、L051、L055、L059、L063、L067、L071、L075、L079、L083、L087、L091、L095、L099 等丁组条目）。对每条工单记录来源编号、计划分钟、实际分钟、偏差（实际减计划）。计算丁组：工单数、计划总分钟、实际总分钟、总偏差（实际总分钟减计划总分钟）、净偏差、正超时量（仅正偏差之和）、超计划工单数（偏差大于0的工单数）。不得推断故障原因或人员绩效。输出字段：group_name、order_count、planned_total、actual_total、total_deviation、positive_overrun_sum、overrun_count、detail_records。detail_records 用字符串逐条列出「来源编号|计划|实际|偏差」，以分号分隔。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;提取并统计丁组全部工单的计划、实际、偏差及超时指标。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;group_name&quot;: &quot;组名，固定为丁组&quot;,
              &quot;order_count&quot;: &quot;丁组工单数量&quot;,
              &quot;planned_total&quot;: &quot;丁组计划分钟总和&quot;,
              &quot;actual_total&quot;: &quot;丁组实际分钟总和&quot;,
              &quot;total_deviation&quot;: &quot;丁组总偏差，即实际总分钟减计划总分钟&quot;,
              &quot;positive_overrun_sum&quot;: &quot;丁组正超时量，即所有正偏差之和&quot;,
              &quot;overrun_count&quot;: &quot;丁组超计划工单数，即偏差大于0的工单数&quot;,
              &quot;detail_records&quot;: &quot;逐条列出丁组工单的来源编号、计划分钟、实际分钟、偏差，格式为「来源编号|计划|实际|偏差」，以分号分隔&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 2500
          },
          &quot;checks&quot;: [
            &quot;丁组工单数量与材料一致&quot;,
            &quot;计划总分钟、实际总分钟、总偏差、正超时量、超计划工单数计算正确&quot;,
            &quot;detail_records 保留来源编号且偏差计算正确&quot;,
            &quot;未虚构故障原因或人员绩效&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;根据四个分组提取结果，综合全表形成完整「维护工单月报」。必须核对：四组工单数之和等于100，四组计划总分钟之和等于全部工单计划总分钟，四组实际总分钟之和等于全部工单实际总分钟，四组总偏差之和等于全部工单总偏差，四组正超时量之和等于全部工单正超时量，四组超计划工单数之和等于全部工单超计划工单数。若发现不一致，以原始任务材料重新核算并指出差异。最终报告必须同时包含：1）各组总工时（甲、乙、丙、丁的计划总分钟与实际总分钟）；2）全部工单的总偏差；3）超计划工单数及限制；4）分别报告净偏差及正超时量，不混淆两者。保留来源编号。材料没有故障原因或人员绩效证据，不能因耗时推断责任；不得只复制一条分支摘要。区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。直接输出完整月报正文，不封装为 JSON。&quot;,
        &quot;parents&quot;: [
          &quot;extract_group_a&quot;,
          &quot;extract_group_b&quot;,
          &quot;extract_group_c&quot;,
          &quot;extract_group_d&quot;
        ],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;汇总四个分组统计结果，核对一致性，生成包含各组总工时、全部工单总偏差、超计划工单数及限制、净偏差与正超时量分别报告的完整月报。&quot;,
          &quot;inputs&quot;: {
            &quot;extract_group_a&quot;: {
              &quot;fields&quot;: [
                &quot;group_name&quot;,
                &quot;order_count&quot;,
                &quot;planned_total&quot;,
                &quot;actual_total&quot;,
                &quot;total_deviation&quot;,
                &quot;positive_overrun_sum&quot;,
                &quot;overrun_count&quot;,
                &quot;detail_records&quot;
              ],
              &quot;reason&quot;: &quot;需要甲组统计结果与明细以汇总全表并核对分组与总计相等。&quot;
            },
            &quot;extract_group_b&quot;: {
              &quot;fields&quot;: [
                &quot;group_name&quot;,
                &quot;order_count&quot;,
                &quot;planned_total&quot;,
                &quot;actual_total&quot;,
                &quot;total_deviation&quot;,
                &quot;positive_overrun_sum&quot;,
                &quot;overrun_count&quot;,
                &quot;detail_records&quot;
              ],
              &quot;reason&quot;: &quot;需要乙组统计结果与明细以汇总全表并核对分组与总计相等。&quot;
            },
            &quot;extract_group_c&quot;: {
              &quot;fields&quot;: [
                &quot;group_name&quot;,
                &quot;order_count&quot;,
                &quot;planned_total&quot;,
                &quot;actual_total&quot;,
                &quot;total_deviation&quot;,
                &quot;positive_overrun_sum&quot;,
                &quot;overrun_count&quot;,
                &quot;detail_records&quot;
              ],
              &quot;reason&quot;: &quot;需要丙组统计结果与明细以汇总全表并核对分组与总计相等。&quot;
            },
            &quot;extract_group_d&quot;: {
              &quot;fields&quot;: [
                &quot;group_name&quot;,
                &quot;order_count&quot;,
                &quot;planned_total&quot;,
                &quot;actual_total&quot;,
                &quot;total_deviation&quot;,
                &quot;positive_overrun_sum&quot;,
                &quot;overrun_count&quot;,
                &quot;detail_records&quot;
              ],
              &quot;reason&quot;: &quot;需要丁组统计结果与明细以汇总全表并核对分组与总计相等。&quot;
            }
          },
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;完整维护工单月报正文，包含各组总工时、全部工单总偏差、超计划工单数及限制、净偏差与正超时量分别报告，并保留来源编号与限制说明&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;medium&quot;,
            &quot;input_budget_tokens&quot;: 65536,
            &quot;expected_output_tokens&quot;: 4000
          },
          &quot;checks&quot;: [
            &quot;最终报告同时包含各组总工时、全部工单总偏差、超计划工单数及限制&quot;,
            &quot;净偏差与正超时量分别报告且不混淆&quot;,
            &quot;分组汇总与总计核对相等，事实和计算与材料一致&quot;,
            &quot;保留来源编号，区分已知事实、建议和未知事项，不虚构原因、数据或已执行操作&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务为100条工单的统计汇总与月报撰写。计算量大且需交叉核对，拆分为按组并行提取统计、再汇总核对并生成最终月报，可降低单节点遗漏风险并利用并行机会；但汇总节点需消费四个分组结果，存在交接与一致性核对开销，整体净收益为正。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 3616
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P019

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| extract_group_a | extraction | 无 | 提取并统计甲组工单数据 |
| extract_group_b | extraction | 无 | 提取并统计乙组工单数据 |
| extract_group_c | extraction | 无 | 提取并统计丙组工单数据 |
| extract_group_d | extraction | 无 | 提取并统计丁组工单数据 |
| answer | generation | extract_group_a,extract_group_b,extract_group_c,extract_group_d | 汇总四组统计结果并生成完整月报正文 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;extract_group_a&quot;,
        &quot;node_type&quot;: &quot;extraction&quot;,
        &quot;prompt_template&quot;: &quot;从原始任务材料中提取甲组全部工单（来源编号、计划分钟、实际分钟），逐条计算偏差=实际-计划，并统计：甲组工单数、计划总分钟、实际总分钟、净偏差总和、正超时量总和（仅正偏差相加）、超计划工单数（偏差&gt;0的条数）。保留每条工单的来源编号。只依据材料，不推断原因。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;提取并统计甲组工单数据&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;group&quot;: &quot;组名，固定为甲组&quot;,
              &quot;count&quot;: &quot;甲组工单数量&quot;,
              &quot;planned_total&quot;: &quot;甲组计划总分钟&quot;,
              &quot;actual_total&quot;: &quot;甲组实际总分钟&quot;,
              &quot;net_deviation&quot;: &quot;甲组净偏差总和，可为负&quot;,
              &quot;positive_overrun&quot;: &quot;甲组正超时量总和，仅正偏差相加&quot;,
              &quot;overrun_count&quot;: &quot;甲组超计划工单数&quot;,
              &quot;detail&quot;: &quot;甲组每条工单的来源编号、计划分钟、实际分钟、偏差，逐条列出&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 3000
          },
          &quot;checks&quot;: [
            &quot;甲组工单数量与材料一致&quot;,
            &quot;计划总分钟、实际总分钟、净偏差、正超时量、超计划工单数计算正确&quot;,
            &quot;每条工单保留来源编号&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;extract_group_b&quot;,
        &quot;node_type&quot;: &quot;extraction&quot;,
        &quot;prompt_template&quot;: &quot;从原始任务材料中提取乙组全部工单（来源编号、计划分钟、实际分钟），逐条计算偏差=实际-计划，并统计：乙组工单数、计划总分钟、实际总分钟、净偏差总和、正超时量总和（仅正偏差相加）、超计划工单数（偏差&gt;0的条数）。保留每条工单的来源编号。只依据材料，不推断原因。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;提取并统计乙组工单数据&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;group&quot;: &quot;组名，固定为乙组&quot;,
              &quot;count&quot;: &quot;乙组工单数量&quot;,
              &quot;planned_total&quot;: &quot;乙组计划总分钟&quot;,
              &quot;actual_total&quot;: &quot;乙组实际总分钟&quot;,
              &quot;net_deviation&quot;: &quot;乙组净偏差总和，可为负&quot;,
              &quot;positive_overrun&quot;: &quot;乙组正超时量总和，仅正偏差相加&quot;,
              &quot;overrun_count&quot;: &quot;乙组超计划工单数&quot;,
              &quot;detail&quot;: &quot;乙组每条工单的来源编号、计划分钟、实际分钟、偏差，逐条列出&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 3000
          },
          &quot;checks&quot;: [
            &quot;乙组工单数量与材料一致&quot;,
            &quot;计划总分钟、实际总分钟、净偏差、正超时量、超计划工单数计算正确&quot;,
            &quot;每条工单保留来源编号&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;extract_group_c&quot;,
        &quot;node_type&quot;: &quot;extraction&quot;,
        &quot;prompt_template&quot;: &quot;从原始任务材料中提取丙组全部工单（来源编号、计划分钟、实际分钟），逐条计算偏差=实际-计划，并统计：丙组工单数、计划总分钟、实际总分钟、净偏差总和、正超时量总和（仅正偏差相加）、超计划工单数（偏差&gt;0的条数）。保留每条工单的来源编号。只依据材料，不推断原因。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;提取并统计丙组工单数据&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;group&quot;: &quot;组名，固定为丙组&quot;,
              &quot;count&quot;: &quot;丙组工单数量&quot;,
              &quot;planned_total&quot;: &quot;丙组计划总分钟&quot;,
              &quot;actual_total&quot;: &quot;丙组实际总分钟&quot;,
              &quot;net_deviation&quot;: &quot;丙组净偏差总和，可为负&quot;,
              &quot;positive_overrun&quot;: &quot;丙组正超时量总和，仅正偏差相加&quot;,
              &quot;overrun_count&quot;: &quot;丙组超计划工单数&quot;,
              &quot;detail&quot;: &quot;丙组每条工单的来源编号、计划分钟、实际分钟、偏差，逐条列出&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 3000
          },
          &quot;checks&quot;: [
            &quot;丙组工单数量与材料一致&quot;,
            &quot;计划总分钟、实际总分钟、净偏差、正超时量、超计划工单数计算正确&quot;,
            &quot;每条工单保留来源编号&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;extract_group_d&quot;,
        &quot;node_type&quot;: &quot;extraction&quot;,
        &quot;prompt_template&quot;: &quot;从原始任务材料中提取丁组全部工单（来源编号、计划分钟、实际分钟），逐条计算偏差=实际-计划，并统计：丁组工单数、计划总分钟、实际总分钟、净偏差总和、正超时量总和（仅正偏差相加）、超计划工单数（偏差&gt;0的条数）。保留每条工单的来源编号。只依据材料，不推断原因。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;提取并统计丁组工单数据&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;group&quot;: &quot;组名，固定为丁组&quot;,
              &quot;count&quot;: &quot;丁组工单数量&quot;,
              &quot;planned_total&quot;: &quot;丁组计划总分钟&quot;,
              &quot;actual_total&quot;: &quot;丁组实际总分钟&quot;,
              &quot;net_deviation&quot;: &quot;丁组净偏差总和，可为负&quot;,
              &quot;positive_overrun&quot;: &quot;丁组正超时量总和，仅正偏差相加&quot;,
              &quot;overrun_count&quot;: &quot;丁组超计划工单数&quot;,
              &quot;detail&quot;: &quot;丁组每条工单的来源编号、计划分钟、实际分钟、偏差，逐条列出&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 3000
          },
          &quot;checks&quot;: [
            &quot;丁组工单数量与材料一致&quot;,
            &quot;计划总分钟、实际总分钟、净偏差、正超时量、超计划工单数计算正确&quot;,
            &quot;每条工单保留来源编号&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;综合四个分组的提取统计结果，形成完整维护工单月报。必须同时包含：1）各组总工时（甲、乙、丙、丁的计划总分钟与实际总分钟）；2）全部工单的总偏差（净偏差总和）；3）超计划工单数及限制说明；4）分别报告净偏差及正超时量，不混淆两者。核对分组汇总与总计相等，检查冲突、遗漏、术语和证据一致性。保留来源编号。遵守材料约束：不虚构故障原因、人员绩效或已执行操作；材料未说明的原因保持未知。最终直接输出月报正文，不封装为JSON。&quot;,
        &quot;parents&quot;: [
          &quot;extract_group_a&quot;,
          &quot;extract_group_b&quot;,
          &quot;extract_group_c&quot;,
          &quot;extract_group_d&quot;
        ],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;汇总四组统计结果并生成完整月报正文&quot;,
          &quot;inputs&quot;: {
            &quot;extract_group_a&quot;: {
              &quot;fields&quot;: [
                &quot;group&quot;,
                &quot;count&quot;,
                &quot;planned_total&quot;,
                &quot;actual_total&quot;,
                &quot;net_deviation&quot;,
                &quot;positive_overrun&quot;,
                &quot;overrun_count&quot;,
                &quot;detail&quot;
              ],
              &quot;reason&quot;: &quot;需要甲组统计与明细以汇总总工时、总偏差、超计划工单数并保留来源编号&quot;
            },
            &quot;extract_group_b&quot;: {
              &quot;fields&quot;: [
                &quot;group&quot;,
                &quot;count&quot;,
                &quot;planned_total&quot;,
                &quot;actual_total&quot;,
                &quot;net_deviation&quot;,
                &quot;positive_overrun&quot;,
                &quot;overrun_count&quot;,
                &quot;detail&quot;
              ],
              &quot;reason&quot;: &quot;需要乙组统计与明细以汇总总工时、总偏差、超计划工单数并保留来源编号&quot;
            },
            &quot;extract_group_c&quot;: {
              &quot;fields&quot;: [
                &quot;group&quot;,
                &quot;count&quot;,
                &quot;planned_total&quot;,
                &quot;actual_total&quot;,
                &quot;net_deviation&quot;,
                &quot;positive_overrun&quot;,
                &quot;overrun_count&quot;,
                &quot;detail&quot;
              ],
              &quot;reason&quot;: &quot;需要丙组统计与明细以汇总总工时、总偏差、超计划工单数并保留来源编号&quot;
            },
            &quot;extract_group_d&quot;: {
              &quot;fields&quot;: [
                &quot;group&quot;,
                &quot;count&quot;,
                &quot;planned_total&quot;,
                &quot;actual_total&quot;,
                &quot;net_deviation&quot;,
                &quot;positive_overrun&quot;,
                &quot;overrun_count&quot;,
                &quot;detail&quot;
              ],
              &quot;reason&quot;: &quot;需要丁组统计与明细以汇总总工时、总偏差、超计划工单数并保留来源编号&quot;
            }
          },
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;完整维护工单月报正文，包含各组总工时、全部工单总偏差、超计划工单数及限制、净偏差与正超时量分别报告，并保留来源编号&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;medium&quot;,
            &quot;input_budget_tokens&quot;: 65536,
            &quot;expected_output_tokens&quot;: 6000
          },
          &quot;checks&quot;: [
            &quot;月报同时包含各组总工时、全部工单总偏差、超计划工单数及限制&quot;,
            &quot;分别报告净偏差及正超时量，不混淆两者&quot;,
            &quot;分组汇总与总计相等&quot;,
            &quot;保留来源编号，不虚构原因、数据或已执行操作&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务为100条工单的统计汇总与月报撰写。计算量大且需交叉核对，拆分为按组并行提取统计、再汇总核对并生成最终月报，可降低单节点遗漏风险并利用并行机会；但最终报告必须统一呈现，故设置一个汇总生成节点消费全部上游结果。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 2611
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P031

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| cost | synthesis | 无 | 汇总全部原始事实，完成所需计算并列出来源；只交付本节点分析，不虚构信息。 |
| risk | verification | 无 | 核验约束、信息缺口及可能的误判；如有上游结果必须据其完成判断，保留关键来源和限制。 |
| answer | generation | cost,risk | 完整完成原始任务，逐条核对所有交付要求。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;事实汇总与约束核验可以独立进行，再完整交付。&quot;,
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;cost&quot;,
        &quot;node_type&quot;: &quot;synthesis&quot;,
        &quot;parents&quot;: [],
        &quot;prompt_template&quot;: &quot;汇总全部原始事实，完成所需计算并列出来源；只交付本节点分析，不虚构信息。&quot;,
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;汇总全部原始事实，完成所需计算并列出来源；只交付本节点分析，不虚构信息。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;result&quot;: &quot;分析结果&quot;,
              &quot;evidence&quot;: &quot;原始材料来源标识与证据；没有证据时明确说明&quot;,
              &quot;assumptions&quot;: &quot;假设、不确定性与信息缺口；没有时明确说明&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;high&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;保留证据与假设，不虚构数据&quot;,
            &quot;覆盖本节点职责并明确限制&quot;
          ],
          &quot;covers&quot;: [
            0
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;risk&quot;,
        &quot;node_type&quot;: &quot;verification&quot;,
        &quot;parents&quot;: [],
        &quot;prompt_template&quot;: &quot;核验约束、信息缺口及可能的误判；如有上游结果必须据其完成判断，保留关键来源和限制。&quot;,
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;核验约束、信息缺口及可能的误判；如有上游结果必须据其完成判断，保留关键来源和限制。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;result&quot;: &quot;分析结果&quot;,
              &quot;evidence&quot;: &quot;原始材料来源标识与证据；没有证据时明确说明&quot;,
              &quot;assumptions&quot;: &quot;假设、不确定性与信息缺口；没有时明确说明&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;high&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;保留证据与假设，不虚构数据&quot;,
            &quot;覆盖本节点职责并明确限制&quot;
          ],
          &quot;covers&quot;: [
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;parents&quot;: [
          &quot;cost&quot;,
          &quot;risk&quot;
        ],
        &quot;prompt_template&quot;: &quot;完整完成原始任务，逐条核对所有交付要求。&quot;,
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;完整完成原始任务，逐条核对所有交付要求。&quot;,
          &quot;inputs&quot;: {
            &quot;cost&quot;: {
              &quot;fields&quot;: [
                &quot;result&quot;,
                &quot;evidence&quot;,
                &quot;assumptions&quot;
              ],
              &quot;reason&quot;: &quot;消费 cost 的分析、证据与假设，检查一致性后形成判断&quot;
            },
            &quot;risk&quot;: {
              &quot;fields&quot;: [
                &quot;result&quot;,
                &quot;evidence&quot;,
                &quot;assumptions&quot;
              ],
              &quot;reason&quot;: &quot;消费 risk 的分析、证据与假设，检查一致性后形成判断&quot;
            }
          },
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终建议与可追溯依据&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;high&quot;,
            &quot;input_budget_tokens&quot;: 65536,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;保留证据与假设，不虚构数据&quot;,
            &quot;覆盖本节点职责并明确限制&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ]
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: null,
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P032

没有结构合法的计划；仍需记录缺失 / 失败及其理由。

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: null,
  &quot;raw_plan_if_unparsed&quot;: &quot;{\n  \&quot;schema_version\&quot;: \&quot;text-task-plan-v2\&quot;,\n  \&quot;decomposition_reason\&quot;: \&quot;任务为100条工单的统计汇总与月报撰写。计算量大且需交叉核对，拆分为两个独立分组统计节点并行处理，再由汇总节点核对一致性并生成最终月报。拆分净收益在于并行降低时延、分组降低单节点计算错误风险；汇总节点需核对分组与总计相等，扇入开销可控。\&quot;,\n  \&quot;nodes\&quot;: [\n    {\n      \&quot;node_id\&quot;: \&quot;group_a_stats\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是维护工单月报的统计助手。请仅根据以下材料，统计甲组和乙组全部工单的数据。\\n\\n材料：\\n[原始任务中所有 test_workorders-L001 至 L100 的工单数据]\\n\\n要求：\\n1. 分别统计甲组、乙组的工单数、计划总分钟、实际总分钟、总偏差（实际减计划）。\\n2. 分别统计甲组、乙组的净偏差（所有工单偏差的代数和）和正超时量（仅正偏差工单的偏差之和）。\\n3. 分别统计甲组、乙组超计划工单数（偏差大于0的工单数）。\\n4. 保留每条工单的来源编号，不虚构任何原因、数据或评价。\\n5. 输出为 JSON，字段为：group_name、order_count、planned_total、actual_total、total_deviation、net_deviation、positive_overrun、overrun_count、source_ids。所有字段值为非空字符串，source_ids 用逗号分隔来源编号。\&quot;,\n      \&quot;parents\&quot;: [],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;统计甲组和乙组工单的工时、偏差、超时量及超计划工单数\&quot;,\n        \&quot;inputs\&quot;: {},\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;json\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;group_name\&quot;: \&quot;组名，甲组或乙组\&quot;,\n            \&quot;order_count\&quot;: \&quot;该组工单数量\&quot;,\n            \&quot;planned_total\&quot;: \&quot;该组计划总分钟\&quot;,\n            \&quot;actual_total\&quot;: \&quot;该组实际总分钟\&quot;,\n            \&quot;total_deviation\&quot;: \&quot;该组总偏差（实际减计划）\&quot;,\n            \&quot;net_deviation\&quot;: \&quot;该组净偏差（所有偏差代数和）\&quot;,\n            \&quot;positive_overrun\&quot;: \&quot;该组正超时量（仅正偏差之和）\&quot;,\n            \&quot;overrun_count\&quot;: \&quot;该组超计划工单数\&quot;,\n            \&quot;source_ids\&quot;: \&quot;该组所有工单来源编号，逗号分隔\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;medium\&quot;,\n          \&quot;input_budget_tokens\&quot;: 65536,\n          \&quot;expected_output_tokens\&quot;: 2000\n        },\n        \&quot;checks\&quot;: [\n          \&quot;甲组和乙组工单数之和为40\&quot;,\n          \&quot;各组计划总分钟与实际总分钟计算正确\&quot;,\n          \&quot;净偏差与正超时量区分清楚，不混淆\&quot;,\n          \&quot;超计划工单数统计正确\&quot;,\n          \&quot;来源编号完整保留\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    },\n    {\n      \&quot;node_id\&quot;: \&quot;group_b_stats\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是维护工单月报的统计助手。请仅根据以下材料，统计丙组和丁组全部工单的数据。\\n\\n材料：\\n[原始任务中所有 test_workorders-L001 至 L100 的工单数据]\\n\\n要求：\\n1. 分别统计丙组、丁组的工单数、计划总分钟、实际总分钟、总偏差（实际减计划）。\\n2. 分别统计丙组、丁组的净偏差（所有工单偏差的代数和）和正超时量（仅正偏差工单的偏差之和）。\\n3. 分别统计丙组、丁组超计划工单数（偏差大于0的工单数）。\\n4. 保留每条工单的来源编号，不虚构任何原因、数据或评价。\\n5. 输出为 JSON，字段为：group_name、order_count、planned_total、actual_total、total_deviation、net_deviation、positive_overrun、overrun_count、source_ids。所有字段值为非空字符串，source_ids 用逗号分隔来源编号。\&quot;,\n      \&quot;parents\&quot;: [],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;统计丙组和丁组工单的工时、偏差、超时量及超计划工单数\&quot;,\n        \&quot;inputs\&quot;: {},\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;json\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;group_name\&quot;: \&quot;组名，丙组或丁组\&quot;,\n            \&quot;order_count\&quot;: \&quot;该组工单数量\&quot;,\n            \&quot;planned_total\&quot;: \&quot;该组计划总分钟\&quot;,\n            \&quot;actual_total\&quot;: \&quot;该组实际总分钟\&quot;,\n            \&quot;total_deviation\&quot;: \&quot;该组总偏差（实际减计划）\&quot;,\n            \&quot;net_deviation\&quot;: \&quot;该组净偏差（所有偏差代数和）\&quot;,\n            \&quot;positive_overrun\&quot;: \&quot;该组正超时量（仅正偏差之和）\&quot;,\n            \&quot;overrun_count\&quot;: \&quot;该组超计划工单数\&quot;,\n            \&quot;source_ids\&quot;: \&quot;该组所有工单来源编号，逗号分隔\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;medium\&quot;,\n          \&quot;input_budget_tokens\&quot;: 65536,\n          \&quot;expected_output_tokens\&quot;: 2000\n        },\n        \&quot;checks\&quot;: [\n          \&quot;丙组和丁组工单数之和为60\&quot;,\n          \&quot;各组计划总分钟与实际总分钟计算正确\&quot;,\n          \&quot;净偏差与正超时量区分清楚，不混淆\&quot;,\n          \&quot;超计划工单数统计正确\&quot;,\n          \&quot;来源编号完整保留\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    },\n    {\n      \&quot;node_id\&quot;: \&quot;answer\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是维护工单月报的撰写者。请根据以下分组统计结果，综合全表形成完整月报。\\n\\n分组统计结果：\\n甲组和乙组统计：{group_a_stats}\\n丙组和丁组统计：{group_b_stats}\\n\\n原始任务要求：\\n综合全表形成完整月报，核对分组汇总与总计相等，分别报告净偏差及正超时量，不混淆两者。\\n\\n材料约束：\\n- 每条工单给出计划分钟与实际分钟；正偏差为实际减计划，小于零表示提前。\\n- 最终报告必须同时包含各组总工时、全部工单的总偏差、超计划工单数及限制。\\n- 材料没有故障原因或人员绩效证据，不能因耗时推断责任；不能只复制一条分支摘要。\\n- 保留来源编号，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。\\n\\n撰写要求：\\n1. 核对甲、乙、丙、丁四组工单数之和为100，计划总分钟之和与实际总分钟之和分别等于全部工单总计，总偏差等于各组总偏差之和。\\n2. 分别报告各组总工时（计划总分钟、实际总分钟）。\\n3. 报告全部工单的总偏差（实际总分钟减计划总分钟）。\\n4. 报告全部工单的净偏差（所有偏差代数和）和正超时量（仅正偏差之和），明确区分两者。\\n5. 报告超计划工单数（偏差大于0的工单数）及限制（材料无故障原因或人员绩效证据，不能因耗时推断责任）。\\n6. 保留来源编号，不虚构任何原因、数据或评价。\\n7. 直接输出月报正文，不封装为 JSON。\&quot;,\n      \&quot;parents\&quot;: [\&quot;group_a_stats\&quot;, \&quot;group_b_stats\&quot;],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;综合分组统计结果，核对一致性并生成完整维护工单月报\&quot;,\n        \&quot;inputs\&quot;: {\n          \&quot;group_a_stats\&quot;: {\n            \&quot;fields\&quot;: [\&quot;group_name\&quot;, \&quot;order_count\&quot;, \&quot;planned_total\&quot;, \&quot;actual_total\&quot;, \&quot;total_deviation\&quot;, \&quot;net_deviation\&quot;, \&quot;positive_overrun\&quot;, \&quot;overrun_count\&quot;, \&quot;source_ids\&quot;],\n            \&quot;reason\&quot;: \&quot;需要甲组和乙组的统计结果来汇总各组总工时、总偏差、净偏差、正超时量和超计划工单数\&quot;\n          },\n          \&quot;group_b_stats\&quot;: {\n            \&quot;fields\&quot;: [\&quot;group_name\&quot;, \&quot;order_count\&quot;, \&quot;planned_total\&quot;, \&quot;actual_total\&quot;, \&quot;total_deviation\&quot;, \&quot;net_deviation\&quot;, \&quot;positive_overrun\&quot;, \&quot;overrun_count\&quot;, \&quot;source_ids\&quot;],\n            \&quot;reason\&quot;: \&quot;需要丙组和丁组的统计结果来汇总各组总工时、总偏差、净偏差、正超时量和超计划工单数\&quot;\n          }\n        },\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;text\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;text\&quot;: \&quot;完整维护工单月报正文，包含各组总工时、全部工单总偏差、净偏差与正超时量区分、超计划工单数及限制、来源编号保留\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;medium\&quot;,\n          \&quot;input_budget_tokens\&quot;: 131072,\n          \&quot;expected_output_tokens\&quot;: 4000\n        },\n        \&quot;checks\&quot;: [\n          \&quot;月报包含甲、乙、丙、丁四组各自的总工时\&quot;,\n          \&quot;月报包含全部工单的总偏差\&quot;,\n          \&quot;月报分别报告净偏差和正超时量，不混淆两者\&quot;,\n          \&quot;月报包含超计划工单数及限制说明\&quot;,\n          \&quot;分组汇总与总计核对相等\&quot;,\n          \&quot;保留来源编号，不虚构原因、数据或评价\&quot;,\n          \&quot;区分已知事实、建议和未知事项\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    }\n  ],\n  \&quot;final_node_id\&quot;: \&quot;answer\&quot;,\n  \&quot;acceptance_criteria\&quot;: [\n    \&quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。\&quot;,\n    \&quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。\&quot;\n  ]\n}&quot;,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 2288
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

## 题目 7

<details><summary>查看原始题目与材料</summary>
<pre>这是独立编写的虚构封闭场景「多校区用能记录分析」，不代表真实机构或法律规则。只用以下材料，不联网或执行工具。
P1：各行是独立单元的基准用量和本期用量，单位千瓦时。P2：按校区汇总，再报告整体净变化。P3：各校区可独立分析；总体减少不保证每个校区减少，材料没有气温、面积或人数。P4：不能根据用量变化直接认定措施有效，也不能按人均或面积归一化。
来源 test_energy-L001：第1单元，乙校区，基准 81 千瓦时，本期 75 千瓦时；未包含人数、面积与气温。
来源 test_energy-L002：第2单元，丙校区，基准 82 千瓦时，本期 80 千瓦时；未包含人数、面积与气温。
来源 test_energy-L003：第3单元，丁校区，基准 83 千瓦时，本期 85 千瓦时；未包含人数、面积与气温。
来源 test_energy-L004：第4单元，甲校区，基准 84 千瓦时，本期 90 千瓦时；未包含人数、面积与气温。
来源 test_energy-L005：第5单元，乙校区，基准 85 千瓦时，本期 95 千瓦时；未包含人数、面积与气温。
来源 test_energy-L006：第6单元，丙校区，基准 86 千瓦时，本期 100 千瓦时；未包含人数、面积与气温。
来源 test_energy-L007：第7单元，丁校区，基准 87 千瓦时，本期 105 千瓦时；未包含人数、面积与气温。
来源 test_energy-L008：第8单元，甲校区，基准 88 千瓦时，本期 110 千瓦时；未包含人数、面积与气温。
来源 test_energy-L009：第9单元，乙校区，基准 89 千瓦时，本期 115 千瓦时；未包含人数、面积与气温。
来源 test_energy-L010：第10单元，丙校区，基准 90 千瓦时，本期 73 千瓦时；未包含人数、面积与气温。
来源 test_energy-L011：第11单元，丁校区，基准 91 千瓦时，本期 78 千瓦时；未包含人数、面积与气温。
来源 test_energy-L012：第12单元，甲校区，基准 92 千瓦时，本期 83 千瓦时；未包含人数、面积与气温。
来源 test_energy-L013：第13单元，乙校区，基准 93 千瓦时，本期 88 千瓦时；未包含人数、面积与气温。
来源 test_energy-L014：第14单元，丙校区，基准 94 千瓦时，本期 93 千瓦时；未包含人数、面积与气温。
来源 test_energy-L015：第15单元，丁校区，基准 95 千瓦时，本期 98 千瓦时；未包含人数、面积与气温。
来源 test_energy-L016：第16单元，甲校区，基准 96 千瓦时，本期 103 千瓦时；未包含人数、面积与气温。
来源 test_energy-L017：第17单元，乙校区，基准 97 千瓦时，本期 108 千瓦时；未包含人数、面积与气温。
来源 test_energy-L018：第18单元，丙校区，基准 98 千瓦时，本期 113 千瓦时；未包含人数、面积与气温。
来源 test_energy-L019：第19单元，丁校区，基准 99 千瓦时，本期 71 千瓦时；未包含人数、面积与气温。
来源 test_energy-L020：第20单元，甲校区，基准 100 千瓦时，本期 76 千瓦时；未包含人数、面积与气温。
来源 test_energy-L021：第21单元，乙校区，基准 101 千瓦时，本期 81 千瓦时；未包含人数、面积与气温。
来源 test_energy-L022：第22单元，丙校区，基准 102 千瓦时，本期 86 千瓦时；未包含人数、面积与气温。
来源 test_energy-L023：第23单元，丁校区，基准 103 千瓦时，本期 91 千瓦时；未包含人数、面积与气温。
来源 test_energy-L024：第24单元，甲校区，基准 104 千瓦时，本期 96 千瓦时；未包含人数、面积与气温。
来源 test_energy-L025：第25单元，乙校区，基准 105 千瓦时，本期 101 千瓦时；未包含人数、面积与气温。
来源 test_energy-L026：第26单元，丙校区，基准 106 千瓦时，本期 106 千瓦时；未包含人数、面积与气温。
来源 test_energy-L027：第27单元，丁校区，基准 107 千瓦时，本期 111 千瓦时；未包含人数、面积与气温。
来源 test_energy-L028：第28单元，甲校区，基准 108 千瓦时，本期 116 千瓦时；未包含人数、面积与气温。
来源 test_energy-L029：第29单元，乙校区，基准 109 千瓦时，本期 74 千瓦时；未包含人数、面积与气温。
来源 test_energy-L030：第30单元，丙校区，基准 110 千瓦时，本期 79 千瓦时；未包含人数、面积与气温。
来源 test_energy-L031：第31单元，丁校区，基准 80 千瓦时，本期 84 千瓦时；未包含人数、面积与气温。
来源 test_energy-L032：第32单元，甲校区，基准 81 千瓦时，本期 89 千瓦时；未包含人数、面积与气温。
来源 test_energy-L033：第33单元，乙校区，基准 82 千瓦时，本期 94 千瓦时；未包含人数、面积与气温。
来源 test_energy-L034：第34单元，丙校区，基准 83 千瓦时，本期 99 千瓦时；未包含人数、面积与气温。
来源 test_energy-L035：第35单元，丁校区，基准 84 千瓦时，本期 104 千瓦时；未包含人数、面积与气温。
来源 test_energy-L036：第36单元，甲校区，基准 85 千瓦时，本期 109 千瓦时；未包含人数、面积与气温。
来源 test_energy-L037：第37单元，乙校区，基准 86 千瓦时，本期 114 千瓦时；未包含人数、面积与气温。
来源 test_energy-L038：第38单元，丙校区，基准 87 千瓦时，本期 72 千瓦时；未包含人数、面积与气温。
来源 test_energy-L039：第39单元，丁校区，基准 88 千瓦时，本期 77 千瓦时；未包含人数、面积与气温。
来源 test_energy-L040：第40单元，甲校区，基准 89 千瓦时，本期 82 千瓦时；未包含人数、面积与气温。
来源 test_energy-L041：第41单元，乙校区，基准 90 千瓦时，本期 87 千瓦时；未包含人数、面积与气温。
来源 test_energy-L042：第42单元，丙校区，基准 91 千瓦时，本期 92 千瓦时；未包含人数、面积与气温。
来源 test_energy-L043：第43单元，丁校区，基准 92 千瓦时，本期 97 千瓦时；未包含人数、面积与气温。
来源 test_energy-L044：第44单元，甲校区，基准 93 千瓦时，本期 102 千瓦时；未包含人数、面积与气温。
来源 test_energy-L045：第45单元，乙校区，基准 94 千瓦时，本期 107 千瓦时；未包含人数、面积与气温。
来源 test_energy-L046：第46单元，丙校区，基准 95 千瓦时，本期 112 千瓦时；未包含人数、面积与气温。
来源 test_energy-L047：第47单元，丁校区，基准 96 千瓦时，本期 70 千瓦时；未包含人数、面积与气温。
来源 test_energy-L048：第48单元，甲校区，基准 97 千瓦时，本期 75 千瓦时；未包含人数、面积与气温。
来源 test_energy-L049：第49单元，乙校区，基准 98 千瓦时，本期 80 千瓦时；未包含人数、面积与气温。
来源 test_energy-L050：第50单元，丙校区，基准 99 千瓦时，本期 85 千瓦时；未包含人数、面积与气温。
来源 test_energy-L051：第51单元，丁校区，基准 100 千瓦时，本期 90 千瓦时；未包含人数、面积与气温。
来源 test_energy-L052：第52单元，甲校区，基准 101 千瓦时，本期 95 千瓦时；未包含人数、面积与气温。
来源 test_energy-L053：第53单元，乙校区，基准 102 千瓦时，本期 100 千瓦时；未包含人数、面积与气温。
来源 test_energy-L054：第54单元，丙校区，基准 103 千瓦时，本期 105 千瓦时；未包含人数、面积与气温。
来源 test_energy-L055：第55单元，丁校区，基准 104 千瓦时，本期 110 千瓦时；未包含人数、面积与气温。
来源 test_energy-L056：第56单元，甲校区，基准 105 千瓦时，本期 115 千瓦时；未包含人数、面积与气温。
来源 test_energy-L057：第57单元，乙校区，基准 106 千瓦时，本期 73 千瓦时；未包含人数、面积与气温。
来源 test_energy-L058：第58单元，丙校区，基准 107 千瓦时，本期 78 千瓦时；未包含人数、面积与气温。
来源 test_energy-L059：第59单元，丁校区，基准 108 千瓦时，本期 83 千瓦时；未包含人数、面积与气温。
来源 test_energy-L060：第60单元，甲校区，基准 109 千瓦时，本期 88 千瓦时；未包含人数、面积与气温。
来源 test_energy-L061：第61单元，乙校区，基准 110 千瓦时，本期 93 千瓦时；未包含人数、面积与气温。
来源 test_energy-L062：第62单元，丙校区，基准 80 千瓦时，本期 98 千瓦时；未包含人数、面积与气温。
来源 test_energy-L063：第63单元，丁校区，基准 81 千瓦时，本期 103 千瓦时；未包含人数、面积与气温。
来源 test_energy-L064：第64单元，甲校区，基准 82 千瓦时，本期 108 千瓦时；未包含人数、面积与气温。
来源 test_energy-L065：第65单元，乙校区，基准 83 千瓦时，本期 113 千瓦时；未包含人数、面积与气温。
来源 test_energy-L066：第66单元，丙校区，基准 84 千瓦时，本期 71 千瓦时；未包含人数、面积与气温。
来源 test_energy-L067：第67单元，丁校区，基准 85 千瓦时，本期 76 千瓦时；未包含人数、面积与气温。
来源 test_energy-L068：第68单元，甲校区，基准 86 千瓦时，本期 81 千瓦时；未包含人数、面积与气温。
来源 test_energy-L069：第69单元，乙校区，基准 87 千瓦时，本期 86 千瓦时；未包含人数、面积与气温。
来源 test_energy-L070：第70单元，丙校区，基准 88 千瓦时，本期 91 千瓦时；未包含人数、面积与气温。
来源 test_energy-L071：第71单元，丁校区，基准 89 千瓦时，本期 96 千瓦时；未包含人数、面积与气温。
来源 test_energy-L072：第72单元，甲校区，基准 90 千瓦时，本期 101 千瓦时；未包含人数、面积与气温。
来源 test_energy-L073：第73单元，乙校区，基准 91 千瓦时，本期 106 千瓦时；未包含人数、面积与气温。
来源 test_energy-L074：第74单元，丙校区，基准 92 千瓦时，本期 111 千瓦时；未包含人数、面积与气温。
来源 test_energy-L075：第75单元，丁校区，基准 93 千瓦时，本期 116 千瓦时；未包含人数、面积与气温。
来源 test_energy-L076：第76单元，甲校区，基准 94 千瓦时，本期 74 千瓦时；未包含人数、面积与气温。
来源 test_energy-L077：第77单元，乙校区，基准 95 千瓦时，本期 79 千瓦时；未包含人数、面积与气温。
来源 test_energy-L078：第78单元，丙校区，基准 96 千瓦时，本期 84 千瓦时；未包含人数、面积与气温。
来源 test_energy-L079：第79单元，丁校区，基准 97 千瓦时，本期 89 千瓦时；未包含人数、面积与气温。
来源 test_energy-L080：第80单元，甲校区，基准 98 千瓦时，本期 94 千瓦时；未包含人数、面积与气温。
来源 test_energy-L081：第81单元，乙校区，基准 99 千瓦时，本期 99 千瓦时；未包含人数、面积与气温。
来源 test_energy-L082：第82单元，丙校区，基准 100 千瓦时，本期 104 千瓦时；未包含人数、面积与气温。
来源 test_energy-L083：第83单元，丁校区，基准 101 千瓦时，本期 109 千瓦时；未包含人数、面积与气温。
来源 test_energy-L084：第84单元，甲校区，基准 102 千瓦时，本期 114 千瓦时；未包含人数、面积与气温。
来源 test_energy-L085：第85单元，乙校区，基准 103 千瓦时，本期 72 千瓦时；未包含人数、面积与气温。
来源 test_energy-L086：第86单元，丙校区，基准 104 千瓦时，本期 77 千瓦时；未包含人数、面积与气温。
来源 test_energy-L087：第87单元，丁校区，基准 105 千瓦时，本期 82 千瓦时；未包含人数、面积与气温。
来源 test_energy-L088：第88单元，甲校区，基准 106 千瓦时，本期 87 千瓦时；未包含人数、面积与气温。
来源 test_energy-L089：第89单元，乙校区，基准 107 千瓦时，本期 92 千瓦时；未包含人数、面积与气温。
来源 test_energy-L090：第90单元，丙校区，基准 108 千瓦时，本期 97 千瓦时；未包含人数、面积与气温。
来源 test_energy-L091：第91单元，丁校区，基准 109 千瓦时，本期 102 千瓦时；未包含人数、面积与气温。
来源 test_energy-L092：第92单元，甲校区，基准 110 千瓦时，本期 107 千瓦时；未包含人数、面积与气温。
来源 test_energy-L093：第93单元，乙校区，基准 80 千瓦时，本期 112 千瓦时；未包含人数、面积与气温。
来源 test_energy-L094：第94单元，丙校区，基准 81 千瓦时，本期 70 千瓦时；未包含人数、面积与气温。
来源 test_energy-L095：第95单元，丁校区，基准 82 千瓦时，本期 75 千瓦时；未包含人数、面积与气温。
来源 test_energy-L096：第96单元，甲校区，基准 83 千瓦时，本期 80 千瓦时；未包含人数、面积与气温。
来源 test_energy-L097：第97单元，乙校区，基准 84 千瓦时，本期 85 千瓦时；未包含人数、面积与气温。
来源 test_energy-L098：第98单元，丙校区，基准 85 千瓦时，本期 90 千瓦时；未包含人数、面积与气温。
来源 test_energy-L099：第99单元，丁校区，基准 86 千瓦时，本期 95 千瓦时；未包含人数、面积与气温。
来源 test_energy-L100：第100单元，甲校区，基准 87 千瓦时，本期 100 千瓦时；未包含人数、面积与气温。
交付要求：并行核验各校区记录，汇总整体变化、增加单元数和减少单元数，给出有限结论与补充数据需求。</pre>
</details>

**原始验收：** 完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。；遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。

<details><summary>查看冻结参考（长材料已独立重算）</summary>
<pre>{&quot;丁&quot;: {&quot;记录数&quot;: 25, &quot;第一列总和&quot;: 2345, &quot;第二列总和&quot;: 2297, &quot;第一列减第二列&quot;: 48, &quot;正缺口&quot;: 179, &quot;第二列较大记录数&quot;: 13, &quot;第一列较大记录数&quot;: 12, &quot;正超额&quot;: 131}, &quot;丙&quot;: {&quot;记录数&quot;: 25, &quot;第一列总和&quot;: 2351, &quot;第二列总和&quot;: 2266, &quot;第一列减第二列&quot;: 85, &quot;正缺口&quot;: 199, &quot;第二列较大记录数&quot;: 11, &quot;第一列较大记录数&quot;: 13, &quot;正超额&quot;: 114}, &quot;乙&quot;: {&quot;记录数&quot;: 25, &quot;第一列总和&quot;: 2357, &quot;第二列总和&quot;: 2329, &quot;第一列减第二列&quot;: 28, &quot;正缺口&quot;: 206, &quot;第二列较大记录数&quot;: 10, &quot;第一列较大记录数&quot;: 14, &quot;正超额&quot;: 178}, &quot;甲&quot;: {&quot;记录数&quot;: 25, &quot;第一列总和&quot;: 2370, &quot;第二列总和&quot;: 2375, &quot;第一列减第二列&quot;: -5, &quot;正缺口&quot;: 151, &quot;第二列较大记录数&quot;: 12, &quot;第一列较大记录数&quot;: 13, &quot;正超额&quot;: 156}}</pre>
</details>

### P020

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| cost | synthesis | 无 | 汇总全部原始事实，完成所需计算并列出来源；只交付本节点分析，不虚构信息。 |
| risk | verification | 无 | 核验约束、信息缺口及可能的误判；如有上游结果必须据其完成判断，保留关键来源和限制。 |
| answer | generation | cost,risk | 完整完成原始任务，逐条核对所有交付要求。 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;事实汇总与约束核验可以独立进行，再完整交付。&quot;,
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;cost&quot;,
        &quot;node_type&quot;: &quot;synthesis&quot;,
        &quot;parents&quot;: [],
        &quot;prompt_template&quot;: &quot;汇总全部原始事实，完成所需计算并列出来源；只交付本节点分析，不虚构信息。&quot;,
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;汇总全部原始事实，完成所需计算并列出来源；只交付本节点分析，不虚构信息。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;result&quot;: &quot;分析结果&quot;,
              &quot;evidence&quot;: &quot;原始材料来源标识与证据；没有证据时明确说明&quot;,
              &quot;assumptions&quot;: &quot;假设、不确定性与信息缺口；没有时明确说明&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;high&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;保留证据与假设，不虚构数据&quot;,
            &quot;覆盖本节点职责并明确限制&quot;
          ],
          &quot;covers&quot;: [
            0
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;risk&quot;,
        &quot;node_type&quot;: &quot;verification&quot;,
        &quot;parents&quot;: [],
        &quot;prompt_template&quot;: &quot;核验约束、信息缺口及可能的误判；如有上游结果必须据其完成判断，保留关键来源和限制。&quot;,
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;核验约束、信息缺口及可能的误判；如有上游结果必须据其完成判断，保留关键来源和限制。&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;result&quot;: &quot;分析结果&quot;,
              &quot;evidence&quot;: &quot;原始材料来源标识与证据；没有证据时明确说明&quot;,
              &quot;assumptions&quot;: &quot;假设、不确定性与信息缺口；没有时明确说明&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;high&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;保留证据与假设，不虚构数据&quot;,
            &quot;覆盖本节点职责并明确限制&quot;
          ],
          &quot;covers&quot;: [
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;parents&quot;: [
          &quot;cost&quot;,
          &quot;risk&quot;
        ],
        &quot;prompt_template&quot;: &quot;完整完成原始任务，逐条核对所有交付要求。&quot;,
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;完整完成原始任务，逐条核对所有交付要求。&quot;,
          &quot;inputs&quot;: {
            &quot;cost&quot;: {
              &quot;fields&quot;: [
                &quot;result&quot;,
                &quot;evidence&quot;,
                &quot;assumptions&quot;
              ],
              &quot;reason&quot;: &quot;消费 cost 的分析、证据与假设，检查一致性后形成判断&quot;
            },
            &quot;risk&quot;: {
              &quot;fields&quot;: [
                &quot;result&quot;,
                &quot;evidence&quot;,
                &quot;assumptions&quot;
              ],
              &quot;reason&quot;: &quot;消费 risk 的分析、证据与假设，检查一致性后形成判断&quot;
            }
          },
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终建议与可追溯依据&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;high&quot;,
            &quot;input_budget_tokens&quot;: 65536,
            &quot;expected_output_tokens&quot;: 1000
          },
          &quot;checks&quot;: [
            &quot;保留证据与假设，不虚构数据&quot;,
            &quot;覆盖本节点职责并明确限制&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ]
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: null,
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P023

没有结构合法的计划；仍需记录缺失 / 失败及其理由。

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: null,
  &quot;raw_plan_if_unparsed&quot;: &quot;{\n  \&quot;schema_version\&quot;: \&quot;text-task-plan-v2\&quot;,\n  \&quot;decomposition_reason\&quot;: \&quot;任务要求按校区并行核验记录并汇总整体变化、增加单元数和减少单元数，四个校区可独立分析，存在并行机会；但最终交付必须统一汇总并核对冲突与遗漏，因此拆分为四个校区核验节点和一个汇总生成节点。拆分净收益在于并行核验可降低单节点计算负担并提高准确性，汇总节点负责跨校区一致性核对与最终交付，交接开销可控。\&quot;,\n  \&quot;nodes\&quot;: [\n    {\n      \&quot;node_id\&quot;: \&quot;verify_jia\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是数据核验员。仅使用以下材料，不联网或执行工具。材料是虚构封闭场景「多校区用能记录分析」，不代表真实机构或法律规则。\\n\\n任务背景：各行是独立单元的基准用量和本期用量，单位千瓦时。按校区汇总，再报告整体净变化。各校区可独立分析；总体减少不保证每个校区减少，材料没有气温、面积或人数。不能根据用量变化直接认定措施有效，也不能按人均或面积归一化。\\n\\n请只核验甲校区（第4、8、12、16、20、24、28、32、36、40、44、48、52、56、60、64、68、72、76、80、84、88、92、96、100单元）的记录。\\n\\n材料：\\n来源 test_energy-L004：第4单元，甲校区，基准 84 千瓦时，本期 90 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L008：第8单元，甲校区，基准 88 千瓦时，本期 110 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L012：第12单元，甲校区，基准 92 千瓦时，本期 83 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L016：第16单元，甲校区，基准 96 千瓦时，本期 103 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L020：第20单元，甲校区，基准 100 千瓦时，本期 76 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L024：第24单元，甲校区，基准 104 千瓦时，本期 96 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L028：第28单元，甲校区，基准 108 千瓦时，本期 116 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L032：第32单元，甲校区，基准 81 千瓦时，本期 89 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L036：第36单元，甲校区，基准 85 千瓦时，本期 109 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L040：第40单元，甲校区，基准 89 千瓦时，本期 82 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L044：第44单元，甲校区，基准 93 千瓦时，本期 102 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L048：第48单元，甲校区，基准 97 千瓦时，本期 75 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L052：第52单元，甲校区，基准 101 千瓦时，本期 95 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L056：第56单元，甲校区，基准 105 千瓦时，本期 115 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L060：第60单元，甲校区，基准 109 千瓦时，本期 88 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L064：第64单元，甲校区，基准 82 千瓦时，本期 108 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L068：第68单元，甲校区，基准 86 千瓦时，本期 81 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L072：第72单元，甲校区，基准 90 千瓦时，本期 101 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L076：第76单元，甲校区，基准 94 千瓦时，本期 74 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L080：第80单元，甲校区，基准 98 千瓦时，本期 94 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L084：第84单元，甲校区，基准 102 千瓦时，本期 114 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L088：第88单元，甲校区，基准 106 千瓦时，本期 87 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L092：第92单元，甲校区，基准 110 千瓦时，本期 107 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L096：第96单元，甲校区，基准 83 千瓦时，本期 80 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L100：第100单元，甲校区，基准 87 千瓦时，本期 100 千瓦时；未包含人数、面积与气温。\\n\\n请完成：\\n1. 逐条核验甲校区记录，确认单元编号、校区、基准用量、本期用量与来源编号一致。\\n2. 计算甲校区基准用量合计、本期用量合计、净变化（本期合计减基准合计）。\\n3. 统计甲校区增加单元数（本期大于基准）、减少单元数（本期小于基准）、持平单元数（本期等于基准）。\\n4. 列出甲校区中增加、减少、持平的来源编号清单。\\n5. 指出任何记录异常、缺失或不确定事项；不得虚构原因、数据或已执行的操作。\\n\\n输出 JSON，字段如下：\\n- campus：校区名称，填「甲校区」\\n- unit_count：该校区单元数\\n- baseline_total：基准用量合计\\n- current_total：本期用量合计\\n- net_change：净变化，带正负号\\n- increase_count：增加单元数\\n- decrease_count：减少单元数\\n- unchanged_count：持平单元数\\n- increase_sources：增加单元来源编号清单，用顿号分隔\\n- decrease_sources：减少单元来源编号清单，用顿号分隔\\n- unchanged_sources：持平单元来源编号清单，用顿号分隔；如无填「无」\\n- notes：核验说明、异常或不确定事项；如无填「无」\&quot;,\n      \&quot;parents\&quot;: [],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;核验甲校区全部记录并计算该校区基准合计、本期合计、净变化及增减持平单元统计\&quot;,\n        \&quot;inputs\&quot;: {},\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;json\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;campus\&quot;: \&quot;校区名称\&quot;,\n            \&quot;unit_count\&quot;: \&quot;该校区单元数\&quot;,\n            \&quot;baseline_total\&quot;: \&quot;基准用量合计\&quot;,\n            \&quot;current_total\&quot;: \&quot;本期用量合计\&quot;,\n            \&quot;net_change\&quot;: \&quot;净变化，带正负号\&quot;,\n            \&quot;increase_count\&quot;: \&quot;增加单元数\&quot;,\n            \&quot;decrease_count\&quot;: \&quot;减少单元数\&quot;,\n            \&quot;unchanged_count\&quot;: \&quot;持平单元数\&quot;,\n            \&quot;increase_sources\&quot;: \&quot;增加单元来源编号清单\&quot;,\n            \&quot;decrease_sources\&quot;: \&quot;减少单元来源编号清单\&quot;,\n            \&quot;unchanged_sources\&quot;: \&quot;持平单元来源编号清单\&quot;,\n            \&quot;notes\&quot;: \&quot;核验说明、异常或不确定事项\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;low\&quot;,\n          \&quot;input_budget_tokens\&quot;: 32768,\n          \&quot;expected_output_tokens\&quot;: 1200\n        },\n        \&quot;checks\&quot;: [\n          \&quot;甲校区单元数、基准合计、本期合计和净变化计算正确\&quot;,\n          \&quot;增加、减少、持平单元数及来源编号清单与材料一致\&quot;,\n          \&quot;保留来源编号，不虚构原因、数据或已执行操作\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    },\n    {\n      \&quot;node_id\&quot;: \&quot;verify_yi\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是数据核验员。仅使用以下材料，不联网或执行工具。材料是虚构封闭场景「多校区用能记录分析」，不代表真实机构或法律规则。\\n\\n任务背景：各行是独立单元的基准用量和本期用量，单位千瓦时。按校区汇总，再报告整体净变化。各校区可独立分析；总体减少不保证每个校区减少，材料没有气温、面积或人数。不能根据用量变化直接认定措施有效，也不能按人均或面积归一化。\\n\\n请只核验乙校区（第1、5、9、13、17、21、25、29、33、37、41、45、49、53、57、61、65、69、73、77、81、85、89、93、97单元）的记录。\\n\\n材料：\\n来源 test_energy-L001：第1单元，乙校区，基准 81 千瓦时，本期 75 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L005：第5单元，乙校区，基准 85 千瓦时，本期 95 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L009：第9单元，乙校区，基准 89 千瓦时，本期 115 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L013：第13单元，乙校区，基准 93 千瓦时，本期 88 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L017：第17单元，乙校区，基准 97 千瓦时，本期 108 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L021：第21单元，乙校区，基准 101 千瓦时，本期 81 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L025：第25单元，乙校区，基准 105 千瓦时，本期 101 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L029：第29单元，乙校区，基准 109 千瓦时，本期 74 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L033：第33单元，乙校区，基准 82 千瓦时，本期 94 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L037：第37单元，乙校区，基准 86 千瓦时，本期 114 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L041：第41单元，乙校区，基准 90 千瓦时，本期 87 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L045：第45单元，乙校区，基准 94 千瓦时，本期 107 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L049：第49单元，乙校区，基准 98 千瓦时，本期 80 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L053：第53单元，乙校区，基准 102 千瓦时，本期 100 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L057：第57单元，乙校区，基准 106 千瓦时，本期 73 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L061：第61单元，乙校区，基准 110 千瓦时，本期 93 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L065：第65单元，乙校区，基准 83 千瓦时，本期 113 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L069：第69单元，乙校区，基准 87 千瓦时，本期 86 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L073：第73单元，乙校区，基准 91 千瓦时，本期 106 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L077：第77单元，乙校区，基准 95 千瓦时，本期 79 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L081：第81单元，乙校区，基准 99 千瓦时，本期 99 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L085：第85单元，乙校区，基准 103 千瓦时，本期 72 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L089：第89单元，乙校区，基准 107 千瓦时，本期 92 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L093：第93单元，乙校区，基准 80 千瓦时，本期 112 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L097：第97单元，乙校区，基准 84 千瓦时，本期 85 千瓦时；未包含人数、面积与气温。\\n\\n请完成：\\n1. 逐条核验乙校区记录，确认单元编号、校区、基准用量、本期用量与来源编号一致。\\n2. 计算乙校区基准用量合计、本期用量合计、净变化（本期合计减基准合计）。\\n3. 统计乙校区增加单元数（本期大于基准）、减少单元数（本期小于基准）、持平单元数（本期等于基准）。\\n4. 列出乙校区中增加、减少、持平的来源编号清单。\\n5. 指出任何记录异常、缺失或不确定事项；不得虚构原因、数据或已执行的操作。\\n\\n输出 JSON，字段如下：\\n- campus：校区名称，填「乙校区」\\n- unit_count：该校区单元数\\n- baseline_total：基准用量合计\\n- current_total：本期用量合计\\n- net_change：净变化，带正负号\\n- increase_count：增加单元数\\n- decrease_count：减少单元数\\n- unchanged_count：持平单元数\\n- increase_sources：增加单元来源编号清单，用顿号分隔\\n- decrease_sources：减少单元来源编号清单，用顿号分隔\\n- unchanged_sources：持平单元来源编号清单，用顿号分隔；如无填「无」\\n- notes：核验说明、异常或不确定事项；如无填「无」\&quot;,\n      \&quot;parents\&quot;: [],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;核验乙校区全部记录并计算该校区基准合计、本期合计、净变化及增减持平单元统计\&quot;,\n        \&quot;inputs\&quot;: {},\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;json\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;campus\&quot;: \&quot;校区名称\&quot;,\n            \&quot;unit_count\&quot;: \&quot;该校区单元数\&quot;,\n            \&quot;baseline_total\&quot;: \&quot;基准用量合计\&quot;,\n            \&quot;current_total\&quot;: \&quot;本期用量合计\&quot;,\n            \&quot;net_change\&quot;: \&quot;净变化，带正负号\&quot;,\n            \&quot;increase_count\&quot;: \&quot;增加单元数\&quot;,\n            \&quot;decrease_count\&quot;: \&quot;减少单元数\&quot;,\n            \&quot;unchanged_count\&quot;: \&quot;持平单元数\&quot;,\n            \&quot;increase_sources\&quot;: \&quot;增加单元来源编号清单\&quot;,\n            \&quot;decrease_sources\&quot;: \&quot;减少单元来源编号清单\&quot;,\n            \&quot;unchanged_sources\&quot;: \&quot;持平单元来源编号清单\&quot;,\n            \&quot;notes\&quot;: \&quot;核验说明、异常或不确定事项\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;low\&quot;,\n          \&quot;input_budget_tokens\&quot;: 32768,\n          \&quot;expected_output_tokens\&quot;: 1200\n        },\n        \&quot;checks\&quot;: [\n          \&quot;乙校区单元数、基准合计、本期合计和净变化计算正确\&quot;,\n          \&quot;增加、减少、持平单元数及来源编号清单与材料一致\&quot;,\n          \&quot;保留来源编号，不虚构原因、数据或已执行操作\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    },\n    {\n      \&quot;node_id\&quot;: \&quot;verify_bing\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是数据核验员。仅使用以下材料，不联网或执行工具。材料是虚构封闭场景「多校区用能记录分析」，不代表真实机构或法律规则。\\n\\n任务背景：各行是独立单元的基准用量和本期用量，单位千瓦时。按校区汇总，再报告整体净变化。各校区可独立分析；总体减少不保证每个校区减少，材料没有气温、面积或人数。不能根据用量变化直接认定措施有效，也不能按人均或面积归一化。\\n\\n请只核验丙校区（第2、6、10、14、18、22、26、30、34、38、42、46、50、54、58、62、66、70、74、78、82、86、90、94、98单元）的记录。\\n\\n材料：\\n来源 test_energy-L002：第2单元，丙校区，基准 82 千瓦时，本期 80 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L006：第6单元，丙校区，基准 86 千瓦时，本期 100 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L010：第10单元，丙校区，基准 90 千瓦时，本期 73 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L014：第14单元，丙校区，基准 94 千瓦时，本期 93 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L018：第18单元，丙校区，基准 98 千瓦时，本期 113 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L022：第22单元，丙校区，基准 102 千瓦时，本期 86 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L026：第26单元，丙校区，基准 106 千瓦时，本期 106 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L030：第30单元，丙校区，基准 110 千瓦时，本期 79 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L034：第34单元，丙校区，基准 83 千瓦时，本期 99 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L038：第38单元，丙校区，基准 87 千瓦时，本期 72 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L042：第42单元，丙校区，基准 91 千瓦时，本期 92 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L046：第46单元，丙校区，基准 95 千瓦时，本期 112 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L050：第50单元，丙校区，基准 99 千瓦时，本期 85 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L054：第54单元，丙校区，基准 103 千瓦时，本期 105 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L058：第58单元，丙校区，基准 107 千瓦时，本期 78 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L062：第62单元，丙校区，基准 80 千瓦时，本期 98 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L066：第66单元，丙校区，基准 84 千瓦时，本期 71 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L070：第70单元，丙校区，基准 88 千瓦时，本期 91 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L074：第74单元，丙校区，基准 92 千瓦时，本期 111 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L078：第78单元，丙校区，基准 96 千瓦时，本期 84 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L082：第82单元，丙校区，基准 100 千瓦时，本期 104 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L086：第86单元，丙校区，基准 104 千瓦时，本期 77 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L090：第90单元，丙校区，基准 108 千瓦时，本期 97 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L094：第94单元，丙校区，基准 81 千瓦时，本期 70 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L098：第98单元，丙校区，基准 85 千瓦时，本期 90 千瓦时；未包含人数、面积与气温。\\n\\n请完成：\\n1. 逐条核验丙校区记录，确认单元编号、校区、基准用量、本期用量与来源编号一致。\\n2. 计算丙校区基准用量合计、本期用量合计、净变化（本期合计减基准合计）。\\n3. 统计丙校区增加单元数（本期大于基准）、减少单元数（本期小于基准）、持平单元数（本期等于基准）。\\n4. 列出丙校区中增加、减少、持平的来源编号清单。\\n5. 指出任何记录异常、缺失或不确定事项；不得虚构原因、数据或已执行的操作。\\n\\n输出 JSON，字段如下：\\n- campus：校区名称，填「丙校区」\\n- unit_count：该校区单元数\\n- baseline_total：基准用量合计\\n- current_total：本期用量合计\\n- net_change：净变化，带正负号\\n- increase_count：增加单元数\\n- decrease_count：减少单元数\\n- unchanged_count：持平单元数\\n- increase_sources：增加单元来源编号清单，用顿号分隔\\n- decrease_sources：减少单元来源编号清单，用顿号分隔\\n- unchanged_sources：持平单元来源编号清单，用顿号分隔；如无填「无」\\n- notes：核验说明、异常或不确定事项；如无填「无」\&quot;,\n      \&quot;parents\&quot;: [],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;核验丙校区全部记录并计算该校区基准合计、本期合计、净变化及增减持平单元统计\&quot;,\n        \&quot;inputs\&quot;: {},\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;json\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;campus\&quot;: \&quot;校区名称\&quot;,\n            \&quot;unit_count\&quot;: \&quot;该校区单元数\&quot;,\n            \&quot;baseline_total\&quot;: \&quot;基准用量合计\&quot;,\n            \&quot;current_total\&quot;: \&quot;本期用量合计\&quot;,\n            \&quot;net_change\&quot;: \&quot;净变化，带正负号\&quot;,\n            \&quot;increase_count\&quot;: \&quot;增加单元数\&quot;,\n            \&quot;decrease_count\&quot;: \&quot;减少单元数\&quot;,\n            \&quot;unchanged_count\&quot;: \&quot;持平单元数\&quot;,\n            \&quot;increase_sources\&quot;: \&quot;增加单元来源编号清单\&quot;,\n            \&quot;decrease_sources\&quot;: \&quot;减少单元来源编号清单\&quot;,\n            \&quot;unchanged_sources\&quot;: \&quot;持平单元来源编号清单\&quot;,\n            \&quot;notes\&quot;: \&quot;核验说明、异常或不确定事项\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;low\&quot;,\n          \&quot;input_budget_tokens\&quot;: 32768,\n          \&quot;expected_output_tokens\&quot;: 1200\n        },\n        \&quot;checks\&quot;: [\n          \&quot;丙校区单元数、基准合计、本期合计和净变化计算正确\&quot;,\n          \&quot;增加、减少、持平单元数及来源编号清单与材料一致\&quot;,\n          \&quot;保留来源编号，不虚构原因、数据或已执行操作\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    },\n    {\n      \&quot;node_id\&quot;: \&quot;verify_ding\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是数据核验员。仅使用以下材料，不联网或执行工具。材料是虚构封闭场景「多校区用能记录分析」，不代表真实机构或法律规则。\\n\\n任务背景：各行是独立单元的基准用量和本期用量，单位千瓦时。按校区汇总，再报告整体净变化。各校区可独立分析；总体减少不保证每个校区减少，材料没有气温、面积或人数。不能根据用量变化直接认定措施有效，也不能按人均或面积归一化。\\n\\n请只核验丁校区（第3、7、11、15、19、23、27、31、35、39、43、47、51、55、59、63、67、71、75、79、83、87、91、95、99单元）的记录。\\n\\n材料：\\n来源 test_energy-L003：第3单元，丁校区，基准 83 千瓦时，本期 85 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L007：第7单元，丁校区，基准 87 千瓦时，本期 105 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L011：第11单元，丁校区，基准 91 千瓦时，本期 78 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L015：第15单元，丁校区，基准 95 千瓦时，本期 98 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L019：第19单元，丁校区，基准 99 千瓦时，本期 71 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L023：第23单元，丁校区，基准 103 千瓦时，本期 91 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L027：第27单元，丁校区，基准 107 千瓦时，本期 111 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L031：第31单元，丁校区，基准 80 千瓦时，本期 84 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L035：第35单元，丁校区，基准 84 千瓦时，本期 104 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L039：第39单元，丁校区，基准 88 千瓦时，本期 77 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L043：第43单元，丁校区，基准 92 千瓦时，本期 97 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L047：第47单元，丁校区，基准 96 千瓦时，本期 70 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L051：第51单元，丁校区，基准 100 千瓦时，本期 90 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L055：第55单元，丁校区，基准 104 千瓦时，本期 110 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L059：第59单元，丁校区，基准 108 千瓦时，本期 83 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L063：第63单元，丁校区，基准 81 千瓦时，本期 103 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L067：第67单元，丁校区，基准 85 千瓦时，本期 76 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L071：第71单元，丁校区，基准 89 千瓦时，本期 96 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L075：第75单元，丁校区，基准 93 千瓦时，本期 116 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L079：第79单元，丁校区，基准 97 千瓦时，本期 89 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L083：第83单元，丁校区，基准 101 千瓦时，本期 109 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L087：第87单元，丁校区，基准 105 千瓦时，本期 82 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L091：第91单元，丁校区，基准 109 千瓦时，本期 102 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L095：第95单元，丁校区，基准 82 千瓦时，本期 75 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L099：第99单元，丁校区，基准 86 千瓦时，本期 95 千瓦时；未包含人数、面积与气温。\\n\\n请完成：\\n1. 逐条核验丁校区记录，确认单元编号、校区、基准用量、本期用量与来源编号一致。\\n2. 计算丁校区基准用量合计、本期用量合计、净变化（本期合计减基准合计）。\\n3. 统计丁校区增加单元数（本期大于基准）、减少单元数（本期小于基准）、持平单元数（本期等于基准）。\\n4. 列出丁校区中增加、减少、持平的来源编号清单。\\n5. 指出任何记录异常、缺失或不确定事项；不得虚构原因、数据或已执行的操作。\\n\\n输出 JSON，字段如下：\\n- campus：校区名称，填「丁校区」\\n- unit_count：该校区单元数\\n- baseline_total：基准用量合计\\n- current_total：本期用量合计\\n- net_change：净变化，带正负号\\n- increase_count：增加单元数\\n- decrease_count：减少单元数\\n- unchanged_count：持平单元数\\n- increase_sources：增加单元来源编号清单，用顿号分隔\\n- decrease_sources：减少单元来源编号清单，用顿号分隔\\n- unchanged_sources：持平单元来源编号清单，用顿号分隔；如无填「无」\\n- notes：核验说明、异常或不确定事项；如无填「无」\&quot;,\n      \&quot;parents\&quot;: [],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;核验丁校区全部记录并计算该校区基准合计、本期合计、净变化及增减持平单元统计\&quot;,\n        \&quot;inputs\&quot;: {},\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;json\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;campus\&quot;: \&quot;校区名称\&quot;,\n            \&quot;unit_count\&quot;: \&quot;该校区单元数\&quot;,\n            \&quot;baseline_total\&quot;: \&quot;基准用量合计\&quot;,\n            \&quot;current_total\&quot;: \&quot;本期用量合计\&quot;,\n            \&quot;net_change\&quot;: \&quot;净变化，带正负号\&quot;,\n            \&quot;increase_count\&quot;: \&quot;增加单元数\&quot;,\n            \&quot;decrease_count\&quot;: \&quot;减少单元数\&quot;,\n            \&quot;unchanged_count\&quot;: \&quot;持平单元数\&quot;,\n            \&quot;increase_sources\&quot;: \&quot;增加单元来源编号清单\&quot;,\n            \&quot;decrease_sources\&quot;: \&quot;减少单元来源编号清单\&quot;,\n            \&quot;unchanged_sources\&quot;: \&quot;持平单元来源编号清单\&quot;,\n            \&quot;notes\&quot;: \&quot;核验说明、异常或不确定事项\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;low\&quot;,\n          \&quot;input_budget_tokens\&quot;: 32768,\n          \&quot;expected_output_tokens\&quot;: 1200\n        },\n        \&quot;checks\&quot;: [\n          \&quot;丁校区单元数、基准合计、本期合计和净变化计算正确\&quot;,\n          \&quot;增加、减少、持平单元数及来源编号清单与材料一致\&quot;,\n          \&quot;保留来源编号，不虚构原因、数据或已执行操作\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    },\n    {\n      \&quot;node_id\&quot;: \&quot;answer\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是分析汇总员。仅使用以下材料和四个校区核验结果，不联网或执行工具。材料是虚构封闭场景「多校区用能记录分析」，不代表真实机构或法律规则。\\n\\n任务背景：各行是独立单元的基准用量和本期用量，单位千瓦时。按校区汇总，再报告整体净变化。各校区可独立分析；总体减少不保证每个校区减少，材料没有气温、面积或人数。不能根据用量变化直接认定措施有效，也不能按人均或面积归一化。\\n\\n交付要求：并行核验各校区记录，汇总整体变化、增加单元数和减少单元数，给出有限结论与补充数据需求。\\n\\n四个校区核验结果如下：\\n甲校区：{verify_jia}\\n乙校区：{verify_yi}\\n丙校区：{verify_bing}\\n丁校区：{verify_ding}\\n\\n请完成：\\n1. 核对四个校区核验结果之间是否存在冲突、遗漏、术语或证据不一致；如有，指出并说明处理方式。\\n2. 汇总整体基准用量合计、整体本期用量合计、整体净变化（本期合计减基准合计）。\\n3. 汇总整体增加单元数和整体减少单元数；如存在持平单元，也说明持平单元数。\\n4. 按校区分别呈现各校区基准合计、本期合计、净变化、增加单元数、减少单元数及来源编号清单。\\n5. 给出有限结论：仅基于材料说明整体和各校区变化方向，不推断原因、措施有效性或按人均/面积归一化；明确总体减少不保证每个校区减少。\\n6. 给出补充数据需求：说明材料未包含人数、面积、气温等信息，以及为更深入分析可能需要但当前材料未提供的数据；不得虚构已存在的数据。\\n\\n最终直接输出正文，不要封装为 JSON。正文需包含以下部分并按此顺序：\\n一、各校区核验结果\\n二、整体汇总\\n三、有限结论\\n四、补充数据需求\\n\\n要求：事实和计算与材料一致，保留来源编号；区分已知事实、建议和未知事项；不虚构原因、数据或已执行的操作。\&quot;,\n      \&quot;parents\&quot;: [\&quot;verify_jia\&quot;, \&quot;verify_yi\&quot;, \&quot;verify_bing\&quot;, \&quot;verify_ding\&quot;],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;核对四个校区核验结果并汇总整体变化、增加单元数和减少单元数，输出包含各校区核验结果、整体汇总、有限结论和补充数据需求的最终正文\&quot;,\n        \&quot;inputs\&quot;: {\n          \&quot;verify_jia\&quot;: {\n            \&quot;fields\&quot;: [\&quot;campus\&quot;, \&quot;unit_count\&quot;, \&quot;baseline_total\&quot;, \&quot;current_total\&quot;, \&quot;net_change\&quot;, \&quot;increase_count\&quot;, \&quot;decrease_count\&quot;, \&quot;unchanged_count\&quot;, \&quot;increase_sources\&quot;, \&quot;decrease_sources\&quot;, \&quot;unchanged_sources\&quot;, \&quot;notes\&quot;],\n            \&quot;reason\&quot;: \&quot;需要甲校区核验结果以汇总整体数据并呈现甲校区分析\&quot;\n          },\n          \&quot;verify_yi\&quot;: {\n            \&quot;fields\&quot;: [\&quot;campus\&quot;, \&quot;unit_count\&quot;, \&quot;baseline_total\&quot;, \&quot;current_total\&quot;, \&quot;net_change\&quot;, \&quot;increase_count\&quot;, \&quot;decrease_count\&quot;, \&quot;unchanged_count\&quot;, \&quot;increase_sources\&quot;, \&quot;decrease_sources\&quot;, \&quot;unchanged_sources\&quot;, \&quot;notes\&quot;],\n            \&quot;reason\&quot;: \&quot;需要乙校区核验结果以汇总整体数据并呈现乙校区分析\&quot;\n          },\n          \&quot;verify_bing\&quot;: {\n            \&quot;fields\&quot;: [\&quot;campus\&quot;, \&quot;unit_count\&quot;, \&quot;baseline_total\&quot;, \&quot;current_total\&quot;, \&quot;net_change\&quot;, \&quot;increase_count\&quot;, \&quot;decrease_count\&quot;, \&quot;unchanged_count\&quot;, \&quot;increase_sources\&quot;, \&quot;decrease_sources\&quot;, \&quot;unchanged_sources\&quot;, \&quot;notes\&quot;],\n            \&quot;reason\&quot;: \&quot;需要丙校区核验结果以汇总整体数据并呈现丙校区分析\&quot;\n          },\n          \&quot;verify_ding\&quot;: {\n            \&quot;fields\&quot;: [\&quot;campus\&quot;, \&quot;unit_count\&quot;, \&quot;baseline_total\&quot;, \&quot;current_total\&quot;, \&quot;net_change\&quot;, \&quot;increase_count\&quot;, \&quot;decrease_count\&quot;, \&quot;unchanged_count\&quot;, \&quot;increase_sources\&quot;, \&quot;decrease_sources\&quot;, \&quot;unchanged_sources\&quot;, \&quot;&quot;,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;length&quot;,
    &quot;output_tokens&quot;: 8192
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P024

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| verify_jia | generation | 无 | 核验甲校区全部单元记录并计算该校区汇总指标 |
| verify_yi | generation | 无 | 核验乙校区全部单元记录并计算该校区汇总指标 |
| verify_bing | generation | 无 | 核验丙校区全部单元记录并计算该校区汇总指标 |
| verify_ding | generation | 无 | 核验丁校区全部单元记录并计算该校区汇总指标 |
| answer | generation | verify_jia,verify_yi,verify_bing,verify_ding | 汇总四个校区核验结果，计算整体指标，核对一致性并给出有限结论与补充数据需求 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;verify_jia&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;你是数据核验员。只使用以下材料，不联网或执行工具。请核验甲校区所有单元的基准用量和本期用量记录，计算该校区：1）基准用量合计；2）本期用量合计；3）净变化（本期合计减基准合计）；4）增加单元数（本期大于基准）；5）减少单元数（本期小于基准）；6）持平单元数（本期等于基准）。逐条列出甲校区记录，保留来源编号、基准用量、本期用量和变化方向。材料未提供气温、面积、人数，不得按人均或面积归一化，不得推断原因。输出 JSON，字段为：campus、records、baseline_total、current_total、net_change、increase_count、decrease_count、unchanged_count。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;核验甲校区全部单元记录并计算该校区汇总指标&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;campus&quot;: &quot;校区名称，应为甲校区&quot;,
              &quot;records&quot;: &quot;逐条记录，包含来源编号、基准用量、本期用量、变化方向，用分号分隔&quot;,
              &quot;baseline_total&quot;: &quot;甲校区基准用量合计&quot;,
              &quot;current_total&quot;: &quot;甲校区本期用量合计&quot;,
              &quot;net_change&quot;: &quot;甲校区净变化，本期合计减基准合计&quot;,
              &quot;increase_count&quot;: &quot;甲校区本期大于基准的单元数&quot;,
              &quot;decrease_count&quot;: &quot;甲校区本期小于基准的单元数&quot;,
              &quot;unchanged_count&quot;: &quot;甲校区本期等于基准的单元数&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 3000
          },
          &quot;checks&quot;: [
            &quot;甲校区所有记录均被逐条列出且来源编号保留&quot;,
            &quot;合计、净变化、增加数、减少数、持平数计算正确&quot;,
            &quot;未虚构气温、面积、人数或原因&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;verify_yi&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;你是数据核验员。只使用以下材料，不联网或执行工具。请核验乙校区所有单元的基准用量和本期用量记录，计算该校区：1）基准用量合计；2）本期用量合计；3）净变化（本期合计减基准合计）；4）增加单元数（本期大于基准）；5）减少单元数（本期小于基准）；6）持平单元数（本期等于基准）。逐条列出乙校区记录，保留来源编号、基准用量、本期用量和变化方向。材料未提供气温、面积、人数，不得按人均或面积归一化，不得推断原因。输出 JSON，字段为：campus、records、baseline_total、current_total、net_change、increase_count、decrease_count、unchanged_count。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;核验乙校区全部单元记录并计算该校区汇总指标&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;campus&quot;: &quot;校区名称，应为乙校区&quot;,
              &quot;records&quot;: &quot;逐条记录，包含来源编号、基准用量、本期用量、变化方向，用分号分隔&quot;,
              &quot;baseline_total&quot;: &quot;乙校区基准用量合计&quot;,
              &quot;current_total&quot;: &quot;乙校区本期用量合计&quot;,
              &quot;net_change&quot;: &quot;乙校区净变化，本期合计减基准合计&quot;,
              &quot;increase_count&quot;: &quot;乙校区本期大于基准的单元数&quot;,
              &quot;decrease_count&quot;: &quot;乙校区本期小于基准的单元数&quot;,
              &quot;unchanged_count&quot;: &quot;乙校区本期等于基准的单元数&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 3000
          },
          &quot;checks&quot;: [
            &quot;乙校区所有记录均被逐条列出且来源编号保留&quot;,
            &quot;合计、净变化、增加数、减少数、持平数计算正确&quot;,
            &quot;未虚构气温、面积、人数或原因&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;verify_bing&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;你是数据核验员。只使用以下材料，不联网或执行工具。请核验丙校区所有单元的基准用量和本期用量记录，计算该校区：1）基准用量合计；2）本期用量合计；3）净变化（本期合计减基准合计）；4）增加单元数（本期大于基准）；5）减少单元数（本期小于基准）；6）持平单元数（本期等于基准）。逐条列出丙校区记录，保留来源编号、基准用量、本期用量和变化方向。材料未提供气温、面积、人数，不得按人均或面积归一化，不得推断原因。输出 JSON，字段为：campus、records、baseline_total、current_total、net_change、increase_count、decrease_count、unchanged_count。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;核验丙校区全部单元记录并计算该校区汇总指标&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;campus&quot;: &quot;校区名称，应为丙校区&quot;,
              &quot;records&quot;: &quot;逐条记录，包含来源编号、基准用量、本期用量、变化方向，用分号分隔&quot;,
              &quot;baseline_total&quot;: &quot;丙校区基准用量合计&quot;,
              &quot;current_total&quot;: &quot;丙校区本期用量合计&quot;,
              &quot;net_change&quot;: &quot;丙校区净变化，本期合计减基准合计&quot;,
              &quot;increase_count&quot;: &quot;丙校区本期大于基准的单元数&quot;,
              &quot;decrease_count&quot;: &quot;丙校区本期小于基准的单元数&quot;,
              &quot;unchanged_count&quot;: &quot;丙校区本期等于基准的单元数&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 3000
          },
          &quot;checks&quot;: [
            &quot;丙校区所有记录均被逐条列出且来源编号保留&quot;,
            &quot;合计、净变化、增加数、减少数、持平数计算正确&quot;,
            &quot;未虚构气温、面积、人数或原因&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;verify_ding&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;你是数据核验员。只使用以下材料，不联网或执行工具。请核验丁校区所有单元的基准用量和本期用量记录，计算该校区：1）基准用量合计；2）本期用量合计；3）净变化（本期合计减基准合计）；4）增加单元数（本期大于基准）；5）减少单元数（本期小于基准）；6）持平单元数（本期等于基准）。逐条列出丁校区记录，保留来源编号、基准用量、本期用量和变化方向。材料未提供气温、面积、人数，不得按人均或面积归一化，不得推断原因。输出 JSON，字段为：campus、records、baseline_total、current_total、net_change、increase_count、decrease_count、unchanged_count。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;核验丁校区全部单元记录并计算该校区汇总指标&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;campus&quot;: &quot;校区名称，应为丁校区&quot;,
              &quot;records&quot;: &quot;逐条记录，包含来源编号、基准用量、本期用量、变化方向，用分号分隔&quot;,
              &quot;baseline_total&quot;: &quot;丁校区基准用量合计&quot;,
              &quot;current_total&quot;: &quot;丁校区本期用量合计&quot;,
              &quot;net_change&quot;: &quot;丁校区净变化，本期合计减基准合计&quot;,
              &quot;increase_count&quot;: &quot;丁校区本期大于基准的单元数&quot;,
              &quot;decrease_count&quot;: &quot;丁校区本期小于基准的单元数&quot;,
              &quot;unchanged_count&quot;: &quot;丁校区本期等于基准的单元数&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 32768,
            &quot;expected_output_tokens&quot;: 3000
          },
          &quot;checks&quot;: [
            &quot;丁校区所有记录均被逐条列出且来源编号保留&quot;,
            &quot;合计、净变化、增加数、减少数、持平数计算正确&quot;,
            &quot;未虚构气温、面积、人数或原因&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;你是分析汇总员。只使用原始材料和四个校区核验结果，不联网或执行工具。请完成最终交付：1）分别呈现甲、乙、丙、丁四个校区的核验结果，包括各校区基准用量合计、本期用量合计、净变化、增加单元数、减少单元数、持平单元数，并保留来源编号；2）汇总整体基准用量合计、整体本期用量合计、整体净变化、整体增加单元数和整体减少单元数；3）核对四个校区结果之间是否存在冲突、遗漏、术语或证据不一致，并说明核对结论；4）给出有限结论，明确总体减少不保证每个校区减少，材料没有气温、面积或人数，不能根据用量变化直接认定措施有效，也不能按人均或面积归一化；5）列出补充数据需求，例如气温、面积、人数等，但不得虚构这些数据或已执行的操作。最终正文直接输出，不封装为 JSON。&quot;,
        &quot;parents&quot;: [
          &quot;verify_jia&quot;,
          &quot;verify_yi&quot;,
          &quot;verify_bing&quot;,
          &quot;verify_ding&quot;
        ],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;汇总四个校区核验结果，计算整体指标，核对一致性并给出有限结论与补充数据需求&quot;,
          &quot;inputs&quot;: {
            &quot;verify_jia&quot;: {
              &quot;fields&quot;: [
                &quot;campus&quot;,
                &quot;records&quot;,
                &quot;baseline_total&quot;,
                &quot;current_total&quot;,
                &quot;net_change&quot;,
                &quot;increase_count&quot;,
                &quot;decrease_count&quot;,
                &quot;unchanged_count&quot;
              ],
              &quot;reason&quot;: &quot;需要甲校区核验结果以汇总整体指标并呈现分校区分析&quot;
            },
            &quot;verify_yi&quot;: {
              &quot;fields&quot;: [
                &quot;campus&quot;,
                &quot;records&quot;,
                &quot;baseline_total&quot;,
                &quot;current_total&quot;,
                &quot;net_change&quot;,
                &quot;increase_count&quot;,
                &quot;decrease_count&quot;,
                &quot;unchanged_count&quot;
              ],
              &quot;reason&quot;: &quot;需要乙校区核验结果以汇总整体指标并呈现分校区分析&quot;
            },
            &quot;verify_bing&quot;: {
              &quot;fields&quot;: [
                &quot;campus&quot;,
                &quot;records&quot;,
                &quot;baseline_total&quot;,
                &quot;current_total&quot;,
                &quot;net_change&quot;,
                &quot;increase_count&quot;,
                &quot;decrease_count&quot;,
                &quot;unchanged_count&quot;
              ],
              &quot;reason&quot;: &quot;需要丙校区核验结果以汇总整体指标并呈现分校区分析&quot;
            },
            &quot;verify_ding&quot;: {
              &quot;fields&quot;: [
                &quot;campus&quot;,
                &quot;records&quot;,
                &quot;baseline_total&quot;,
                &quot;current_total&quot;,
                &quot;net_change&quot;,
                &quot;increase_count&quot;,
                &quot;decrease_count&quot;,
                &quot;unchanged_count&quot;
              ],
              &quot;reason&quot;: &quot;需要丁校区核验结果以汇总整体指标并呈现分校区分析&quot;
            }
          },
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终交付正文，依次包含四个校区核验结果、整体汇总、一致性核对、有限结论和补充数据需求&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;medium&quot;,
            &quot;input_budget_tokens&quot;: 65536,
            &quot;expected_output_tokens&quot;: 5000
          },
          &quot;checks&quot;: [
            &quot;四个校区核验结果均被分别呈现且保留来源编号&quot;,
            &quot;整体基准合计、本期合计、净变化、增加单元数、减少单元数计算正确&quot;,
            &quot;一致性核对覆盖冲突、遗漏、术语和证据一致性&quot;,
            &quot;有限结论遵守材料约束，不虚构原因、数据或已执行操作&quot;,
            &quot;补充数据需求明确列出且不把未知条件写成事实&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务要求按校区并行核验记录并汇总整体变化、增加单元数和减少单元数，四个校区可独立分析，存在并行机会；但最终交付必须统一汇总并核对冲突、遗漏和证据一致性，因此采用四个校区核验分支加一个汇总节点。材料为100条短记录，单条计算简单，不进一步拆分。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 3026
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P026

没有结构合法的计划；仍需记录缺失 / 失败及其理由。

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: null,
  &quot;raw_plan_if_unparsed&quot;: &quot;{\n  \&quot;schema_version\&quot;: \&quot;text-task-plan-v2\&quot;,\n  \&quot;decomposition_reason\&quot;: \&quot;任务要求按校区并行核验记录并汇总整体变化、增加单元数和减少单元数，四个校区可独立分析，存在并行机会；但最终交付需统一汇总并核对冲突与遗漏，因此拆分为四个校区核验节点和一个汇总节点。拆分净收益是并行核验可减少单节点长文本处理压力，同时汇总节点统一呈现整体结论；交接开销为四个校区核验结果向汇总节点传递，扇入上下文可控。\&quot;,\n  \&quot;nodes\&quot;: [\n    {\n      \&quot;node_id\&quot;: \&quot;verify_jia\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是多校区用能记录核验员。请仅依据以下材料核验甲校区各单元的基准用量和本期用量，单位均为千瓦时。\\n\\n甲校区记录：\\n来源 test_energy-L004：第4单元，甲校区，基准 84 千瓦时，本期 90 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L008：第8单元，甲校区，基准 88 千瓦时，本期 110 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L012：第12单元，甲校区，基准 92 千瓦时，本期 83 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L016：第16单元，甲校区，基准 96 千瓦时，本期 103 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L020：第20单元，甲校区，基准 100 千瓦时，本期 76 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L024：第24单元，甲校区，基准 104 千瓦时，本期 96 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L028：第28单元，甲校区，基准 108 千瓦时，本期 116 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L032：第32单元，甲校区，基准 81 千瓦时，本期 89 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L036：第36单元，甲校区，基准 85 千瓦时，本期 109 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L040：第40单元，甲校区，基准 89 千瓦时，本期 82 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L044：第44单元，甲校区，基准 93 千瓦时，本期 102 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L048：第48单元，甲校区，基准 97 千瓦时，本期 75 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L052：第52单元，甲校区，基准 101 千瓦时，本期 95 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L056：第56单元，甲校区，基准 105 千瓦时，本期 115 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L060：第60单元，甲校区，基准 109 千瓦时，本期 88 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L064：第64单元，甲校区，基准 82 千瓦时，本期 108 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L068：第68单元，甲校区，基准 86 千瓦时，本期 81 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L072：第72单元，甲校区，基准 90 千瓦时，本期 101 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L076：第76单元，甲校区，基准 94 千瓦时，本期 74 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L080：第80单元，甲校区，基准 98 千瓦时，本期 94 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L084：第84单元，甲校区，基准 102 千瓦时，本期 114 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L088：第88单元，甲校区，基准 106 千瓦时，本期 87 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L092：第92单元，甲校区，基准 110 千瓦时，本期 107 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L096：第96单元，甲校区，基准 83 千瓦时，本期 80 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L100：第100单元，甲校区，基准 87 千瓦时，本期 100 千瓦时；未包含人数、面积与气温。\\n\\n请核验并输出：1）甲校区单元总数；2）甲校区基准用量合计；3）甲校区本期用量合计；4）甲校区净变化（本期合计减基准合计）；5）甲校区本期用量大于基准用量的单元数；6）甲校区本期用量小于基准用量的单元数；7）甲校区本期用量等于基准用量的单元数；8）核验说明，包括记录是否完整、有无异常或矛盾，以及材料未提供人数、面积与气温，因此不能进行人均或面积归一化，也不能认定措施有效。\&quot;,\n      \&quot;parents\&quot;: [],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;核验甲校区全部单元记录，计算合计、净变化及增加/减少/持平单元数，并说明材料限制。\&quot;,\n        \&quot;inputs\&quot;: {},\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;json\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;campus\&quot;: \&quot;校区名称，应为甲校区\&quot;,\n            \&quot;unit_count\&quot;: \&quot;甲校区单元总数\&quot;,\n            \&quot;baseline_total\&quot;: \&quot;甲校区基准用量合计，单位千瓦时\&quot;,\n            \&quot;current_total\&quot;: \&quot;甲校区本期用量合计，单位千瓦时\&quot;,\n            \&quot;net_change\&quot;: \&quot;甲校区净变化，单位千瓦时，可为负值\&quot;,\n            \&quot;increase_count\&quot;: \&quot;本期用量大于基准用量的单元数\&quot;,\n            \&quot;decrease_count\&quot;: \&quot;本期用量小于基准用量的单元数\&quot;,\n            \&quot;equal_count\&quot;: \&quot;本期用量等于基准用量的单元数\&quot;,\n            \&quot;verification_note\&quot;: \&quot;核验说明，包括记录完整性、异常或矛盾、材料限制及不能认定措施有效的原因\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;low\&quot;,\n          \&quot;input_budget_tokens\&quot;: 16384,\n          \&quot;expected_output_tokens\&quot;: 1200\n        },\n        \&quot;checks\&quot;: [\n          \&quot;甲校区单元总数应为25\&quot;,\n          \&quot;甲校区基准用量合计和本期用量合计计算正确\&quot;,\n          \&quot;甲校区净变化等于本期合计减基准合计\&quot;,\n          \&quot;增加、减少、持平单元数之和等于单元总数\&quot;,\n          \&quot;核验说明明确材料未提供人数、面积与气温，不能归一化或认定措施有效\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    },\n    {\n      \&quot;node_id\&quot;: \&quot;verify_yi\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是多校区用能记录核验员。请仅依据以下材料核验乙校区各单元的基准用量和本期用量，单位均为千瓦时。\\n\\n乙校区记录：\\n来源 test_energy-L001：第1单元，乙校区，基准 81 千瓦时，本期 75 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L005：第5单元，乙校区，基准 85 千瓦时，本期 95 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L009：第9单元，乙校区，基准 89 千瓦时，本期 115 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L013：第13单元，乙校区，基准 93 千瓦时，本期 88 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L017：第17单元，乙校区，基准 97 千瓦时，本期 108 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L021：第21单元，乙校区，基准 101 千瓦时，本期 81 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L025：第25单元，乙校区，基准 105 千瓦时，本期 101 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L029：第29单元，乙校区，基准 109 千瓦时，本期 74 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L033：第33单元，乙校区，基准 82 千瓦时，本期 94 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L037：第37单元，乙校区，基准 86 千瓦时，本期 114 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L041：第41单元，乙校区，基准 90 千瓦时，本期 87 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L045：第45单元，乙校区，基准 94 千瓦时，本期 107 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L049：第49单元，乙校区，基准 98 千瓦时，本期 80 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L053：第53单元，乙校区，基准 102 千瓦时，本期 100 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L057：第57单元，乙校区，基准 106 千瓦时，本期 73 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L061：第61单元，乙校区，基准 110 千瓦时，本期 93 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L065：第65单元，乙校区，基准 83 千瓦时，本期 113 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L069：第69单元，乙校区，基准 87 千瓦时，本期 86 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L073：第73单元，乙校区，基准 91 千瓦时，本期 106 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L077：第77单元，乙校区，基准 95 千瓦时，本期 79 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L081：第81单元，乙校区，基准 99 千瓦时，本期 99 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L085：第85单元，乙校区，基准 103 千瓦时，本期 72 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L089：第89单元，乙校区，基准 107 千瓦时，本期 92 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L093：第93单元，乙校区，基准 80 千瓦时，本期 112 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L097：第97单元，乙校区，基准 84 千瓦时，本期 85 千瓦时；未包含人数、面积与气温。\\n\\n请核验并输出：1）乙校区单元总数；2）乙校区基准用量合计；3）乙校区本期用量合计；4）乙校区净变化（本期合计减基准合计）；5）乙校区本期用量大于基准用量的单元数；6）乙校区本期用量小于基准用量的单元数；7）乙校区本期用量等于基准用量的单元数；8）核验说明，包括记录是否完整、有无异常或矛盾，以及材料未提供人数、面积与气温，因此不能进行人均或面积归一化，也不能认定措施有效。\&quot;,\n      \&quot;parents\&quot;: [],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;核验乙校区全部单元记录，计算合计、净变化及增加/减少/持平单元数，并说明材料限制。\&quot;,\n        \&quot;inputs\&quot;: {},\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;json\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;campus\&quot;: \&quot;校区名称，应为乙校区\&quot;,\n            \&quot;unit_count\&quot;: \&quot;乙校区单元总数\&quot;,\n            \&quot;baseline_total\&quot;: \&quot;乙校区基准用量合计，单位千瓦时\&quot;,\n            \&quot;current_total\&quot;: \&quot;乙校区本期用量合计，单位千瓦时\&quot;,\n            \&quot;net_change\&quot;: \&quot;乙校区净变化，单位千瓦时，可为负值\&quot;,\n            \&quot;increase_count\&quot;: \&quot;本期用量大于基准用量的单元数\&quot;,\n            \&quot;decrease_count\&quot;: \&quot;本期用量小于基准用量的单元数\&quot;,\n            \&quot;equal_count\&quot;: \&quot;本期用量等于基准用量的单元数\&quot;,\n            \&quot;verification_note\&quot;: \&quot;核验说明，包括记录完整性、异常或矛盾、材料限制及不能认定措施有效的原因\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;low\&quot;,\n          \&quot;input_budget_tokens\&quot;: 16384,\n          \&quot;expected_output_tokens\&quot;: 1200\n        },\n        \&quot;checks\&quot;: [\n          \&quot;乙校区单元总数应为25\&quot;,\n          \&quot;乙校区基准用量合计和本期用量合计计算正确\&quot;,\n          \&quot;乙校区净变化等于本期合计减基准合计\&quot;,\n          \&quot;增加、减少、持平单元数之和等于单元总数\&quot;,\n          \&quot;核验说明明确材料未提供人数、面积与气温，不能归一化或认定措施有效\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    },\n    {\n      \&quot;node_id\&quot;: \&quot;verify_bing\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是多校区用能记录核验员。请仅依据以下材料核验丙校区各单元的基准用量和本期用量，单位均为千瓦时。\\n\\n丙校区记录：\\n来源 test_energy-L002：第2单元，丙校区，基准 82 千瓦时，本期 80 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L006：第6单元，丙校区，基准 86 千瓦时，本期 100 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L010：第10单元，丙校区，基准 90 千瓦时，本期 73 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L014：第14单元，丙校区，基准 94 千瓦时，本期 93 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L018：第18单元，丙校区，基准 98 千瓦时，本期 113 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L022：第22单元，丙校区，基准 102 千瓦时，本期 86 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L026：第26单元，丙校区，基准 106 千瓦时，本期 106 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L030：第30单元，丙校区，基准 110 千瓦时，本期 79 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L034：第34单元，丙校区，基准 83 千瓦时，本期 99 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L038：第38单元，丙校区，基准 87 千瓦时，本期 72 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L042：第42单元，丙校区，基准 91 千瓦时，本期 92 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L046：第46单元，丙校区，基准 95 千瓦时，本期 112 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L050：第50单元，丙校区，基准 99 千瓦时，本期 85 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L054：第54单元，丙校区，基准 103 千瓦时，本期 105 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L058：第58单元，丙校区，基准 107 千瓦时，本期 78 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L062：第62单元，丙校区，基准 80 千瓦时，本期 98 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L066：第66单元，丙校区，基准 84 千瓦时，本期 71 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L070：第70单元，丙校区，基准 88 千瓦时，本期 91 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L074：第74单元，丙校区，基准 92 千瓦时，本期 111 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L078：第78单元，丙校区，基准 96 千瓦时，本期 84 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L082：第82单元，丙校区，基准 100 千瓦时，本期 104 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L086：第86单元，丙校区，基准 104 千瓦时，本期 77 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L090：第90单元，丙校区，基准 108 千瓦时，本期 97 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L094：第94单元，丙校区，基准 81 千瓦时，本期 70 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L098：第98单元，丙校区，基准 85 千瓦时，本期 90 千瓦时；未包含人数、面积与气温。\\n\\n请核验并输出：1）丙校区单元总数；2）丙校区基准用量合计；3）丙校区本期用量合计；4）丙校区净变化（本期合计减基准合计）；5）丙校区本期用量大于基准用量的单元数；6）丙校区本期用量小于基准用量的单元数；7）丙校区本期用量等于基准用量的单元数；8）核验说明，包括记录是否完整、有无异常或矛盾，以及材料未提供人数、面积与气温，因此不能进行人均或面积归一化，也不能认定措施有效。\&quot;,\n      \&quot;parents\&quot;: [],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;核验丙校区全部单元记录，计算合计、净变化及增加/减少/持平单元数，并说明材料限制。\&quot;,\n        \&quot;inputs\&quot;: {},\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;json\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;campus\&quot;: \&quot;校区名称，应为丙校区\&quot;,\n            \&quot;unit_count\&quot;: \&quot;丙校区单元总数\&quot;,\n            \&quot;baseline_total\&quot;: \&quot;丙校区基准用量合计，单位千瓦时\&quot;,\n            \&quot;current_total\&quot;: \&quot;丙校区本期用量合计，单位千瓦时\&quot;,\n            \&quot;net_change\&quot;: \&quot;丙校区净变化，单位千瓦时，可为负值\&quot;,\n            \&quot;increase_count\&quot;: \&quot;本期用量大于基准用量的单元数\&quot;,\n            \&quot;decrease_count\&quot;: \&quot;本期用量小于基准用量的单元数\&quot;,\n            \&quot;equal_count\&quot;: \&quot;本期用量等于基准用量的单元数\&quot;,\n            \&quot;verification_note\&quot;: \&quot;核验说明，包括记录完整性、异常或矛盾、材料限制及不能认定措施有效的原因\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;low\&quot;,\n          \&quot;input_budget_tokens\&quot;: 16384,\n          \&quot;expected_output_tokens\&quot;: 1200\n        },\n        \&quot;checks\&quot;: [\n          \&quot;丙校区单元总数应为25\&quot;,\n          \&quot;丙校区基准用量合计和本期用量合计计算正确\&quot;,\n          \&quot;丙校区净变化等于本期合计减基准合计\&quot;,\n          \&quot;增加、减少、持平单元数之和等于单元总数\&quot;,\n          \&quot;核验说明明确材料未提供人数、面积与气温，不能归一化或认定措施有效\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    },\n    {\n      \&quot;node_id\&quot;: \&quot;verify_ding\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是多校区用能记录核验员。请仅依据以下材料核验丁校区各单元的基准用量和本期用量，单位均为千瓦时。\\n\\n丁校区记录：\\n来源 test_energy-L003：第3单元，丁校区，基准 83 千瓦时，本期 85 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L007：第7单元，丁校区，基准 87 千瓦时，本期 105 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L011：第11单元，丁校区，基准 91 千瓦时，本期 78 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L015：第15单元，丁校区，基准 95 千瓦时，本期 98 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L019：第19单元，丁校区，基准 99 千瓦时，本期 71 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L023：第23单元，丁校区，基准 103 千瓦时，本期 91 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L027：第27单元，丁校区，基准 107 千瓦时，本期 111 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L031：第31单元，丁校区，基准 80 千瓦时，本期 84 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L035：第35单元，丁校区，基准 84 千瓦时，本期 104 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L039：第39单元，丁校区，基准 88 千瓦时，本期 77 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L043：第43单元，丁校区，基准 92 千瓦时，本期 97 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L047：第47单元，丁校区，基准 96 千瓦时，本期 70 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L051：第51单元，丁校区，基准 100 千瓦时，本期 90 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L055：第55单元，丁校区，基准 104 千瓦时，本期 110 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L059：第59单元，丁校区，基准 108 千瓦时，本期 83 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L063：第63单元，丁校区，基准 81 千瓦时，本期 103 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L067：第67单元，丁校区，基准 85 千瓦时，本期 76 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L071：第71单元，丁校区，基准 89 千瓦时，本期 96 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L075：第75单元，丁校区，基准 93 千瓦时，本期 116 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L079：第79单元，丁校区，基准 97 千瓦时，本期 89 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L083：第83单元，丁校区，基准 101 千瓦时，本期 109 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L087：第87单元，丁校区，基准 105 千瓦时，本期 82 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L091：第91单元，丁校区，基准 109 千瓦时，本期 102 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L095：第95单元，丁校区，基准 82 千瓦时，本期 75 千瓦时；未包含人数、面积与气温。\\n来源 test_energy-L099：第99单元，丁校区，基准 86 千瓦时，本期 95 千瓦时；未包含人数、面积与气温。\\n\\n请核验并输出：1）丁校区单元总数；2）丁校区基准用量合计；3）丁校区本期用量合计；4）丁校区净变化（本期合计减基准合计）；5）丁校区本期用量大于基准用量的单元数；6）丁校区本期用量小于基准用量的单元数；7）丁校区本期用量等于基准用量的单元数；8）核验说明，包括记录是否完整、有无异常或矛盾，以及材料未提供人数、面积与气温，因此不能进行人均或面积归一化，也不能认定措施有效。\&quot;,\n      \&quot;parents\&quot;: [],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;核验丁校区全部单元记录，计算合计、净变化及增加/减少/持平单元数，并说明材料限制。\&quot;,\n        \&quot;inputs\&quot;: {},\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;json\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;campus\&quot;: \&quot;校区名称，应为丁校区\&quot;,\n            \&quot;unit_count\&quot;: \&quot;丁校区单元总数\&quot;,\n            \&quot;baseline_total\&quot;: \&quot;丁校区基准用量合计，单位千瓦时\&quot;,\n            \&quot;current_total\&quot;: \&quot;丁校区本期用量合计，单位千瓦时\&quot;,\n            \&quot;net_change\&quot;: \&quot;丁校区净变化，单位千瓦时，可为负值\&quot;,\n            \&quot;increase_count\&quot;: \&quot;本期用量大于基准用量的单元数\&quot;,\n            \&quot;decrease_count\&quot;: \&quot;本期用量小于基准用量的单元数\&quot;,\n            \&quot;equal_count\&quot;: \&quot;本期用量等于基准用量的单元数\&quot;,\n            \&quot;verification_note\&quot;: \&quot;核验说明，包括记录完整性、异常或矛盾、材料限制及不能认定措施有效的原因\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;low\&quot;,\n          \&quot;input_budget_tokens\&quot;: 16384,\n          \&quot;expected_output_tokens\&quot;: 1200\n        },\n        \&quot;checks\&quot;: [\n          \&quot;丁校区单元总数应为25\&quot;,\n          \&quot;丁校区基准用量合计和本期用量合计计算正确\&quot;,\n          \&quot;丁校区净变化等于本期合计减基准合计\&quot;,\n          \&quot;增加、减少、持平单元数之和等于单元总数\&quot;,\n          \&quot;核验说明明确材料未提供人数、面积与气温，不能归一化或认定措施有效\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    },\n    {\n      \&quot;node_id\&quot;: \&quot;answer\&quot;,\n      \&quot;node_type\&quot;: \&quot;generation\&quot;,\n      \&quot;prompt_template\&quot;: \&quot;你是多校区用能记录分析汇总员。请仅依据以下四个校区核验结果和原始任务材料，汇总整体变化、增加单元数和减少单元数，并给出有限结论与补充数据需求。\\n\\n原始任务要求：并行核验各校区记录，汇总整体变化、增加单元数和减少单元数，给出有限结论与补充数据需求。\\n\\n材料约束：这是独立编写的虚构封闭场景「多校区用能记录分析」，不代表真实机构或法律规则。只用以下材料，不联网或执行工具。各行是独立单元的基准用量和本期用量，单位千瓦时。按校区汇总，再报告整体净变化。各校区可独立分析；总体减少不保证每个校区减少，材料没有气温、面积或人数。不能根据用量变化直接认定措施有效，也不能按人均或面积归一化。\\n\\n甲校区核验结果：\\n{campus_jia}\\n\\n乙校区核验结果：\\n{campus_yi}\\n\\n丙校区核验结果：\\n{campus_bing}\\n\\n丁校区核验结果：\\n{campus_ding}\\n\\n请输出最终正文，依次包含以下部分：\\n1. 各校区核验结果：分别列出甲、乙、丙、丁四个校区的单元总数、基准用量合计、本期用量合计、净变化、增加单元数、减少单元数、持平单元数，并保留来源编号范围或关键来源编号。\\n2. 整体汇总：给出全部单元总数、整体基准用量合计、整体本期用量合计、整体净变化、整体增加单元数和整体减少单元数；如存在持平单元数也一并列出。\\n3. 有限结论：仅基于材料说明可确认的事实，包括整体净变化方向和各校区净变化方向；明确总体减少不保证每个校区减少；明确不能根据用量变化直接认定措施有效，也不能按人均或面积归一化。\\n4. 补充数据需求：列出为得出更强结论所需但材料未提供的数据，例如人数、面积、气温、措施执行记录等，并说明这些数据缺失限制了哪些判断。\\n\\n注意：不得虚构原因、数据或已执行的操作；区分已知事实、建议和未知事项；所有事实和计算必须与材料一致并保留来源编号。\&quot;,\n      \&quot;parents\&quot;: [\n        \&quot;verify_jia\&quot;,\n        \&quot;verify_yi\&quot;,\n        \&quot;verify_bing\&quot;,\n        \&quot;verify_ding\&quot;\n      ],\n      \&quot;contract\&quot;: {\n        \&quot;objective\&quot;: \&quot;汇总四个校区核验结果，输出整体变化、增加单元数和减少单元数，并给出有限结论与补充数据需求。\&quot;,\n        \&quot;inputs\&quot;: {\n          \&quot;verify_jia\&quot;: {\n            \&quot;fields\&quot;: [\n              \&quot;campus\&quot;,\n              \&quot;unit_count\&quot;,\n              \&quot;baseline_total\&quot;,\n              \&quot;current_total\&quot;,\n              \&quot;net_change\&quot;,\n              \&quot;increase_count\&quot;,\n              \&quot;decrease_count\&quot;,\n              \&quot;equal_count\&quot;,\n              \&quot;verification_note\&quot;\n            ],\n            \&quot;reason\&quot;: \&quot;需要甲校区核验结果以汇总各校区数据和整体变化。\&quot;\n          },\n          \&quot;verify_yi\&quot;: {\n            \&quot;fields\&quot;: [\n              \&quot;campus\&quot;,\n              \&quot;unit_count\&quot;,\n              \&quot;baseline_total\&quot;,\n              \&quot;current_total\&quot;,\n              \&quot;net_change\&quot;,\n              \&quot;increase_count\&quot;,\n              \&quot;decrease_count\&quot;,\n              \&quot;equal_count\&quot;,\n              \&quot;verification_note\&quot;\n            ],\n            \&quot;reason\&quot;: \&quot;需要乙校区核验结果以汇总各校区数据和整体变化。\&quot;\n          },\n          \&quot;verify_bing\&quot;: {\n            \&quot;fields\&quot;: [\n              \&quot;campus\&quot;,\n              \&quot;unit_count\&quot;,\n              \&quot;baseline_total\&quot;,\n              \&quot;current_total\&quot;,\n              \&quot;net_change\&quot;,\n              \&quot;increase_count\&quot;,\n              \&quot;decrease_count\&quot;,\n              \&quot;equal_count\&quot;,\n              \&quot;verification_note\&quot;\n            ],\n            \&quot;reason\&quot;: \&quot;需要丙校区核验结果以汇总各校区数据和整体变化。\&quot;\n          },\n          \&quot;verify_ding\&quot;: {\n            \&quot;fields\&quot;: [\n              \&quot;campus\&quot;,\n              \&quot;unit_count\&quot;,\n              \&quot;baseline_total\&quot;,\n              \&quot;current_total\&quot;,\n              \&quot;net_change\&quot;,\n              \&quot;increase_count\&quot;,\n              \&quot;decrease_count\&quot;,\n              \&quot;equal_count\&quot;,\n              \&quot;verification_note\&quot;\n            ],\n            \&quot;reason\&quot;: \&quot;需要丁校区核验结果以汇总各校区数据和整体变化。\&quot;\n          }\n        },\n        \&quot;output\&quot;: {\n          \&quot;format\&quot;: \&quot;text\&quot;,\n          \&quot;fields\&quot;: {\n            \&quot;text\&quot;: \&quot;最终交付正文，依次包含各校区核验结果、整体汇总、有限结论和补充数据需求\&quot;\n          }\n        },\n        \&quot;capability\&quot;: {\n          \&quot;difficulty\&quot;: \&quot;medium\&quot;,\n          \&quot;risk\&quot;: \&quot;medium\&quot;,\n          \&quot;input_budget_tokens\&quot;: 65536,\n          \&quot;expected_output_tokens\&quot;: 3000\n        },\n        \&quot;checks\&quot;: [\n          \&quot;最终正文依次包含各校区核验结果、整体汇总、有限结论和补充数据需求四个部分\&quot;,\n          \&quot;各校区核验结果分别列出甲、乙、丙、丁校区的单元总数、基准合计、本期合计、净变化、增加单元数、减少单元数及持平单元数\&quot;,\n          \&quot;整体汇总给出全部单元总数、整体基准合计、整体本期合计、整体净变化、整体增加单元数和整体减少单元数\&quot;,\n          \&quot;有限结论区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作\&quot;,\n          \&quot;明确总体减少不保证每个校区减少，且不能根据用量变化直接认定措施有效或按人均/面积归一化\&quot;,\n          \&quot;补充数据需求列出材料未提供的数据并说明其限制的判断\&quot;,\n          \&quot;事实和计算与材料一致并保留来源编号\&quot;\n        ],\n        \&quot;covers\&quot;: [0, 1],\n        \&quot;execution\&quot;: \&quot;text-model\&quot;,\n        \&quot;failure_policy\&quot;: \&quot;stop\&quot;\n      }\n    }\n  ],\n  \&quot;final_node_id\&quot;: \&quot;answer\&quot;,\n  \&quot;acceptance_criteria\&quot;: [\n    \&quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。\&quot;,\n    \&quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。\&quot;\n  ]\n}&quot;,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 7516
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

### P030

| 节点 | 类型 | 上游 | 职责 |
| --- | --- | --- | --- |
| verify_jia | generation | 无 | 核验甲校区全部单元记录并计算校区汇总指标 |
| verify_yi | generation | 无 | 核验乙校区全部单元记录并计算校区汇总指标 |
| verify_bing | generation | 无 | 核验丙校区全部单元记录并计算校区汇总指标 |
| verify_ding | generation | 无 | 核验丁校区全部单元记录并计算校区汇总指标 |
| answer | generation | verify_jia,verify_yi,verify_bing,verify_ding | 汇总四个校区核验结果，计算整体指标，给出有限结论与补充数据需求，形成最终交付正文 |

<details><summary>查看完整契约、节点输出和最终交付</summary>
<pre>{
  &quot;plan&quot;: {
    &quot;nodes&quot;: [
      {
        &quot;node_id&quot;: &quot;verify_jia&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;你是数据核验员。仅使用以下材料，不联网、不执行工具、不虚构信息。材料为虚构封闭场景「多校区用能记录分析」。\n\n请核验甲校区所有单元记录：从材料中找出所有标注「甲校区」的行，逐条列出来源编号、基准用量（千瓦时）、本期用量（千瓦时），并计算：\n1. 甲校区基准用量合计；\n2. 甲校区本期用量合计；\n3. 甲校区净变化（本期合计减基准合计）；\n4. 甲校区增加单元数（本期大于基准）；\n5. 甲校区减少单元数（本期小于基准）；\n6. 甲校区持平单元数（本期等于基准）。\n\n只依据材料中明确给出的数字和校区标注，不得按人均或面积归一化，不得推断措施有效性。保留所有来源编号。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;核验甲校区全部单元记录并计算校区汇总指标&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;campus&quot;: &quot;校区名称，固定为甲校区&quot;,
              &quot;records&quot;: &quot;逐条列出甲校区来源编号、基准用量、本期用量，用分号分隔&quot;,
              &quot;baseline_total&quot;: &quot;甲校区基准用量合计，仅数字&quot;,
              &quot;current_total&quot;: &quot;甲校区本期用量合计，仅数字&quot;,
              &quot;net_change&quot;: &quot;甲校区净变化，仅数字，可为负&quot;,
              &quot;increase_count&quot;: &quot;甲校区增加单元数，仅数字&quot;,
              &quot;decrease_count&quot;: &quot;甲校区减少单元数，仅数字&quot;,
              &quot;unchanged_count&quot;: &quot;甲校区持平单元数，仅数字&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 16384,
            &quot;expected_output_tokens&quot;: 1200
          },
          &quot;checks&quot;: [
            &quot;甲校区记录数量与材料一致&quot;,
            &quot;合计和净变化计算正确&quot;,
            &quot;增加、减少、持平单元数之和等于甲校区记录总数&quot;,
            &quot;保留所有来源编号&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;verify_yi&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;你是数据核验员。仅使用以下材料，不联网、不执行工具、不虚构信息。材料为虚构封闭场景「多校区用能记录分析」。\n\n请核验乙校区所有单元记录：从材料中找出所有标注「乙校区」的行，逐条列出来源编号、基准用量（千瓦时）、本期用量（千瓦时），并计算：\n1. 乙校区基准用量合计；\n2. 乙校区本期用量合计；\n3. 乙校区净变化（本期合计减基准合计）；\n4. 乙校区增加单元数（本期大于基准）；\n5. 乙校区减少单元数（本期小于基准）；\n6. 乙校区持平单元数（本期等于基准）。\n\n只依据材料中明确给出的数字和校区标注，不得按人均或面积归一化，不得推断措施有效性。保留所有来源编号。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;核验乙校区全部单元记录并计算校区汇总指标&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;campus&quot;: &quot;校区名称，固定为乙校区&quot;,
              &quot;records&quot;: &quot;逐条列出乙校区来源编号、基准用量、本期用量，用分号分隔&quot;,
              &quot;baseline_total&quot;: &quot;乙校区基准用量合计，仅数字&quot;,
              &quot;current_total&quot;: &quot;乙校区本期用量合计，仅数字&quot;,
              &quot;net_change&quot;: &quot;乙校区净变化，仅数字，可为负&quot;,
              &quot;increase_count&quot;: &quot;乙校区增加单元数，仅数字&quot;,
              &quot;decrease_count&quot;: &quot;乙校区减少单元数，仅数字&quot;,
              &quot;unchanged_count&quot;: &quot;乙校区持平单元数，仅数字&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 16384,
            &quot;expected_output_tokens&quot;: 1200
          },
          &quot;checks&quot;: [
            &quot;乙校区记录数量与材料一致&quot;,
            &quot;合计和净变化计算正确&quot;,
            &quot;增加、减少、持平单元数之和等于乙校区记录总数&quot;,
            &quot;保留所有来源编号&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;verify_bing&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;你是数据核验员。仅使用以下材料，不联网、不执行工具、不虚构信息。材料为虚构封闭场景「多校区用能记录分析」。\n\n请核验丙校区所有单元记录：从材料中找出所有标注「丙校区」的行，逐条列出来源编号、基准用量（千瓦时）、本期用量（千瓦时），并计算：\n1. 丙校区基准用量合计；\n2. 丙校区本期用量合计；\n3. 丙校区净变化（本期合计减基准合计）；\n4. 丙校区增加单元数（本期大于基准）；\n5. 丙校区减少单元数（本期小于基准）；\n6. 丙校区持平单元数（本期等于基准）。\n\n只依据材料中明确给出的数字和校区标注，不得按人均或面积归一化，不得推断措施有效性。保留所有来源编号。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;核验丙校区全部单元记录并计算校区汇总指标&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;campus&quot;: &quot;校区名称，固定为丙校区&quot;,
              &quot;records&quot;: &quot;逐条列出丙校区来源编号、基准用量、本期用量，用分号分隔&quot;,
              &quot;baseline_total&quot;: &quot;丙校区基准用量合计，仅数字&quot;,
              &quot;current_total&quot;: &quot;丙校区本期用量合计，仅数字&quot;,
              &quot;net_change&quot;: &quot;丙校区净变化，仅数字，可为负&quot;,
              &quot;increase_count&quot;: &quot;丙校区增加单元数，仅数字&quot;,
              &quot;decrease_count&quot;: &quot;丙校区减少单元数，仅数字&quot;,
              &quot;unchanged_count&quot;: &quot;丙校区持平单元数，仅数字&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 16384,
            &quot;expected_output_tokens&quot;: 1200
          },
          &quot;checks&quot;: [
            &quot;丙校区记录数量与材料一致&quot;,
            &quot;合计和净变化计算正确&quot;,
            &quot;增加、减少、持平单元数之和等于丙校区记录总数&quot;,
            &quot;保留所有来源编号&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;verify_ding&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;你是数据核验员。仅使用以下材料，不联网、不执行工具、不虚构信息。材料为虚构封闭场景「多校区用能记录分析」。\n\n请核验丁校区所有单元记录：从材料中找出所有标注「丁校区」的行，逐条列出来源编号、基准用量（千瓦时）、本期用量（千瓦时），并计算：\n1. 丁校区基准用量合计；\n2. 丁校区本期用量合计；\n3. 丁校区净变化（本期合计减基准合计）；\n4. 丁校区增加单元数（本期大于基准）；\n5. 丁校区减少单元数（本期小于基准）；\n6. 丁校区持平单元数（本期等于基准）。\n\n只依据材料中明确给出的数字和校区标注，不得按人均或面积归一化，不得推断措施有效性。保留所有来源编号。&quot;,
        &quot;parents&quot;: [],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;核验丁校区全部单元记录并计算校区汇总指标&quot;,
          &quot;inputs&quot;: {},
          &quot;output&quot;: {
            &quot;format&quot;: &quot;json&quot;,
            &quot;fields&quot;: {
              &quot;campus&quot;: &quot;校区名称，固定为丁校区&quot;,
              &quot;records&quot;: &quot;逐条列出丁校区来源编号、基准用量、本期用量，用分号分隔&quot;,
              &quot;baseline_total&quot;: &quot;丁校区基准用量合计，仅数字&quot;,
              &quot;current_total&quot;: &quot;丁校区本期用量合计，仅数字&quot;,
              &quot;net_change&quot;: &quot;丁校区净变化，仅数字，可为负&quot;,
              &quot;increase_count&quot;: &quot;丁校区增加单元数，仅数字&quot;,
              &quot;decrease_count&quot;: &quot;丁校区减少单元数，仅数字&quot;,
              &quot;unchanged_count&quot;: &quot;丁校区持平单元数，仅数字&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;low&quot;,
            &quot;risk&quot;: &quot;low&quot;,
            &quot;input_budget_tokens&quot;: 16384,
            &quot;expected_output_tokens&quot;: 1200
          },
          &quot;checks&quot;: [
            &quot;丁校区记录数量与材料一致&quot;,
            &quot;合计和净变化计算正确&quot;,
            &quot;增加、减少、持平单元数之和等于丁校区记录总数&quot;,
            &quot;保留所有来源编号&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      },
      {
        &quot;node_id&quot;: &quot;answer&quot;,
        &quot;node_type&quot;: &quot;generation&quot;,
        &quot;prompt_template&quot;: &quot;你是分析汇总员。仅使用以下材料和四个校区核验结果，不联网、不执行工具、不虚构信息。材料为虚构封闭场景「多校区用能记录分析」。\n\n请完成最终交付，正文必须依次包含以下部分：\n\n一、各校区核验结果\n分别呈现甲、乙、丙、丁四个校区的：记录来源编号及基准/本期用量、基准合计、本期合计、净变化、增加单元数、减少单元数、持平单元数。保留来源编号。\n\n二、整体汇总\n计算并报告：\n1. 全部单元基准用量合计；\n2. 全部单元本期用量合计；\n3. 整体净变化（本期合计减基准合计）；\n4. 整体增加单元数；\n5. 整体减少单元数；\n6. 整体持平单元数。\n\n三、有限结论\n仅基于材料给出结论，明确说明：总体减少不保证每个校区减少；材料没有气温、面积或人数；不能根据用量变化直接认定措施有效，也不能按人均或面积归一化。\n\n四、补充数据需求\n列出为得出更强结论所需但材料未提供的数据，例如气温、面积、人数、措施执行记录等，并说明这些是未知事项而非已知事实。\n\n核对四个校区结果是否存在冲突、遗漏或术语不一致；如发现冲突，在正文中指出。不得虚构原因、数据或已执行的操作。&quot;,
        &quot;parents&quot;: [
          &quot;verify_jia&quot;,
          &quot;verify_yi&quot;,
          &quot;verify_bing&quot;,
          &quot;verify_ding&quot;
        ],
        &quot;contract&quot;: {
          &quot;objective&quot;: &quot;汇总四个校区核验结果，计算整体指标，给出有限结论与补充数据需求，形成最终交付正文&quot;,
          &quot;inputs&quot;: {
            &quot;verify_jia&quot;: {
              &quot;fields&quot;: [
                &quot;campus&quot;,
                &quot;records&quot;,
                &quot;baseline_total&quot;,
                &quot;current_total&quot;,
                &quot;net_change&quot;,
                &quot;increase_count&quot;,
                &quot;decrease_count&quot;,
                &quot;unchanged_count&quot;
              ],
              &quot;reason&quot;: &quot;需要甲校区核验结果以汇总整体指标并呈现各校区分析&quot;
            },
            &quot;verify_yi&quot;: {
              &quot;fields&quot;: [
                &quot;campus&quot;,
                &quot;records&quot;,
                &quot;baseline_total&quot;,
                &quot;current_total&quot;,
                &quot;net_change&quot;,
                &quot;increase_count&quot;,
                &quot;decrease_count&quot;,
                &quot;unchanged_count&quot;
              ],
              &quot;reason&quot;: &quot;需要乙校区核验结果以汇总整体指标并呈现各校区分析&quot;
            },
            &quot;verify_bing&quot;: {
              &quot;fields&quot;: [
                &quot;campus&quot;,
                &quot;records&quot;,
                &quot;baseline_total&quot;,
                &quot;current_total&quot;,
                &quot;net_change&quot;,
                &quot;increase_count&quot;,
                &quot;decrease_count&quot;,
                &quot;unchanged_count&quot;
              ],
              &quot;reason&quot;: &quot;需要丙校区核验结果以汇总整体指标并呈现各校区分析&quot;
            },
            &quot;verify_ding&quot;: {
              &quot;fields&quot;: [
                &quot;campus&quot;,
                &quot;records&quot;,
                &quot;baseline_total&quot;,
                &quot;current_total&quot;,
                &quot;net_change&quot;,
                &quot;increase_count&quot;,
                &quot;decrease_count&quot;,
                &quot;unchanged_count&quot;
              ],
              &quot;reason&quot;: &quot;需要丁校区核验结果以汇总整体指标并呈现各校区分析&quot;
            }
          },
          &quot;output&quot;: {
            &quot;format&quot;: &quot;text&quot;,
            &quot;fields&quot;: {
              &quot;text&quot;: &quot;最终交付正文，依次包含各校区核验结果、整体汇总、有限结论、补充数据需求四部分&quot;
            }
          },
          &quot;capability&quot;: {
            &quot;difficulty&quot;: &quot;medium&quot;,
            &quot;risk&quot;: &quot;medium&quot;,
            &quot;input_budget_tokens&quot;: 65536,
            &quot;expected_output_tokens&quot;: 3000
          },
          &quot;checks&quot;: [
            &quot;正文依次包含各校区核验结果、整体汇总、有限结论、补充数据需求四部分&quot;,
            &quot;整体汇总数字与四个校区结果一致，增加/减少/持平单元数之和等于100&quot;,
            &quot;保留来源编号，事实和计算与材料一致&quot;,
            &quot;区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作&quot;,
            &quot;明确说明总体减少不保证每个校区减少，且未按人均或面积归一化&quot;
          ],
          &quot;covers&quot;: [
            0,
            1
          ],
          &quot;execution&quot;: &quot;text-model&quot;,
          &quot;failure_policy&quot;: &quot;stop&quot;
        }
      }
    ],
    &quot;final_node_id&quot;: &quot;answer&quot;,
    &quot;acceptance_criteria&quot;: [
      &quot;完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。&quot;,
      &quot;遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。&quot;
    ],
    &quot;schema_version&quot;: &quot;text-task-plan-v2&quot;,
    &quot;decomposition_reason&quot;: &quot;任务要求并行核验各校区记录并汇总整体变化、增加/减少单元数及有限结论。四个校区可独立分析，适合分支为四个校区核验节点，再由汇总节点合并并生成最终交付。拆分净收益在于并行核验减少端到端时延，同时汇总节点统一核对冲突、遗漏和术语一致性；交接开销为四个校区结果的结构化汇总，成本可控。&quot;
  },
  &quot;raw_plan_if_unparsed&quot;: null,
  &quot;planner_response_status&quot;: {
    &quot;status&quot;: &quot;billed&quot;,
    &quot;finish_reason&quot;: &quot;stop&quot;,
    &quot;output_tokens&quot;: 3305
  },
  &quot;execution_trace&quot;: [],
  &quot;final_output&quot;: null
}</pre>
</details>

待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。

