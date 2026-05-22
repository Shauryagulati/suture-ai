"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

import {
  type LocalAudioTrack,
  type RemoteParticipant,
  type RemoteTrack,
  type RemoteTrackPublication,
  Room,
  RoomEvent,
  Track,
  createLocalAudioTrack,
} from "livekit-client";

interface BrowserCallerProps {
  livekitUrl: string;
  token: string;
  roomName: string;
}

type CallState = "idle" | "connecting" | "connected" | "ended" | "error";

export function BrowserCaller({
  livekitUrl,
  token,
  roomName,
}: BrowserCallerProps): React.ReactElement {
  const [state, setState] = useState<CallState>("idle");
  const [micEnabled, setMicEnabled] = useState(false);
  const roomRef = useRef<Room | null>(null);
  const micTrackRef = useRef<LocalAudioTrack | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);

  // Tear-down on unmount.
  useEffect(() => {
    return () => {
      micTrackRef.current?.stop();
      micTrackRef.current = null;
      roomRef.current?.disconnect();
      roomRef.current = null;
    };
  }, []);

  const connect = async () => {
    if (state === "connecting" || state === "connected") return;
    setState("connecting");
    try {
      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
      });
      roomRef.current = room;

      room.on(RoomEvent.TrackSubscribed, attachAgentAudio);
      room.on(RoomEvent.Disconnected, () => setState("ended"));

      await room.connect(livekitUrl, token);
      setState("connected");
      toast.success(`Joined ${roomName}`);
    } catch (e) {
      setState("error");
      toast.error(`Could not join the call: ${e}`);
    }
  };

  const attachAgentAudio = (
    track: RemoteTrack,
    _pub: RemoteTrackPublication,
    _participant: RemoteParticipant,
  ) => {
    if (track.kind !== Track.Kind.Audio) return;
    if (audioElRef.current) {
      track.attach(audioElRef.current);
    }
  };

  const toggleMic = async () => {
    if (state !== "connected" || !roomRef.current) return;
    if (micEnabled && micTrackRef.current) {
      micTrackRef.current.stop();
      const lp = roomRef.current.localParticipant;
      await lp.unpublishTrack(micTrackRef.current);
      micTrackRef.current = null;
      setMicEnabled(false);
      return;
    }
    try {
      const track = await createLocalAudioTrack({ echoCancellation: true });
      micTrackRef.current = track;
      await roomRef.current.localParticipant.publishTrack(track);
      setMicEnabled(true);
    } catch (e) {
      toast.error(`Mic failed: ${e}`);
    }
  };

  const disconnect = () => {
    micTrackRef.current?.stop();
    micTrackRef.current = null;
    roomRef.current?.disconnect();
    setMicEnabled(false);
    setState("ended");
  };

  return (
    <div className="rounded-md border bg-card p-6 space-y-4 max-w-md">
      <header className="space-y-1">
        <h2 className="font-semibold text-lg">Browser test caller</h2>
        <p className="text-xs text-muted-foreground">
          v1 has no PSTN trunk — this page joins the LiveKit room as the patient so you can talk to
          Ember from your browser. Room: <span className="font-mono">{roomName}</span>
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        {state === "idle" || state === "ended" || state === "error" ? (
          <Button onClick={connect}>{state === "ended" ? "Reconnect" : "Connect"}</Button>
        ) : null}
        {state === "connected" ? (
          <Button variant={micEnabled ? "destructive" : "default"} onClick={toggleMic}>
            {micEnabled ? "Mute mic" : "Unmute mic"}
          </Button>
        ) : null}
        {state === "connected" ? (
          <Button variant="outline" onClick={disconnect}>
            Disconnect
          </Button>
        ) : null}
      </div>

      <p className="text-xs text-muted-foreground">
        State: <span className="font-mono">{state}</span>
        {state === "connected" && !micEnabled ? " — mic off; click to talk" : null}
      </p>

      {/* Agent audio attaches here. No captions track — Ember speech is captured
          in the live transcript pane, which doubles as accessibility text. */}
      {/* biome-ignore lint/a11y/useMediaCaption: see comment above */}
      <audio ref={audioElRef} autoPlay />
    </div>
  );
}
