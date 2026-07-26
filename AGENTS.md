# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

将华为运动健康导出的加密 ZIP 文件转换为 Strava 兼容的 TCX 文件。核心功能包括：
- 解析 AES 加密的华为 ZIP 文件
- GCJ-02 到 WGS-84 坐标纠偏（解决中国境内的火星坐标系偏移）
- 生成包含心率、步频、海拔数据的 TCX 文件
- 可选的 Strava OAuth 直传功能

## Development Commands

```bash
# 安装依赖
pip install -r requirements.txt

# 本地开发运行
python -m uvicorn app:app --reload --port 8000

# Docker 部署
docker compose up -d
```

## Architecture

```
├── app.py              # FastAPI 主应用：文件上传、SSE 进度流、结果下载
├── core/parser.py      # 核心解析逻辑：ZIP 解压、坐标纠偏、TCX 生成
├── routers/strava.py   # Strava OAuth 与上传 API
├── templates/          # Jinja2 HTML 模板
└── static/             # 前端资源（Tailwind CSS、Alpine.js、字体）
```

### Key Data Flow

1. **上传**：用户上传加密 ZIP + 密码 → `POST /api/parse` → 返回 task_id
2. **解析**：后台线程解析 ZIP，通过 SSE 推送进度 → `GET /api/parse/progress/{task_id}`
3. **下载**：解析完成后下载生成的 TCX ZIP → `GET /api/download/{task_id}`

### Coordinate Conversion

华为使用 GCJ-02（火星坐标系），需要转换为 WGS-84 才能正确显示在 Strava。`core/parser.py` 中的 `gcj02_to_wgs84_exact` 使用二分法迭代实现精确转换。

### TCX Structure

- 每个 Lap 默认按 1km 自动分段，或使用华为手动分段数据
- 步频转换：华为报告双脚步数，TCX 需要单脚步数（除以 2）
- 室内运动：无 GPS 时根据 pace 节点生成虚拟轨迹以保留心率图表

## Environment Configuration

复制 `.env.example` 为 `.env` 配置 Strava 直传功能（可选）：
- `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET`：Strava API 应用凭证
- `SESSION_SECRET_KEY`：会话加密密钥

## Notes

- 临时文件存储在 `temp/` 目录，自动清理超过 1 小时的文件
- 最大上传文件 2GB，并发解析限制 3 个任务
- 前端依赖已本地化，无需外网访问即可运行