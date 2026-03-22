import { ApplicationConfig, provideZoneChangeDetection, importProvidersFrom } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { LucideAngularModule, Moon, Sun, Bell, Settings, LogOut, Search, LayoutDashboard, ArrowUpRight, LineChart, Megaphone, GraduationCap, Menu, ChevronLeft, CheckCircle2, XCircle, AlertCircle, TrendingUp, TrendingDown, Briefcase, BarChart2, AlertTriangle, ArrowUp, ArrowDown, Landmark, Building2, FileText, Paperclip, Rocket, Zap, RefreshCw, ChartColumn } from 'lucide-angular';


import { routes } from './app.routes';
import { authInterceptor } from './core/interceptors/auth.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),
    provideHttpClient(withInterceptors([authInterceptor])),
    provideAnimationsAsync(),
    importProvidersFrom(LucideAngularModule.pick({
      Moon, Sun, Bell, Settings, LogOut, Search, LayoutDashboard, ArrowUpRight, LineChart, Megaphone, GraduationCap, Menu, ChevronLeft, CheckCircle2, XCircle, AlertCircle, TrendingUp, TrendingDown, Briefcase, BarChart2, AlertTriangle, ArrowUp, ArrowDown, Landmark, Building2, FileText, Paperclip, Rocket, Zap, RefreshCw, ChartColumn
    }))
  ]
};
