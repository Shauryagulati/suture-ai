export default function SettingsPage(): React.ReactElement {
  return (
    <div className="p-10">
      <h1 className="mb-2 text-2xl font-semibold">Settings</h1>
      <p className="max-w-prose text-sm text-muted-foreground">
        Clinic configuration, user management, and outreach-cadence rules are managed here. These
        controls are a post-v1 enhancement.
      </p>
    </div>
  );
}
