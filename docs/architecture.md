# Aegis Linux — Architecture

## Layers

```
┌────────────────────────────────────────────────────────────┐
│  ui/         Tkinter presentation                          │
│  ├─ theme.py   palette + font helpers                      │
│  ├─ widgets/   Card, ScrollableFrame, Sparkline, Gauge,    │
│  │             Sidebar, Toast, ConfirmDialog               │
│  └─ pages/    one file per page (dashboard, cleaner, …)    │
├────────────────────────────────────────────────────────────┤
│  services/    use cases — pure orchestration                │
│  ├─ cleaner_service   plan + execute + undo               │
│  ├─ health_service    composite 0-100 score                │
│  ├─ performance_service  tuning recommendations            │
│  ├─ security_service  findings aggregator                  │
│  ├─ monitor_service   1Hz periodic sampler                  │
│  └─ backup_service    tar.gz snapshots + restore            │
├────────────────────────────────────────────────────────────┤
│  rules/       declarative target / threshold lists          │
├────────────────────────────────────────────────────────────┤
│  collectors/  I/O adapters (read /proc, /sys, subprocess)  │
├────────────────────────────────────────────────────────────┤
│  domain/      pure dataclasses (no I/O, no Tk)             │
├────────────────────────────────────────────────────────────┤
│  core/        cross-cutting infra                           │
│  ├─ config       JSON config persistence (atomic)          │
│  ├─ logging      rotating file log + stderr stream         │
│  ├─ paths        XDG directories                            │
│  ├─ process      CmdResult wrapper for subprocess          │
│  ├─ concurrency  TaskRunner + MainThreadInvoker            │
│  ├─ privileges   pkexec/sudo wrapper                        │
│  └─ events       in-process pub/sub                         │
└────────────────────────────────────────────────────────────┘
```

## Threading model

The UI is single-threaded (Tk main loop). All I/O and CPU-heavy work
runs in a :class:`TaskRunner` thread pool. Callbacks invoked from
worker threads are routed through a :class:`MainThreadInvoker` which
queues them onto the Tk event loop — widget calls are safe.

```
   worker thread                     Tk main thread
        │                                  │
        │ svc.scan()                        │
        │─────────► running                 │
        │                                  │ (50ms tick)
        │                                  │ drain queue
        │                                  │ widget.after
        │                                  │
   on_done(result)                          │
        │                                  │
        │ queue.put(fn, result)            │
        │                                  │ fn(result)
```

The bridge is registered as ``root._aegis_bridge``; pages find it via
``_get_bridge(parent)`` walking up the widget tree.

## Dependency rules

* UI never imports collectors directly — it goes through services.
* Domain imports nothing from the outside world.
* Collectors only depend on ``core/`` (process, logging, paths).
* Services depend on collectors, domain, rules.
* Rules are pure data (no imports beyond stdlib).

## Config persistence

``$XDG_CONFIG_HOME/aegis/config.json`` — written atomically (temp file
+ ``os.replace``). Unknown keys are preserved via the ``_extra`` dict
so old/new clients can read each other's files.

## Backup model

``$XDG_DATA_HOME/aegis-linux/backups/`` holds tarballs. Each
reversible cleaner target snapshots its files before deletion. The
``RestorePointsPage`` lists every backup, lets the user restore or
delete. TTL pruning runs on every :class:`HealthService` invocation.

## Error handling

* Collectors never raise — return zeros / empty lists.
* Services catch per-probe exceptions; one bad probe doesn't kill the
  report.
* Privilege escalation wraps pkexec/sudo and surfaces the return code
  to the caller.
* UI failures show a toast; the main loop is never crashed by a
  widget callback.