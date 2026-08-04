import 'package:flutter/material.dart';

import '../../core/services/auth_service.dart';
import '../../shared/widgets/profile_menu.dart';
import '../fo_analysis/fo_analysis_screen.dart';
import '../moving_averages/moving_averages_screen.dart';
import '../profile/profile_screen.dart';
import '../stocks/stock_comparison_screen.dart';

class AfterMarketAnalysisScreen extends StatelessWidget {
  final AuthService authService;

  const AfterMarketAnalysisScreen({super.key, required this.authService});

  void _open(BuildContext context, Widget screen) {
    Navigator.push(context, MaterialPageRoute(builder: (_) => screen));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('AMA'),
        actions: [
          ProfileMenu(
            authService: authService,
            onOpenProfile: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => ProfileScreen(authService: authService)),
              );
            },
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            'Explore post-close insights with F&O, stock comparison, and moving averages screeners.',
            style: TextStyle(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
              fontSize: 13,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 14),
          _AnalysisCard(
            title: 'F&O Analysis',
            subtitle: 'Momentum, futures and options analysis',
            icon: Icons.candlestick_chart_rounded,
            onTap: () => _open(context, FOAnalysisScreen(authService: authService)),
          ),
          const SizedBox(height: 10),
          _AnalysisCard(
            title: 'Stock Comparison',
            subtitle: 'Compare symbols by date and identify movers',
            icon: Icons.compare_arrows_rounded,
            onTap: () => _open(context, StockComparisonScreen(authService: authService)),
          ),
          const SizedBox(height: 10),
          _AnalysisCard(
            title: 'Moving Averages',
            subtitle: 'MA50/100/200 with 10-day momentum screener',
            icon: Icons.timeline_rounded,
            onTap: () => _open(context, MovingAveragesScreen(authService: authService)),
          ),
        ],
      ),
    );
  }
}

class _AnalysisCard extends StatelessWidget {
  final String title;
  final String subtitle;
  final IconData icon;
  final VoidCallback onTap;

  const _AnalysisCard({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(12),
                  color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.14),
                ),
                child: Icon(icon, color: Theme.of(context).colorScheme.primary),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 3),
                    Text(
                      subtitle,
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right_rounded),
            ],
          ),
        ),
      ),
    );
  }
}
