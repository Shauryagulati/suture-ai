import { redirect } from "next/navigation";

export default function HomePage(): never {
  // The authenticated app lives under (authed); the inbox is the home screen.
  // The (authed) layout bounces unauthenticated users to /login.
  redirect("/inbox");
}
