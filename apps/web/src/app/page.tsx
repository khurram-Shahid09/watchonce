export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-6 px-6 py-24">
      <p className="text-sm font-medium uppercase tracking-widest text-zinc-500">WatchOnce</p>
      <h1 className="text-4xl font-semibold tracking-tight">Show it once. It&apos;s automated forever.</h1>
      <p className="max-w-xl text-lg leading-8 text-zinc-600 dark:text-zinc-400">
        Record a browser task once. WatchOnce turns it into a documented, parameterized workflow that
        runs deterministically, asks before risky steps, and repairs itself when the UI changes.
      </p>
      <p className="text-sm text-zinc-500">Dashboard coming soon: sign-in lands on day 3 of the build plan.</p>
    </main>
  );
}
