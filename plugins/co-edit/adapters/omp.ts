import { spawn, type ChildProcess } from "node:child_process";
import { fileURLToPath } from "node:url";
import { basename, dirname, relative, resolve } from "node:path";
import { StringDecoder } from "node:string_decoder";
import type { ExtensionAPI, ExtensionContext } from "@oh-my-pi/pi-coding-agent";
import { Text } from "@oh-my-pi/pi-tui";

const RUNTIME = fileURLToPath(
	new URL("../scripts/runtime.py", import.meta.url),
);
const INTENT = "coedit.scope.v1";
const PLAN_NOTE =
	"Plan mode collects pending work but aside hints do not start model turns; leave plan mode to process coedit.";
const MAX_EVENT = 1_048_576;
const MAX_REPLY = 16_777_216;
const BATCH_MS = 500;
type Json = Record<string, any>;
type Intent = { sessionId: string; scope: string; enabled: boolean };
type Watch = {
	owner: string;
	scope: string;
	child: ChildProcess;
	stop: () => Promise<void>;
};

function singleLine(value: unknown, limit = 160): string {
	const text = String(value ?? "")
		.replace(/[\u0000-\u001f\u007f]/g, " ")
		.replace(/\s+/g, " ")
		.trim();
	return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function location(row: Json, scope?: string): string {
	if (typeof row.file !== "string") return "";
	const root = scope && /\.(md|typ)$/i.test(scope) ? dirname(scope) : scope;
	const local = root ? relative(root, row.file) : basename(row.file);
	return `${singleLine(local && !local.startsWith("..") ? local : basename(row.file))}:${row.line ?? "?"}`;
}

function timingLine(timings: Json = {}): string {
	const submitted = Date.parse(timings.submitted_at);
	if (!Number.isFinite(submitted)) return "";
	const parts = [`Signed ${new Date(submitted).toISOString().slice(11, 19)}Z`];
	for (const [key, label] of [
		["hint_emitted_at", "emitted"],
		["adapter_received_at", "received"],
		["handoff_at", "handed off"],
		["queue_confirmed_at", "queue confirmed"],
		["picked_up_at", "picked up"],
		["committed_at", "committed"],
		["archived_at", "archived"],
	]) {
		const at = Date.parse(timings[key]);
		if (!Number.isFinite(at)) continue;
		const seconds = (at - submitted) / 1000;
		parts.push(
			`${label} ${seconds < 0 ? "(clock order changed)" : `+${seconds.toFixed(seconds < 10 ? 1 : 0)}s`}`,
		);
	}
	return parts.join(" · ");
}

function requestLines(row: Json, scope?: string, expanded = false): string[] {
	const state =
		row.state === "needs-resubmission"
			? row.generation
				? "needs a new sign"
				: "unsigned"
			: singleLine(row.state);
	const lines = [
		`${singleLine(row.summary || row.raw)} · ${state}${row.blocked ? " · blocked" : ""}`,
		`${location(row, scope)}${row.next_action?.label ? ` · Next: ${singleLine(row.next_action.label, 240)}` : ""}`,
	];
	if (expanded) {
		if (row.reason) lines.push(singleLine(row.reason, 320));
		const outcomes = Object.entries(row.recovery ?? {}).filter(
			([, value]) =>
				value && typeof value === "object" && (value as Json).status !== "none",
		);
		if (outcomes.length)
			lines.push(
				outcomes
					.map(
						([kind, value]) => `${kind}: ${singleLine((value as Json).status)}`,
					)
					.join(" · "),
			);
		const timing = timingLine(row.timings);
		const historical = row.state === "needs-resubmission";
		if (timing)
			lines.push(historical ? `Previous submission · ${timing}` : timing);
		lines.push(
			historical
				? `Current text ${singleLine(row.revision, 12)} · last signed submission ${row.generation ?? 0}${row.submitted_revision ? ` (${singleLine(row.submitted_revision, 12)})` : ""}`
				: `Revision ${row.generation ?? 0} · ${singleLine(row.revision, 12)}`,
		);
		if (row.link) lines.push(String(row.link));
	}
	return lines;
}

function resultText(value: Json, expanded = false): string {
	if (value.error)
		return `Coedit: ${singleLine(value.error.message ?? value.error, expanded ? 1000 : 240)}${value.error.code ? ` (${singleLine(value.error.code)})` : ""}`;
	if (value.stopped)
		return "Coedit stopped; documents and pending work preserved.";
	const scope = value.scope ?? value.adapter?.scope ?? value.scopes?.[0]?.scope;
	const lines: string[] = [];
	if (Array.isArray(value.scopes)) {
		const active = value.scopes.some((item: Json) => item.active);
		lines.push(
			`Coedit · ${value.ready ? "ready" : active ? "not ready" : "stopped"}${scope ? ` · ${singleLine(scope)}` : ""}${value.hold ? " · applies held" : ""}${value.pause ? " · notifications paused" : ""}`,
		);
	}
	if (value.request) {
		lines.push(...requestLines(value.request, scope, expanded));
		if (expanded && typeof value.document?.text === "string") {
			const source = value.document.text.split("\n");
			const start = Math.max(0, Number(value.request.line ?? 1) - 2);
			lines.push(
				"",
				...source
					.slice(start, start + 12)
					.map((line: string) => singleLine(line, 240)),
			);
		}
	} else if (Array.isArray(value.pending)) {
		const limit = expanded ? 24 : 4;
		for (const row of value.pending.slice(0, limit))
			lines.push(...requestLines(row, scope, expanded), "");
		if (value.pending.length > limit)
			lines.push(`${value.pending.length - limit} more · /coedit pending`);
		if (!value.pending.length) lines.push("No pending requests.");
	}
	const current = value.diagnostics?.current;
	if (Array.isArray(current))
		for (const issue of current.slice(0, expanded ? 8 : 2))
			lines.push(`Current: ${singleLine(issue.message ?? issue.code, 240)}`);
	const history = value.diagnostics?.history;
	if (expanded && Array.isArray(history) && history.length) {
		lines.push("Recovered/history:");
		for (const issue of history.slice(-4))
			lines.push(
				`  ${singleLine(issue.message ?? issue.code, 200)}${issue.recovered_at ? ` · recovered ${issue.recovered_at}` : ""}`,
			);
	}
	if ("snapshot_error" in value) {
		lines.push(
			`Receipts refreshed for revision ${value.generation}; no document mutation.`,
		);
		if (value.snapshot_error)
			lines.push(
				`Current snapshot unavailable: ${singleLine(value.snapshot_error.message ?? value.snapshot_error)}`,
			);
		if (expanded)
			for (const [kind, outcome] of Object.entries(value.recovery ?? {}))
				lines.push(`  ${kind}: ${singleLine((outcome as Json).status)}`);
	}
	if (!lines.length) {
		if (value.status) lines.push(`Coedit · ${singleLine(value.status)}`);
		else if (typeof value.hold === "boolean")
			lines.push(
				value.hold
					? "Coedit applies held; collection continues."
					: "Coedit applies released.",
			);
		else if (typeof value.pause === "boolean")
			lines.push(
				value.pause
					? "Coedit notifications paused; collection continues."
					: "Coedit notifications resumed.",
			);
		else lines.push("Coedit operation completed.");
	}
	if (expanded && value.operation_id)
		lines.push(`Receipt: ${value.operation_id}`);
	if (value.type === "ready" && value.limitation)
		lines.push("Plan mode collects requests without idle model wake.");
	return lines.join("\n").trim();
}

function resultDetails(result: Json): Json {
	if (result.details && Object.keys(result.details).length)
		return result.details;
	const text =
		result.content?.find((part: Json) => part.type === "text")?.text ?? "";
	try {
		return JSON.parse(text);
	} catch {
		return { error: { message: text || "No runtime result available." } };
	}
}

// The runtime alone owns authorization, request parsing, leases and write receipts.
export default function coeditExtension(pi: ExtensionAPI) {
	const z = pi.zod;
	const parameters = z.object({
		op: z.enum([
			"start",
			"status",
			"pending",
			"read",
			"write",
			"state",
			"resolve",
			"reconcile",
			"hold",
			"pause",
			"submit",
			"stop",
		]),
		scope: z.string().optional(),
		request_id: z.string().optional(),
		generation: z.number().int().optional(),
		operation_id: z.string().optional(),
		target: z
			.object({
				path: z.string(),
				expected: z.string(),
				replacement: z.string(),
				base: z.string().optional(),
			})
			.optional(),
		proposal: z
			.object({ path: z.string(), expected: z.string() })
			.nullable()
			.optional()
			.describe(
				"Exact selected proposal guard; null or omitted for a direct edit. Never invent an empty proposal.",
			),
		purpose: z.enum(["apply", "answer", "proposal"]).optional(),
		state: z.enum(["working", "awaiting-user"]).optional(),
		reason: z.string().optional(),
		record: z.string().optional(),
		cleanup: z
			.array(z.object({ path: z.string(), expected: z.string() }))
			.optional(),
		reviewed: z
			.boolean()
			.optional()
			.describe(
				"True only when the user explicitly reviewed the current answer and requested archival. Never infer review from silence or a completed answer.",
			),
		value: z.boolean().optional(),
	});
	let watch: Watch | undefined;
	let changing = false;
	let stopRequested = false;
	let intent: Intent | undefined;
	let transition: Promise<unknown> = Promise.resolve();
	const activeCalls = new Set<() => void>();

	function serialize<T>(action: () => Promise<T>): Promise<T> {
		const next = transition.then(action, action);
		transition = next.catch(() => {});
		return next;
	}
	function log(error: unknown) {
		pi.logger.error(`Coedit: ${String(error)}`);
	}
	function group(child: ChildProcess, signal: NodeJS.Signals) {
		if (!child.pid) return;
		try {
			process.kill(-child.pid, signal);
		} catch (error) {
			if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error;
		}
	}
	function persist(ctx: ExtensionContext, scope: string, enabled: boolean) {
		intent = { sessionId: ctx.sessionManager.getSessionId(), scope, enabled };
		pi.appendEntry(INTENT, intent);
	}
	function saved(ctx: ExtensionContext): Intent | undefined {
		const id = ctx.sessionManager.getSessionId();
		// Entire session, not current branch: rewinding history cannot undo an explicit stop.
		const entries = ctx.sessionManager.getEntries();
		for (let index = entries.length - 1; index >= 0; index--) {
			const entry = entries[index];
			if (entry.type !== "custom" || entry.customType !== INTENT) continue;
			const data = entry.data as Intent | undefined;
			if (
				data?.sessionId === id &&
				typeof data.scope === "string" &&
				typeof data.enabled === "boolean"
			)
				return data;
		}
	}
	function call(payload: Json, signal?: AbortSignal): Promise<Json> {
		if (changing || (stopRequested && payload.op !== "stop") || signal?.aborted)
			return Promise.reject(new Error("Coedit call cancelled before dispatch"));
		const {
			promise,
			resolve: resolveCall,
			reject,
		} = Promise.withResolvers<Json>();
		const child = spawn("python3", [RUNTIME, "call"], {
			detached: true,
			stdio: ["pipe", "pipe", "pipe"],
		});
		let stdout = "",
			stderr = "",
			size = 0,
			settled = false;
		const out = new StringDecoder("utf8"),
			err = new StringDecoder("utf8");
		const timer = setTimeout(
			() =>
				fail(
					new Error(
						`Coedit runtime timed out; operation ${payload.operation_id ?? payload.op} may be uncertain. Query status/receipts; do not blindly retry.`,
					),
				),
			payload.op === "write" || payload.op === "resolve" ? 180_000 : 60_000,
		);
		function finish(error?: Error, result?: Json) {
			if (settled) return;
			settled = true;
			clearTimeout(timer);
			signal?.removeEventListener("abort", abort);
			activeCalls.delete(abort);
			if (error) reject(error);
			else resolveCall(result!);
		}
		function fail(error: Error) {
			try {
				group(child, "SIGKILL");
			} catch (failure) {
				log(failure);
			}
			finish(error);
		}
		function abort() {
			fail(
				new Error(
					`Coedit call interrupted; operation ${payload.operation_id ?? payload.op} may have committed. Query status/receipts before further writes.`,
				),
			);
		}
		function receive(chunk: Buffer, isError: boolean) {
			if (settled) return;
			try {
				size += chunk.length;
				if (size > MAX_REPLY)
					return fail(
						new Error(
							"Runtime reply exceeds transport limit; query narrower request status.",
						),
					);
				if (isError) stderr += err.write(chunk);
				else stdout += out.write(chunk);
			} catch (error) {
				fail(error as Error);
			}
		}
		child.stdout!.on("data", (chunk) => receive(chunk, false));
		child.stderr!.on("data", (chunk) => receive(chunk, true));
		for (const stream of [child.stdin!, child.stdout!, child.stderr!])
			stream.on("error", fail);
		child.on("error", fail);
		child.on("close", (code) => {
			if (settled) return;
			try {
				stdout += out.end();
				stderr += err.end();
				const result = JSON.parse(stdout);
				if (!result || typeof result !== "object" || Array.isArray(result))
					throw new Error("Invalid runtime reply");
				if (code !== 0) throw new Error(JSON.stringify(result));
				finish(undefined, result);
			} catch (error) {
				finish(
					new Error(
						`${error instanceof Error ? error.message : String(error)}${stderr ? `; ${stderr.slice(0, 2048)}` : ""}`,
					),
				);
			}
		});
		activeCalls.add(abort);
		signal?.addEventListener("abort", abort, { once: true });
		if (signal?.aborted) abort();
		else child.stdin!.end(JSON.stringify(payload));
		return promise;
	}

	async function start(
		scope: string,
		ctx: ExtensionContext,
		signal?: AbortSignal,
	): Promise<Json> {
		if (changing || stopRequested || signal?.aborted)
			throw new Error("Session is changing or start was cancelled");
		if (process.platform === "win32")
			throw new Error("Coedit watch requires POSIX process groups");
		const owner = ctx.sessionManager.getSessionId();
		scope = resolve(ctx.cwd, scope);
		if (watch) {
			if (watch.owner === owner && watch.scope === scope)
				return { owner, scope, watching: true, limitation: PLAN_NOTE };
			throw new Error("Stop the existing coedit scope before starting another");
		}
		const child = spawn(
			"python3",
			[
				RUNTIME,
				"watch",
				"--scope",
				scope,
				"--owner",
				owner,
				"--harness",
				"omp",
			],
			{
				cwd: ctx.cwd,
				detached: true,
				stdio: ["pipe", "pipe", "pipe"],
			},
		);
		let ready = false,
			accepting = true,
			stopping: Promise<void> | undefined;
		let flushTimer: Timer | undefined;
		let hint: Json | undefined,
			lastRevision: string | undefined,
			lastDiagnostic: string | undefined;
		let partial = "",
			overflow = false,
			stderr = "";
		let currentState: Json | undefined;
		const {
			promise: readiness,
			resolve: resolveReady,
			reject: rejectReady,
		} = Promise.withResolvers<Json>();
		const { promise: closed, resolve: resolveClosed } =
			Promise.withResolvers<void>();
		const sameSession = () => ctx.sessionManager.getSessionId() === owner;
		function clearFlush() {
			if (flushTimer !== undefined) ctx.clearTimer(flushTimer);
			flushTimer = undefined;
		}
		function guard(fn: () => void) {
			try {
				fn();
			} catch (error) {
				log(error);
				rejectReady(error as Error);
				void stop().catch(log);
			}
		}
		function status(text: string) {
			if (sameSession()) ctx.ui.setStatus("coedit", `coedit: ${text}`);
		}
		function recordDelivery(
			stage: "adapter_received" | "handoff",
			requests: Json[],
		) {
			if (!requests.length) return;
			void call({
				op: "delivery",
				owner,
				requests: requests.map(({ id, generation, revision }) => ({
					id,
					generation,
					revision,
				})),
				stage,
			}).catch(log);
		}
		function flush() {
			clearFlush();
			if (!accepting || !ready || !sameSession() || !hint) return;
			if (currentState?.ready === false || currentState?.pause) return;
			if (intent?.sessionId === owner && !intent.enabled) return;
			const current = hint;
			hint = undefined;
			pi.sendMessage(
				{
					customType: "coedit",
					display: true,
					details: current,
					content: `Coedit submitted work changed (hint, not authorization). Read durable status/current request, mark working, and continue independent authorized work. A committed answer stays visible as answered until explicit human review; do not archive it merely because you answered. ${JSON.stringify(current)}\n${PLAN_NOTE}`,
				},
				{ deliverAs: "aside" },
			);
			recordDelivery("handoff", current.requests ?? []);
		}
		function enqueue(value: Json) {
			hint = value; // Only latest state; durable runtime retains every request.
			flushTimer ??= ctx.setTimeout(() => guard(flush), BATCH_MS);
		}
		function consume(line: string) {
			if (!accepting || !sameSession()) return;
			const event = JSON.parse(line);
			if (event.owner !== owner)
				throw new Error("Runtime emitted a foreign owner event");
			if (event.type === "ready") {
				ready = true;
				status("watching");
				resolveReady(event);
			} else if (event.type === "status") {
				currentState = event;
				const parts = [event.ready ? "watching" : "not ready"];
				for (const [key, label] of [
					["eligible_count", "ready"],
					["answered_count", "answered"],
					["awaiting_user_count", "awaiting review"],
					["unsubmitted_count", "unsigned"],
					["blocked_count", "blocked"],
				]) {
					if (event[key]) parts.push(`${event[key]} ${label}`);
				}
				if (event.hold) parts.push("applies held");
				if (event.pause) parts.push("notifications paused");
				status(parts.join(" · "));
				if (!event.current_diagnostics?.length) lastDiagnostic = undefined;
				if (!event.eligible_count || event.pause) {
					hint = undefined;
					clearFlush();
					lastRevision = undefined;
				} else if (hint && event.ready) {
					flushTimer ??= ctx.setTimeout(() => guard(flush), BATCH_MS);
				}
			} else if (event.type === "pending") {
				const revision = String(event.revision);
				const pending = Array.isArray(event.pending) ? event.pending : [];
				if (revision === lastRevision) return;
				lastRevision = revision;
				recordDelivery("adapter_received", pending);
				if (pending.length)
					enqueue({
						owner,
						scope,
						revision,
						count: pending.length,
						requests: pending
							.slice(0, 12)
							.map((row: Json) => ({
								id: String(row.id).slice(0, 128),
								generation: row.generation,
								revision: String(row.revision).slice(0, 128),
								state: String(row.state).slice(0, 64),
								summary: singleLine(row.summary),
							})),
						omitted: Math.max(0, pending.length - 12),
					});
				else {
					hint = undefined;
					clearFlush();
				}
			} else if (event.type === "diagnostic") {
				const error = singleLine(event.error?.message ?? event.error, 400);
				status("attention needed · /coedit pending");
				if (error !== lastDiagnostic) {
					lastDiagnostic = error;
					ctx.ui.notify(`Coedit: ${error}`, "warning");
				}
			}
		}
		const decoder = new StringDecoder("utf8");
		child.stdout!.on("data", (chunk: Buffer) =>
			guard(() => {
				const text = decoder.write(chunk);
				let offset = 0;
				while (offset < text.length) {
					const newline = text.indexOf("\n", offset),
						end = newline < 0 ? text.length : newline;
					const room = Math.max(0, MAX_EVENT - partial.length);
					partial += text.slice(offset, Math.min(end, offset + room));
					overflow ||= end - offset > room;
					if (newline < 0) break;
					if (overflow)
						enqueue({
							owner,
							scope,
							requests: [],
							overflow: true,
							message:
								"Oversized work update omitted; query durable status for current requests.",
						});
					else if (partial.trim()) consume(partial);
					partial = "";
					overflow = false;
					offset = newline + 1;
				}
			}),
		);
		child.stderr!.on("data", (chunk: Buffer) =>
			guard(() => {
				stderr = (stderr + chunk.toString("utf8")).slice(-2048);
			}),
		);
		for (const stream of [child.stdin!, child.stdout!, child.stderr!])
			stream.on("error", (error) =>
				guard(() => {
					throw error;
				}),
			);
		child.on("error", (error) =>
			guard(() => {
				throw error;
			}),
		);
		child.on("close", (code, exitSignal) => {
			resolveClosed();
			guard(() => {
				rejectReady(
					new Error(
						`Coedit exited before ready: ${exitSignal ?? code}; ${lastDiagnostic ?? stderr}`,
					),
				);
				if (
					accepting &&
					sameSession() &&
					!(intent?.sessionId === owner && !intent.enabled)
				) {
					status("stopped unexpectedly; /coedit start to reattach");
					ctx.ui.notify(
						`Coedit watcher exited (${exitSignal ?? code}); scope intent retained. Use /coedit start to reattach.`,
						"warning",
					);
				}
				accepting = false;
				clearFlush();
				if (watch?.child === child) watch = undefined;
			});
		});
		function stop(): Promise<void> {
			if (stopping) return stopping;
			accepting = false;
			clearFlush();
			rejectReady(new Error("Coedit watch stopped before readiness"));
			stopping = (async () => {
				child.stdin?.end();
				group(child, "SIGTERM");
				const escalation = setTimeout(() => {
					try {
						group(child, "SIGKILL");
					} catch (error) {
						log(error);
					}
				}, 3000);
				try {
					await closed;
				} finally {
					clearTimeout(escalation);
				}
				if (watch?.child === child) watch = undefined;
			})();
			return stopping;
		}
		watch = { owner, scope, child, stop };
		const timeout = setTimeout(
			() =>
				guard(() => {
					throw new Error(
						"Coedit editor listener did not become ready within 30 seconds",
					);
				}),
			30_000,
		);
		const abort = () => {
			void stop().catch(log);
		};
		signal?.addEventListener("abort", abort, { once: true });
		try {
			if (signal?.aborted) abort();
			const result = await readiness;
			if (!accepting || changing || stopRequested || !sameSession())
				throw new Error("Owning session changed during attachment");
			persist(ctx, scope, true);
			return { ...result, limitation: PLAN_NOTE };
		} catch (error) {
			await stop();
			throw error;
		} finally {
			clearTimeout(timeout);
			signal?.removeEventListener("abort", abort);
		}
	}

	async function run(
		input: unknown,
		ctx: ExtensionContext,
		signal?: AbortSignal,
	): Promise<Json> {
		const request = parameters.parse(input);
		const owner = ctx.sessionManager.getSessionId();
		if (request.op === "start")
			return serialize(() => {
				const scope = request.scope ?? saved(ctx)?.scope;
				if (!scope)
					throw new Error("start requires an explicit file or folder scope");
				return start(scope, ctx, signal);
			});
		if (request.op === "stop") {
			stopRequested = true;
			for (const abort of activeCalls) abort();
			const stoppingWatch = watch;
			void stoppingWatch?.stop().catch((error) =>
				console.error("[coedit] stopping watch:", error),
			);
			return serialize(async () => {
				persist(ctx, saved(ctx)?.scope ?? stoppingWatch?.scope ?? "", false);
				try {
					return await call({ op: "stop", owner }, signal);
				} finally {
					try {
						await stoppingWatch?.stop();
					} finally {
						ctx.ui.setStatus("coedit", undefined);
						stopRequested = false;
					}
				}
			});
		}
		const { scope: _scope, ...payload } = request;
		const result = await call(
			{
				...payload,
				op: request.op === "pending" ? "status" : request.op,
				owner,
			},
			signal,
		);
		return request.op === "status" || request.op === "pending"
			? {
					...result,
					adapter: {
						watching: watch?.owner === owner,
						scope: watch?.scope,
						limitation: PLAN_NOTE,
					},
				}
			: result;
	}
	async function detach() {
		changing = true;
		try {
			for (const abort of activeCalls) abort();
			await watch?.stop();
			await transition;
		} finally {
			changing = false;
		}
	}
	async function resume(_event: unknown, ctx: ExtensionContext) {
		await serialize(async () => {
			intent = saved(ctx);
			if (!intent?.enabled || watch) return;
			try {
				await start(intent.scope, ctx);
			} catch (error) {
				ctx.ui.notify(
					`Coedit scope remains saved but not ready: ${String(error)}`,
					"warning",
				);
			}
		});
	}
	// Child focus only rebinds the TUI view in OMP; it does not emit these owning-session events.
	// Cleanup after successful switch/branch also avoids detaching on a cancelled transition.
	pi.on("session_shutdown", detach);
	pi.on("session_switch", async (event, ctx) => {
		await detach();
		await resume(event, ctx);
	});
	pi.on("session_branch", async (event, ctx) => {
		await detach();
		await resume(event, ctx);
	});
	pi.on("session_start", resume);
	// Tree navigation keeps the same owner and the latest durable intent; no automatic stop/rearm.
	pi.registerTool({
		name: "coedit",
		label: "Coedit",
		loadMode: "essential",
		approval: "exec",
		parameters,
		description: `Shared coedit: explicitly start a scope; inspect status/pending/read and safe next actions; mark working before processing; guarded write with purpose apply/answer/proposal. A committed answer stays answered and visible until explicit user review. Use read-only reconcile after uncertain outcomes; never replay. Resolve is separate and reviewed:true is only explicit human-reviewed answer archival. Owner is this conversation automatically. Writes require current request_id/generation, a unique operation_id and exact target/proposal guards. ${PLAN_NOTE}`,
		async execute(_id, input, signal, _update, ctx) {
			const result = await run(input, ctx, signal);
			return {
				content: [{ type: "text", text: JSON.stringify(result) }],
				details: result,
			};
		},
		renderCall(args) {
			return new Text(
				`Coedit · ${singleLine(args.op)}${args.scope ? ` · ${singleLine(args.scope)}` : ""}`,
				0,
				0,
			);
		},
		renderResult(result, options) {
			return new Text(
				options.isPartial
					? "Coedit operation in progress…"
					: resultText(resultDetails(result), options.expanded),
				0,
				0,
			);
		},
	});
	pi.registerMessageRenderer<Json>("coedit", (message, options) => {
		const details = message.details ?? {};
		const lines = [
			`Coedit · ${typeof details.count === "number" ? `${details.count} submitted request${details.count === 1 ? "" : "s"} ready` : "pending work changed"}`,
		];
		if (options.expanded)
			for (const row of details.requests ?? [])
				if (row.summary) lines.push(singleLine(row.summary));
		return new Text(lines.join("\n"), 0, 0);
	});
	pi.registerCommand("coedit", {
		description:
			"Coedit status/pending, start <path>, stop, hold/release, pause/unpause, submit, or JSON operation",
		async handler(args, ctx) {
			try {
				const text = args.trim();
				if (text === "help") {
					ctx.ui.notify(
						`/coedit [status|pending|start <path>|stop|hold|release|pause|unpause|submit]\nJSON exposes the same coedit tool operations. ${PLAN_NOTE}`,
						"info",
					);
					return;
				}
				let input: Json;
				if (text.startsWith("{")) input = JSON.parse(text);
				else if (text.startsWith("start "))
					input = { op: "start", scope: text.slice(6).trim() };
				else if (["hold", "release", "pause", "unpause"].includes(text))
					input = {
						op: ["hold", "release"].includes(text) ? "hold" : "pause",
						value: ["hold", "pause"].includes(text),
					};
				else input = { op: text || "status" };
				const result = await run(input, ctx);
				if (
					input.op === "pending" &&
					ctx.hasUI &&
					Array.isArray(result.pending) &&
					result.pending.length
				) {
					const labels = result.pending.map(
						(row: Json, index: number) =>
							`${index + 1}. ${singleLine(row.summary || row.raw, 100)} · ${row.blocked ? "blocked" : row.state} · ${location(row, result.scope)}`,
					);
					const choice = await ctx.ui.select(
						"Coedit pending · choose a request",
						labels,
					);
					const index = labels.indexOf(choice ?? "");
					if (index < 0) return;
					const detail = await run(
						{ op: "read", request_id: result.pending[index].id },
						ctx,
					);
					const row = detail.request;
					ctx.ui.notify(resultText(detail, true), "info");
					const actions = ["Discuss this request", "Reconcile receipts"];
					const answered = detail.operations?.some(
						(operation: Json) =>
							operation.generation === row.generation &&
							operation.purpose === "answer" &&
							operation.status === "committed",
					);
					if (answered && !["resolved", "cancelled"].includes(row.state))
						actions.push("Archive reviewed answer");
					actions.push("Back");
					const action = await ctx.ui.select("Coedit · next action", actions);
					if (action === "Discuss this request") {
						pi.sendUserMessage(
							`Discuss the selected coedit request ${row.id}, generation ${row.generation}. Read its current context and offer the relevant review choices. This selection is not a new submission, approval to apply a proposal, or confirmation that an answer was reviewed.`,
							{ deliverAs: "aside" },
						);
					} else if (action === "Reconcile receipts") {
						ctx.ui.notify(
							resultText(
								await run({ op: "reconcile", request_id: row.id }, ctx),
								true,
							),
							"info",
						);
					} else if (action === "Archive reviewed answer") {
						const existing = detail.resolutions?.find(
							(item: Json) =>
								item.generation === row.generation &&
								item.status !== "resolved",
						);
						const archived = await run(
							{
								op: "resolve",
								request_id: row.id,
								generation: row.generation,
								operation_id: existing?.operation_id ?? crypto.randomUUID(),
								record:
									existing?.record ??
									"User reviewed the visible answer and requested archival from the coedit pending view.",
								reviewed: true,
							},
							ctx,
						);
						ctx.ui.notify(resultText(archived, true), "info");
					}
				} else
					ctx.ui.notify(
						resultText(result, ["read", "reconcile"].includes(input.op)),
						result.error ? "error" : "info",
					);
			} catch (error) {
				const text = error instanceof Error ? error.message : String(error);
				ctx.ui.notify(
					resultText(resultDetails({ content: [{ type: "text", text }] })),
					"error",
				);
			}
		},
	});
}
