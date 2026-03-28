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
    path: 'onboarding',
    loadComponent: () => import('./features/onboarding/onboarding.component').then(m => m.OnboardingComponent),
    canActivate: [authGuard]
  },
  {
    path: 'dashboard',
    loadComponent: () => import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent),
    canActivate: [authGuard]
  },
  {
    path: 'stocks/:symbol',
    loadComponent: () => import('./features/stock-detail/stock-detail.component').then(m => m.StockDetailComponent),
    canActivate: [authGuard]
  },
  {
    path: 'stocks',
    loadComponent: () => import('./features/watchlist/watchlist.component').then(m => m.WatchlistComponent),
    canActivate: [authGuard]
  },
  {
    path: 'after-market-analysis',
    loadComponent: () => import('./features/after-market-analysis/after-market-analysis.component').then(m => m.AfterMarketAnalysisComponent),
    children: [
      {
        path: '',
        redirectTo: 'stock-comparison',
        pathMatch: 'full'
      },
      {
        path: 'fo-analysis',
        loadComponent: () => import('./features/fo-analysis/fo-analysis.component').then(m => m.FOAnalysisComponent),
      },
      {
        path: 'stock-comparison',
        loadComponent: () => import('./features/stock-comparison/stock-comparison.component').then(m => m.StockComparisonComponent),
      },
      {
        path: 'moving-averages',
        loadComponent: () => import('./features/moving-averages/moving-averages.component').then(m => m.MovingAveragesComponent),
      }
    ],
    canActivate: [authGuard]
  },
  {
    path: 'fo',
    redirectTo: 'after-market-analysis/fo-analysis',
    pathMatch: 'full'
  },
  {
    path: 'stock-comparison',
    redirectTo: 'after-market-analysis/stock-comparison',
    pathMatch: 'full'
  },
  {
    path: 'moving-averages',
    redirectTo: 'after-market-analysis/moving-averages',
    pathMatch: 'full'
  },
  {
    path: 'announcements',
    loadComponent: () => import('./features/announcements/announcements.component').then(m => m.AnnouncementsComponent),
    canActivate: [authGuard]
  },
  {
    path: 'learn',
    loadComponent: () => import('./features/learn/learn.component').then(m => m.LearnComponent),
    canActivate: [authGuard]
  },
  {
    path: 'strategy-builder',
    loadComponent: () => import('./features/strategy-builder/strategy-builder.component').then(m => m.StrategyBuilderComponent),
    canActivate: [authGuard]
  },
  {
    path: 'portfolio',
    loadComponent: () => import('./features/portfolio/portfolio.component').then(m => m.PortfolioComponent),
    canActivate: [authGuard]
  },
  {
    path: 'profile',
    loadComponent: () => import('./features/profile/profile.component').then(m => m.ProfileComponent),
    canActivate: [authGuard]
  },

  {
    path: '**',
    redirectTo: 'dashboard'
  }
];
