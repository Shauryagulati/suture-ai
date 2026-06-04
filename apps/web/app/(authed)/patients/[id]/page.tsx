import { ContactHistory } from "@/components/outreach/contact-history";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getPatient } from "@/lib/patients";
import { notFound } from "next/navigation";

export default async function PatientDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<React.ReactElement> {
  const { id } = await params;
  const patient = await getPatient(id);
  if (!patient) notFound();

  const address = [patient.address_line1, patient.address_line2].filter(Boolean).join(", ") || "—";
  const cityState = [patient.city, patient.state].filter(Boolean).join(", ") || "—";

  return (
    <div className="max-w-4xl space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">
          {patient.first_name} {patient.last_name}
        </h1>
        <p className="text-xs text-muted-foreground">{patient.mrn ?? "No MRN"}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Demographics</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
          <Field label="Date of birth" value={patient.dob} />
          <Field label="Phone" value={patient.phone} />
          <Field label="Email" value={patient.email ?? "—"} />
          <Field label="Address" value={address} />
          <Field label="City / State" value={cityState} />
          <Field label="ZIP" value={patient.zip_code ?? "—"} />
        </CardContent>
      </Card>

      <section>
        <h2 className="mb-3 text-lg font-medium">Contact history</h2>
        <ContactHistory patientId={id} />
      </section>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }): React.ReactElement {
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p>{value}</p>
    </div>
  );
}
