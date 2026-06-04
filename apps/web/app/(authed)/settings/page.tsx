import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getClinicSettings } from "@/lib/clinic";

export default async function SettingsPage(): Promise<React.ReactElement> {
  const settings = await getClinicSettings();

  return (
    <div className="max-w-3xl space-y-6 p-10">
      <h1 className="text-2xl font-semibold">Settings</h1>

      {!settings ? (
        <p className="text-sm text-muted-foreground">Could not load clinic settings.</p>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Clinic</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <div>
                <span className="text-muted-foreground">Name: </span>
                {settings.clinic_name}
              </div>
              <div>
                <span className="text-muted-foreground">Your role: </span>
                <span className="capitalize">{settings.your_role}</span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Members ({settings.members.length})</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Role</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {settings.members.map((m) => (
                    <TableRow key={m.email}>
                      <TableCell className="text-sm">{m.full_name}</TableCell>
                      <TableCell className="text-sm">{m.email}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className="capitalize">
                          {m.role}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <p className="max-w-prose text-xs text-muted-foreground">
            Editing clinic details and managing users (invite, deactivate, change roles) are post-v1
            enhancements.
          </p>
        </>
      )}
    </div>
  );
}
