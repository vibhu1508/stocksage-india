import { Component, Input, OnDestroy, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

import { VoiceService } from '../../../core/services/voice.service';

/**
 * Live voice waveform for the recording state — bars that ripple continuously
 * and swell with the current mic loudness (`voice.level$`, 0..1). Runs its own
 * requestAnimationFrame loop so it animates without churning the parent panel.
 */
@Component({
  selector: 'app-voice-wave',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="flex h-8 w-full items-center justify-center gap-[3px]">
      @for (h of heights(); track $index) {
        <span class="w-[3px] rounded-full bg-primary transition-[height] duration-75"
              [style.height.%]="h"></span>
      }
    </div>
  `,
})
export class VoiceWaveComponent implements OnInit, OnDestroy {
  @Input({ required: true }) voice!: VoiceService;
  @Input() bars = 28;

  readonly heights = signal<number[]>([]);
  private raf?: number;
  private phase = 0;

  ngOnInit(): void {
    this.heights.set(new Array(this.bars).fill(15));
    this.loop();
  }

  ngOnDestroy(): void {
    if (this.raf) cancelAnimationFrame(this.raf);
  }

  private loop = (): void => {
    this.phase += 0.28;
    const lvl = Math.max(0, Math.min(1, this.voice?.level$.value ?? 0));
    const n = this.bars;
    const arr = new Array<number>(n);
    for (let i = 0; i < n; i++) {
      const wob = (Math.sin(this.phase + i * 0.5) + 1) / 2; // 0..1
      // % of the 32px track: a small idle floor + loudness-driven swell.
      arr[i] = 15 + (10 + lvl * 78) * (0.3 + 0.7 * wob);
    }
    this.heights.set(arr);
    this.raf = requestAnimationFrame(this.loop);
  };
}
