import { Sidebar } from "@/components/Sidebar";

export default function PriorAuthPage(): React.ReactElement {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-10 text-muted-foreground">
        Prior Auth — Module 4 ships the payer-rules RAG and packet generator.
      </main>
    </div>
  );
}
