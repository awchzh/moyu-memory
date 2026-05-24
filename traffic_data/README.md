# MOYU Traffic Data Archive

GitHub Traffic API 只保留 14 天的数据。此目录保存历史快照，永久存档。

## 文件说明

| 文件 | 内容 |
|------|------|
| `clone_data.csv` | 当前 14 天克隆数据（实时刷新） |
| `view_data.csv` | 当前 14 天浏览数据（实时刷新） |
| `clone_data_YYYY-MM.csv` | 历史月存档 |
| `view_data_YYYY-MM.csv` | 历史月存档 |

## 数据刷新

每周日 10:00 自动拉取最新 14 天数据（cron job `github-traffic-tracker`）。
每月首日运行时自动生成月存档。
