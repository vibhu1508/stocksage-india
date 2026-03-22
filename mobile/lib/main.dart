import 'package:flutter/material.dart';
import 'config/theme.dart';
import 'core/services/auth_service.dart';
import 'features/auth/login_screen.dart';
import 'features/dashboard/dashboard_screen.dart';
import 'features/stocks/stock_comparison_screen.dart';
import 'features/fo_analysis/fo_analysis_screen.dart';
import 'features/announcements/announcements_screen.dart';
import 'features/learn/learn_screen.dart';

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
      listenable: _authService,
      builder: (context, _) {
        return MaterialApp(
          title: 'StockSage India',
          debugShowCheckedModeBanner: false,
          theme: AppTheme.darkTheme,
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
  int _currentIndex = 0;
  final _announcementsKey = GlobalKey<AnnouncementsScreenState>();

  void _switchTab(int index, {int? subTab}) {
    setState(() => _currentIndex = index);
    if (index == 3 && subTab == 1) {
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
      const StockComparisonScreen(),
      const FOAnalysisScreen(),
      AnnouncementsScreen(key: _announcementsKey),
      const LearnScreen(),
    ];
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: _currentIndex == 0,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) {
          setState(() => _currentIndex = 0);
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
                icon: Icon(Icons.dashboard_rounded),
                label: 'Dashboard',
              ),
              BottomNavigationBarItem(
                icon: Icon(Icons.compare_arrows_rounded),
                label: 'Stocks',
              ),
              BottomNavigationBarItem(
                icon: Icon(Icons.candlestick_chart_rounded),
                label: 'F&O',
              ),
              BottomNavigationBarItem(
                icon: Icon(Icons.article_rounded),
                label: 'News',
              ),
              BottomNavigationBarItem(
                icon: Icon(Icons.school_rounded),
                label: 'Learn',
              ),
            ],
          ),
        ),
      ),
    );
  }
}
