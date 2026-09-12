---
name: ak-release
description: Prepare a repository release using the external Apart Kit release workflow, including changelog and announcement drafts. Publishing follows the user's authorized scope; this adapter never sends announcements.
---

# Apart Kit release adapter

Apart Kit remains the source owner. Resolve its external repository through the configured agent-config root; the current Mac source is `~/Code/apart-kit/commands/dev/release.md`. Read that command before using the workflow. If it is missing, report the missing external source; do not migrate or recreate it here. Read the target repository's instructions as well.

Apply the source's release analysis, versioning, changelog, demo selection and announcement preparation using native file/shell tools. Preserve the user's target repository and already approved version/scope. Determine whether there is a previous tag before constructing a range; if none exists, inspect full history instead of using an invalid `..HEAD` fallback. Use the actual branch and specific release tag, not a blanket push of all tags. Do not run mutating demo commands merely to produce a recording.

Before drafting an announcement addressed to others, read the applicable writing guidance (`~/.claude/context-writing.md` on the configured Mac). Produce the draft locally. This adapter stops before sending announcements or email. Commit/tag/push/release publication proceeds only when covered by the user's release instruction; if the request was preparation only, finish the concrete draft and checks before asking about publication. Do not repeat permission already supplied. Apply the target repository's existing validation and review gates.

Use recoverable trash for temporary demo files, replacing the vendor example's `rm`. Resolve native tool schemas and supported CLI syntax rather than carrying over CC `allowed-tools`, shell pre-expansion, or fictional tool names. Preserve the external source unchanged.
