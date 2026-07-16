# Project Overhaul — 重构规划目录

> **创建时间**: 2026-07-11  
> **用途**: 为后续开发 agent 提供完整的重构参照文档

---

## 文件索引

| 文件 | 内容 | 适合谁看 |
|---|---|---|
| `OVERHAUL_PLAN.md` | 完整重构规划：背景、架构、目录结构、技术决策、分 5 阶段实施计划、接口定义 | **所有开发者** |
| `DATA_SCHEMA.md` | JSON 配置文件格式规范：`game.json`、`settings.json`、`ldplayer_versions.json`、`locales/*.json` | **写配置 / 改代码的人** |

---

## 快速导航

- **想了解为什么要重构？** → `OVERHAUL_PLAN.md` §1-2
- **想看目标目录结构？** → `OVERHAUL_PLAN.md` §4
- **想看为什么选 PySide6？** → `OVERHAUL_PLAN.md` §5.1
- **想看怎么开始写代码？** → `OVERHAUL_PLAN.md` §6 (Phase 1-5)
- **想看接口签名？** → `OVERHAUL_PLAN.md` §7
- **想看配置文件格式？** → `DATA_SCHEMA.md`
- **想了解多语言设计？** → `OVERHAUL_PLAN.md` §5.6
- **想添加新游戏？** → `DATA_SCHEMA.md` §7

---

## 当前状态

- [x] 规划文档完成
- [x] Phase 1: 文件结构调整 (2026-07-11)
- [x] Phase 2: Python 模块拆分 (2026-07-11)
- [x] Phase 3: 配置化 & 多游戏支持 (2026-07-11)
- [x] Phase 4: GUI 开发 (2026-07-11)
- [x] Phase 5: 打包 & 清理 (2026-07-11)
