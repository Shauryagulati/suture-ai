import { Sidebar } from "@/components/Sidebar";

export default function PatientsPage(): React.ReactElement {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-10 text-muted-foreground">
        Patients — Module 1+ ships the patient registry and activity timeline.
      </main>
    </div>
  );
}
