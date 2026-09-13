(async function coeditBridge(action, p) {
  const fs = require('fs');
  const path = require('path');
  const crypto = require('crypto');
  const fail = (code, message, uncertain = false, details = {}) => {
    const error = new Error(message);
    Object.assign(error, { code, uncertain, details });
    throw error;
  };
  const hash = value => crypto.createHash('sha256').update(value, 'utf8').digest('hex');
  const now = () => new Date().toISOString();
  const inside = (root, candidate) => candidate === root || candidate.startsWith(root + path.sep);
  const absolute = value => {
    if (typeof value !== 'string' || !path.isAbsolute(value) || value.includes('\0'))
      fail('invalid-path', 'Paths must be absolute');
    return path.normalize(value);
  };
  const vault = fs.realpathSync(app.vault.adapter.getBasePath());
  const excluded = new Set(['node_modules', 'vendor', 'target', 'dist', 'build', '__pycache__']);
  const supported = value => /\.(md|typ)$/i.test(value);
  function safePath(value, absent = false) {
    const result = absolute(value);
    if (!inside(vault, result) || result === vault) fail('outside-vault', 'Document must be inside the active vault');
    const rel = path.relative(vault, result);
    if (rel.split(path.sep).some(part => part.startsWith('.') || excluded.has(part)))
      fail('excluded-path', 'Hidden/internal/generated paths are outside coedit scope');
    const check = absent && !fs.existsSync(result) ? path.dirname(result) : result;
    if (fs.realpathSync(check) !== check) fail('symlink-path', 'Aliased document paths are not supported');
    return result;
  }
  const relative = value => path.relative(vault, value).split(path.sep).join('/');
  const fromRelative = value => path.resolve(vault, value);
  const key = '__coeditRuntimeV1';
  if (app[key] && app[key].brand !== 'coedit-transient-bridge-1')
    fail('listener-collision', 'An unknown bridge owns the runtime slot');
  if (!app[key]) app[key] = { brand: 'coedit-transient-bridge-1', owners: new Map() };
  const registry = app[key];
  const ttl = 120000;

  function stateRoot(value) {
    const root = absolute(value);
    if (inside(vault, root) || (p._source_dir && inside(absolute(p._source_dir), root)))
      fail('unsafe-state-dir', 'Runtime state must be outside the vault and coedit source');
    fs.mkdirSync(root, { recursive: true, mode: 0o700 });
    if (fs.realpathSync(root) !== root) fail('unsafe-state-dir', 'Runtime state path must not be aliased');
    return root;
  }
  function durable(filename, value) {
    const temp = filename + '.' + crypto.randomUUID() + '.tmp';
    let fd;
    try {
      fd = fs.openSync(temp, 'wx', 0o600);
      fs.writeFileSync(fd, JSON.stringify(value) + '\n');
      fs.fsyncSync(fd);
      fs.closeSync(fd); fd = undefined;
      fs.renameSync(temp, filename);
      const dir = fs.openSync(path.dirname(filename), 'r');
      try { fs.fsyncSync(dir); } finally { fs.closeSync(dir); }
    } finally {
      if (fd !== undefined) fs.closeSync(fd);
      if (fs.existsSync(temp)) fs.unlinkSync(temp);
    }
  }
  function receiptFile(root, owner, operation) {
    if (typeof operation !== 'string' || !operation) fail('invalid-operation', 'Operation ID is required');
    const directory = path.join(root, 'editor-receipts', hash(owner));
    fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
    if (fs.realpathSync(directory) !== directory) fail('unsafe-state-dir', 'Receipt directory is aliased');
    return path.join(directory, hash(operation) + '.json');
  }
  function receipt(s, operation, root) {
    const filename = receiptFile(root || s.stateDir, p.owner, operation);
    if (s?.receipts.has(operation)) return s.receipts.get(operation);
    if (!fs.existsSync(filename)) return { known: false, status: 'unknown', owner: p.owner, operation_id: operation };
    const value = JSON.parse(fs.readFileSync(filename, 'utf8'));
    if (value.owner !== p.owner || value.operation_id !== operation)
      fail('receipt-corrupt', 'Receipt identity mismatch', true);
    return { ...value, known: true };
  }
  function stop(s) {
    s.closed = true;
    for (const [emitter, ref] of s.listeners) emitter.offref(ref);
    clearInterval(s.timer);
    // Tabs, including tabs opened for edits, may now be user-owned. Never close them.
    if (registry.owners.get(s.owner) === s) registry.owners.delete(s.owner);
  }
  function expired(s) {
    if (Date.now() - s.heartbeat > ttl) return true;
    if (s.pid) {
      try { process.kill(s.pid, 0); } catch (error) { if (error.code === 'ESRCH') return true; }
    }
    return false;
  }
  function owner(epoch) {
    const s = registry.owners.get(p.owner);
    if (!s || s.closed || expired(s)) {
      if (s) stop(s);
      fail('owner-expired', 'No live editor listener owns this scope');
    }
    if (epoch !== undefined && epoch !== s.epoch) fail('epoch-mismatch', 'Editor epoch changed; reconcile before writing');
    s.heartbeat = Date.now();
    return s;
  }
  function admitted(s, value, absent = false) {
    const file = safePath(value, absent);
    if (!supported(file)) fail('unsupported-format', 'Only Markdown and local Typst editors are supported');
    if (!(s.folder ? inside(s.scope, file) : file === s.scope || file === s.sidecar))
      fail('outside-scope', 'Document is outside this owner scope');
    return file;
  }
  function views(file) {
    const found = [];
    app.workspace.iterateAllLeaves(leaf => {
      if (leaf.view?.file?.path === relative(file)) found.push(leaf);
    });
    return found;
  }
  function live(file, required = false) {
    const leaves = views(file);
    if (!leaves.length) {
      if (required) fail('no-editor', 'A verified editor is required: ' + file);
      return null;
    }
    for (const leaf of leaves) {
      if (leaf.view.getViewType() !== 'markdown' || !leaf.view.editor || typeof leaf.view.editor.replaceRange !== 'function')
        fail('unsupported-view', 'Document has a non-editor or unknown open view: ' + file);
    }
    const text = leaves[0].view.editor.getValue();
    if (leaves.some(leaf => leaf.view.editor.getValue() !== text))
      fail('conflicting-views', 'Multiple live buffers disagree: ' + file);
    return { editor: leaves[0].view.editor, text, leaves };
  }
  async function openEditor(s, value) {
    const file = admitted(s, value);
    const existing = live(file);
    if (existing) return existing;
    const target = app.vault.getAbstractFileByPath(relative(file));
    if (!target || !target.extension) fail('missing-document', 'Document does not exist in the vault index');
    const active = app.workspace.activeLeaf;
    if (!active || !active.parent) fail('no-inactive-tab', 'Cannot establish an inactive tab without an existing pane');
    const parent = active.parent;
    const parents = new Map();
    app.workspace.iterateAllLeaves(leaf => parents.set(leaf, leaf.parent));
    const focused = document.activeElement;
    const leaf = app.workspace.getLeaf('tab');
    if (parents.has(leaf)) fail('unsafe-tab', 'Refusing to repurpose an existing tab');
    let claimed = false;
    let activation;
    const layoutIntact = () => leaf.parent === parent &&
      [...parents].every(([item, previous]) => item.parent === previous);
    try {
      // The factory activates synchronously. Restore only that activation, before
      // yielding; after openFile awaits, current user focus is never overwritten.
      if (app.workspace.activeLeaf === leaf) {
        app.workspace.setActiveLeaf(active, { focus: false });
        if (focused?.isConnected && typeof focused.focus === 'function') focused.focus({ preventScroll: true });
      }
      activation = app.workspace.on('active-leaf-change', current => {
        if (current === leaf) claimed = true;
      });
      if (target.extension !== target.extension.toLowerCase()) {
        // openFile's case-sensitive registry lookup otherwise launches an external
        // app. Its native editor path uses this exact setViewState contract.
        await leaf.setViewState({ type: 'markdown', state: { file: target.path }, active: false });
      } else {
        await leaf.openFile(target, { active: false });
      }
      owner(s.epoch);
      if (app.workspace.activeLeaf !== active || !layoutIntact())
        fail('pane-changed', 'Inactive editor verification failed; no document text was changed');
      return live(file, true);
    } catch (error) {
      // Only a newly allocated, never-user-activated leaf in the unchanged tab
      // group is disposable. A pre-existing or claimed tab is never detached.
      if (!claimed && app.workspace.activeLeaf !== leaf && layoutIntact()) {
        try { leaf.detach(); } catch (_) {}
      }
      throw error;
    } finally {
      if (activation) app.workspace.offref(activation);
    }
  }
  function unique(text, anchor, label) {
    if (typeof anchor !== 'string' || !anchor) fail('invalid-anchor', label + ' must be nonempty exact text');
    const start = text.indexOf(anchor);
    if (start < 0) fail('anchor-missing', label + ' no longer exists');
    if (text.indexOf(anchor, start + 1) >= 0) fail('anchor-ambiguous', label + ' occurs more than once');
    return start;
  }
  function gap(s, reason) {
    s.coverageLost = true;
    s.gapVersion++;
    s.gapReason = reason;
  }
  function capture(s, event) {
    if (s.closed) return;
    if (expired(s)) { stop(s); return; }
    const value = { ...event, seq: ++s.seq, time: now() };
    if (s.operation) value.operation_id = s.operation;
    s.events.push(value);
    if (typeof value.text === 'string') s.observed.set(value.path, value.text);
    try {
      const fd = fs.openSync(s.journal, 'a', 0o600);
      try { fs.writeFileSync(fd, JSON.stringify(value) + '\n'); fs.fsyncSync(fd); }
      finally { fs.closeSync(fd); }
    } catch (error) { gap(s, 'event-journal: ' + error.message); }
    return value;
  }
  function fence(s, after) {
    if (!Number.isSafeInteger(after) || after < s.acked || after > s.seq)
      fail('event-cursor', 'Event cursor is absent, unacknowledged coverage was lost, or cursor is ahead');
    if (s.coverageLost) fail('coverage-gap', 'Reconcile and acknowledge the coverage gap before mutation');
  }
  function guardEvents(s, after, file, anchor, label) {
    for (const event of s.events) {
      if (event.seq <= after || (event.path !== file && event.old_path !== file)) continue;
      if (event.old_path || typeof event.text !== 'string') fail('inflight-change', label + ' moved or became unreadable');
      try { unique(event.text, anchor, label); }
      catch (_) { fail('inflight-change', label + ' changed during preparation, even if subsequently reverted'); }
    }
  }
  function guardArchive(s, after, guard) {
    if (!guard) return;
    admitted(s, guard.path);
    const buffer = live(guard.path, true);
    if (buffer.text !== guard.base)
      fail('archive-base-drifted', 'Archive sidecar differs from the verified full-buffer base');
    for (const event of s.events) {
      if (event.seq > after && (event.path === guard.path || event.old_path === guard.path))
        fail('archive-inflight-change', 'Archive sidecar changed after verification, even if subsequently reverted');
    }
  }

  if (action === 'attach') {
    if (typeof p.owner !== 'string' || !p.owner) fail('invalid-owner', 'Owner is required');
    const scope = absolute(p.scope) === vault ? vault : safePath(p.scope);
    const folder = fs.statSync(scope).isDirectory();
    if (!folder && !supported(scope)) fail('unsupported-format', 'Scope file must be Markdown or local Typst');
    const sidecar = folder ? null : scope + '.notes.md';
    const stateDir = stateRoot(p.state_dir);
    for (const other of registry.owners.values()) {
      if (expired(other)) { stop(other); continue; }
      if (other.owner === p.owner) {
        if (other.scope !== scope || other.stateDir !== stateDir || (p.pid && other.pid !== p.pid))
          fail('owner-collision', 'Owner already attached with different scope, state directory or process');
        other.heartbeat = Date.now();
        return { owner: p.owner, epoch: other.epoch, vault, scope, resumed: true };
      }
      const a = folder ? [scope] : [scope, sidecar];
      const b = other.folder ? [other.scope] : [other.scope, other.sidecar];
      if (a.some(x => b.some(y => x === y || (folder && inside(x, y)) || (other.folder && inside(y, x)))))
        fail('scope-owned', 'An overlapping live editor owner exists', false, { owner: other.owner, scope: other.scope });
    }
    if (p.pid !== undefined && (!Number.isSafeInteger(p.pid) || p.pid <= 0)) fail('invalid-pid', 'Watch PID must be positive');
    const epoch = crypto.randomUUID();
    const journalDir = path.join(stateDir, 'editor-events');
    fs.mkdirSync(journalDir, { recursive: true, mode: 0o700 });
    if (fs.realpathSync(journalDir) !== journalDir) fail('unsafe-state-dir', 'Event directory is aliased');
    const s = { owner: p.owner, scope, folder, sidecar, stateDir, epoch, pid: p.pid,
      seq: 0, acked: 0, delivered: 0, events: [], receipts: new Map(), observed: new Map(),
      notices: new Map(),
      heartbeat: Date.now(), coverageLost: true, gapVersion: 1, deliveredGap: 0,
      gapReason: 'new-editor-epoch', listeners: [], closed: false, operation: null,
      journal: path.join(journalDir, hash(p.owner) + '.jsonl') };
    durable(s.journal, { epoch, kind: 'attach', time: now(), coverage_lost: true });
    registry.owners.set(p.owner, s);
    try {
      s.listeners.push([app.workspace, app.workspace.on('editor-change', (editor, view) => {
        try {
          if (!view?.file?.path) { gap(s, 'editor-event-without-file'); return; }
          const file = admitted(s, fromRelative(view.file.path));
          capture(s, { path: file, text: editor.getValue(), kind: 'change' });
        } catch (error) {
          if (!['outside-scope', 'outside-vault', 'unsupported-format', 'excluded-path'].includes(error.code))
            gap(s, 'editor-event: ' + error.message);
        }
      })]);
      s.listeners.push([app.vault, app.vault.on('rename', (file, oldPath) => {
        const previous = fromRelative(oldPath);
        const next = fromRelative(file.path);
        let oldOwned = false, newOwned = false;
        try { oldOwned = s.folder ? inside(s.scope, previous) : previous === s.scope || previous === s.sidecar; } catch (_) {}
        try { admitted(s, next); newOwned = true; } catch (_) {}
        if (!oldOwned && !newOwned) return;
        try {
          const buffer = newOwned ? live(next) : null;
          capture(s, { path: next, old_path: previous, text: buffer ? buffer.text : fs.readFileSync(next, 'utf8'), kind: 'change' });
          s.observed.delete(previous);
        } catch (error) { gap(s, 'rename: ' + error.message); }
      })]);
      s.timer = setInterval(() => {
        if (expired(s)) stop(s);
      }, 1000);
    } catch (error) { stop(s); throw error; }
    return { owner: p.owner, epoch, vault, scope, lease_ms: ttl };
  }
  if (action === 'receipt') {
    const s = registry.owners.get(p.owner);
    const root = p.state_dir ? stateRoot(p.state_dir) : s?.stateDir;
    if (!root) fail('state-dir-required', 'Receipt recovery requires state_dir after app restart');
    return receipt(s, p.operation_id, root);
  }
  if (action === 'detach') {
    const s = registry.owners.get(p.owner);
    if (s) {
      if (p.epoch !== undefined && p.epoch !== s.epoch) fail('epoch-mismatch', 'Refusing to detach a different editor epoch');
      stop(s);
    }
    return { owner: p.owner, detached: true };
  }
  const s = owner(p.epoch);
  if (action === 'snapshot') {
    const after = p.after_seq ?? s.acked;
    if (!Number.isSafeInteger(after) || after < 0) fail('event-cursor', 'Invalid snapshot cursor');
    if (after < s.acked || after > s.seq) gap(s, 'snapshot-cursor-outside-epoch');
    const files = new Set();
    const candidate = value => {
      if (!supported(value) || !(s.folder ? inside(s.scope, value) : value === s.scope || value === s.sidecar)) return;
      try { files.add(admitted(s, value)); } catch (_) {}
    };
    if (s.folder) {
      const root = s.scope === vault ? app.vault.getRoot() : app.vault.getAbstractFileByPath(relative(s.scope));
      const stack = root ? [root] : [];
      while (stack.length) {
        const entry = stack.pop();
        if (entry !== root && (entry.name.startsWith('.') || excluded.has(entry.name))) continue;
        if (Array.isArray(entry.children)) {
          for (const child of entry.children) stack.push(child);
        } else candidate(fromRelative(entry.path));
      }
    } else {
      candidate(s.scope);
      candidate(s.sidecar);
    }
    app.workspace.iterateAllLeaves(leaf => {
      if (leaf.view?.file?.path) {
        candidate(fromRelative(leaf.view.file.path));
      }
    });
    const documents = [];
    // No await: intermediate events, final live buffers, active cursor and cursor
    // acknowledgement watermark describe one coherent JS execution interval.
    for (const file of files) {
      try {
        const buffer = live(file);
        const text = buffer ? buffer.text : fs.readFileSync(file, 'utf8');
        if (s.observed.has(file) && s.observed.get(file) !== text) {
          gap(s, 'uncaptured-buffer-or-disk-change');
          capture(s, { path: file, text, kind: 'change' });
        }
        s.observed.set(file, text);
        documents.push({ path: file, text, format: path.extname(file).slice(1).toLowerCase(), editor: !!buffer });
      } catch (error) { documents.push({ path: file, error: error.code || 'unreadable', reason: error.message }); }
    }
    for (const previous of [...s.observed.keys()]) {
      if (!files.has(previous)) {
        capture(s, { path: previous, text: '', kind: 'change', deleted: true });
        s.observed.delete(previous);
      }
    }
    let active;
    const view = app.workspace.activeLeaf?.view;
    if (view?.file?.path && view.editor) {
      try {
        const file = admitted(s, fromRelative(view.file.path));
        const buffer = live(file, true);
        const units = view.editor.posToOffset(view.editor.getCursor());
        active = { path: file, cursor_offset: Array.from(buffer.text.slice(0, units)).length };
      } catch (_) {}
    }
    s.delivered = s.seq;
    s.deliveredGap = s.gapVersion;
    return { owner: s.owner, epoch: s.epoch, seq: s.seq,
      events: s.events.filter(event => event.seq > (after <= s.seq ? after : 0)), documents, active,
      coverage_lost: s.coverageLost, coverage_reason: s.coverageLost ? s.gapReason : undefined };
  }
  if (action === 'ack') {
    const through = p.through_seq;
    if (!Number.isSafeInteger(through) || through < s.acked || through > s.delivered)
      fail('event-cursor', 'Only a delivered snapshot cursor may be acknowledged');
    const remaining = s.events.filter(event => event.seq > through);
    durable(s.journal, { epoch: s.epoch, acked: through, events: remaining });
    s.events = remaining;
    s.acked = through;
    if (through === s.delivered && s.deliveredGap === s.gapVersion) s.coverageLost = false;
    return { owner: s.owner, epoch: s.epoch, acked: through };
  }
  if (action === 'ensure') {
    const file = admitted(s, p.path, true);
    if (!fs.existsSync(file)) {
      if (p.existing_only === true) fail('missing-document', 'Existing archive was removed; refusing to recreate it');
      if (!file.endsWith('.notes.md')) fail('unsafe-create', 'Only an adjacent notes sidecar may be created');
      const source = file.slice(0, -'.notes.md'.length);
      try {
        admitted(s, source);
        if (!fs.statSync(source).isFile()) fail('unsafe-create', 'Sidecar source is not a document');
      } catch (_) { fail('unsafe-create', 'Sidecar must have an existing authorized adjacent main document'); }
      owner(s.epoch);
      try { await app.vault.create(relative(file), ''); }
      catch (error) {
        // A racing creator wins; read its editor, never replace its content.
        if (!app.vault.getAbstractFileByPath(relative(file))) throw error;
      }
    }
    const buffer = await openEditor(s, file);
    return { owner: s.owner, epoch: s.epoch, path: file, text: buffer.text };
  }
  if (action === 'notice') {
    if (p.epoch === undefined) fail('epoch-required', 'Notice requires an editor epoch');
    const file = admitted(s, p.path);
    if (typeof p.raw !== 'string' || !p.raw || p.revision !== hash(p.raw))
      fail('notice-revision', 'Notice requires the exact request revision');
    if (typeof p.message !== 'string' || !p.message.trim() || p.message.length > 2000 ||
        !['info', 'warning', 'error'].includes(p.level) ||
        typeof p.key !== 'string' || !p.key || p.key.length > 512)
      fail('invalid-notice', 'Notice requires a bounded message, level and stable event key');
    fence(s, p.after_seq);
    if (p.after_seq > s.delivered)
      fail('event-cursor', 'Notice context was not delivered in a snapshot');
    for (const event of s.events) {
      if (event.seq > p.after_seq && (event.path === file || event.old_path === file))
        fail('notice-stale', 'Request document changed after the notice context');
    }
    // Read existing views or disk only: feedback never opens a tab or touches focus.
    const buffer = live(file);
    const text = buffer ? buffer.text : fs.readFileSync(file, 'utf8');
    if (!s.observed.has(file) || s.observed.get(file) !== text)
      fail('notice-stale', 'Notice document differs from the observed snapshot');
    const index = text.indexOf(p.raw);
    if (index < 0) fail('notice-stale', 'Notice request no longer exists');
    const duplicate = text.indexOf(p.raw, index + 1) >= 0;
    if (duplicate && p.level !== 'warning')
      fail('anchor-ambiguous', 'Only a duplicate warning may identify ambiguous request text');
    const identity = hash(JSON.stringify({ path: file, revision: p.revision, message: p.message, level: p.level }));
    const previous = s.notices.get(p.key);
    if (previous && previous !== identity)
      fail('notice-key-collision', 'Notice key already identifies different feedback');
    if (previous) return { owner: s.owner, epoch: s.epoch, key: p.key, shown: false, deduplicated: true };
    const line = text.slice(0, index).split('\n').length;
    const excerpt = p.raw.replace(/\s+/g, ' ').slice(0, 160);
    const { Notice } = require('obsidian');
    new Notice(`Coedit ${p.level}: ${p.message}\n${relative(file)}:${line}${duplicate ? ' (duplicate request)' : ''}\n${excerpt}\nRevision ${p.revision.slice(0, 12)}`, p.level === 'info' ? 6000 : 10000);
    // Mark only after native display succeeds; this action never touches edit receipts.
    s.notices.set(p.key, identity);
    return { owner: s.owner, epoch: s.epoch, key: p.key, shown: true, path: file, line, revision: p.revision };
  }
  if (action === 'submit') {
    if (p.epoch === undefined) fail('epoch-required', 'Submit requires an editor epoch');
    const file = admitted(s, p.path);
    if (typeof p.replacement !== 'string' || !p.replacement)
      fail('invalid-submission', 'Parser-supplied signed replacement is required');
    if (!p.replacement.includes('⏵')) fail('invalid-submission', 'Signed replacement has no submission token');
    await openEditor(s, file);
    owner(p.epoch); fence(s, p.after_seq);
    const buffer = live(file, true);
    const index = unique(buffer.text, p.raw, 'Request');
    guardEvents(s, p.after_seq, file, p.raw, 'Request');
    if (p.replacement !== p.raw) {
      s.operation = 'submit:' + crypto.randomUUID();
      try {
        buffer.editor.replaceRange(p.replacement, buffer.editor.offsetToPos(index), buffer.editor.offsetToPos(index + p.raw.length));
      } finally { s.operation = null; }
      if (buffer.editor.getValue() !== buffer.text.slice(0, index) + p.replacement + buffer.text.slice(index + p.raw.length))
        fail('submit-uncertain', 'Editor result differs from submitted revision', true);
    }
    const text = buffer.editor.getValue();
    unique(text, p.replacement, 'Submitted request');
    const event = capture(s, { path: file, text, raw: p.replacement, kind: 'submit' });
    if (s.coverageLost) fail('submit-uncertain', 'Submission capture lost coverage', true);
    return { owner: s.owner, epoch: s.epoch, raw: p.replacement, seq: event.seq, time: event.time, submitted_at: event.time };
  }
  if (action === 'write') {
    if (p.epoch === undefined) fail('epoch-required', 'Write requires an editor epoch');
    const input = hash(JSON.stringify({ request: p.request, target: p.target, proposal: p.proposal || null,
      ...(p.archive_guard !== undefined ? { archive_guard: p.archive_guard } : {}) }));
    const previous = receipt(s, p.operation_id);
    if (previous.known) {
      // Guard omission retains ordinary-write identities; a changed archive proof
      // is a different immutable input, including on uncertain receipt recovery.
      if (previous.input_sha256 !== input) fail('operation-collision', 'Operation ID was already used for different inputs', true);
      return previous;
    }
    if (!p.request || !p.target) fail('invalid-write', 'Request and target guards are required');
    const requestPath = admitted(s, p.request.path);
    const targetPath = admitted(s, p.target.path);
    const proposalPath = p.proposal ? admitted(s, p.proposal.path) : null;
    if (typeof p.target.expected !== 'string' || typeof p.target.replacement !== 'string')
      fail('invalid-write', 'Target expected and replacement must be exact strings');
    let archiveGuard = null;
    if (p.archive_guard !== undefined) {
      if (!p.archive_guard || typeof p.archive_guard !== 'object' ||
          typeof p.archive_guard.base !== 'string' || !p.archive_guard.base ||
          typeof p.archive_guard.path !== 'string' || !p.archive_guard.path.endsWith('.notes.md'))
        fail('invalid-archive-guard', 'Archive guard requires a sidecar path and exact nonempty full-buffer base');
      archiveGuard = Object.freeze({ path: admitted(s, p.archive_guard.path), base: p.archive_guard.base });
      fence(s, p.after_seq);
      guardArchive(s, p.after_seq, archiveGuard);
    }
    for (const file of new Set([requestPath, targetPath, proposalPath].filter(Boolean))) await openEditor(s, file);
    // Everything below, including the event fence and replaceRange, is synchronous.
    owner(p.epoch); fence(s, p.after_seq);
    guardArchive(s, p.after_seq, archiveGuard);
    unique(live(requestPath, true).text, p.request.raw, 'Request');
    guardEvents(s, p.after_seq, requestPath, p.request.raw, 'Request');
    if (proposalPath) {
      unique(live(proposalPath, true).text, p.proposal.expected, 'Selected proposal');
      guardEvents(s, p.after_seq, proposalPath, p.proposal.expected, 'Selected proposal');
    }
    const buffer = live(targetPath, true);
    let index;
    if (p.target.expected === '') {
      if (typeof p.target.base !== 'string' || buffer.text !== p.target.base)
        fail('append-base-drifted', 'Append requires an exact full-buffer base');
      index = buffer.text.length;
    } else index = unique(buffer.text, p.target.expected, 'Target');
    const next = buffer.text.slice(0, index) + p.target.replacement + buffer.text.slice(index + p.target.expected.length);
    const filename = receiptFile(s.stateDir, s.owner, p.operation_id);
    const record = { known: true, owner: s.owner, epoch: s.epoch, operation_id: p.operation_id,
      path: targetPath, status: 'prepared', prepared_at: now(), before_sha256: hash(buffer.text),
      after_sha256: hash(next), request_sha256: hash(p.request.raw),
      input_sha256: input, ...(archiveGuard ? { archive_guard: archiveGuard } : {}) };
    durable(filename, record);
    s.receipts.set(p.operation_id, record);
    let attempted = false;
    try {
      owner(p.epoch); fence(s, p.after_seq);
      guardArchive(s, p.after_seq, archiveGuard);
      const current = live(targetPath, true);
      if (current.editor !== buffer.editor || current.text !== buffer.text)
        fail('prepared-target-drifted', 'Target editor changed after durable preparation; no mutation was attempted');
      unique((requestPath === targetPath ? current : live(requestPath, true)).text, p.request.raw, 'Request');
      guardEvents(s, p.after_seq, requestPath, p.request.raw, 'Request');
      if (proposalPath) {
        unique((proposalPath === targetPath ? current : live(proposalPath, true)).text, p.proposal.expected, 'Selected proposal');
        guardEvents(s, p.after_seq, proposalPath, p.proposal.expected, 'Selected proposal');
      }
      s.operation = p.operation_id;
      attempted = true;
      buffer.editor.replaceRange(p.target.replacement, buffer.editor.offsetToPos(index),
        buffer.editor.offsetToPos(index + p.target.expected.length));
      if (buffer.editor.getValue() !== next) fail('postwrite-mismatch', 'Editor changed the result during the transaction', true);
      // Verify every open view after the transaction, not only the selected editor.
      live(targetPath, true);
      const result = { ...record, status: 'committed', committed_at: now(), seq: s.seq };
      durable(filename, result);
      s.receipts.set(p.operation_id, result);
      return result;
    } catch (error) {
      const result = { ...record, status: attempted ? 'uncertain' : 'rejected',
        attempted, error: error.message, error_code: error.code, time: now() };
      try { durable(filename, result); }
      catch (receiptError) {
        result.status = 'uncertain';
        result.receipt_error = receiptError.message;
      }
      s.receipts.set(p.operation_id, result);
      if (result.status === 'rejected')
        fail(error.code || 'write-rejected', error.message, false, result);
      fail('write-uncertain', 'Editor transaction may have committed; inspect receipt and live document', true, result);
    } finally { s.operation = null; }
  }
  fail('invalid-action', 'Unknown editor bridge action');
})
