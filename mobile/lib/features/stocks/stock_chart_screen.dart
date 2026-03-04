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

  // Info Tabs State
  String _activeTab =
      'Fundamentals'; // Fundamentals, Financials, Option Chain, News
  bool _isLoadingTab = false;
  Map<String, dynamic>? _fundamentalsData;
  Map<String, dynamic>? _financialsData;
  List<dynamic>? _newsData;

  // Options State
  List<String> _optionDates = [];
  String? _selectedOptionDate;
  List<dynamic> _optionCalls = [];
  List<dynamic> _optionPuts = [];

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

        // Default tab selection
        if (isIndex &&
            (_activeTab == 'Fundamentals' || _activeTab == 'Financials')) {
          _activeTab = 'Option Chain';
        } else if (!isIndex &&
            ![
              'Fundamentals',
              'Financials',
              'Option Chain',
              'News',
            ].contains(_activeTab)) {
          _activeTab = 'Fundamentals';
        }
      });
      await _loadChartData(symbol, _activePeriod);
      _loadTabData();
    } catch (e) {
      if (mounted) {
        setState(() => _isLoadingQuote = false);
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Failed to load $symbol')));
      }
    }
  }

  Future<void> _loadTabData() async {
    if (_isIndex &&
        (_activeTab == 'Fundamentals' || _activeTab == 'Financials'))
      return;

    setState(() => _isLoadingTab = true);
    try {
      if (_activeTab == 'Fundamentals') {
        _fundamentalsData = await _chartService.getFundamentals(
          _selectedSymbol,
        );
      } else if (_activeTab == 'Financials') {
        _financialsData = await _chartService.getFinancials(_selectedSymbol);
      } else if (_activeTab == 'News') {
        final res = await _chartService.getNews(_selectedSymbol);
        _newsData = res['articles'];
      } else if (_activeTab == 'Option Chain') {
        final datesRes = await _chartService.getOptionDates(_selectedSymbol);
        _optionDates = List<String>.from(datesRes['dates'] ?? []);
        if (_optionDates.isNotEmpty) {
          _selectedOptionDate = _optionDates.first;
          await _loadOptionChain();
        }
      }
    } catch (e) {
      debugPrint('Tab load error: $e');
    } finally {
      if (mounted) setState(() => _isLoadingTab = false);
    }
  }

  Future<void> _loadOptionChain() async {
    if (_selectedOptionDate == null) return;
    setState(() => _isLoadingTab = true);
    try {
      final res = await _chartService.getOptionChain(
        _selectedSymbol,
        _selectedOptionDate!,
      );
      _optionCalls = res['calls'] ?? [];
      _optionPuts = res['puts'] ?? [];
    } catch (e) {
      debugPrint('Options error: $e');
    } finally {
      if (mounted) setState(() => _isLoadingTab = false);
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
                _buildStockActionButtons(),
                _buildTabContent(),
                const SizedBox(height: 40),
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

  Widget _buildStockActionButtons() {
    List<String> actions = [];
    if (_isIndex) {
      actions = ['Option Chain', 'News'];
    } else {
      actions = ['Fundamentals', 'Financials', 'Option Chain', 'News'];
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: SizedBox(
        height: 36,
        child: ListView.builder(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          itemCount: actions.length,
          itemBuilder: (context, index) {
            final action = actions[index];
            final isActive = _activeTab == action;
            return Padding(
              padding: const EdgeInsets.only(right: 8),
              child: ActionChip(
                label: Text(action),
                backgroundColor: isActive
                    ? AppTheme.primaryColor.withValues(alpha: 0.2)
                    : AppTheme.cardColor,
                labelStyle: TextStyle(
                  color: isActive ? AppTheme.primaryColor : Colors.grey,
                  fontSize: 13,
                  fontWeight: isActive ? FontWeight.bold : FontWeight.normal,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(20),
                  side: BorderSide(
                    color: isActive
                        ? AppTheme.primaryColor
                        : Colors.transparent,
                  ),
                ),
                onPressed: () {
                  setState(() => _activeTab = action);
                  _loadTabData();
                },
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildTabContent() {
    if (_isLoadingTab) {
      return const Padding(
        padding: EdgeInsets.all(32),
        child: Center(child: CircularProgressIndicator()),
      );
    }

    switch (_activeTab) {
      case 'Fundamentals':
        return _buildFundamentalsTab();
      case 'Financials':
        return _buildFinancialsTab();
      case 'Option Chain':
        return _buildOptionsTab();
      case 'News':
        return _buildNewsTab();
      default:
        return const SizedBox.shrink();
    }
  }

  Widget _buildFundamentalsTab() {
    if (_fundamentalsData == null) return const SizedBox.shrink();
    final f = _fundamentalsData!;

    Widget statRow(String label, String value) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 8.0, horizontal: 16),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              label,
              style: const TextStyle(color: Colors.grey, fontSize: 13),
            ),
            Text(
              value,
              style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
            ),
          ],
        ),
      );
    }

    return Column(
      children: [
        statRow(
          'Sector',
          f['sector']?.toString().isNotEmpty == true ? f['sector'] : '—',
        ),
        statRow(
          'Industry',
          f['industry']?.toString().isNotEmpty == true ? f['industry'] : '—',
        ),
        statRow('P/E Ratio', f['pe']?.toStringAsFixed(2) ?? '—'),
        statRow('EPS', '₹${f['eps']?.toStringAsFixed(2) ?? '—'}'),
        statRow('Book Value', '₹${f['bookValue']?.toStringAsFixed(2) ?? '—'}'),
        statRow('ROE', '${(f['roe'] * 100).toStringAsFixed(2)}%'),
        statRow(
          'Revenue Growth',
          '${(f['revenueGrowth'] * 100).toStringAsFixed(2)}%',
        ),
        statRow(
          '52W High',
          '₹${f['fiftyTwoWeekHigh']?.toStringAsFixed(2) ?? '—'}',
        ),
        statRow(
          '52W Low',
          '₹${f['fiftyTwoWeekLow']?.toStringAsFixed(2) ?? '—'}',
        ),
      ],
    );
  }

  Widget _buildFinancialsTab() {
    if (_financialsData == null || _financialsData!['data'] == null)
      return const SizedBox.shrink();

    final Map<String, dynamic> data = _financialsData!['data'];
    if (data.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(16),
        child: Text("No financial data"),
      );
    }

    final periods = data.keys.toList();
    final rows = ['Total Income', 'Expenditure', 'Net Profit', 'EPS'];

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: DataTable(
        headingRowHeight: 40,
        dataRowMinHeight: 40,
        dataRowMaxHeight: 40,
        columnSpacing: 24,
        columns: [
          const DataColumn(
            label: Text('Item', style: TextStyle(color: Colors.grey)),
          ),
          ...periods.map(
            (p) => DataColumn(
              label: Text(p, style: const TextStyle(color: Colors.grey)),
            ),
          ),
        ],
        rows: rows.map((rowKey) {
          return DataRow(
            cells: [
              DataCell(
                Text(
                  rowKey,
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
              ),
              ...periods.map((p) {
                final val = data[p]?[rowKey];
                String text = '—';
                if (val != null) {
                  if (rowKey == 'EPS')
                    text = val.toStringAsFixed(2);
                  else
                    text = '₹${(val / 10000000).toStringAsFixed(2)}Cr';
                }
                return DataCell(Text(text));
              }),
            ],
          );
        }).toList(),
      ),
    );
  }

  Widget _buildOptionsTab() {
    if (_optionDates.isEmpty)
      return const Padding(
        padding: EdgeInsets.all(16),
        child: Text("No options data"),
      );

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16.0),
          child: DropdownButton<String>(
            value: _selectedOptionDate,
            isExpanded: true,
            dropdownColor: AppTheme.cardColor,
            underline: Container(height: 1, color: Colors.white24),
            items: _optionDates
                .map((d) => DropdownMenuItem(value: d, child: Text(d)))
                .toList(),
            onChanged: (val) {
              if (val != null) {
                setState(() => _selectedOptionDate = val);
                _loadOptionChain();
              }
            },
          ),
        ),
        if (_optionCalls.isNotEmpty || _optionPuts.isNotEmpty)
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: DataTable(
              headingRowHeight: 32,
              dataRowMinHeight: 36,
              dataRowMaxHeight: 36,
              columnSpacing: 16,
              columns: const [
                DataColumn(
                  label: Text(
                    'Call LTP',
                    style: TextStyle(
                      color: AppTheme.successColor,
                      fontSize: 12,
                    ),
                  ),
                ),
                DataColumn(
                  label: Text(
                    'Strike',
                    style: TextStyle(color: Colors.white, fontSize: 12),
                  ),
                ),
                DataColumn(
                  label: Text(
                    'Put LTP',
                    style: TextStyle(color: AppTheme.errorColor, fontSize: 12),
                  ),
                ),
              ],
              rows: List.generate(_optionCalls.length, (i) {
                final call = _optionCalls[i];
                final put = _optionPuts.length > i ? _optionPuts[i] : {};
                return DataRow(
                  cells: [
                    DataCell(
                      Text(
                        call['lastPrice']?.toStringAsFixed(2) ?? '—',
                        style: TextStyle(color: AppTheme.successColor),
                      ),
                    ),
                    DataCell(
                      Text(
                        call['strike']?.toStringAsFixed(0) ?? '—',
                        style: TextStyle(fontWeight: FontWeight.bold),
                      ),
                    ),
                    DataCell(
                      Text(
                        put['lastPrice']?.toStringAsFixed(2) ?? '—',
                        style: TextStyle(color: AppTheme.errorColor),
                      ),
                    ),
                  ],
                );
              }),
            ),
          ),
      ],
    );
  }

  Widget _buildNewsTab() {
    if (_newsData == null || _newsData!.isEmpty)
      return const Padding(
        padding: EdgeInsets.all(16),
        child: Text("No news data"),
      );

    return ListView.separated(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: _newsData!.length,
      separatorBuilder: (_, __) =>
          const Divider(height: 1, color: Colors.white10),
      itemBuilder: (context, i) {
        final news = _newsData![i];
        return ListTile(
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 16,
            vertical: 4,
          ),
          title: Text(
            news['title'] ?? '',
            style: const TextStyle(fontSize: 13, height: 1.3),
          ),
          subtitle: Text(
            news['publishedAt'] ?? '',
            style: const TextStyle(fontSize: 11, color: Colors.grey),
          ),
        );
      },
    );
  }
}
