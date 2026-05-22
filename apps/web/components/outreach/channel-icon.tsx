import { Mail, MessageCircle, Phone } from "lucide-react";

import type { OutreachChannel } from "@/lib/queries/outreach";

const ICONS = {
  sms: MessageCircle,
  email: Mail,
  voice: Phone,
} as const;

export function ChannelIcon({
  channel,
  className,
}: {
  channel: OutreachChannel;
  className?: string;
}): React.ReactElement {
  const Icon = ICONS[channel];
  return <Icon className={className ?? "h-4 w-4"} aria-label={channel} />;
}
