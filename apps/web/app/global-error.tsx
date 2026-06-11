"use client";

// Root error boundary. Replaces the whole document when an error escapes the
// root layout or a route with no closer error.tsx (e.g. /login, /schedule).
// Must render its own <html>/<body> and use inline styles — the root layout
// and globals.css are not applied when this renders.
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}): React.ReactElement {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "system-ui, -apple-system, sans-serif",
          background: "#fafafa",
          color: "#111",
        }}
      >
        <div style={{ maxWidth: 420, padding: 32, textAlign: "center" }}>
          <h2 style={{ fontSize: 20, fontWeight: 600, marginBottom: 8 }}>Something went wrong</h2>
          <p style={{ fontSize: 14, color: "#555", marginBottom: 20 }}>
            {error.message || "An unexpected error occurred."}
          </p>
          <button
            type="button"
            onClick={() => reset()}
            style={{
              padding: "8px 16px",
              borderRadius: 6,
              border: "1px solid #ccc",
              background: "#111",
              color: "#fff",
              cursor: "pointer",
            }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
