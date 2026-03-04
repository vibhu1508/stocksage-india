import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class LayoutService {
  private videoPlayingSource = new BehaviorSubject<boolean>(false);
  videoPlaying$ = this.videoPlayingSource.asObservable();

  setVideoPlaying(playing: boolean) {
    this.videoPlayingSource.next(playing);
  }
}
