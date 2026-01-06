import { Routes } from '@angular/router';
import { authGuard, guestGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  {
    path: '',
    redirectTo: 'dashboard',
    pathMatch: 'full'
  },
  {
    path: 'login',
    loadComponent: () => import('./features/auth/login/login.component').then(m => m.LoginComponent),
    canActivate: [guestGuard]
  },
  {
    path: 'auth/callback',
    loadComponent: () => import('./features/auth/callback/callback.component').then(m => m.CallbackComponent)
  },
  {
    path: 'dashboard',
    loadComponent: () => import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent),
    canActivate: [authGuard]
  },
  {
    path: 'stocks',
    loadComponent: () => import('./features/stock-comparison/stock-comparison.component').then(m => m.StockComparisonComponent),
    canActivate: [authGuard]
  },
  {
    path: 'fo',
    loadComponent: () => import('./features/fo-analysis/fo-analysis.component').then(m => m.FOAnalysisComponent),
    canActivate: [authGuard]
  },
  {
    path: 'announcements',
    loadComponent: () => import('./features/announcements/announcements.component').then(m => m.AnnouncementsComponent),
    canActivate: [authGuard]
  },
  {
    path: '**',
    redirectTo: 'dashboard'
  }
];
