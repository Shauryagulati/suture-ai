import Link from "next/link";

export default function PatientsPage(): React.ReactElement {
  return (
    <main className="flex-1 p-10">
      <h1 className="mb-2 text-2xl font-semibold">Patients</h1>
      <p className="text-sm text-muted-foreground">
        Open a patient detail page from a referral or the upcoming Module 1 patient registry.
        For a quick look at outreach history, browse to{" "}
        <Link href="/outreach" className="underline">
          Outreach
        </Link>
        .
      </p>
    </main>
  );
}
