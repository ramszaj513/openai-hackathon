import { api } from "./api";

type TranscriptEvent = {
  type?: string;
  item_id?: string;
  delta?: string;
  transcript?: string;
  error?: { message?: string };
};

type TranscriptItem = { partial: string; final?: string };

export class RealtimeTranscript {
  private readonly order: string[] = [];
  private readonly items = new Map<string, TranscriptItem>();

  consume(event: TranscriptEvent): string | null {
    const itemId = event.item_id;
    if (
      !itemId ||
      (event.type !== "conversation.item.input_audio_transcription.delta" &&
        event.type !== "conversation.item.input_audio_transcription.completed")
    ) {
      return null;
    }
    if (!this.items.has(itemId)) {
      this.order.push(itemId);
      this.items.set(itemId, { partial: "" });
    }
    const item = this.items.get(itemId)!;
    if (event.type.endsWith(".delta")) item.partial += event.delta ?? "";
    else item.final = event.transcript ?? item.partial;
    return this.order
      .map((id) => {
        const value = this.items.get(id)!;
        return value.final ?? value.partial;
      })
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();
  }
}

export type RealtimeTranscriptionSession = {
  stop: () => Promise<void>;
  dispose: () => void;
};

export async function startRealtimeTranscription(
  onTranscript: (transcript: string) => void,
  onError: (message: string) => void,
): Promise<RealtimeTranscriptionSession> {
  if (!navigator.mediaDevices?.getUserMedia || typeof RTCPeerConnection === "undefined") {
    throw new Error("This browser does not support microphone input through WebRTC.");
  }

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  });
  const peer = new RTCPeerConnection();
  const channel = peer.createDataChannel("oai-events");
  const transcript = new RealtimeTranscript();
  let stopping = false;
  let disposed = false;
  let resolveFinal: (() => void) | null = null;

  const dispose = () => {
    if (disposed) return;
    disposed = true;
    stream.getTracks().forEach((track) => track.stop());
    channel.close();
    peer.close();
  };

  channel.onmessage = (message) => {
    try {
      const event = JSON.parse(String(message.data)) as TranscriptEvent;
      const next = transcript.consume(event);
      if (next !== null) onTranscript(next);
      if (event.type === "conversation.item.input_audio_transcription.completed" && stopping) {
        resolveFinal?.();
      }
      if (event.type === "error") {
        onError(event.error?.message ?? "OpenAI Realtime transcription reported an error.");
        resolveFinal?.();
      }
    } catch {
      onError("The live transcription stream returned an invalid event.");
    }
  };

  try {
    const track = stream.getAudioTracks()[0];
    if (!track) throw new Error("No microphone audio track is available.");
    peer.addTrack(track, stream);
    const offer = await peer.createOffer();
    await peer.setLocalDescription(offer);
    if (!offer.sdp) throw new Error("The browser could not create a WebRTC offer.");
    const answerSdp = await api.createTranscriptionSession(offer.sdp);
    await peer.setRemoteDescription({ type: "answer", sdp: answerSdp });
    await waitForOpenChannel(channel);
  } catch (cause) {
    dispose();
    throw cause;
  }

  return {
    async stop() {
      if (stopping) return;
      stopping = true;
      if (channel.readyState === "open") {
        const finalEvent = new Promise<void>((resolve) => {
          resolveFinal = resolve;
        });
        channel.send(JSON.stringify({ type: "input_audio_buffer.commit" }));
        await Promise.race([finalEvent, wait(4000)]);
      }
      dispose();
    },
    dispose,
  };
}

function waitForOpenChannel(channel: RTCDataChannel): Promise<void> {
  if (channel.readyState === "open") return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(
      () => reject(new Error("Timed out while opening the live transcription connection.")),
      10000,
    );
    channel.addEventListener(
      "open",
      () => {
        window.clearTimeout(timeout);
        resolve();
      },
      { once: true },
    );
    channel.addEventListener(
      "error",
      () => {
        window.clearTimeout(timeout);
        reject(new Error("The live transcription connection could not be opened."));
      },
      { once: true },
    );
  });
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}
