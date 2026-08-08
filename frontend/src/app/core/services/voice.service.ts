import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

/**
 * Voice I/O for the assistant.
 *
 * STT: records mic audio with MediaRecorder (works in EVERY modern browser) and
 * sends it to the backend, which transcribes with Whisper (English/Hindi/Hinglish).
 * TTS: reads replies aloud with the browser's speechSynthesis (widely supported).
 */
@Injectable({ providedIn: 'root' })
export class VoiceService {
  private readonly backend = import.meta.env.NG_APP_BACKEND;
  private mediaRecorder?: MediaRecorder;
  private chunks: Blob[] = [];

  readonly recording$ = new BehaviorSubject<boolean>(false);
  readonly transcribing$ = new BehaviorSubject<boolean>(false);
  readonly speaking$ = new BehaviorSubject<boolean>(false);
  /** Live mic loudness, normalised 0..1, for the recording waveform. */
  readonly level$ = new BehaviorSubject<number>(0);

  private audioCtx?: AudioContext;
  private analyser?: AnalyserNode;
  private meterRaf?: number;

  get sttSupported(): boolean {
    return (
      typeof navigator !== 'undefined' &&
      !!navigator.mediaDevices?.getUserMedia &&
      typeof (window as any).MediaRecorder !== 'undefined'
    );
  }

  get ttsSupported(): boolean {
    return typeof window !== 'undefined' && 'speechSynthesis' in window;
  }

  // ── Speech to text (record → backend Whisper) ──

  async startRecording(onError?: (msg: string) => void): Promise<void> {
    if (!this.sttSupported) {
      onError?.('Voice input isn’t supported in this browser.');
      return;
    }
    if (this.recording$.value) return;
    this.stopSpeaking(); // barge-in

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      onError?.('Microphone access is blocked. Please allow mic permission and try again.');
      return;
    }

    this.chunks = [];
    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) this.chunks.push(e.data);
    };
    this.mediaRecorder = recorder;
    this.recording$.next(true);
    this.startMeter(stream);
    recorder.start();
  }

  /** Analyse the mic stream to drive the recording waveform (0..1 RMS level). */
  private startMeter(stream: MediaStream): void {
    try {
      const Ctx = (window as any).AudioContext || (window as any).webkitAudioContext;
      if (!Ctx) return;
      this.audioCtx = new Ctx();
      const source = this.audioCtx!.createMediaStreamSource(stream);
      const analyser = this.audioCtx!.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      this.analyser = analyser;
      const buf = new Uint8Array(analyser.frequencyBinCount);

      const tick = () => {
        analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) {
          const v = (buf[i] - 128) / 128;
          sum += v * v;
        }
        const rms = Math.sqrt(sum / buf.length); // 0..~1
        // Boost + clamp so normal speech fills the meter.
        this.level$.next(Math.min(1, rms * 3.2));
        this.meterRaf = requestAnimationFrame(tick);
      };
      tick();
    } catch {
      /* metering is best-effort */
    }
  }

  private stopMeter(): void {
    if (this.meterRaf) cancelAnimationFrame(this.meterRaf);
    this.meterRaf = undefined;
    this.analyser = undefined;
    try {
      this.audioCtx?.close();
    } catch {
      /* noop */
    }
    this.audioCtx = undefined;
    this.level$.next(0);
  }

  /** Stop recording, upload, and resolve with the transcript ('' on failure). */
  async stopRecording(): Promise<string> {
    const recorder = this.mediaRecorder;
    if (!recorder) {
      this.recording$.next(false);
      return '';
    }
    return new Promise<string>((resolve) => {
      recorder.onstop = async () => {
        try {
          recorder.stream.getTracks().forEach((t) => t.stop());
        } catch {
          /* noop */
        }
        this.stopMeter();
        this.recording$.next(false);
        this.mediaRecorder = undefined;

        const blob = new Blob(this.chunks, { type: recorder.mimeType || 'audio/webm' });
        this.chunks = [];
        if (!blob.size) {
          resolve('');
          return;
        }

        this.transcribing$.next(true);
        try {
          resolve(await this.upload(blob));
        } catch {
          resolve('');
        } finally {
          this.transcribing$.next(false);
        }
      };
      try {
        recorder.stop();
      } catch {
        this.recording$.next(false);
        resolve('');
      }
    });
  }

  cancelRecording(): void {
    const recorder = this.mediaRecorder;
    if (recorder) {
      try {
        recorder.onstop = null as any;
        recorder.stop();
        recorder.stream.getTracks().forEach((t) => t.stop());
      } catch {
        /* noop */
      }
    }
    this.stopMeter();
    this.mediaRecorder = undefined;
    this.chunks = [];
    this.recording$.next(false);
  }

  /** Set when the server says voice is unavailable, so the UI can explain why. */
  unavailableReason = '';

  private async upload(blob: Blob): Promise<string> {
    const form = new FormData();
    form.append('audio', blob, 'clip.webm');
    const resp = await fetch(`${this.backend}/api/chat/transcribe`, { method: 'POST', body: form });
    if (!resp.ok) {
      // 503 = voice disabled on this server (e.g. not enough RAM for the model).
      let detail = '';
      try {
        detail = (await resp.json())?.detail || '';
      } catch {
        /* non-JSON error body */
      }
      this.unavailableReason = detail || 'Voice input is unavailable right now.';
      throw new Error(this.unavailableReason);
    }
    this.unavailableReason = '';
    const data = await resp.json();
    return (data?.text || '').trim();
  }

  // ── Text to speech (browser) ──

  /**
   * Strip markdown so the voice reads the words, not the syntax.
   * Without this, "**RELIANCE**" is read aloud as "star star RELIANCE star star"
   * (and "## Heading" as "hash hash…") by most speech engines.
   */
  toSpeakable(md: string): string {
    return (md || '')
      .replace(/```[\s\S]*?```/g, ' ')            // fenced code blocks
      .replace(/`([^`]*)`/g, '$1')                // inline code
      .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')      // images
      .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')    // links → their text
      .replace(/^\s{0,3}#{1,6}\s+/gm, '')         // headings
      .replace(/^\s{0,3}>\s?/gm, '')              // blockquotes
      .replace(/^\s*([-*_]\s*){3,}$/gm, ' ')      // horizontal rules
      .replace(/^\s*[-*+]\s+/gm, '')              // bullet markers
      .replace(/^\s*\d+[.)]\s+/gm, '')            // numbered list markers
      .replace(/(\*\*|__)(.*?)\1/g, '$2')         // bold
      .replace(/(\*|_)(.*?)\1/g, '$2')            // italic
      .replace(/~~(.*?)~~/g, '$1')                // strikethrough
      .replace(/[*_`#]/g, '')                     // any stragglers
      .replace(/[ \t]{2,}/g, ' ')
      .trim();
  }

  /**
   * @param queue when true, follow whatever is already speaking instead of
   *        cutting it off — lets a reply be spoken sentence by sentence as it streams.
   */
  speak(text: string, opts: { queue?: boolean } = {}): void {
    if (!this.ttsSupported || !text.trim()) return;
    // speechSynthesis queues natively; only cancel when explicitly replacing.
    if (!opts.queue) this.stopSpeaking();

    const isDevanagari = /[ऀ-ॿ]/.test(text);
    const targetLang = isDevanagari ? 'hi-IN' : 'en-IN';

    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = targetLang;
    const voices = window.speechSynthesis.getVoices();
    const voice =
      voices.find((v) => v.lang === targetLang) ||
      voices.find((v) => v.lang?.startsWith(targetLang.slice(0, 2)));
    if (voice) utter.voice = voice;
    utter.onstart = () => this.speaking$.next(true);
    utter.onend = () => this.speaking$.next(false);
    utter.onerror = () => this.speaking$.next(false);

    window.speechSynthesis.speak(utter);
  }

  stopSpeaking(): void {
    if (this.ttsSupported) {
      window.speechSynthesis.cancel();
      this.speaking$.next(false);
    }
  }
}
