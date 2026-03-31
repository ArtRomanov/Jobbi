export function App() {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily:
          "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        backgroundColor: "#fafafa",
        color: "#1a1a1a",
      }}
    >
      <h1 style={{ fontSize: "3rem", fontWeight: 700, marginBottom: "0.5rem" }}>
        Jobbi
      </h1>
      <p style={{ fontSize: "1.125rem", color: "#666" }}>
        Your job search assistant
      </p>
    </div>
  );
}
