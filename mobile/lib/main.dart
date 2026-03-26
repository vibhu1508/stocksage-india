import 'package:flutter/material.dart';
import 'config/theme.dart';
import 'core/navigation/app_tabs.dart';
import 'core/services/auth_service.dart';
import 'features/auth/login_screen.dart';
import 'features/dashboard/dashboard_screen.dart';
import 'features/portfolio/portfolio_screen.dart';
import 'features/profile/profile_screen.dart';
import 'features/strategy_builder/strategy_builder_screen.dart';
import 'features/stocks/stock_comparison_screen.dart';
import 'features/fo_analysis/fo_analysis_screen.dart';
import 'features/announcements/announcements_screen.dart';
import 'package:lucide_icons/lucide_icons.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const StockSageApp());
}

class StockSageApp extends StatefulWidget {
  const StockSageApp({super.key});

  @override
  State<StockSageApp> createState() => _StockSageAppState();
}

class _StockSageAppState extends State<StockSageApp> {
  final AuthService _authService = AuthService();
  bool _initialized = false;

  @override
  void initState() {
    super.initState();
    _initAuth();
  }

  Future<void> _initAuth() async {
    await _authService.init();
    setState(() => _initialized = true);
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([_authService, themeNotifier]),
      builder: (context, _) {
        return MaterialApp(
          title: 'StockSage India',
          debugShowCheckedModeBanner: false,
          theme: AppTheme.lightTheme,
          darkTheme: AppTheme.darkTheme,
          themeMode: themeNotifier.value,
          home: _buildHome(),
        );
      },
    );
  }

  Widget _buildHome() {
    if (!_initialized) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    if (!_authService.isAuthenticated) {
      return LoginScreen(authService: _authService);
    }

    final user = _authService.currentUser;
    final shouldShowOnboarding = user != null && !user.onboardingCompleted && !user.onboardingSkipped;
    if (shouldShowOnboarding) {
      return ProfileScreen(authService: _authService, onboardingRequired: true);
    }

    return MainShell(authService: _authService);
  }
}

class MainShell extends StatefulWidget {
  final AuthService authService;
  const MainShell({super.key, required this.authService});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _currentIndex = AppTabs.home;
  final _announcementsKey = GlobalKey<AnnouncementsScreenState>();

  void _switchTab(int index, {int? subTab}) {
    setState(() => _currentIndex = index);
    if (index == AppTabs.news && subTab == 1) {
      // Small delay so the screen is visible before switching sub-tab
      Future.delayed(const Duration(milliseconds: 100), () {
        _announcementsKey.currentState?.switchToBSE();
      });
    }
  }

  late final List<Widget> _screens;

  @override
  void initState() {
    super.initState();
    _screens = [
      DashboardScreen(
        authService: widget.authService,
        onNavigateToTab: _switchTab,
      ),
      PortfolioScreen(authService: widget.authService),
      StockComparisonScreen(authService: widget.authService),
      FOAnalysisScreen(authService: widget.authService),
      const StrategyBuilderScreen(),
      AnnouncementsScreen(key: _announcementsKey, authService: widget.authService),
    ];
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: _currentIndex == AppTabs.home,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) {
          setState(() => _currentIndex = AppTabs.home);
        }
      },
      child: Scaffold(
        body: AnimatedSwitcher(
          duration: const Duration(milliseconds: 300),
          switchInCurve: Curves.easeOut,
          switchOutCurve: Curves.easeIn,
          transitionBuilder: (child, animation) {
            return FadeTransition(opacity: animation, child: child);
          },
          child: KeyedSubtree(
            key: ValueKey(_currentIndex),
            child: _screens[_currentIndex],
          ),
        ),
        bottomNavigationBar: Container(
          decoration: BoxDecoration(
            border: Border(top: BorderSide(color: Colors.white10, width: 0.5)),
          ),
          child: BottomNavigationBar(
            currentIndex: _currentIndex,
            onTap: _switchTab,
            items: const [
              BottomNavigationBarItem(
                icon: Icon(LucideIcons.layoutDashboard),
                label: 'Home',
              ),
              BottomNavigationBarItem(
                icon: Icon(LucideIcons.briefcase),
                label: 'Portfolio',
              ),
              BottomNavigationBarItem(
                icon: Icon(LucideIcons.arrowUpRight),
                label: 'Stocks',
              ),
              BottomNavigationBarItem(
                icon: Icon(LucideIcons.lineChart),
                label: 'F&O',
              ),
              BottomNavigationBarItem(
                icon: Icon(Icons.account_tree_outlined),
                label: 'Strategy',
              ),
              BottomNavigationBarItem(
                icon: Icon(LucideIcons.megaphone),
                label: 'News',
              ),
            ],
          ),
        ),
      ),
    );
  }
}
