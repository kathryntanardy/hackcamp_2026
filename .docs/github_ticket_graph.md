# Ticket dependency graph

Synced from GitHub issues on 2026-11-07 (`kathryntanardy/hackcamp_2026`).
✅ = closed on GitHub **or done in workspace**. Open: **17** (#14, #17–#22, #23–#30, #32–#33). Closed/done: **16** (#1–#13, #15–#16, #31).

**New:** **#30–#33** (F14 map search + F15 categories/CWEs).

Unblocked next (deps closed): **#14**, **#18**, **#19**, **#20**, **#21**, **#22**, **#32**.
Blocked: **#17** (needs #14), **#23–#29** (`blocked-by-design` / after #22), **#30** (needs #24+#31), **#33** (needs FE + #32).

```mermaid
flowchart TB
  subgraph Platform["Platform"]
    n1["#1 workspace setup ✅"]
    n2["#2 agent tables ✅"]
  end
  subgraph IngestGold["Ingest + gold"]
    n3["#3 GitHub pull ✅"]
    n4["#4 bronze/silver ✅"]
    n5["#5 gold score ✅"]
    n31["#31 scrape desc/topics/advisories ✅"]
    n32["#32 categories + CWE buckets"]
  end
  subgraph AgentLoop["Agent tools + loop"]
    n6["#6 UC tools ✅"]
    n7["#7 live-fetch cache ✅"]
    n8["#8 triage ✅"]
    n9["#9 investigate loop ✅"]
    n10["#10 verdict+findings ✅"]
    n11["#11 MLflow traces ✅"]
  end
  subgraph EvalJobs["Eval + jobs"]
    n13["#13 eval labels ✅"]
    n14["#14 MLflow eval"]
    n15["#15 scheduled job ✅"]
    n16["#16 UC lineage ✅"]
  end
  subgraph AppServing["App + serving"]
    n12["#12 API+Apps ✅"]
    n21["#21 model serving"]
  end
  subgraph Frontend["Frontend"]
    n22["#22 design handoff"]
    n23["#23 FE scaffold"]
    n24["#24 galaxy map"]
    n25["#25 repo drawer"]
    n26["#26 trace tab"]
    n27["#27 findings page"]
    n28["#28 FE↔API"]
  end
  subgraph Stretch["Stretch / polish"]
    n17["#17 demo prep"]
    n18["#18 vector search"]
    n19["#19 run memory"]
    n20["#20 ai_query"]
    n29["#29 FE stretch"]
    n30["#30 NL map search"]
    n33["#33 category/vuln filters"]
  end
  n1 --> n2
  n1 --> n3
  n3 --> n4
  n4 --> n5
  n5 --> n6
  n2 --> n6
  n1 --> n7
  n2 --> n7
  n5 --> n8
  n2 --> n8
  n8 --> n9
  n6 --> n9
  n7 --> n9
  n9 --> n10
  n9 --> n11
  n5 --> n12
  n10 --> n12
  n11 --> n12
  n2 --> n13
  n13 --> n14
  n10 --> n14
  n11 --> n14
  n5 --> n15
  n10 --> n15
  n10 --> n16
  n12 --> n17
  n14 --> n17
  n9 --> n18
  n10 --> n19
  n5 --> n20
  n10 --> n21
  n11 --> n21
  n22 --> n23
  n23 --> n24
  n23 --> n25
  n25 --> n26
  n23 --> n27
  n24 --> n28
  n25 --> n28
  n27 --> n28
  n12 --> n28
  n28 --> n29
  n3 --> n31
  n4 --> n31
  n31 --> n32
  n24 --> n30
  n31 --> n30
  n24 --> n33
  n25 --> n33
  n27 --> n33
  n32 --> n33
```
