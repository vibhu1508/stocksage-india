import 'dart:async';
import 'package:flutter/material.dart';
import 'package:interactive_chart/interactive_chart.dart';
import '../../config/theme.dart';
import '../../core/services/chart_service.dart';

class StockChartScreen extends StatefulWidget {
  const StockChartScreen({super.key});

  @override
  State<StockChartScreen> createState() => _StockChartScreenState();
}

class _StockChartScreenState extends State<StockChartScreen> {
  final ChartService _chartService = ChartService();
  final TextEditingController _searchController = TextEditingController();

  // State
  String _selectedSymbol = 'NIFTY';
  String _selectedName = 'NIFTY 50';
  Map<String, dynamic>? _quoteData;
  List<CandleData> _chartData = [];
  bool _isLoadingQuote = false;
  bool _isLoadingChart = false;
  String _activePeriod = '1y';
  bool _isIndex = true;

  // Search
  List<dynamic> _searchResults = [];
  bool _isSearching = false;
  Timer? _debounce;

  final List<Map<String, String>> _indexPresets = [
    {'symbol': 'NIFTY', 'name': 'Nifty 50'},
    {'symbol': 'NIFTY BANK', 'name': 'Nifty Bank'},
    {'symbol': 'NIFTY IT', 'name': 'Nifty IT'},
    {'symbol': 'NIFTY NEXT 50', 'name': 'Nifty Next 50'},
    {'symbol': 'NIFTY MIDCAP 100', 'name': 'Nifty Midcap 100'},
    {'symbol': 'NIFTY SMLCAP 100', 'name': 'Smallcap 100'},
    {'symbol': 'NIFTY AUTO', 'name': 'Nifty Auto'},
    {'symbol': 'NIFTY PHARMA', 'name': 'Nifty Pharma'},
    {'symbol': 'NIFTY FMCG', 'name': 'Nifty FMCG'},
    {'symbol': 'NIFTY PSU BANK', 'name': 'Nifty PSU Bank'},
    {'symbol': 'NIFTY ENERGY', 'name': 'Nifty Energy'},
    {'symbol': 'NIFTY REALTY', 'name': 'Nifty Realty'},
  ];

  final Map<String, Map<String, String>> _periods = {
    '1d': {'label': '1D', 'interval': '1m'},
    '5d': {'label': '5D', 'interval': '5m'},
    '1mo': {'label': '1M', 'interval': '1d'},
    '3mo': {'label': '3M', 'interval': '1d'},
    '6mo': {'label': '6M', 'interval': '1d'},
    '1y': {'label': '1Y', 'interval': '1d'},
    '2y': {'label': '2Y', 'interval': '1d'},
    '5y': {'label': '5Y', 'interval': '1wk'},
    'max': {'label': 'Max', 'interval': '1mo'},
  };

  @override
  void initState() {
    super.initState();
    _loadStockData('NIFTY', isIndex: true);
  }

  @override
  void dispose() {
    _searchController.dispose();
    _debounce?.cancel();
    super.dispose();
  }

  void _onSearchChanged(String query) {
    if (_debounce?.isActive ?? false) _debounce!.cancel();
    if (query.length < 2) {
      setState(() {
        _searchResults = [];
        _isSearching = false;
      });
      return;
    }

    _debounce = Timer(const Duration(milliseconds: 400), () async {
      setState(() => _isSearching = true);
      try {
        final res = await _chartService.searchTickers(query);
        setState(() {
          _searchResults = res['results'] ?? [];
          _isSearching = false;
        });
      } catch (e) {
        setState(() => _isSearching = false);
      }
    });
  }

  Future<void> _loadStockData(String symbol, {bool isIndex = false}) async {
    setState(() {
      _selectedSymbol = symbol;
      _isIndex = isIndex;
      _isLoadingQuote = true;
      _searchResults = [];
      _searchController.clear();
      FocusManager.instance.primaryFocus?.unfocus();
    });

    try {
      final quote = await _chartService.getQuote(symbol);
      setState(() {
        _quoteData = quote;
        _selectedName = quote['name'] ?? symbol;
        _isLoadingQuote = false;
      });
      await _loadChartData(symbol, _activePeriod);
    } catch (e) {
      if (mounted) {
        setState(() => _isLoadingQuote = false);
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Failed to load $symbol')));
      }
    }
  }

  Future<void> _loadChartData(String symbol, String period) async {
    setState(() {
      _isLoadingChart = true;
      _activePeriod = period;
    });

    final interval = _periods[period]?['interval'] ?? '1d';

    try {
      final res = await _chartService.getHistory(symbol, period, interval);
      final List<dynamic> history = res['history'] ?? [];

      final candles = history.map((e) {
        int timestamp;
        final timeVal = e['time'];
        if (timeVal is String) {
          timestamp = DateTime.parse(timeVal).millisecondsSinceEpoch;
        } else {
          timestamp = (timeVal as num).toInt() * 1000;
        }
        return CandleData(
          timestamp: timestamp,
          open: (e['open'] as num).toDouble(),
          high: (e['high'] as num).toDouble(),
          low: (e['low'] as num).toDouble(),
          close: (e['close'] as num).toDouble(),
          volume: (e['volume'] as num).toDouble(),
        );
      }).toList();

      setState(() {
        _chartData = candles;
        _isLoadingChart = false;
      });
    } catch (e) {
      setState(() => _isLoadingChart = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: _buildSearchBar(),
      body: Stack(
        children: [
          SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildIndexPresets(),
                _buildQuoteHeader(),
                _buildChartArea(),
                _buildTimeToggles(),
                const Divider(height: 1, color: Colors.white10),
                if (!_isIndex) _buildStockActionButtons(),
              ],
            ),
          ),
          if (_searchResults.isNotEmpty) _buildSearchDropdown(),
        ],
      ),
    );
  }

  PreferredSizeWidget _buildSearchBar() {
    return AppBar(
      title: TextField(
        controller: _searchController,
        onChanged: _onSearchChanged,
        style: const TextStyle(fontSize: 14),
        decoration: InputDecoration(
          hintText: 'Search stocks or indices...',
          prefixIcon: const Icon(Icons.search, color: Colors.grey),
          suffixIcon: _isSearching
              ? const Padding(
                  padding: EdgeInsets.all(12),
                  child: SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                )
              : null,
          filled: true,
          fillColor: AppTheme.cardColor,
          contentPadding: const EdgeInsets.symmetric(vertical: 0),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(30),
            borderSide: BorderSide.none,
          ),
        ),
      ),
    );
  }

  Widget _buildSearchDropdown() {
    return Positioned(
      top: 0,
      left: 16,
      right: 16,
      child: Material(
        elevation: 8,
        borderRadius: BorderRadius.circular(12),
        color: AppTheme.cardColor,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: 300),
          child: ListView.separated(
            shrinkWrap: true,
            itemCount: _searchResults.length,
            separatorBuilder: (_, __) =>
                const Divider(height: 1, color: Colors.white10),
            itemBuilder: (context, index) {
              final item = _searchResults[index];
              final sym = item['symbol'] ?? '';
              final type = item['type'] ?? '';
              final isIdx = type.toLowerCase() == 'index';
              return ListTile(
                title: Text(
                  sym,
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                subtitle: Text(
                  item['name'] ?? '',
                  style: const TextStyle(fontSize: 12, color: Colors.grey),
                ),
                trailing: Text(
                  type,
                  style: const TextStyle(fontSize: 10, color: Colors.grey),
                ),
                onTap: () => _loadStockData(sym, isIndex: isIdx),
              );
            },
          ),
        ),
      ),
    );
  }

  Widget _buildIndexPresets() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      child: SizedBox(
        height: 34,
        child: ListView.builder(
          scrollDirection: Axis.horizontal,
          itemCount: _indexPresets.length,
          itemBuilder: (context, index) {
            final preset = _indexPresets[index];
            final isActive = _selectedSymbol == preset['symbol'];
            return Padding(
              padding: const EdgeInsets.only(right: 8),
              child: InkWell(
                onTap: () => _loadStockData(preset['symbol']!, isIndex: true),
                borderRadius: BorderRadius.circular(20),
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 6,
                  ),
                  decoration: BoxDecoration(
                    color: isActive
                        ? AppTheme.primaryColor
                        : AppTheme.cardColor,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: isActive ? AppTheme.primaryColor : Colors.white12,
                    ),
                  ),
                  child: Text(
                    preset['name']!,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: isActive
                          ? FontWeight.bold
                          : FontWeight.normal,
                      color: isActive ? Colors.white : Colors.grey,
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildQuoteHeader() {
    if (_isLoadingQuote) {
      return const Padding(
        padding: EdgeInsets.all(16),
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (_quoteData == null) return const SizedBox.shrink();

    final price = (_quoteData!['price'] ?? 0).toDouble();
    final change = (_quoteData!['change'] ?? 0).toDouble();
    final pctChange = (_quoteData!['pctChange'] ?? 0).toDouble();
    final isPositive = change >= 0;
    final color = isPositive ? AppTheme.successColor : AppTheme.errorColor;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _selectedName,
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                Text(
                  _selectedSymbol,
                  style: const TextStyle(fontSize: 12, color: Colors.grey),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '₹${price.toStringAsFixed(2)}',
                style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                ),
              ),
              Row(
                children: [
                  Icon(
                    isPositive ? Icons.arrow_drop_up : Icons.arrow_drop_down,
                    color: color,
                    size: 20,
                  ),
                  Text(
                    '${change.abs().toStringAsFixed(2)} (${pctChange.abs().toStringAsFixed(2)}%)',
                    style: TextStyle(
                      fontSize: 14,
                      color: color,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildChartArea() {
    if (_isLoadingChart) {
      return const SizedBox(
        height: 280,
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (_chartData.isEmpty) {
      return const SizedBox(
        height: 280,
        child: Center(
          child: Text(
            'No chart data available',
            style: TextStyle(color: Colors.grey),
          ),
        ),
      );
    }

    return SizedBox(
      height: 280,
      width: double.infinity,
      child: InteractiveChart(
        candles: _chartData,
        style: const ChartStyle(
          volumeColor: Color(0x33FFFFFF),
          priceGainColor: AppTheme.successColor,
          priceLossColor: AppTheme.errorColor,
        ),
      ),
    );
  }

  Widget _buildTimeToggles() {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: _periods.entries.map((entry) {
            final isActive = _activePeriod == entry.key;
            return Padding(
              padding: const EdgeInsets.only(right: 8),
              child: InkWell(
                onTap: () => _loadChartData(_selectedSymbol, entry.key),
                borderRadius: BorderRadius.circular(6),
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 6,
                  ),
                  decoration: BoxDecoration(
                    color: isActive
                        ? AppTheme.primaryColor.withValues(alpha: 0.2)
                        : Colors.transparent,
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(
                      color: isActive ? AppTheme.primaryColor : Colors.white12,
                    ),
                  ),
                  child: Text(
                    entry.value['label']!,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: isActive
                          ? FontWeight.bold
                          : FontWeight.normal,
                      color: isActive ? AppTheme.primaryColor : Colors.grey,
                    ),
                  ),
                ),
              ),
            );
          }).toList(),
        ),
      ),
    );
  }

  /// Only shown when a stock (not an index) is selected via search
  Widget _buildStockActionButtons() {
    final actions = [
      'Fundamentals',
      'Financials',
      'Option Chain',
      'News',
      'Announcements',
    ];

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: SizedBox(
        height: 36,
        child: ListView.builder(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          itemCount: actions.length,
          itemBuilder: (context, index) {
            return Padding(
              padding: const EdgeInsets.only(right: 8),
              child: ActionChip(
                label: Text(actions[index]),
                backgroundColor: AppTheme.cardColor,
                labelStyle: const TextStyle(color: Colors.grey, fontSize: 13),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(20),
                ),
                side: BorderSide.none,
                onPressed: () {
                  // TODO: Navigate to detail pages
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text('${actions[index]} coming soon!')),
                  );
                },
              ),
            );
          },
        ),
      ),
    );
  }
}
