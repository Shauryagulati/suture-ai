import { Sidebar } from "@/components/Sidebar";

export default function TasksPage(): React.ReactElement {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-10 text-muted-foreground">
        Tasks — Module 3a ships the workflow engine and SLA-tracked task queue.
      </main>
    </div>
  );
}
