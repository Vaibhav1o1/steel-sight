# Decisions Log

| Date | Task | Decision | Reason |
|---|---|---|---|
| 2026-10-03 | T05 | Used React 19 `useSyncExternalStore` for client hydration and localStorage sync | Prevent cascading renders and satisfy `react-hooks/set-state-in-effect` without `as` casts |
