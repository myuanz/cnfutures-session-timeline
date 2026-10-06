# cnfutures-session-timeline

离线计算中国期货交易区间历史，任意天和任意品种. 预期使用场景: 

- 从 CTP tick 重建分钟数据

我手工整理了所有期货 session 变动历史，如有新上线品种或交易时间调整，我会发布新版本.

节假日使用 `chinese-calendar`

## 使用

```bash
> uvx cnfutures-session-timeline 20260928 AU
2026-09-28 AU（交易日口径，北京时间）
交易：节假日或额外休市取消前置夜盘
  09:00 → 10:15
  10:30 → 11:30
  13:30 → 15:00

> uvx cnfutures-session-timeline 20260928 AU --json
{"template_name": "day-0900-1500", "periods": [{"start": "09:00:00", "end": "10:15:00"}, {"start": "10:30:00", "end": "11:30:00"}, {"start": "13:30:00", "end": "15:00:00"}], "reason": "节假日或额外休市取消前置夜盘", "effective_at": "2026-09-28"}
```

## Python API

```python
from datetime import date
from cnfutures_session_timeline import SessionTimeline

st = SessionTimeline.load()

st.resolve(date(2020, 3, 4), 'CU')
# ResolvedSession(periods=(0900~1015,1030~1130,1330~1500), COVID19暂停夜盘 @ 2020-02-04)
st.resolve(20200508, 'CU')
# ResolvedSession(periods=(2100~0100,0900~1015,1030~1130,1330~1500), 恢复夜盘 @ 2020-05-07)

st.resolve(20260101, 'IC')
# ResolvedSession(periods=(), 元旦 @ 2026-01-01)

st.resolve(20240209, "CU")
# ResolvedSession(periods=(), 除夕日额外休市 @ 2024-02-09)

st.resolve(20200508, 'EC')
# KeyError: '品种 EC 在 2020-05-08 尚未上市'
st.resolve(20250908, 'EC')
# ResolvedSession(periods=(0900~1015,1030~1130,1330~1500), 上市 @ 2023-08-18)

```

## 安装

```bash
uv add cnfutures-session-timeline
# or use pip: 
# pip install -U cnfutures-session-timeline
```

## 数据维护

- `src/cnfutures_session_timeline/future_session_events.csv`：上市、夜盘开通、时段调整，以及疫情暂停和恢复夜盘等持续生效的变更。
- `src/cnfutures_session_timeline/extra_closures.csv`：节假日之外的单日休市，目前只有 2024-02-09 的额外除夕休市

## 发布历史

### 2026.09.20

初次发布，含至今所有品种
