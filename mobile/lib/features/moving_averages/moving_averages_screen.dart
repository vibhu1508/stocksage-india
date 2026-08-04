import 'package:flutter/material.dart';

import '../../config/theme.dart';
import '../../core/services/auth_service.dart';
import '../../core/services/dhan_chart_service.dart';
import '../../shared/widgets/profile_menu.dart';
import '../profile/profile_screen.dart';
import '../stocks/stock_detail_screen.dart';

class MovingAveragesScreen extends StatefulWidget {
  final AuthService authService;

  const MovingAveragesScreen({super.key, required this.authService});

  @override
  State<MovingAveragesScreen> createState() => _MovingAveragesScreenState();
}

class _MovingAveragesScreenState extends State<MovingAveragesScreen> {
  final _symbolsController = TextEditingController(text: 'RELIANCE, TCS, INFY, HDFCBANK, AXISBANK');
  final _filterController = TextEditingController();

  bool _loading = false;
  String _error = '';
  String _signalFilter = 'all';
  List<_MAScreenerRow> _rows = [];

  @override
  void initState() {
    super.initState();
    _runScan();
  }

  @override
  void dispose() {
    _symbolsController.dispose();
    _filterController.dispose();
    super.dispose();
  }

  Future<void> _runScan() async {
    setState(() {
      _loading = true;
      _error = '';
      _rows = [];
    });

    final symbols = _symbolsController.text
        .split(',')
        .map((s) => s.trim().toUpperCase())
        .where((s) => s.isNotEmpty)
        .toSet()
        .take(30)
        .toList();

    if (symbols.isEmpty) {
      setState(() {
        _loading = false;
        _error = 'Enter at least one symbol.';
      });
      return;
    }

    final out = <_MAScreenerRow>[];

    for (final symbol in symbols) {
      try {
        final res = await DhanChartService.getBootstrap(symbol: symbol, timeframe: ChartTimeframe.daily);
        final candles = res.candles;
        out.add(_buildRow(symbol, candles));
      } catch (e) {
        out.add(
          _MAScreenerRow(
            symbol: symbol,
            close: null,
            ma50: null,
            ma100: null,
            ma200: null,
            momentum10: null,
            signal: 'N/A',
            error: e.toString().replaceFirst('Exception: ', ''),
          ),
        );
      }
    }

    if (!mounted) return;
    setState(() {
      _rows = out;
      _loading = false;
    });
  }

  _MAScreenerRow _buildRow(String symbol, List<DhanChartCandle> candles) {
    final close = candles.isNotEmpty ? candles.last.close : null;
    final ma50 = _calculateMA(candles, 50);
    final ma100 = _calculateMA(candles, 100);
    final ma200 = _calculateMA(candles, 200);
    final momentum10 = _calculateMomentum(candles, 10);

    String signal = 'N/A';
    if (close != null && ma50 != null && ma100 != null && ma200 != null) {
      if (close > ma50 && ma50 > ma100 && ma100 > ma200) {
        signal = 'Bullish';
      } else if (close < ma50 && ma50 < ma100 && ma100 < ma200) {
        signal = 'Bearish';
      } else {
        signal = 'Mixed';
      }
    }

    return _MAScreenerRow(
      symbol: symbol,
      close: close,
      ma50: ma50,
      ma100: ma100,
      ma200: ma200,
      momentum10: momentum10,
      signal: signal,
    );
  }

  double? _calculateMA(List<DhanChartCandle> candles, int length) {
    if (candles.length < length) return null;
    double sum = 0;
    for (int i = candles.length - length; i < candles.length; i++) {
      sum += candles[i].close;
    }
    return sum / length;
  }

  double? _calculateMomentum(List<DhanChartCandle> candles, int period) {
    if (candles.length <= period) return null;
    return candles.last.close - candles[candles.length - 1 - period].close;
  }

  String _fmt(num? value) {
    if (value == null) return '--';
    return value.toStringAsFixed(2);
  }

  String _fmtSigned(num? value) {
    if (value == null) return '--';
    final n = value.toDouble();
    return '${n >= 0 ? '+' : ''}${n.toStringAsFixed(2)}';
  }

  List<_MAScreenerRow> get _filteredRows {
    final q = _filterController.text.trim().toUpperCase();
    return _rows.where((r) {
      if (q.isNotEmpty && !r.symbol.contains(q)) return false;
      switch (_signalFilter) {
        case 'bullish':
          return r.signal == 'Bullish';
        case 'bearish':
          return r.signal == 'Bearish';
        case 'mixed':
          return r.signal == 'Mixed';
        case 'na':
          return r.signal == 'N/A';
        case 'all':
        default:
          return true;
      }
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final rows = _filteredRows;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Moving Averages'),
        actions: [
          ProfileMenu(
            authService: widget.authService,
            onOpenProfile: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => ProfileScreen(authService: widget.authService)),
              );
            },
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _runScan,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextField(
              controller: _symbolsController,
              maxLines: 2,
              decoration: const InputDecoration(
                labelText: 'Symbols (comma separated)',
                hintText: 'RELIANCE, TCS, INFY',
              ),
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: ElevatedButton.icon(
                    onPressed: _loading ? null : _runScan,
                    icon: _loading
                        ? const SizedBox(
                            width: 14,
                            height: 14,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          )
                        : const Icon(Icons.radar_rounded),
                    label: Text(_loading ? 'Scanning...' : 'Run Screener'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _filterController,
                    decoration: const InputDecoration(
                      hintText: 'Filter symbol',
                      prefixIcon: Icon(Icons.search),
                    ),
                    onChanged: (_) => setState(() {}),
                  ),
                ),
                const SizedBox(width: 8),
                DropdownButton<String>(
                  value: _signalFilter,
                  items: const [
                    DropdownMenuItem(value: 'all', child: Text('All')),
                    DropdownMenuItem(value: 'bullish', child: Text('Bullish')),
                    DropdownMenuItem(value: 'bearish', child: Text('Bearish')),
                    DropdownMenuItem(value: 'mixed', child: Text('Mixed')),
                    DropdownMenuItem(value: 'na', child: Text('N/A')),
                  ],
                  onChanged: (v) {
                    if (v == null) return;
                    setState(() => _signalFilter = v);
                  },
                ),
              ],
            ),
            if (_error.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(_error, style: const TextStyle(color: Colors.redAccent)),
            ],
            const SizedBox(height: 10),
            ...rows.map((row) {
              final momentumPositive = (row.momentum10 ?? 0) >= 0;
              final signalColor = row.signal == 'Bullish'
                  ? AppTheme.successColor
                  : row.signal == 'Bearish'
                      ? AppTheme.errorColor
                      : Theme.of(context).colorScheme.onSurfaceVariant;

              return Card(
                margin: const EdgeInsets.only(bottom: 10),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Text(row.symbol, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
                          const Spacer(),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(999),
                              color: signalColor.withValues(alpha: 0.15),
                            ),
                            child: Text(
                              row.signal,
                              style: TextStyle(color: signalColor, fontSize: 11, fontWeight: FontWeight.w700),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 10,
                        runSpacing: 6,
                        children: [
                          Text('Close: ${_fmt(row.close)}'),
                          Text('MA50: ${_fmt(row.ma50)}'),
                          Text('MA100: ${_fmt(row.ma100)}'),
                          Text('MA200: ${_fmt(row.ma200)}'),
                          Text(
                            'Momentum10: ${_fmtSigned(row.momentum10)}',
                            style: TextStyle(color: momentumPositive ? AppTheme.successColor : AppTheme.errorColor),
                          ),
                        ],
                      ),
                      if ((row.error ?? '').isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Text(row.error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                      ],
                      const SizedBox(height: 8),
                      TextButton.icon(
                        onPressed: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(builder: (_) => StockDetailScreen(symbol: row.symbol)),
                          );
                        },
                        icon: const Icon(Icons.open_in_new, size: 16),
                        label: const Text('Open Stock'),
                      ),
                    ],
                  ),
                ),
              );
            }),
          ],
        ),
      ),
    );
  }
}

class _MAScreenerRow {
  final String symbol;
  final double? close;
  final double? ma50;
  final double? ma100;
  final double? ma200;
  final double? momentum10;
  final String signal;
  final String? error;

  _MAScreenerRow({
    required this.symbol,
    required this.close,
    required this.ma50,
    required this.ma100,
    required this.ma200,
    required this.momentum10,
    required this.signal,
    this.error,
  });
}
