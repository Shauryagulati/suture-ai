import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { listPatients } from "@/lib/patients";
import Link from "next/link";
import { PatientSearch } from "./_search";

export default async function PatientsPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}): Promise<React.ReactElement> {
  const { q } = await searchParams;
  const { items, total } = await listPatients(q);

  return (
    <div className="space-y-4 p-10">
      <div>
        <h1 className="text-2xl font-semibold">Patients</h1>
        <p className="text-sm text-muted-foreground">
          {total} patient{total === 1 ? "" : "s"} in this clinic. Patients are created when a
          referral or discharge is approved in the Inbox.
        </p>
      </div>

      <PatientSearch initialQuery={q ?? ""} />

      {items.length === 0 ? (
        <div className="rounded-md border border-dashed p-12 text-center">
          <p className="text-sm text-muted-foreground">
            {q ? "No patients match your search." : "No patients yet."}
          </p>
        </div>
      ) : (
        <div className="rounded-md border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>MRN</TableHead>
                <TableHead>City</TableHead>
                <TableHead>State</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((p) => (
                <TableRow key={p.id} className="cursor-pointer">
                  <TableCell>
                    <Link href={`/patients/${p.id}`} className="font-medium hover:underline">
                      {p.last_name}, {p.first_name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-sm tabular-nums">{p.mrn ?? "—"}</TableCell>
                  <TableCell className="text-sm">{p.city ?? "—"}</TableCell>
                  <TableCell className="text-sm">{p.state ?? "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
