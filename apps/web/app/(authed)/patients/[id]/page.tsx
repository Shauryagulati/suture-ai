import { ContactHistory } from "@/components/outreach/contact-history";

export default async function PatientDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<React.ReactElement> {
  const { id } = await params;
  return (
    <div className="space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Patient</h1>
        <p className="text-xs text-muted-foreground">{id}</p>
      </div>
      <section>
        <h2 className="mb-3 text-lg font-medium">Contact history</h2>
        <ContactHistory patientId={id} />
      </section>
    </div>
  );
}
