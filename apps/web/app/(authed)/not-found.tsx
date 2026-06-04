import Link from "next/link";

export default function AuthedNotFound(): React.ReactElement {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-10 text-center">
      <p className="text-sm font-medium text-muted-foreground">404</p>
      <h2 className="text-xl font-semibold">Not found</h2>
      <p className="max-w-md text-sm text-muted-foreground">
        That record doesn&apos;t exist, or it belongs to another clinic and isn&apos;t visible here.
      </p>
      <Link href="/inbox" className="text-sm underline">
        Back to Inbox
      </Link>
    </div>
  );
}
