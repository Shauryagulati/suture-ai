import { Sidebar } from "@/components/Sidebar";

export default function InboxPage(): React.ReactElement {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-10 text-muted-foreground">
        Inbox — Module 1 ships document upload, classification, and the review queue.
      </main>
    </div>
  );
}
