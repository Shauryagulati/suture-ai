import { TaskTable } from "@/components/tasks/task-table";

export default function TasksPage(): React.ReactElement {
  return (
    <div className="p-10">
      <h1 className="text-2xl font-semibold mb-2">Tasks</h1>
      <p className="text-muted-foreground mb-6">SLA-tracked work queue for the active clinic.</p>
      <TaskTable />
    </div>
  );
}
