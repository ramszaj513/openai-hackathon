import { describe, expect, it } from "vitest";
import { RealtimeTranscript } from "./realtimeTranscription";

describe("RealtimeTranscript", () => {
  it("assembles live deltas and replaces them with the final transcript", () => {
    const transcript = new RealtimeTranscript();

    expect(
      transcript.consume({
        type: "conversation.item.input_audio_transcription.delta",
        item_id: "item-1",
        delta: "Kup ",
      }),
    ).toBe("Kup");
    expect(
      transcript.consume({
        type: "conversation.item.input_audio_transcription.delta",
        item_id: "item-1",
        delta: "monitor",
      }),
    ).toBe("Kup monitor");
    expect(
      transcript.consume({
        type: "conversation.item.input_audio_transcription.completed",
        item_id: "item-1",
        transcript: "Kup monitor.",
      }),
    ).toBe("Kup monitor.");
  });

  it("keeps committed utterances in first-seen order", () => {
    const transcript = new RealtimeTranscript();
    transcript.consume({
      type: "conversation.item.input_audio_transcription.completed",
      item_id: "first",
      transcript: "Pierwsze zdanie.",
    });

    expect(
      transcript.consume({
        type: "conversation.item.input_audio_transcription.completed",
        item_id: "second",
        transcript: "Drugie zdanie.",
      }),
    ).toBe("Pierwsze zdanie. Drugie zdanie.");
  });
});
