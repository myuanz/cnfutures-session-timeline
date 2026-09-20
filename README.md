# cnfutures-session-timeline

获取中国期货交易区间历史，任意天和任意品种. 预期使用场景: 

- 从 CTP tick 重建分钟数据

我手工整理了所有期货 session 变动历史，如有新上线品种或交易时间调整，我会发布新版本.

## 用例

```python
from datetime import date
from cnfutures_session_timeline import SessionTimeline

st = SessionTimeline.load()

st.resolve(date(2020, 3, 4), 'CU')
# ResolvedSession(periods=(0900~1015,1030~1130,1330~1500), COVID19暂停夜盘 @ 2020-02-04)
st.resolve(20200508, 'CU')
# ResolvedSession(periods=(2100~0100,0900~1015,1030~1130,1330~1500), 恢复夜盘 @ 2020-05-07)

st.resolve(20260101, 'IC')
# ResolvedSession(periods=(0930~1130,1300~1500), 调整交易时间 @ 2016-01-04)

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

## 发布历史

### 2026.09.20

初次发布，含至今所有品种
