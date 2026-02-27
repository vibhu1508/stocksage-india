import 'package:flutter/material.dart';
import '../../core/services/auth_service.dart';
import '../../config/theme.dart';

class DashboardScreen extends StatelessWidget {
  final AuthService authService;
  const DashboardScreen({super.key, required this.authService});

  String _getGreeting() {
    final hour = DateTime.now().hour;
    if (hour < 12) return 'Good Morning';
    if (hour < 17) return 'Good Afternoon';
    return 'Good Evening';
  }

  @override
  Widget build(BuildContext context) {
    final user = authService.currentUser;

    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
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
                  // Profile avatar + logout
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
                            Text(user?.email ?? ''),
                          ],
                        ),
                      ),
                      PopupMenuItem(
                        onTap: () => authService.logout(),
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
                ],
              ),
              const SizedBox(height: 28),

              // Stats Cards
              _buildStatsGrid(),
              const SizedBox(height: 28),

              // Quick Actions
              const Text(
                'Quick Actions',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 16),
              _buildQuickActions(context),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStatsGrid() {
    final stats = [
      {
        'label': 'Market Status',
        'value': 'Open',
        'icon': Icons.circle,
        'color': AppTheme.successColor,
      },
      {
        'label': 'NIFTY 50',
        'value': '22,456.80',
        'icon': Icons.trending_up,
        'color': AppTheme.successColor,
      },
      {
        'label': 'SENSEX',
        'value': '73,892.45',
        'icon': Icons.bar_chart,
        'color': AppTheme.accentColor,
      },
      {
        'label': 'Announcements',
        'value': 'Today',
        'icon': Icons.article,
        'color': AppTheme.warningColor,
      },
    ];

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        crossAxisSpacing: 12,
        mainAxisSpacing: 12,
        childAspectRatio: 1.6,
      ),
      itemCount: stats.length,
      itemBuilder: (context, index) {
        final stat = stats[index];
        return Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppTheme.cardColor,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: Colors.white10),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Icon(
                stat['icon'] as IconData,
                color: stat['color'] as Color,
                size: 22,
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    stat['value'] as String,
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  Text(
                    stat['label'] as String,
                    style: TextStyle(
                      fontSize: 12,
                      color: AppTheme.textSecondary,
                    ),
                  ),
                ],
              ),
            ],
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
      },
    ];

    return Column(
      children: actions.map((action) {
        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          child: Material(
            color: AppTheme.cardColor,
            borderRadius: BorderRadius.circular(16),
            child: InkWell(
              onTap: () {
                // Navigate via bottom nav - handled by MainShell
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
                        color: AppTheme.primaryColor.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Icon(
                        action['icon'] as IconData,
                        color: AppTheme.primaryColor,
                      ),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            action['label'] as String,
                            style: const TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          Text(
                            action['desc'] as String,
                            style: TextStyle(
                              fontSize: 13,
                              color: AppTheme.textSecondary,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Icon(
                      Icons.arrow_forward_ios,
                      size: 16,
                      color: AppTheme.textSecondary,
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      }).toList(),
    );
  }
}
