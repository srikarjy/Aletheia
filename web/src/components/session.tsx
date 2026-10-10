"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";

type Me = { signedIn: boolean; sub?: string; role?: string };

export function useMe() {
  return useQuery<Me>({
    queryKey: ["me"],
    queryFn: async () => (await fetch("/api/auth/me")).json(),
  });
}

export function SessionBar() {
  const { data } = useMe();
  const qc = useQueryClient();
  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    await qc.invalidateQueries();
  }
  return (
    <header className="flex items-center justify-between border-b px-6 py-3 text-sm">
      <Link href="/" className="font-semibold">Aletheia</Link>
      {data?.signedIn ? (
        <div className="flex items-center gap-3">
          <span>{data.sub} <span className="rounded bg-gray-200 px-1.5 py-0.5 text-xs dark:bg-gray-800">{data.role}</span></span>
          <button onClick={logout} className="underline">Sign out</button>
        </div>
      ) : (
        <Link href="/login" className="underline">Sign in</Link>
      )}
    </header>
  );
}
