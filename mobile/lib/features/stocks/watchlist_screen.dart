import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../config/theme.dart';
import '../../core/models/stock.dart';
import '../../core/services/auth_service.dart';
import '../../core/services/dhan_chart_service.dart';
import '../../core/services/stock_service.dart';
import '../../shared/widgets/profile_menu.dart';
import '../portfolio/portfolio_service.dart';
import '../profile/profile_screen.dart';
import 'stock_detail_screen.dart';

class WatchlistScreen extends StatefulWidget {
  final AuthService authService;

  const WatchlistScreen({super.key, required this.authService});

  @override
  State<WatchlistScreen> createState() => _WatchlistScreenState();
}

class _WatchlistScreenState extends State<WatchlistScreen> {
  final _searchController = TextEditingController();

  static const List<String> _defaultSymbols = [
    'AXISBANK',
    'RELIANCE',
    'INFY',
    'TCS',
    'HDFCBANK',
  ];

  List<String> _watchSymbols = List<String>.from(_defaultSymbols);
  List<String> _portfolioSymbols = [];
  List<SymbolSearchResult> _suggestions = [];
  bool _showSuggestions = false;

  String _selectedSymbol = 'AXISBANK';
  ChartTimeframe _timeframe = ChartTimeframe.five;
  _WatchlistChartType _chartType = _WatchlistChartType.line;
  int _panelIndex = 0; // 0 chart, 1 depth

  bool _chartLoading = false;
  String _chartError = '';
  List<DhanChartCandle> _candles = [];

  bool _depthLoading = false;
  String _depthError = '';
  int _depthLimit = 20;
  List<DhanDepthLevel> _depthBuy = [];
  List<DhanDepthLevel> _depthSell = [];

  @override
  void initState() {
    super.initState();
    _loadPortfolioSymbols();
    _refreshSelectedData();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _loadPortfolioSymbols() async {
    try {
      final service = PortfolioService();
      final res = await service.getHoldings();
      final holdings = (res['holdings'] as List?) ?? const [];
      final symbols = holdings
          .whereType<PortfolioHolding>()
          .map((h) => h.symbol.trim().toUpperCase())
          .where((s) => s.isNotEmpty)
          .toSet()
          .toList()
        ..sort();
      if (!mounted) return;
      setState(() => _portfolioSymbols = symbols);
    } catch (_) {
      if (!mounted) return;
      setState(() => _portfolioSymbols = []);
    }
  }

  Future<void> _refreshSelectedData() async {
    await Future.wait([
      _loadChart(),
      _loadDepth(limit: _depthLimit),
    ]);
  }

  Future<void> _loadChart() async {
    setState(() {
      _chartLoading = true;
      _chartError = '';
    });

    try {
      final res = await DhanChartService.getBootstrap(
        symbol: _selectedSymbol,
        timeframe: _timeframe,
      );
      if (!mounted) return;
      setState(() {
        _candles = res.candles;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _chartError = e.toString().replaceFirst('Exception: ', '');
        _candles = [];
      });
    } finally {
      if (mounted) {
        setState(() => _chartLoading = false);
      }
    }
  }

  Future<void> _loadDepth({required int limit}) async {
    setState(() {
      _depthLoading = true;
      _depthError = '';
      _depthLimit = limit;
    });

    try {
      final res = await DhanChartService.getMarketDepth(
        symbol: _selectedSymbol,
        timeframe: _timeframe,
        limit: limit,
      );
      if (!mounted) return;
      setState(() {
        _depthBuy = res.buy;
        _depthSell = res.sell;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _depthError = e.toString().replaceFirst('Exception: ', '');
        _depthBuy = [];
        _depthSell = [];
      });
    } finally {
      if (mounted) {
        setState(() => _depthLoading = false);
      }
    }
  }

  Future<void> _searchSymbols(String query) async {
    if (query.trim().length < 2) {
      setState(() {
        _suggestions = [];
        _showSuggestions = false;
      });
      return;
    }

    try {
      final results = await StockService.searchSymbols(query.trim(), 8);
      if (!mounted) return;
      setState(() {
        _suggestions = results;
        _showSuggestions = results.isNotEmpty;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _suggestions = [];
        _showSuggestions = false;
      });
    }
  }

  void _addSymbolFromInput() {
    final symbol = _searchController.text.trim().toUpperCase();
    if (symbol.isEmpty) return;

    if (!_watchSymbols.contains(symbol)) {
      setState(() {
        _watchSymbols = [symbol, ..._watchSymbols];
      });
    }

    _searchController.clear();
    setState(() {
      _showSuggestions = false;
      _suggestions = [];
    });

    _selectSymbol(symbol);
  }

  void _selectSuggestion(SymbolSearchResult item) {
    _searchController.text = item.symbol;
    _showSuggestions = false;
    _suggestions = [];
    _addSymbolFromInput();
  }

  void _selectSymbol(String symbol) {
    final normalized = symbol.trim().toUpperCase();
    if (normalized.isEmpty) return;

    setState(() {
      _selectedSymbol = normalized;
    });
    _refreshSelectedData();
  }

  void _removeSymbol(String symbol) {
    if (_watchSymbols.length <= 1) return;

    setState(() {
      _watchSymbols = _watchSymbols.where((s) => s != symbol).toList();
      if (_selectedSymbol == symbol) {
        _selectedSymbol = _watchSymbols.first;
      }
    });

    if (_selectedSymbol == symbol) {
      _refreshSelectedData();
    }
  }

  String _fmtNum(num? value, {int digits = 2}) {
    if (value == null) return '--';
    return value.toStringAsFixed(digits);
  }

  String _fmtQty(num? value) {
    if (value == null) return '--';
    return value.toStringAsFixed(0);
  }

  Widget _buildSymbolSection({
    required String title,
    required List<String> symbols,
    required bool removable,
  }) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            const SizedBox(height: 10),
            if (symbols.isEmpty)
              Text('No symbols', style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant))
            else
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: symbols.map((symbol) {
                  final selected = symbol == _selectedSymbol;
                  return InputChip(
                    selected: selected,
                    label: Text(symbol),
                    selectedColor: Theme.of(context).colorScheme.primaryContainer,
                    backgroundColor: Theme.of(context).cardColor,
                    checkmarkColor: Theme.of(context).colorScheme.onPrimaryContainer,
                    labelStyle: TextStyle(
                      color: selected
                          ? Theme.of(context).colorScheme.onPrimaryContainer
                          : Theme.of(context).colorScheme.onSurface,
                      fontWeight: FontWeight.w600,
                    ),
                    onSelected: (_) => _selectSymbol(symbol),
                    onDeleted: removable ? () => _removeSymbol(symbol) : null,
                    deleteIcon: removable
                        ? Icon(
                            Icons.close,
                            size: 16,
                            color: selected
                                ? Theme.of(context).colorScheme.onPrimaryContainer
                                : Theme.of(context).colorScheme.onSurfaceVariant,
                          )
                        : null,
                  );
                }).toList(),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildChartPanel() {
    final closePoints = _candles
        .asMap()
        .entries
        .map((e) => FlSpot(e.key.toDouble(), e.value.close))
        .toList();
    final selected = _candles.isNotEmpty ? _candles.last : null;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            LayoutBuilder(
              builder: (context, constraints) {
                final narrow = constraints.maxWidth < 640;
                if (narrow) {
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Chart', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Expanded(
                            child: DropdownButtonFormField<_WatchlistChartType>(
                              initialValue: _chartType,
                              isDense: true,
                              decoration: const InputDecoration(
                                labelText: 'Chart Type',
                                contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                              ),
                              items: _WatchlistChartType.values
                                  .map(
                                    (type) => DropdownMenuItem<_WatchlistChartType>(
                                      value: type,
                                      child: Text(type.label),
                                    ),
                                  )
                                  .toList(),
                              onChanged: (value) {
                                if (value == null) return;
                                setState(() => _chartType = value);
                              },
                            ),
                          ),
                          const SizedBox(width: 8),
                          TextButton(
                            onPressed: () {
                              Navigator.push(
                                context,
                                MaterialPageRoute(builder: (_) => StockDetailScreen(symbol: _selectedSymbol)),
                              );
                            },
                            child: const Text('Open Full'),
                          ),
                        ],
                      ),
                    ],
                  );
                }

                return Row(
                  children: [
                    const Text('Chart', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
                    const Spacer(),
                    SizedBox(
                      width: 145,
                      child: DropdownButtonFormField<_WatchlistChartType>(
                        initialValue: _chartType,
                        isDense: true,
                        decoration: const InputDecoration(
                          labelText: 'Chart Type',
                          contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                        ),
                        items: _WatchlistChartType.values
                            .map(
                              (type) => DropdownMenuItem<_WatchlistChartType>(
                                value: type,
                                child: Text(type.label),
                              ),
                            )
                            .toList(),
                        onChanged: (value) {
                          if (value == null) return;
                          setState(() => _chartType = value);
                        },
                      ),
                    ),
                    const SizedBox(width: 8),
                    TextButton(
                      onPressed: () {
                        Navigator.push(
                          context,
                          MaterialPageRoute(builder: (_) => StockDetailScreen(symbol: _selectedSymbol)),
                        );
                      },
                      child: const Text('Open Full Stock Page'),
                    ),
                  ],
                );
              },
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: ChartTimeframe.values.map((tf) {
                return ChoiceChip(
                  selected: _timeframe == tf,
                  label: Text(tf.label),
                  selectedColor: Theme.of(context).colorScheme.primaryContainer,
                  backgroundColor: Theme.of(context).cardColor,
                  labelStyle: TextStyle(
                    color: _timeframe == tf
                        ? Theme.of(context).colorScheme.onPrimaryContainer
                        : Theme.of(context).colorScheme.onSurface,
                    fontWeight: FontWeight.w600,
                  ),
                  onSelected: (_) {
                    setState(() => _timeframe = tf);
                    _refreshSelectedData();
                  },
                );
              }).toList(),
            ),
            if (selected != null) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _ohlcPill('O ${_fmtNum(selected.open)}'),
                  _ohlcPill('H ${_fmtNum(selected.high)}', color: AppTheme.successColor),
                  _ohlcPill('L ${_fmtNum(selected.low)}', color: AppTheme.errorColor),
                  _ohlcPill('C ${_fmtNum(selected.close)}'),
                ],
              ),
            ],
            const SizedBox(height: 10),
            if (_chartLoading)
              const SizedBox(height: 280, child: Center(child: CircularProgressIndicator()))
            else if (_chartError.isNotEmpty)
              Text(_chartError, style: const TextStyle(color: AppTheme.errorColor))
            else if (closePoints.isEmpty)
              const SizedBox(height: 280, child: Center(child: Text('No chart data')))
            else
              SizedBox(
                height: 280,
                child: _buildPriceChart(closePoints),
              ),
          ],
        ),
      ),
    );
  }

  Widget _ohlcPill(String text, {Color? color}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Theme.of(context).dividerColor.withValues(alpha: 0.6)),
        color: Theme.of(context).brightness == Brightness.dark ? const Color(0xFF111827) : const Color(0xFFF8FAFC),
      ),
      child: Text(
        text,
        style: TextStyle(
          fontWeight: FontWeight.w700,
          fontSize: 12,
          color: color,
        ),
      ),
    );
  }

  Widget _buildDepthPanel() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Market Depth', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                ChoiceChip(
                  selected: _depthLimit == 20,
                  label: const Text('Top 20'),
                  selectedColor: Theme.of(context).colorScheme.primaryContainer,
                  backgroundColor: Theme.of(context).cardColor,
                  labelStyle: TextStyle(
                    color: _depthLimit == 20
                        ? Theme.of(context).colorScheme.onPrimaryContainer
                        : Theme.of(context).colorScheme.onSurface,
                    fontWeight: FontWeight.w600,
                  ),
                  onSelected: (_) => _loadDepth(limit: 20),
                ),
                ChoiceChip(
                  selected: _depthLimit == 200,
                  label: const Text('View 200 Depth'),
                  selectedColor: Theme.of(context).colorScheme.primaryContainer,
                  backgroundColor: Theme.of(context).cardColor,
                  labelStyle: TextStyle(
                    color: _depthLimit == 200
                        ? Theme.of(context).colorScheme.onPrimaryContainer
                        : Theme.of(context).colorScheme.onSurface,
                    fontWeight: FontWeight.w600,
                  ),
                  onSelected: (_) => _loadDepth(limit: 200),
                ),
              ],
            ),
            const SizedBox(height: 12),
            if (_depthLoading)
              const Center(child: CircularProgressIndicator())
            else if (_depthError.isNotEmpty)
              Text(_depthError, style: const TextStyle(color: AppTheme.errorColor))
            else
              Column(
                children: [
                  _buildDepthTable('Buy Orders', _depthBuy, true),
                  const SizedBox(height: 12),
                  _buildDepthTable('Sell Orders', _depthSell, false),
                ],
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildDepthTable(String title, List<DhanDepthLevel> rows, bool buySide) {
    final showRows = rows.take(12).toList();
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Theme.of(context).dividerColor.withValues(alpha: 0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          ...showRows.map((r) {
            final color = buySide ? AppTheme.successColor : AppTheme.errorColor;
            return Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                children: [
                  Expanded(child: Text(_fmtQty(r.orders), textAlign: TextAlign.right, style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant))),
                  const SizedBox(width: 8),
                  Expanded(child: Text(_fmtQty(r.quantity), textAlign: TextAlign.right, style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant))),
                  const SizedBox(width: 8),
                  Expanded(child: Text(_fmtNum(r.price), textAlign: TextAlign.right, style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.w700))),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Watchlist'),
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
      body: GestureDetector(
        behavior: HitTestBehavior.translucent,
        onTap: () {
          FocusScope.of(context).unfocus();
          setState(() {
            _showSuggestions = false;
          });
        },
        child: RefreshIndicator(
          onRefresh: _refreshSelectedData,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Add Symbol', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _searchController,
                              decoration: const InputDecoration(
                                hintText: 'Search/add stock or option symbol',
                                prefixIcon: Icon(Icons.search),
                              ),
                              onChanged: _searchSymbols,
                              onSubmitted: (_) => _addSymbolFromInput(),
                            ),
                          ),
                          const SizedBox(width: 8),
                          ElevatedButton(
                            onPressed: _addSymbolFromInput,
                            child: const Text('Add'),
                          ),
                        ],
                      ),
                      if (_showSuggestions && _suggestions.isNotEmpty)
                        Container(
                          margin: const EdgeInsets.only(top: 8),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(color: Theme.of(context).dividerColor),
                          ),
                          child: Column(
                            children: _suggestions.map((s) {
                              return ListTile(
                                dense: true,
                                title: Text(s.symbol),
                                subtitle: Text(s.name, maxLines: 1, overflow: TextOverflow.ellipsis),
                                onTap: () => _selectSuggestion(s),
                              );
                            }).toList(),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              _buildSymbolSection(title: 'Watchlist Symbols', symbols: _watchSymbols, removable: true),
              const SizedBox(height: 12),
              _buildSymbolSection(title: 'Portfolio Symbols', symbols: _portfolioSymbols, removable: false),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  ChoiceChip(
                    selected: _panelIndex == 0,
                    label: const Text('Chart'),
                    selectedColor: Theme.of(context).colorScheme.primaryContainer,
                    backgroundColor: Theme.of(context).cardColor,
                    labelStyle: TextStyle(
                      color: _panelIndex == 0
                          ? Theme.of(context).colorScheme.onPrimaryContainer
                          : Theme.of(context).colorScheme.onSurface,
                      fontWeight: FontWeight.w600,
                    ),
                    onSelected: (_) => setState(() => _panelIndex = 0),
                  ),
                  ChoiceChip(
                    selected: _panelIndex == 1,
                    label: const Text('Market Depth'),
                    selectedColor: Theme.of(context).colorScheme.primaryContainer,
                    backgroundColor: Theme.of(context).cardColor,
                    labelStyle: TextStyle(
                      color: _panelIndex == 1
                          ? Theme.of(context).colorScheme.onPrimaryContainer
                          : Theme.of(context).colorScheme.onSurface,
                      fontWeight: FontWeight.w600,
                    ),
                    onSelected: (_) => setState(() => _panelIndex = 1),
                  ),
                  OutlinedButton.icon(
                    onPressed: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(builder: (_) => StockDetailScreen(symbol: _selectedSymbol)),
                      );
                    },
                    icon: const Icon(Icons.open_in_new, size: 18),
                    label: const Text('Details'),
                    style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      side: BorderSide(
                        color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.8),
                      ),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              _panelIndex == 0 ? _buildChartPanel() : _buildDepthPanel(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPriceChart(List<FlSpot> closePoints) {
    final minY = _candles.map((c) => c.low).reduce((a, b) => a < b ? a : b);
    final maxY = _candles.map((c) => c.high).reduce((a, b) => a > b ? a : b);
    final yRange = (maxY - minY).abs();
    final interval = _niceInterval(yRange == 0 ? maxY.abs() : yRange, targetTicks: 5);
    final decimalPlaces = _priceDecimals(yRange);

    if (_chartType == _WatchlistChartType.candles) {
      return _buildCandlestickChart(minY: minY, maxY: maxY);
    }

    if (_chartType == _WatchlistChartType.bars) {
      final bars = closePoints
          .map(
            (spot) => BarChartGroupData(
              x: spot.x.toInt(),
              barRods: [
                BarChartRodData(
                  toY: spot.y,
                  width: 4,
                  color: Theme.of(context).colorScheme.primary,
                  borderRadius: BorderRadius.circular(1),
                ),
              ],
            ),
          )
          .toList();

      return BarChart(
        BarChartData(
          minY: minY,
          maxY: maxY,
          barGroups: bars,
          alignment: BarChartAlignment.spaceBetween,
          gridData: FlGridData(show: true, drawVerticalLine: true, horizontalInterval: interval),
          borderData: FlBorderData(
            show: true,
            border: Border.all(color: Theme.of(context).dividerColor.withValues(alpha: 0.4)),
          ),
          titlesData: FlTitlesData(
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            leftTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 50,
                interval: interval,
                getTitlesWidget: (value, meta) => _buildLeftAxisLabel(value, meta, decimalPlaces),
              ),
            ),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 28,
                interval: _bottomInterval(closePoints.length),
                getTitlesWidget: _buildBottomAxisLabel,
              ),
            ),
          ),
        ),
      );
    }

    return LineChart(
      LineChartData(
        minY: minY,
        maxY: maxY,
        lineBarsData: [
          LineChartBarData(
            spots: closePoints,
            isCurved: true,
            color: Theme.of(context).colorScheme.primary,
            barWidth: 2,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(
              show: _chartType == _WatchlistChartType.area,
              color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.18),
            ),
          ),
        ],
        gridData: FlGridData(
          show: true,
          drawVerticalLine: true,
          horizontalInterval: interval,
        ),
        borderData: FlBorderData(
          show: true,
          border: Border.all(color: Theme.of(context).dividerColor.withValues(alpha: 0.4)),
        ),
        titlesData: FlTitlesData(
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 50,
              interval: interval,
              getTitlesWidget: (value, meta) => _buildLeftAxisLabel(value, meta, decimalPlaces),
            ),
          ),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 28,
              interval: _bottomInterval(closePoints.length),
              getTitlesWidget: _buildBottomAxisLabel,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildCandlestickChart({required double minY, required double maxY}) {
    return LayoutBuilder(
      builder: (context, constraints) {
        return CustomPaint(
          size: Size(constraints.maxWidth, 280),
          painter: _WatchlistCandlestickPainter(
            candles: _candles,
            minY: minY,
            maxY: maxY,
            upColor: AppTheme.successColor,
            downColor: AppTheme.errorColor,
            axisColor: Theme.of(context).dividerColor.withValues(alpha: 0.6),
          ),
        );
      },
    );
  }

  Widget _buildLeftAxisLabel(double value, TitleMeta meta, int decimals) {
    return SideTitleWidget(
      meta: meta,
      space: 6,
      child: Text(
        value.toStringAsFixed(decimals),
        style: TextStyle(
          fontSize: 11,
          color: Theme.of(context).colorScheme.onSurfaceVariant,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  Widget _buildBottomAxisLabel(double value, TitleMeta meta) {
    if (_candles.isEmpty) {
      return const SizedBox.shrink();
    }

    final index = value.round();
    if (index < 0 || index >= _candles.length) {
      return const SizedBox.shrink();
    }

    final ts = DateTime.fromMillisecondsSinceEpoch(_candles[index].time * 1000);
    final label = _timeframe == ChartTimeframe.daily ? DateFormat('dd MMM').format(ts) : DateFormat('HH:mm').format(ts);

    return SideTitleWidget(
      meta: meta,
      space: 6,
      child: Text(
        label,
        style: TextStyle(
          fontSize: 10,
          color: Theme.of(context).colorScheme.onSurfaceVariant,
        ),
      ),
    );
  }

  double _bottomInterval(int points) {
    if (points <= 1) return 1;
    return (points / 4).ceilToDouble();
  }

  int _priceDecimals(double range) {
    if (range >= 100) return 0;
    if (range >= 10) return 1;
    return 2;
  }

  double _niceInterval(double range, {int targetTicks = 5}) {
    if (range <= 0 || range.isNaN || range.isInfinite) return 1;
    final rough = range / targetTicks;
    final exponent = rough == 0 ? 0 : (math.log(rough) / math.ln10).floor();
    final magnitude = double.parse('1e$exponent');
    final residual = rough / magnitude;

    final niceResidual = residual <= 1
        ? 1.0
        : residual <= 2
            ? 2.0
            : residual <= 5
                ? 5.0
                : 10.0;
    return niceResidual * magnitude;
  }
}

enum _WatchlistChartType { line, area, bars, candles }

extension _WatchlistChartTypeLabel on _WatchlistChartType {
  String get label {
    switch (this) {
      case _WatchlistChartType.line:
        return 'Line';
      case _WatchlistChartType.area:
        return 'Area';
      case _WatchlistChartType.bars:
        return 'Bars';
      case _WatchlistChartType.candles:
        return 'Candles';
    }
  }
}

class _WatchlistCandlestickPainter extends CustomPainter {
  final List<DhanChartCandle> candles;
  final double minY;
  final double maxY;
  final Color upColor;
  final Color downColor;
  final Color axisColor;

  _WatchlistCandlestickPainter({
    required this.candles,
    required this.minY,
    required this.maxY,
    required this.upColor,
    required this.downColor,
    required this.axisColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (candles.isEmpty) return;

    const leftPad = 42.0;
    const rightPad = 10.0;
    const topPad = 10.0;
    const bottomPad = 24.0;

    final chartRect = Rect.fromLTWH(
      leftPad,
      topPad,
      size.width - leftPad - rightPad,
      size.height - topPad - bottomPad,
    );

    if (chartRect.width <= 0 || chartRect.height <= 0) return;

    final borderPaint = Paint()
      ..color = axisColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;
    canvas.drawRect(chartRect, borderPaint);

    final range = (maxY - minY).abs() < 0.000001 ? 1.0 : (maxY - minY);
    double yToPx(double value) {
      return chartRect.bottom - ((value - minY) / range) * chartRect.height;
    }

    final step = chartRect.width / candles.length;
    final candleWidth = (step * 0.65).clamp(1.5, 10.0);

    final wickPaint = Paint()..strokeWidth = 1.1;
    final bodyPaint = Paint()..style = PaintingStyle.fill;

    for (int i = 0; i < candles.length; i++) {
      final c = candles[i];
      final x = chartRect.left + (i * step) + ((step - candleWidth) / 2);
      if (x > chartRect.right) break;

      final openY = yToPx(c.open);
      final closeY = yToPx(c.close);
      final highY = yToPx(c.high);
      final lowY = yToPx(c.low);
      final isUp = c.close >= c.open;
      final color = isUp ? upColor : downColor;

      wickPaint.color = color;
      bodyPaint.color = color.withValues(alpha: 0.9);

      final centerX = x + (candleWidth / 2);
      canvas.drawLine(Offset(centerX, highY), Offset(centerX, lowY), wickPaint);

      final bodyTop = isUp ? closeY : openY;
      final bodyBottom = isUp ? openY : closeY;
      final bodyHeight = (bodyBottom - bodyTop).abs().clamp(1.5, chartRect.height);
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(x, bodyTop, candleWidth, bodyHeight),
          const Radius.circular(1.2),
        ),
        bodyPaint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _WatchlistCandlestickPainter oldDelegate) {
    return oldDelegate.candles != candles ||
        oldDelegate.minY != minY ||
        oldDelegate.maxY != maxY ||
        oldDelegate.upColor != upColor ||
        oldDelegate.downColor != downColor ||
        oldDelegate.axisColor != axisColor;
  }
}
