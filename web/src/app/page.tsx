import { ClaimChecker } from "@/components/claim-checker";

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-2xl space-y-4 p-6">
      <h1 className="text-xl font-semibold">Check a scientific claim</h1>
      <ClaimChecker />
    </main>
  );
}
