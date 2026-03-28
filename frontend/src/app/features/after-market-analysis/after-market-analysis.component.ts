import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { LucideAngularModule } from 'lucide-angular';

@Component({
  selector: 'app-after-market-analysis',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive, RouterOutlet, LucideAngularModule],
  templateUrl: './after-market-analysis.component.html',
  styleUrl: './after-market-analysis.component.scss',
})
export class AfterMarketAnalysisComponent {}
