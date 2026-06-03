export default function AuthedLoading(): React.ReactElement {
  return (
    <div className="flex h-full items-center justify-center p-10">
      <div
        className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-foreground"
        role="status"
        aria-label="Loading"
      />
      <span className="sr-only">Loading…</span>
    </div>
  );
}
