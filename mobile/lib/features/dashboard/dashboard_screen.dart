import 'package:flutter/material.dart';
import 'dart:async';
import '../../core/services/auth_service.dart';
import '../../core/services/market_service.dart';
import '../../config/theme.dart';

class DashboardScreen extends StatefulWidget {
  final AuthService authService;
  final void Function(int, {int? subTab}) onNavigateToTab;
  const DashboardScreen({
    super.key,
    required this.authService,
    required this.onNavigateToTab,
  });

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late List<Animation<double>> _fadeAnimations;
  late List<Animation<Offset>> _slideAnimations;

  // Live market data
  MarketData? _marketData;
  Timer? _refreshTimer;

  // Top gainers
  List<Map<String, dynamic>> _topGainers = [];
  late PageController _carouselController;
  Timer? _carouselTimer;
  int _carouselPage = 0;

  // Top losers
  List<Map<String, dynamic>> _topLosers = [];
  late PageController _losersCarouselController;
  Timer? _losersCarouselTimer;
  int _losersCarouselPage = 0;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1200),
      vsync: this,
    );

    _fadeAnimations = List.generate(7, (i) {
      final start = i * 0.1;
      final end = (start + 0.4).clamp(0.0, 1.0);
      return Tween<double>(begin: 0, end: 1).animate(
        CurvedAnimation(
          parent: _controller,
          curve: Interval(start, end, curve: Curves.easeOut),
        ),
      );
    });

    _slideAnimations = List.generate(7, (i) {
      final start = i * 0.1;
      final end = (start + 0.4).clamp(0.0, 1.0);
      return Tween<Offset>(
        begin: const Offset(0, 0.3),
        end: Offset.zero,
      ).animate(
        CurvedAnimation(
          parent: _controller,
          curve: Interval(start, end, curve: Curves.easeOutCubic),
        ),
      );
    });

    _controller.forward();
    _fetchMarketData();
    _fetchTopGainers();
    _fetchTopLosers();
    _refreshTimer = Timer.periodic(const Duration(seconds: 10), (_) {
      _fetchMarketData();
    });
    _carouselController = PageController();
    _losersCarouselController = PageController();
  }

  Future<void> _fetchMarketData() async {
    try {
      final data = await MarketService.getLiveData();
      if (mounted) {
        setState(() {
          _marketData = data;
        });
      }
    } catch (_) {}
  }

  Future<void> _fetchTopGainers() async {
    try {
      final data = await MarketService.getTopGainers();
      if (mounted && data.isNotEmpty) {
        setState(() => _topGainers = data);
        _startCarouselTimer();
      }
    } catch (_) {}
  }

  void _startCarouselTimer() {
    _carouselTimer?.cancel();
    _carouselTimer = Timer.periodic(const Duration(seconds: 3), (_) {
      if (_topGainers.isEmpty || !mounted) return;
      _carouselPage = (_carouselPage + 1) % _topGainers.length;
      if (_carouselController.hasClients) {
        _carouselController.animateToPage(
          _carouselPage,
          duration: const Duration(milliseconds: 400),
          curve: Curves.easeInOut,
        );
      }
    });
  }

  Future<void> _fetchTopLosers() async {
    try {
      final data = await MarketService.getTopLosers();
      if (mounted && data.isNotEmpty) {
        setState(() => _topLosers = data);
        _startLosersCarouselTimer();
      }
    } catch (_) {}
  }

  void _startLosersCarouselTimer() {
    _losersCarouselTimer?.cancel();
    _losersCarouselTimer = Timer.periodic(const Duration(seconds: 3), (_) {
      if (_topLosers.isEmpty || !mounted) return;
      _losersCarouselPage = (_losersCarouselPage + 1) % _topLosers.length;
      if (_losersCarouselController.hasClients) {
        _losersCarouselController.animateToPage(
          _losersCarouselPage,
          duration: const Duration(milliseconds: 400),
          curve: Curves.easeInOut,
        );
      }
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    _refreshTimer?.cancel();
    _carouselTimer?.cancel();
    _carouselController.dispose();
    _losersCarouselTimer?.cancel();
    _losersCarouselController.dispose();
    super.dispose();
  }

  String _getGreeting() {
    final hour = DateTime.now().hour;
    if (hour < 12) return 'Good Morning';
    if (hour < 17) return 'Good Afternoon';
    return 'Good Evening';
  }

  Widget _animated(int index, Widget child) {
    return FadeTransition(
      opacity: _fadeAnimations[index],
      child: SlideTransition(position: _slideAnimations[index], child: child),
    );
  }

  @override
  Widget build(BuildContext context) {
    final user = widget.authService.currentUser;

    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header — animated
              _animated(
                0,
                Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            _getGreeting(),
                            style: TextStyle(
                              fontSize: 14,
                              color: AppTheme.textSecondary,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            user?.name ?? 'User',
                            style: const TextStyle(
                              fontSize: 24,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ],
                      ),
                    ),
                    PopupMenuButton(
                      offset: const Offset(0, 48),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                      itemBuilder: (context) => [
                        PopupMenuItem(
                          child: Row(
                            children: [
                              const Icon(Icons.person_outline, size: 20),
                              const SizedBox(width: 8),
                              Flexible(
                                child: Text(
                                  user?.email ?? '',
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                            ],
                          ),
                        ),
                        PopupMenuItem(
                          onTap: () => widget.authService.logout(),
                          child: const Row(
                            children: [
                              Icon(
                                Icons.logout,
                                size: 20,
                                color: AppTheme.errorColor,
                              ),
                              SizedBox(width: 8),
                              Text(
                                'Logout',
                                style: TextStyle(color: AppTheme.errorColor),
                              ),
                            ],
                          ),
                        ),
                      ],
                      child: Hero(
                        tag: 'avatar',
                        child: CircleAvatar(
                          radius: 22,
                          backgroundColor: AppTheme.primaryColor,
                          backgroundImage: user?.picture != null
                              ? NetworkImage(user!.picture!)
                              : null,
                          child: user?.picture == null
                              ? Text(
                                  (user?.name ?? 'U')[0].toUpperCase(),
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w700,
                                    color: Colors.white,
                                  ),
                                )
                              : null,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 28),

              // Stats Cards — each animated separately
              _buildAnimatedStatsGrid(),
              const SizedBox(height: 20),

              // Top Gainers Carousel
              if (_topGainers.isNotEmpty) ...[
                _animated(
                  4,
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const Icon(
                            Icons.trending_up,
                            size: 18,
                            color: Colors.greenAccent,
                          ),
                          const SizedBox(width: 6),
                          const Text(
                            'Top Gainers',
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          const Spacer(),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 3,
                            ),
                            decoration: BoxDecoration(
                              color: Colors.greenAccent.withValues(alpha: 0.15),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(
                              'LIVE',
                              style: TextStyle(
                                fontSize: 10,
                                fontWeight: FontWeight.w700,
                                color: Colors.greenAccent,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      SizedBox(
                        height: 80,
                        child: PageView.builder(
                          controller: _carouselController,
                          itemCount: _topGainers.length,
                          onPageChanged: (i) =>
                              setState(() => _carouselPage = i),
                          itemBuilder: (context, index) {
                            final g = _topGainers[index];
                            final pct =
                                (g['pct_change'] as num?)?.toDouble() ?? 0;
                            final price = (g['price'] as num?)?.toDouble() ?? 0;
                            final change =
                                (g['change'] as num?)?.toDouble() ?? 0;
                            return Container(
                              margin: const EdgeInsets.symmetric(horizontal: 2),
                              padding: const EdgeInsets.all(14),
                              decoration: BoxDecoration(
                                gradient: LinearGradient(
                                  colors: [
                                    Colors.greenAccent.withValues(alpha: 0.08),
                                    AppTheme.cardColor,
                                  ],
                                  begin: Alignment.topLeft,
                                  end: Alignment.bottomRight,
                                ),
                                borderRadius: BorderRadius.circular(14),
                                border: Border.all(
                                  color: Colors.greenAccent.withValues(
                                    alpha: 0.2,
                                  ),
                                ),
                              ),
                              child: Row(
                                children: [
                                  // Left: Symbol + Price
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      mainAxisAlignment:
                                          MainAxisAlignment.center,
                                      children: [
                                        Text(
                                          g['symbol'] ?? '',
                                          style: const TextStyle(
                                            fontWeight: FontWeight.w700,
                                            fontSize: 15,
                                          ),
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                        const SizedBox(height: 4),
                                        Text(
                                          '₹${price.toStringAsFixed(2)}',
                                          style: TextStyle(
                                            fontSize: 13,
                                            color: AppTheme.textSecondary,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  // Right: Change + Percent
                                  Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    crossAxisAlignment: CrossAxisAlignment.end,
                                    children: [
                                      Container(
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: 8,
                                          vertical: 4,
                                        ),
                                        decoration: BoxDecoration(
                                          color: Colors.greenAccent.withValues(
                                            alpha: 0.15,
                                          ),
                                          borderRadius: BorderRadius.circular(
                                            8,
                                          ),
                                        ),
                                        child: Row(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            const Icon(
                                              Icons.arrow_upward,
                                              size: 12,
                                              color: Colors.greenAccent,
                                            ),
                                            const SizedBox(width: 2),
                                            Text(
                                              '+${pct.toStringAsFixed(2)}%',
                                              style: const TextStyle(
                                                color: Colors.greenAccent,
                                                fontWeight: FontWeight.w700,
                                                fontSize: 13,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                      const SizedBox(height: 4),
                                      Text(
                                        '+${change.toStringAsFixed(2)}',
                                        style: TextStyle(
                                          fontSize: 11,
                                          color: Colors.greenAccent.withValues(
                                            alpha: 0.7,
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            );
                          },
                        ),
                      ),
                      // Page indicator dots
                      const SizedBox(height: 8),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: List.generate(
                          _topGainers.length,
                          (i) => AnimatedContainer(
                            duration: const Duration(milliseconds: 200),
                            width: i == _carouselPage ? 16 : 6,
                            height: 6,
                            margin: const EdgeInsets.symmetric(horizontal: 2),
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(3),
                              color: i == _carouselPage
                                  ? Colors.greenAccent
                                  : AppTheme.textSecondary.withValues(
                                      alpha: 0.3,
                                    ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
              ],

              // Top Losers Carousel
              if (_topLosers.isNotEmpty) ...[
                _animated(
                  4,
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const Icon(
                            Icons.trending_down,
                            size: 18,
                            color: Colors.redAccent,
                          ),
                          const SizedBox(width: 6),
                          const Text(
                            'Top Losers',
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          const Spacer(),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 3,
                            ),
                            decoration: BoxDecoration(
                              color: Colors.redAccent.withValues(alpha: 0.15),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(
                              'LIVE',
                              style: TextStyle(
                                fontSize: 10,
                                fontWeight: FontWeight.w700,
                                color: Colors.redAccent,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      SizedBox(
                        height: 80,
                        child: PageView.builder(
                          controller: _losersCarouselController,
                          itemCount: _topLosers.length,
                          onPageChanged: (i) =>
                              setState(() => _losersCarouselPage = i),
                          itemBuilder: (context, index) {
                            final g = _topLosers[index];
                            final pct =
                                (g['pct_change'] as num?)?.toDouble() ?? 0;
                            final price = (g['price'] as num?)?.toDouble() ?? 0;
                            final change =
                                (g['change'] as num?)?.toDouble() ?? 0;
                            return Container(
                              margin: const EdgeInsets.symmetric(horizontal: 2),
                              padding: const EdgeInsets.all(14),
                              decoration: BoxDecoration(
                                gradient: LinearGradient(
                                  colors: [
                                    Colors.redAccent.withValues(alpha: 0.08),
                                    AppTheme.cardColor,
                                  ],
                                  begin: Alignment.topLeft,
                                  end: Alignment.bottomRight,
                                ),
                                borderRadius: BorderRadius.circular(14),
                                border: Border.all(
                                  color: Colors.redAccent.withValues(
                                    alpha: 0.2,
                                  ),
                                ),
                              ),
                              child: Row(
                                children: [
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      mainAxisAlignment:
                                          MainAxisAlignment.center,
                                      children: [
                                        Text(
                                          g['symbol'] ?? '',
                                          style: const TextStyle(
                                            fontWeight: FontWeight.w700,
                                            fontSize: 15,
                                          ),
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                        const SizedBox(height: 4),
                                        Text(
                                          '\u20b9${price.toStringAsFixed(2)}',
                                          style: TextStyle(
                                            fontSize: 13,
                                            color: AppTheme.textSecondary,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    crossAxisAlignment: CrossAxisAlignment.end,
                                    children: [
                                      Container(
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: 8,
                                          vertical: 4,
                                        ),
                                        decoration: BoxDecoration(
                                          color: Colors.redAccent.withValues(
                                            alpha: 0.15,
                                          ),
                                          borderRadius: BorderRadius.circular(
                                            8,
                                          ),
                                        ),
                                        child: Row(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            const Icon(
                                              Icons.arrow_downward,
                                              size: 12,
                                              color: Colors.redAccent,
                                            ),
                                            const SizedBox(width: 2),
                                            Text(
                                              '${pct.toStringAsFixed(2)}%',
                                              style: const TextStyle(
                                                color: Colors.redAccent,
                                                fontWeight: FontWeight.w700,
                                                fontSize: 13,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                      const SizedBox(height: 4),
                                      Text(
                                        '${change.toStringAsFixed(2)}',
                                        style: TextStyle(
                                          fontSize: 11,
                                          color: Colors.redAccent.withValues(
                                            alpha: 0.7,
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            );
                          },
                        ),
                      ),
                      const SizedBox(height: 8),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: List.generate(
                          _topLosers.length,
                          (i) => AnimatedContainer(
                            duration: const Duration(milliseconds: 200),
                            width: i == _losersCarouselPage ? 16 : 6,
                            height: 6,
                            margin: const EdgeInsets.symmetric(horizontal: 2),
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(3),
                              color: i == _losersCarouselPage
                                  ? Colors.redAccent
                                  : AppTheme.textSecondary.withValues(
                                      alpha: 0.3,
                                    ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
              ],

              // Quick Actions title
              _animated(
                5,
                const Text(
                  'Quick Actions',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                ),
              ),
              const SizedBox(height: 16),

              // Quick action cards
              _animated(6, _buildQuickActions(context)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAnimatedStatsGrid() {
    // Market status
    final status = _marketData?.marketStatus ?? 'Loading...';
    Color statusColor;
    switch (status) {
      case 'Open':
        statusColor = AppTheme.successColor;
        break;
      case 'Pre-Open':
      case 'Pre-Market':
        statusColor = AppTheme.warningColor;
        break;
      default:
        statusColor = AppTheme.errorColor;
    }

    // NIFTY data
    final nifty = _marketData?.nifty;
    final niftyValue = nifty?.formattedValue ?? '--';
    final niftyChange = nifty != null
        ? '${nifty.isPositive ? "+" : ""}${nifty.pctChange}%'
        : '';
    final niftyColor = nifty != null
        ? (nifty.isPositive ? AppTheme.successColor : AppTheme.errorColor)
        : AppTheme.textSecondary;

    // SENSEX data
    final sensex = _marketData?.sensex;
    final sensexValue = sensex?.formattedValue ?? '--';
    final sensexChange = sensex != null
        ? '${sensex.isPositive ? "+" : ""}${sensex.pctChange}%'
        : '';
    final sensexColor = sensex != null
        ? (sensex.isPositive ? AppTheme.successColor : AppTheme.errorColor)
        : AppTheme.textSecondary;

    final stats = [
      {
        'label': 'Market Status',
        'value': status,
        'icon': Icons.circle,
        'color': statusColor,
        'sub': '',
      },
      {
        'label': 'NIFTY 50',
        'value': niftyValue,
        'icon': nifty != null && nifty.isPositive
            ? Icons.trending_up
            : Icons.trending_down,
        'color': niftyColor,
        'sub': niftyChange,
      },
      {
        'label': 'SENSEX',
        'value': sensexValue,
        'icon': sensex != null && sensex.isPositive
            ? Icons.trending_up
            : Icons.trending_down,
        'color': sensexColor,
        'sub': sensexChange,
      },
      {
        'label': 'My Portfolio',
        'value': 'View',
        'icon': Icons.account_balance_wallet_rounded,
        'color': AppTheme.warningColor,
        'sub': 'Coming Soon',
      },
    ];

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        crossAxisSpacing: 12,
        mainAxisSpacing: 12,
        childAspectRatio: 1.4,
      ),
      itemCount: stats.length,
      itemBuilder: (context, index) {
        final stat = stats[index];
        final label = stat['label'] as String;
        final isMarketStatus = label == 'Market Status';
        final isIndex = label == 'NIFTY 50' || label == 'SENSEX';
        bool? chartUp;
        if (label == 'NIFTY 50' && nifty != null) chartUp = nifty.isPositive;
        if (label == 'SENSEX' && sensex != null) chartUp = sensex.isPositive;
        return _animated(
          index + 1,
          _StatCard(
            label: label,
            value: stat['value'] as String,
            icon: stat['icon'] as IconData,
            color: stat['color'] as Color,
            subtitle: stat['sub'] as String,
            pulseGlow: isMarketStatus,
            showChart: isIndex,
            chartGoingUp: chartUp,
          ),
        );
      },
    );
  }

  Widget _buildQuickActions(BuildContext context) {
    final actions = [
      {
        'label': 'Compare Stocks',
        'desc': 'Analyze price changes',
        'icon': Icons.compare_arrows_rounded,
        'tab': 1,
      },
      {
        'label': 'F&O Analysis',
        'desc': 'Futures & options data',
        'icon': Icons.candlestick_chart_rounded,
        'tab': 2,
      },
      {
        'label': 'NSE Announcements',
        'desc': 'Corporate filings',
        'icon': Icons.article_rounded,
        'tab': 3,
      },
      {
        'label': 'BSE Announcements',
        'desc': 'BSE filings',
        'icon': Icons.newspaper_rounded,
        'tab': 3,
        'subTab': 1,
      },
    ];

    return Column(
      children: actions.map((action) {
        return _QuickActionCard(
          label: action['label'] as String,
          desc: action['desc'] as String,
          icon: action['icon'] as IconData,
          onTap: () {
            final tab = action['tab'] as int;
            final subTab = action['subTab'] as int?;
            widget.onNavigateToTab(tab, subTab: subTab);
          },
        );
      }).toList(),
    );
  }
}

// Extracted stat card with scale animation on tap
class _StatCard extends StatefulWidget {
  final String label, value;
  final IconData icon;
  final Color color;
  final String subtitle;
  final bool pulseGlow;
  final bool showChart;
  final bool? chartGoingUp;
  const _StatCard({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
    this.subtitle = '',
    this.pulseGlow = false,
    this.showChart = false,
    this.chartGoingUp,
  });

  @override
  State<_StatCard> createState() => _StatCardState();
}

class _StatCardState extends State<_StatCard> with TickerProviderStateMixin {
  late AnimationController _scaleController;
  late Animation<double> _scale;
  AnimationController? _glowController;
  AnimationController? _chartController;

  @override
  void initState() {
    super.initState();
    _scaleController = AnimationController(
      duration: const Duration(milliseconds: 150),
      vsync: this,
      lowerBound: 0.95,
      upperBound: 1.0,
      value: 1.0,
    );
    _scale = _scaleController;

    if (widget.pulseGlow) {
      _glowController = AnimationController(
        duration: const Duration(milliseconds: 1500),
        vsync: this,
      )..repeat(reverse: true);
    }

    if (widget.showChart) {
      _chartController = AnimationController(
        duration: const Duration(milliseconds: 2000),
        vsync: this,
      )..forward();
    }
  }

  @override
  void dispose() {
    _scaleController.dispose();
    _glowController?.dispose();
    _chartController?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTapDown: (_) => _scaleController.reverse(),
      onTapUp: (_) => _scaleController.forward(),
      onTapCancel: () => _scaleController.forward(),
      child: ScaleTransition(
        scale: _scale,
        child: AnimatedBuilder(
          animation: Listenable.merge([
            if (_glowController != null) _glowController!,
            if (_chartController != null) _chartController!,
          ]),
          builder: (context, child) {
            final glowAlpha = _glowController?.value ?? 0.0;
            return Container(
              clipBehavior: Clip.antiAlias,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    AppTheme.cardColor,
                    widget.color.withValues(alpha: 0.08),
                  ],
                ),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: widget.pulseGlow
                      ? widget.color.withValues(alpha: 0.2 + glowAlpha * 0.5)
                      : widget.color.withValues(alpha: 0.2),
                  width: widget.pulseGlow ? 1.5 : 1.0,
                ),
                boxShadow: widget.pulseGlow
                    ? [
                        BoxShadow(
                          color: widget.color.withValues(
                            alpha: glowAlpha * 0.3,
                          ),
                          blurRadius: 12 + glowAlpha * 8,
                          spreadRadius: glowAlpha * 2,
                        ),
                      ]
                    : null,
              ),
              child: Stack(
                children: [
                  // Mini chart background
                  if (widget.showChart && _chartController != null)
                    Positioned.fill(
                      child: CustomPaint(
                        painter: _MiniChartPainter(
                          color: widget.color,
                          progress: _chartController!.value,
                          goingUp: widget.chartGoingUp ?? true,
                        ),
                      ),
                    ),
                  // Content
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Container(
                          padding: const EdgeInsets.all(6),
                          decoration: BoxDecoration(
                            color: widget.color.withValues(alpha: 0.15),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Icon(
                            widget.icon,
                            color: widget.color,
                            size: 18,
                          ),
                        ),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              widget.value,
                              style: const TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.w700,
                              ),
                              overflow: TextOverflow.ellipsis,
                            ),
                            Row(
                              children: [
                                Flexible(
                                  child: Text(
                                    widget.label,
                                    style: TextStyle(
                                      fontSize: 11,
                                      color: AppTheme.textSecondary,
                                    ),
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                                if (widget.subtitle.isNotEmpty) ...[
                                  const SizedBox(width: 4),
                                  Text(
                                    widget.subtitle,
                                    style: TextStyle(
                                      fontSize: 11,
                                      fontWeight: FontWeight.w600,
                                      color: widget.color,
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

/// Paints a sharp animated mini chart line in the background
class _MiniChartPainter extends CustomPainter {
  final Color color;
  final double progress;
  final bool goingUp;

  _MiniChartPainter({
    required this.color,
    required this.progress,
    required this.goingUp,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;

    // Realistic price action data points (normalized 0-1)
    // Sharp zigzag pattern like actual intraday charts
    final rawPoints = goingUp
        ? [
            0.78,
            0.72,
            0.75,
            0.65,
            0.68,
            0.60,
            0.55,
            0.58,
            0.50,
            0.52,
            0.45,
            0.48,
            0.40,
            0.42,
            0.35,
            0.38,
            0.30,
            0.33,
            0.28,
            0.25,
            0.22,
          ]
        : [
            0.22,
            0.28,
            0.25,
            0.32,
            0.30,
            0.38,
            0.42,
            0.40,
            0.48,
            0.45,
            0.52,
            0.50,
            0.58,
            0.55,
            0.62,
            0.60,
            0.68,
            0.65,
            0.72,
            0.75,
            0.78,
          ];

    final n = rawPoints.length;
    final segW = w / (n - 1);
    final drawW = w * progress;

    final path = Path();

    // Map normalized values to Y coordinates with padding
    final topPad = h * 0.12;
    final botPad = h * 0.12;
    final chartH = h - topPad - botPad;

    path.moveTo(0, topPad + rawPoints[0] * chartH);

    for (int i = 1; i < n; i++) {
      final x = segW * i;
      if (x > drawW) break;
      final y = topPad + rawPoints[i] * chartH;
      path.lineTo(x, y);
    }

    // Sharp line stroke
    final linePaint = Paint()
      ..color = color.withValues(alpha: 0.35)
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke
      ..strokeJoin = StrokeJoin.bevel;
    canvas.drawPath(path, linePaint);

    // Fill area under the line
    final lastX = ((n - 1) * segW).clamp(0.0, drawW).toDouble();
    final fillPath = Path.from(path);
    fillPath.lineTo(lastX, h);
    fillPath.lineTo(0, h);
    fillPath.close();

    final fillPaint = Paint()
      ..shader = LinearGradient(
        begin: goingUp ? Alignment.topCenter : Alignment.bottomCenter,
        end: goingUp ? Alignment.bottomCenter : Alignment.topCenter,
        colors: [color.withValues(alpha: 0.10), color.withValues(alpha: 0.01)],
      ).createShader(Rect.fromLTWH(0, 0, w, h));
    canvas.drawPath(fillPath, fillPaint);
  }

  @override
  bool shouldRepaint(_MiniChartPainter old) =>
      old.progress != progress || old.goingUp != goingUp || old.color != color;
}

// Extracted quick action card with animated hover/ripple
class _QuickActionCard extends StatefulWidget {
  final String label, desc;
  final IconData icon;
  final VoidCallback onTap;
  const _QuickActionCard({
    required this.label,
    required this.desc,
    required this.icon,
    required this.onTap,
  });

  @override
  State<_QuickActionCard> createState() => _QuickActionCardState();
}

class _QuickActionCardState extends State<_QuickActionCard>
    with SingleTickerProviderStateMixin {
  late AnimationController _hoverController;
  late Animation<double> _iconSlide;

  @override
  void initState() {
    super.initState();
    _hoverController = AnimationController(
      duration: const Duration(milliseconds: 200),
      vsync: this,
    );
    _iconSlide = Tween<double>(
      begin: 0.0,
      end: 4.0,
    ).animate(CurvedAnimation(parent: _hoverController, curve: Curves.easeOut));
  }

  @override
  void dispose() {
    _hoverController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      child: Material(
        color: AppTheme.cardColor,
        borderRadius: BorderRadius.circular(16),
        child: InkWell(
          onTap: widget.onTap,
          onHighlightChanged: (highlighted) {
            highlighted
                ? _hoverController.forward()
                : _hoverController.reverse();
          },
          borderRadius: BorderRadius.circular(16),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Container(
                  width: 48,
                  height: 48,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [
                        AppTheme.primaryColor.withValues(alpha: 0.2),
                        AppTheme.accentColor.withValues(alpha: 0.1),
                      ],
                    ),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(widget.icon, color: AppTheme.primaryColor),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        widget.label,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      Text(
                        widget.desc,
                        style: TextStyle(
                          fontSize: 13,
                          color: AppTheme.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                AnimatedBuilder(
                  animation: _iconSlide,
                  builder: (context, child) {
                    return Transform.translate(
                      offset: Offset(_iconSlide.value, 0),
                      child: child,
                    );
                  },
                  child: Icon(
                    Icons.arrow_forward_ios,
                    size: 16,
                    color: AppTheme.textSecondary,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
