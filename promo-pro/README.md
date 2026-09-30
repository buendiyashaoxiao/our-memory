# 美高 / 美本物理 · 高级感宣传片（竖屏 1080×1920 · 43 秒）

成片：`promo.mp4`（静音轨，建议配一段氛围感钢琴 / 电子 BGM，在碰撞 2.6s 处卡一个重低音）

## 分镜

| 时间 | 画面 | 文字 |
|---|---|---|
| 0–6s | 两颗粒子加速对撞 → 白光闪爆 + 冲击波 → 800 个火花散开，带电粒子在磁场里画出气泡室螺旋轨迹 | The universe runs on a handful of equations. / 宇宙，只靠几条方程运转 |
| 6–12s | 恒星与四颗行星按开普勒定律运行（近日点快、远日点慢） | CLASSICAL MECHANICS · F = G m₁m₂ / r² · 经典力学 |
| 12–18s | 正负电荷的电场线逐条展开，粒子沿场线流动 | ELECTRICITY & MAGNETISM · ∇·E = ρ/ε₀ · 电磁学 |
| 18–25s | 双波源干涉，点阵随波起伏，干涉条纹逐渐显现 | WAVES & QUANTUM · iħ∂ψ/∂t = Ĥψ · 波动与量子 |
| 25–31s | 上千颗粒子旋转汇聚成「PHYSICS」 | 美高 · 美本物理 / AP Physics 1·2·C / Honors · IB HL / University Physics I & II |
| 31–37s | 旋臂星系缓慢转动 | 01 先建立物理直觉 / 02 英文术语 · 中文讲透 / 03 从 AP 冲 5 分到大学高年级课 |
| 37–43s | 星系坍缩成一点 → 爆发成星空 | Physics, understood. / 把物理，真正学懂 / @你的账号名 |

## 重新生成

1. 改 `promo.html`（账号名搜索「@你的账号名」；每行文字的出现时间在 `data-a` / `data-b`）。浏览器直接打开可循环预览。
2. 字体放在 `fonts/`（Google Fonts：Cormorant Garamond、Inter、Noto Serif SC、STIX Two Text），文件名见 `promo.html` 顶部 `@font-face`。
3. `node render.mjs` 输出 `promo.mp4`；`node render.mjs --stills 3,15,28` 只导出截图。
