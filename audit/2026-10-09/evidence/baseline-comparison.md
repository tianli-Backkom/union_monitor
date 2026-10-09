# 旧站功能对照

| 能力 | 合并后位置 | 结果 | 证据 |
|---|---|---|---|
|UBS跨仓总览/状态/排序/仓库CSV|#ubs|retained|ubs-browser U01–U04/U31|
|UBS单仓筛选/PR排序/分页/图表与表格耗时|#ubs/repo/NAME|retained|ubs-browser U05–U20|
|UBS全部批次/代表默认展开/质量与CSV|单仓及quality页|retained-with-defects|U24–U30/U34–U37|
|UBS统计口径/源链接/重新加载|#method和共享顶栏|retained-with-defects|U10/A03/F04|
|Triton E2E/NPU散点与选区统计|#triton|retained|T02/T03/T10–T12/A12/A13|
|Triton分支/独立状态/共享五档时间/拖拽|#triton|retained-but-new-contract-unmet|T04–T12/T22–T25/T08|
|Triton关注/全部/搜索/详情/固定悬浮卡片|#triton|retained-with-defects|T13–T15/T18–T21/T28/A01|
|Triton全页时间联动/筛选导出/跨域状态|本轮批准的新验收基准|failed|T08/T09/T16/T17/A02|
|新鲜度/近似起点/证据缺口提示|#triton|retained|截图与D08/D09；66近似批次/9倒置警告如实保留|

对照的是公开源代码、控件清单与合并版浏览器行为；两个旧站没有重新进行全部交互验收。Triton旧站为内嵌数据单页，外部 web/triton-core.js 探测404不代表旧页缺少核心函数。