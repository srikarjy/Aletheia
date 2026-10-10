"use client";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type DebateResult, type Job } from "@/lib/api";
import { useMe } from "./session";

const MAX_CLAIM = 500;

async function submitClaim(claim: string): Promise<Job> {
  const { data, error, response } = await api.POST("/debate/async", { body: { claim, async_mode: true, multi_agent: false } });
  if (!data) throw new Error(describe(response.status, error));
  return data;
}

function describe(status: number, error: unknown): string {
  if (status === 401) return "Your session expired. Sign in again.";
  if (status === 403) return "You are not allowed to do that.";
  if (status === 422) return "That claim was rejected (empty, too long, or contains hidden characters).";
  if (status === 429) return "Run budget exceeded. Try again later.";
  return `Request failed (${status}). ${typeof error === "string" ? error : ""}`;
}

export function ClaimChecker() {
  const { data: me } = useMe();
  const [claim, setClaim] = useState("");
  const submit = useMutation({ mutationFn: submitClaim });
  const jobId = submit.data?.job_id;

  const job = useQuery<Job>({
    queryKey: ["job", jobId],
    enabled: !!jobId,
    queryFn: async () => {
      const { data, error, response } = await api.GET("/debate/jobs/{job_id}", { params: { path: { job_id: jobId! } } });
      if (!data) throw new Error(describe(response.status, error));
      return data;
    },
    refetchInterval: (q) => (["completed", "failed"].includes(q.state.data?.status ?? "") ? false : 2000),
  });

  if (me && !me.signedIn) {
    return <p className="text-sm">Sign in to check a claim.</p>;
  }

  return (
    <div className="space-y-6">
      <form
        className="space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (claim.trim()) submit.mutate(claim.trim());
        }}
      >
        <label htmlFor="claim" className="block text-sm font-medium">Scientific claim</label>
        <textarea
          id="claim"
          value={claim}
          onChange={(e) => setClaim(e.target.value)}
          maxLength={MAX_CLAIM}
          rows={3}
          className="w-full rounded border p-2 text-sm dark:bg-gray-900"
          placeholder="e.g. Vitamin D supplementation reduces the risk of COVID-19 infection"
        />
        <div className="flex items-center justify-between text-xs">
          <span>{claim.length}/{MAX_CLAIM}</span>
          <button
            type="submit"
            disabled={!claim.trim() || submit.isPending}
            className="rounded bg-black px-3 py-1.5 text-white disabled:opacity-40 dark:bg-white dark:text-black"
          >
            {submit.isPending ? "Submitting…" : "Check claim"}
          </button>
        </div>
      </form>

      {submit.error && <p role="alert" className="text-sm text-red-600">{submit.error.message}</p>}
      {job.error && <p role="alert" className="text-sm text-red-600">{job.error.message}</p>}
      {job.data && <JobView job={job.data} />}
    </div>
  );
}

function JobView({ job }: { job: Job }) {
  if (job.status === "failed") return <p role="alert" className="text-sm text-red-600">Run failed: {job.error ?? "unknown error"}</p>;
  if (job.status !== "completed" || !job.result) return <p className="text-sm">Status: {job.status}…</p>;
  return <Result r={job.result} />;
}

function Result({ r }: { r: DebateResult }) {
  return (
    <section className="space-y-3 rounded border p-4 text-sm">
      <div className="flex items-baseline gap-3">
        <span className="text-lg font-semibold capitalize">{r.verdict}</span>
        <span>confidence {(r.confidence * 100).toFixed(0)}%</span>
      </div>
      {/* Model output is rendered as plain text; React escapes it, and we never use dangerouslySetInnerHTML. */}
      <p>{r.conclusion}</p>
      <p className="text-xs opacity-70">{r.confidence_rationale}</p>
      {r.sources.length > 0 && (
        <ul className="list-disc pl-5 text-xs">
          {r.sources.map((s, i) => (
            <li key={i}>{JSON.stringify(s)}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
