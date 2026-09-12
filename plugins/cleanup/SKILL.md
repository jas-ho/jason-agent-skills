---
name: cleanup
description: "System health check and cleanup - memory, processes, caches, startup items"
---

## Harness and dependencies

Use the current harness's native file, shell, question and worker tools. CC calls its question tool AskUserQuestion; OMP uses ask; Codex uses the question interface actually exposed in the session, with a plain question when unavailable. Tool names in examples describe operations, not a requirement to nest Claude Code. Incoming command arguments are literal user text, never shell code. A skill invocation may supply the same text directly. Check each required CLI/service before its step; keep the workflow available and report missing dependencies. Preserve explicitly optional signal behavior below.

## Platform routing

Run `uname -s` first. The detailed commands below are macOS diagnostics. On Linux use `uptime`, `free -h`, `df -h`, `ps -eo user,pid,ppid,pcpu,rss,etime,comm --sort=-rss`, `systemctl --failed` and `systemctl --user --failed`; inspect only relevant user caches with `du`. Skip Apple-only pressure/thermal/GUI commands and label them not applicable. Inventory Claude, Codex and OMP processes by observed PID, parent, cwd and tmux ownership, not only Claude's process name. Age alone does not prove abandonment. Never terminate a session or service as a diagnostic; cairn's concierge is service-owned and must only be managed with the supported concierge command when requested.

# System Cleanup Skill

Run all diagnostics and present a prioritized health report with clear recommendations.

## Diagnostic Commands

**IMPORTANT:** Run ALL commands below as separate parallel Bash tool calls in a SINGLE response. This allows slow commands (cache du, memory_pressure) to run concurrently with fast ones.

### Fast diagnostics (run in parallel with everything else)

```bash
# 1. Uptime, memory, swap, disk in one shot (fallback if fastfetch missing)
fastfetch -l none -s Uptime:Memory:Swap:Disk --pipe 2>/dev/null || { uptime; sysctl vm.swapusage; df -h /System/Volumes/Data | tail -1; }
```

```bash
# 2. Top memory consumers
ps aux -m | head -1 && ps aux -m | head -21 | tail -20
```

```bash
# 3. High CPU processes (user column matters: only suggest kill for user-owned app processes)
ps -eo user,pid,pcpu,etime,comm -r | head -15
```

```bash
# 4. Claude sessions with PID, terminal, start time, memory
# (pgrep + ps -p, NOT `ps | grep` — piping ps into grep can silently return nothing in sandboxed shells)
pgrep -x claude >/dev/null && ps -o pid,tty,lstart,rss,command -p "$(pgrep -x claude | paste -sd, -)" || echo "no claude sessions found"
```

```bash
# 5a. MCP/LSP servers (dynamic - catches any *mcp*, pyright, langserver)
# bracket trick in the pattern stops pgrep -f matching this command's own shell wrapper
P=$(pgrep -if "[m]cp|[p]yright|[l]angserver" | head -15 | paste -sd, -); [ -n "$P" ] && ps -o pid,ppid,etime,rss,command -p "$P" || echo "none"
```

```bash
# 5b. Sleep blockers: caffeinate, any sleep assertion holder, and the keepawake kernel flag
pgrep -x caffeinate >/dev/null && ps -o pid,etime,command -p "$(pgrep -x caffeinate | paste -sd, -)" || echo "no caffeinate"
pmset -g assertions 2>/dev/null | grep -iE "pid [0-9]+.*Prevent" | head -6   # assertion holders with owning PID
pmset -g | grep -i sleepdisabled   # flag only if value is 1 = keepawake-style kernel flag (Mac will NOT sleep, even lid-closed)
```

```bash
# 5c. Tmux check
pgrep -x tmux >/dev/null && echo "TMUX_RUNNING=yes" || echo "TMUX_RUNNING=no"
```

```bash
# 6a. Thermal state
pmset -g therm 2>/dev/null
```

```bash
# 6b. Docker
docker system df 2>/dev/null || echo "Docker unavailable or not running"
```

### Slow diagnostics (run in parallel - these take time)

```bash
# 7. Memory pressure (can take 2-5 seconds; free-percentage is the LAST line, so no head)
memory_pressure 2>/dev/null | grep -i "free percentage"; echo "vm_pressure_level=$(sysctl -n kern.memorystatus_vm_pressure_level 2>/dev/null)"
# vm_pressure_level: 1=normal, 2=warn, 4=critical
```

```bash
# 8. Dev caches - scan ~/.cache/, ~/.npm, ~/.bun, homebrew (dynamic)
du -sh ~/.cache/*/ ~/.npm ~/.bun ~/Library/Caches/Homebrew 2>/dev/null | sort -hr | head -10
```

```bash
# 9. App caches - top 10 largest (dynamic)
du -sh ~/Library/Caches/*/ 2>/dev/null | sort -hr | head -10
```

```bash
# 10a. Dev tools - Xcode, Android, other dev caches (dynamic)
du -sh ~/Library/Developer/*/ 2>/dev/null | sort -hr | head -5
```

```bash
# 10b. Time Machine snapshots
tmutil listlocalsnapshots / 2>/dev/null | head -5
```

## Output Format

**All values, PIDs, app names, and sizes in the template below are illustrative placeholders — only report what the diagnostics actually observed. Never copy example numbers or commands into the report.**

Present as a single health report:

````
## System Health Report

### 🎯 Status & Recommendation

[Based on memory_pressure output, give ONE clear recommendation]

Examples:
- "Memory pressure: NORMAL. System is healthy."
- "Memory pressure: WARN. Consider closing some apps or restarting soon."
- "Memory pressure: CRITICAL. Restart your Mac now."

### 📊 Quick Stats

| Metric | Value | Note |
|--------|-------|------|
| Memory Pressure | [from memory_pressure] | [status emoji] |
| Uptime | X days | [🟢 <7d / 🟡 7-14d / 🔴 >14d] |
| Swap Used | X GB / [total reported by fastfetch or vm.swapusage] | [only flag if pressure is bad] |
| Disk | X GiB / Y GiB (Z%) | [🟢 <80% / 🟡 80-90% / 🔴 >90%; note df can overstate usage — purgeable/snapshot space is reclaimed automatically] |

### 🔥 High CPU (if any >50% for >1hr)

[Only show if processes found. Flag anything using >50% CPU that's been running >1 hour]

| PID | CPU | Runtime | Process | Action |
|-----|-----|---------|---------|--------|
| 26815 | 100% | 1-02:56 | Microsoft Edge | Restart app |

### 🧠 Top Memory Users

[Table of top 5-8 apps by memory, with notes on anything unusual]

| App | Memory | Note |
|-----|--------|------|
| Claude (7 sessions) | ~3.5GB | See sessions below |
| Claude infra (MCP, chroma) | ~10GB | Supporting services |
| Microsoft Edge | 4.0GB | Running 3+ days - restart it |
| Notion | 1.5GB | Normal |

### 🤖 Claude Sessions

[List all Claude sessions with PID, age, and memory - sorted oldest first]

| PID | Terminal | Age | Memory | Status |
|-----|----------|-----|--------|--------|
| 88825 | s002 | 3 days | 472MB | 🟡 Stale |
| 24666 | s012 | 5 days | 189MB | 🟡 Stale |
| 62249 | s007 | 9 hours | 525MB | Active |
| 89060 | s010 | 2 min | 637MB | Current |

### ⚡ Quick Actions

**Kill runaway CPU process:** (if flagged above — kill by observed PID, not by name; `comm` names often don't match `pkill` patterns)
```bash
kill <PID> && sleep 2 && open -a "<App>"
````

**Kill stale Claude sessions:**

```bash
kill 88825 24666  # Sessions from Mon, Fri
```

**Clean dev caches (safe, frees ~23GB):**

```bash
npm cache clean --force && brew cleanup -s && pip cache purge 2>/dev/null
```

**Restart memory-heavy apps** (killall sends TERM = normal quit for GUI apps; only suggest for apps without unsaved-work risk):

```bash
# Restart Edge (saves ~4GB, loses tabs - they restore on reopen)
killall "Microsoft Edge"

# Restart Notion (saves ~1.5GB)
killall "Notion"
```

[Only show if tmux is running:]
**Find which tmux window owns a session's tty** (tty suffix does NOT map to window index):

```bash
tmux list-panes -a -F "#{session_name}:#{window_index} #{pane_tty}"   # then: tmux switch-client -t <session>
```

### 🗑️ Cleanup Opportunities

**Dev Caches** (won't fix sluggishness, but frees disk):

| Cache    | Size  | Command                   |
| -------- | ----- | ------------------------- |
| uv       | 11GB  | `uv cache clean`          |
| npm      | 8.2GB | `npm cache clean --force` |
| Homebrew | 3.9GB | `brew cleanup -s`         |
| pip      | -     | `pip cache purge`         |

**App Caches** (quit the app first; can reset app state / log you out; use `trash`, not `rm -rf`, so it's recoverable):
[Show top entries from dynamic scan of ~/Library/Caches/]

| App                | Size  | Command                                           |
| ------------------ | ----- | ------------------------------------------------- |
| com.spotify.client | 2.5GB | `trash "$HOME/Library/Caches/com.spotify.client"` |
| Google             | 1.4GB | `trash "$HOME/Library/Caches/Google"`             |

Quote every generated path — cache directory names can contain spaces.

**Other** (if present and significant):

- Xcode DerivedData: X GB → `trash ~/Library/Developer/Xcode/DerivedData`
- Playwright browsers: X GB → `trash ~/Library/Caches/ms-playwright`
- Docker: X GB → `docker system prune` (broad: removes stopped containers, unused networks, dangling images, build cache)

### ⚠️ Potential Issues

[Only show section if there are issues to report]

- **Orphan MCP/LSP servers:** Found X processes (from grep _mcp_|pyright|langserver). Will be cleaned on restart.
- **Stale caffeinate:** PID XXXX running for X days preventing sleep. Kill with: `kill XXXX`
- **SleepDisabled flag on:** keepawake-style kernel flag is set — Mac cannot sleep even lid-closed (battery drain/heat risk). If no keepawake run is intentionally active: `sudo pmset -a disablesleep 0`
- **Thermal throttling:** [if pmset shows throttling]
- **High swap with pressure:** System is thrashing. Restart recommended.

```

## Decision Logic

### Primary Recommendation (pick ONE, in priority order)

1. **If vm_pressure_level=4 (critical):**
   → "🔴 Restart your Mac now. Memory pressure is critical."

2. **If any process >50% CPU for >1 hour:**
   → "🔴 [App] is using [X]% CPU for [runtime]. Restart it: `kill [PID]` then reopen" (kill by PID — `comm` names rarely match `pkill` patterns)
   Only recommend kill for clearly user-owned app processes. For system processes (root-owned, WindowServer, kernel_task, mds_stores, backupd, security agents), report the issue and suggest investigation or a reboot instead — killing them can log the user out or is a symptom, not the cause (e.g. mds_stores = Spotlight reindexing).

3. **If vm_pressure_level=2 (warn) + uptime >7d:**
   → "🟡 Consider restarting. Memory pressure is elevated and uptime is [X] days."

4. **If uptime >14d (regardless of pressure):**
   → "🟡 Consider restarting soon. [X] days uptime can accumulate memory leaks."

5. **If multiple stale Claude sessions (>2 from previous days):**
   → "🟢 System healthy. You have [N] old Claude sessions to clean up."

6. **Otherwise:**
   → "🟢 System is healthy. No action needed."

### Stale Session Definition

A Claude session is "stale" if it started on a previous day. This is a suggestion only — the user may have long-running sessions on purpose. Frame kill commands as optional and suggest checking the session's tmux window first.

### Age Calculation

Convert start times to relative age:
- Today: show "X hours" or "X min"
- Yesterday: show "1 day"
- This week: show "X days"
- Older: show "X days" with day name (e.g., "5 days (Fri)")

### Claude Memory Breakdown

Separate Claude processes into:
1. **Sessions**: Main `claude` processes attached to terminals (user sessions)
2. **Infrastructure**: MCP servers (pyright, workspace-mcp, context7-mcp, chroma-mcp), worker processes

This helps users understand why "Claude" shows high memory - it's not just sessions.

### What NOT to Do

- Do NOT auto-kill any processes
- Do NOT auto-delete any caches
- Do NOT present disk cleanup as fixing sluggishness (it doesn't)
- Do NOT alarm about high swap if pressure is normal
- Do NOT give complex threshold explanations
- Do NOT show empty cache entries (skip if 0 or missing)

### Tone

- Direct and actionable
- One clear recommendation at the top
- Copy-paste commands in Quick Actions
- Details below for those who want them

## Notes for Implementation

1. **Parallel execution:** Run all diagnostic commands in parallel for speed
2. **Parse memory_pressure:** "System-wide memory free percentage" line + the sysctl level (1=normal, 2=warn, 4=critical). If fastfetch was missing, the fallback prints raw uptime/sysctl/df — extract the same four metrics from those.
3. **Detect high CPU:** From CPU-sorted ps output, flag any process >50% CPU with etime >1 hour (format: HH:MM:SS or D-HH:MM:SS)
4. **Aggregate by app:** From ps output, mentally group processes by app (e.g., sum all Microsoft Edge Helper processes)
5. **Calculate ages:** Convert `lstart` to relative time (days/hours/minutes ago)
6. **Extract PIDs:** Include PIDs in session table for kill commands
7. **Group Claude processes:** Separate sessions (with TTY) from infrastructure (no TTY or known MCP names)
8. **Build kill command:** Collect stale session PIDs into single `kill` command
9. **Skip missing items:** If Xcode/Docker not installed, don't show those sections
10. **Detect tmux:** If tmux running, show window switching tips
11. **Keep it scannable:** User should get the answer in 3 seconds from the top section
```
