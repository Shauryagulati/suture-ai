import Link from "next/link";

export default function PatientsPage(): React.ReactElement {
  return (
    <div className="p-10">
      <h1 className="mb-2 text-2xl font-semibold">Patients</h1>
      <p className="max-w-prose text-sm text-muted-foreground">
        Patients are created automatically when you approve a referral or discharge in the{" "}
        <Link href="/inbox" className="underline">
          Inbox
        </Link>
        . Open a patient from a referral or discharge detail page to see their contact history. A
        standalone patient registry is a Module 1 enhancement.
      </p>
    </div>
  );
}
