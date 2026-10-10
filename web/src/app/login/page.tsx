"use client";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [sub, setSub] = useState("");
  const [role, setRole] = useState<"student" | "admin">("student");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sub, role }),
    });
    if (!res.ok) {
      setError(res.status === 404 ? "Dev login is disabled (set DEV_LOGIN_ENABLED=true in development)." : "Login failed.");
      return;
    }
    await qc.invalidateQueries({ queryKey: ["me"] });
    router.push("/");
  }

  return (
    <main className="mx-auto max-w-sm space-y-4 p-6">
      <h1 className="text-xl font-semibold">Dev sign in</h1>
      <p className="text-xs opacity-70">Development only. Signs a short-lived token with a local key; a real identity provider replaces this.</p>
      <form onSubmit={onSubmit} className="space-y-3 text-sm">
        <input value={sub} onChange={(e) => setSub(e.target.value)} placeholder="you@bu.edu" aria-label="Identity" className="w-full rounded border p-2 dark:bg-gray-900" required />
        <select value={role} onChange={(e) => setRole(e.target.value as "student" | "admin")} aria-label="Role" className="w-full rounded border p-2 dark:bg-gray-900">
          <option value="student">student</option>
          <option value="admin">admin</option>
        </select>
        <button className="w-full rounded bg-black px-3 py-2 text-white dark:bg-white dark:text-black">Sign in</button>
      </form>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    </main>
  );
}
